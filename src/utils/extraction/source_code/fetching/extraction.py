"""High-level contract-code extraction flow."""

import re
from typing import Any, Dict, List, Optional

from ..parser import SolidityCodeParser
from ..shared import BLOCKSCOUT_URLS, logger


class SourceCodeFetchingExtractionMixin:
    def extract_contract_code(
        self,
        contract_address: str,
        chain_id: int,
        selectors: Optional[List[str]] = None,
        selector_sources: Optional[Dict[str, List[Dict]]] = None
    ) -> Dict[str, Any]:
        """
        Extract and parse contract source code.

        Args:
            contract_address: Contract address
            chain_id: Chain ID
            selectors: Optional list of selectors to filter diamond facets
            selector_sources: Optional dict mapping selector -> list of {facet_address, chain_id} 
                             from ABI detection (for efficient Diamond proxy extraction)

        Returns:
            Dictionary with extracted code:
            {
                'address': str,
                'chain_id': int,
                'is_proxy': bool,
                'implementation': Optional[str],
                'is_diamond': bool,
                'facets': Dict[str, str],  # selector -> facet_address
                'source_code': str,
                'functions': Dict,
                'structs': Dict,
                'enums': Dict,
                'internal_functions': Dict
            }
        """
        # Check cache (thread-safe)
        cache_key = f"{chain_id}:{contract_address.lower()}"
        # Include selectors in cache key to avoid stale/partial diamond facet data
        if selectors:
            cache_key = f"{cache_key}:{','.join(sorted(selectors))}"
        # Include selector_sources in cache key - if we have facet mappings, include them
        if selector_sources:
            # Hash the facet addresses to detect when mappings change
            facet_hash = hash(frozenset((sel, sources[0]['facet_address'] if sources else '') 
                                        for sel, sources in selector_sources.items() if sources))
            cache_key = f"{cache_key}:ss{facet_hash}"
        
        with self._cache_lock:
            if cache_key in self.code_cache:
                logger.debug(f"Using cached code for {contract_address}")
                return self.code_cache[cache_key]

        logger.info(f"Extracting source code for {contract_address} on chain {chain_id}")

        result = {
            'address': contract_address,
            'chain_id': chain_id,
            'is_proxy': False,
            'implementation': None,
            'is_diamond': False,
            'facets': {},
            'source_code': None,
            'functions': {},
            'structs': {},
            'enums': {},
            'constants': {},
            'modifiers': {},
            'internal_functions': {}
        }

        # Save original address for Diamond proxy detection
        original_address = contract_address

        # Check for diamond proxy FIRST (before checking EIP-1967 proxy)
        # If selector_sources provided, use them directly (already detected during ABI fetch)
        facets = {}
        use_selector_sources = False
        
        if selector_sources and selectors:
            logger.info(f"🔍 Building facets from selector_sources for chain {chain_id}...")
            logger.info(f"   selector_sources has {len(selector_sources)} total mappings")
            # Build facets mapping from selector_sources - FILTER BY CURRENT CHAIN_ID
            found_count = 0
            missing_selectors = []
            for selector in selectors:
                sources = selector_sources.get(selector, [])
                # Find a source that matches the current chain_id
                matching_source = None
                for source in sources:
                    if source.get('chain_id') == chain_id:
                        matching_source = source
                        break
                
                if matching_source:
                    facet_addr = matching_source.get('facet_address', '')
                    if facet_addr:
                        facets[selector] = facet_addr.lower()
                        found_count += 1
                else:
                    missing_selectors.append(selector)
            
            if facets:
                logger.info(f"Using pre-detected selector→facet mapping for chain {chain_id} ({found_count}/{len(selectors)} selectors mapped)")
                if missing_selectors:
                    logger.debug(f"  Selectors not on this chain: {len(missing_selectors)}")
                use_selector_sources = True
            else:
                logger.info(f"No selector→facet mappings found for chain {chain_id}, falling back to detection")
        
        # Diamond proxies should be detected using the original proxy address
        if not use_selector_sources and selectors:
            logger.info(f"Checking for Diamond proxy with {len(selectors)} selectors: {selectors[:3]}...")
            facets = self.detect_diamond_proxy(original_address, chain_id, selectors)
            if facets and '_is_diamond_but_unmapped' in facets:
                # Detected as Diamond but couldn't map facets
                # This means the selectors don't exist on this contract/chain
                # Return empty so caller can try next contract/chain
                result['is_diamond'] = True
                result['facets'] = {}
                logger.info(f"✓ Detected Diamond proxy (but cannot map selectors to facets)")
                logger.warning(f"Selectors not found on this Diamond - caller should try next contract/chain")
                with self._cache_lock:
                    self.code_cache[cache_key] = result
                return result
        
        # If we have facets (from selector_sources OR from detect_diamond_proxy), extract from them
        logger.info(f"🔍 Facet check for chain {chain_id}: {len(facets)} selector→facet mappings, use_selector_sources={use_selector_sources}")
        if facets and not facets.get('_is_diamond_but_unmapped'):
                # Successfully mapped selectors to facets
                result['is_diamond'] = True
                result['facets'] = facets
                unique_facet_addresses = set(facets.values())
                logger.info(f"✓ Diamond proxy on chain {chain_id} - will extract from {len(unique_facet_addresses)} unique facets:")
                for fa in list(unique_facet_addresses)[:10]:
                    logger.info(f"   - {fa}")

                # Extract source code from each unique facet IN PARALLEL for speed
                from concurrent.futures import ThreadPoolExecutor, as_completed
                import time
                
                logger.info(f"Extracting source code from {len(unique_facet_addresses)} unique facets (parallel)...")
                
                all_functions = {}
                all_custom_types = {}
                all_using_statements = []
                all_libraries = {}
                all_structs = {}
                all_enums = {}
                all_constants = {}
                all_modifiers = {}
                all_internal_functions = {}
                per_facet_codes = {}  # Store per-facet parsed code for efficient lookups
                
                def fetch_and_parse_facet(facet_addr):
                    """Fetch and parse a single facet's source code."""
                    short_addr = facet_addr[:10] + "..."
                    t0 = time.time()
                    
                    # Fetch source code with retry logic (up to 3 attempts)
                    source_code = None
                    max_retries = 3
                    for attempt in range(max_retries):
                        # Try Sourcify first, then Etherscan, then Blockscout
                        source_code = self.fetch_source_from_sourcify(facet_addr, chain_id)
                        if not source_code:
                            source_code = self.fetch_source_from_etherscan(facet_addr, chain_id)
                        if not source_code:
                            source_code = self.fetch_source_from_blockscout(facet_addr, chain_id)
                        
                        if source_code:
                            break
                        
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 2  # 2s, 4s backoff
                            logger.warning(f"  [{short_addr}] Fetch failed, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                            time.sleep(wait_time)
                    
                    if not source_code:
                        logger.warning(f"  [{short_addr}] ✗ Could not fetch source after {max_retries} attempts")
                        return facet_addr, None
                    
                    # Detect if facet code is Vyper or Solidity
                    is_vyper = self.is_vyper_code(source_code)
                    
                    facet_result = {
                        'source_code': source_code,
                        'functions': {},
                        'custom_types': {},
                        'using_statements': [],
                        'libraries': {},
                        'structs': {},
                        'enums': {},
                        'constants': {},
                        'modifiers': {},
                        'internal_functions': {}
                    }
                    
                    if is_vyper:
                        facet_result['functions'] = self.extract_vyper_functions(source_code)
                        facet_result['internal_functions'] = {
                            k: v for k, v in facet_result['functions'].items()
                            if v['visibility'] == 'internal'
                        }
                    else:
                        parser = SolidityCodeParser(source_code)
                        facet_result['custom_types'] = parser.extract_custom_types()
                        facet_result['using_statements'] = parser.extract_using_statements()
                        facet_result['libraries'] = parser.extract_libraries()
                        facet_result['structs'] = parser.extract_structs()
                        facet_result['enums'] = parser.extract_enums()
                        facet_result['constants'] = parser.extract_constants()
                        facet_result['modifiers'] = parser.extract_modifiers()
                        facet_result['functions'] = parser.extract_functions()
                        facet_result['internal_functions'] = {
                            k: v for k, v in facet_result['functions'].items()
                            if v['visibility'] in ['internal', 'private']
                        }
                    
                    # Try to extract contract name from source
                    contract_name_match = re.search(r'contract\s+(\w+)\s*(?:is|{)', source_code)
                    contract_name = contract_name_match.group(1) if contract_name_match else 'Unknown'
                    facet_result['contract_name'] = contract_name
                    
                    elapsed = time.time() - t0
                    func_count = len(facet_result['functions'])
                    struct_count = len(facet_result['structs'])
                    struct_names = list(facet_result['structs'].keys())
                    logger.info(f"  [{short_addr}] ✓ {contract_name}: {func_count} functions, {struct_count} structs ({elapsed:.1f}s)")
                    if struct_count > 0:
                        logger.debug(f"  [{short_addr}] Structs: {struct_names[:5]}{'...' if struct_count > 5 else ''}")
                    return facet_addr, facet_result
                
                # Use ThreadPoolExecutor to fetch facets in parallel (max 4 concurrent)
                logger.info(f"Starting parallel fetch for {len(unique_facet_addresses)} facets on chain {chain_id}...")
                max_workers = min(4, len(unique_facet_addresses))
                t_start = time.time()
                
                try:
                    with ThreadPoolExecutor(max_workers=max_workers) as executor:
                        futures = {executor.submit(fetch_and_parse_facet, addr): addr 
                                  for addr in unique_facet_addresses}
                        
                        for future in as_completed(futures):
                            try:
                                facet_addr, facet_result = future.result()
                                if facet_result:
                                    # Merge into combined results
                                    all_functions.update(facet_result['functions'])
                                    all_custom_types.update(facet_result.get('custom_types', {}))
                                    all_using_statements.extend(facet_result.get('using_statements', []))
                                    all_libraries.update(facet_result.get('libraries', {}))
                                    all_structs.update(facet_result['structs'])
                                    all_enums.update(facet_result['enums'])
                                    all_constants.update(facet_result['constants'])
                                    all_modifiers.update(facet_result['modifiers'])
                                    all_internal_functions.update(facet_result['internal_functions'])
                                    # Store per-facet code for efficient lookups later
                                    per_facet_codes[facet_addr] = facet_result
                            except Exception as fe:
                                logger.error(f"  Error processing facet future: {fe}")
                except Exception as e:
                    logger.error(f"Parallel facet extraction failed: {e}")
                
                elapsed_total = time.time() - t_start
                logger.info(f"Parallel extraction complete: {len(per_facet_codes)}/{len(unique_facet_addresses)} facets succeeded in {elapsed_total:.1f}s")

                result['functions'] = all_functions
                result['custom_types'] = all_custom_types
                result['using_statements'] = all_using_statements
                result['libraries'] = all_libraries
                result['structs'] = all_structs
                result['enums'] = all_enums
                result['constants'] = all_constants
                result['modifiers'] = all_modifiers
                result['internal_functions'] = all_internal_functions
                result['source_code'] = f"Diamond proxy with {len(unique_facet_addresses)} facets"
                
                # Store per-facet codes and selector-to-facet mapping for efficient lookups
                result['_per_facet_codes'] = per_facet_codes
                result['_selector_to_facet'] = {sel: addr.lower() for sel, addr in facets.items()}

                logger.info(f"✓ Extracted total: {len(all_functions)} functions, {len(all_custom_types)} custom types, {len(all_using_statements)} using statements, {len(all_libraries)} libraries, {len(all_structs)} structs, {len(all_enums)} enums, {len(all_constants)} constants, {len(all_modifiers)} modifiers from all facets")

                # Cache and return (thread-safe)
                with self._cache_lock:
                    self.code_cache[cache_key] = result
                return result
        
        # Not a Diamond proxy, check for standard EIP-1967 proxy
        if not result['is_diamond']:
            impl_address = self.detect_proxy_implementation(contract_address, chain_id)
            if impl_address:
                result['is_proxy'] = True
                result['implementation'] = impl_address
                contract_address = impl_address  # Use implementation for source code
                logger.info(f"Using implementation address: {impl_address}")

        # Fetch contract name from Etherscan (most reliable source)
        contract_name = self.get_contract_name_from_etherscan(contract_address, chain_id)
        if contract_name:
            result['contract_name'] = contract_name
            logger.info(f"✓ Deployed contract: {contract_name}")

        # Fetch source code (try Sourcify first, then Etherscan, then Blockscout)
        source_code = self.fetch_source_from_sourcify(contract_address, chain_id)
        if not source_code:
            source_code = self.fetch_source_from_etherscan(contract_address, chain_id)
        if not source_code and chain_id in BLOCKSCOUT_URLS:
            logger.info(f"Chain {chain_id} has Blockscout support - trying Blockscout...")
            source_code = self.fetch_source_from_blockscout(contract_address, chain_id)

        if not source_code:
            logger.warning(f"Could not fetch source code for {contract_address}")
            with self._cache_lock:
                self.code_cache[cache_key] = result
            return result

        result['source_code'] = source_code

        # Detect if code is Vyper or Solidity
        is_vyper = self.is_vyper_code(source_code)

        if is_vyper:
            logger.info("Detected Vyper code - using Vyper parser")
            # Extract functions using Vyper parser
            result['functions'] = self.extract_vyper_functions(source_code)
            # Vyper doesn't have structs/enums/modifiers in the same way as Solidity
            result['structs'] = {}
            result['enums'] = {}
            result['constants'] = {}
            result['modifiers'] = {}  # Vyper doesn't have modifiers
            result['internal_functions'] = {
                k: v for k, v in result['functions'].items()
                if v['visibility'] == 'internal'
            }
        else:
            logger.info("Detected Solidity code - using Solidity parser")
            # Parse using Solidity parser
            parser = SolidityCodeParser(source_code)

            logger.info("  [1/7] Extracting custom types...")
            result['custom_types'] = parser.extract_custom_types()
            logger.info(f"  ✓ Found {len(result['custom_types'])} custom types")

            logger.info("  [2/7] Extracting using statements...")
            result['using_statements'] = parser.extract_using_statements()
            logger.info(f"  ✓ Found {len(result['using_statements'])} using statements")

            logger.info("  [3/8] Extracting libraries...")
            result['libraries'] = parser.extract_libraries()
            logger.info(f"  ✓ Found {len(result['libraries'])} libraries")

            logger.info("  [4/8] Extracting interfaces...")
            result['interfaces'] = parser.extract_interfaces()
            logger.info(f"  ✓ Found {len(result['interfaces'])} interfaces/contracts")

            logger.info("  [5/8] Extracting structs...")
            result['structs'] = parser.extract_structs()
            logger.info(f"  ✓ Found {len(result['structs'])} structs")

            logger.info("  [6/8] Extracting enums...")
            result['enums'] = parser.extract_enums()
            logger.info(f"  ✓ Found {len(result['enums'])} enums")

            logger.info("  [7/9] Extracting constants...")
            result['constants'] = parser.extract_constants()
            logger.info(f"  ✓ Found {len(result['constants'])} constants")

            logger.info("  [8/9] Extracting modifiers...")
            result['modifiers'] = parser.extract_modifiers()
            logger.info(f"  ✓ Found {len(result['modifiers'])} modifiers")

            logger.info("  [9/9] Extracting functions (this may take a while for large contracts)...")
            result['functions'] = parser.extract_functions()
            logger.info(f"  ✓ Found {len(result['functions'])} functions")

            # Separate internal functions
            result['internal_functions'] = {
                k: v for k, v in result['functions'].items()
                if v['visibility'] in ['internal', 'private']
            }

        logger.info(f"Extracted {len(result['functions'])} functions, "
                   f"{len(result.get('custom_types', {}))} custom types, "
                   f"{len(result.get('using_statements', []))} using statements, "
                   f"{len(result.get('libraries', {}))} libraries, "
                   f"{len(result['structs'])} structs, "
                   f"{len(result['enums'])} enums, "
                   f"{len(result['constants'])} constants, "
                   f"{len(result.get('modifiers', {}))} modifiers")

        # Cache the result (thread-safe)
        with self._cache_lock:
            self.code_cache[cache_key] = result

        return result

