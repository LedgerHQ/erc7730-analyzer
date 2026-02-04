"""
ABI Merger for multi-chain deployments.

Fetches ABIs from multiple chains and intelligently merges them,
keeping all unique functions while avoiding duplicates.
"""

import logging
from typing import List, Dict, Callable, Tuple, Optional

logger = logging.getLogger(__name__)


class ABIMerger:
    """Handles fetching and merging ABIs from multiple chain deployments."""

    def __init__(self):
        self.function_signatures = {}  # signature -> function ABI
        self.event_signatures = {}  # signature -> event ABI
        self.other_items = []  # constructors, fallback, receive
        # Track where each selector came from: selector -> LIST of {facet_address, chain_id, signature}
        # Multiple sources allow fallback if one fails during source extraction
        self.selector_sources = {}
    
    def _compute_selector(self, signature: str) -> str:
        """Compute 4-byte function selector from signature."""
        from eth_utils import keccak
        return '0x' + keccak(text=signature).hex()[:8]

    def _get_function_signature(self, func: Dict) -> Optional[str]:
        """
        Generate canonical function signature.

        Format: functionName(type1,type2,...)
        """
        if func.get('type') != 'function':
            return None

        name = func.get('name')
        if not name:
            return None

        inputs = func.get('inputs', [])
        param_types = []
        for inp in inputs:
            param_types.append(self._get_canonical_type(inp))

        signature = f"{name}({','.join(param_types)})"
        return signature

    def _get_event_signature(self, event: Dict) -> Optional[str]:
        """
        Generate canonical event signature.

        Format: EventName(type1,type2,...)
        """
        if event.get('type') != 'event':
            return None

        name = event.get('name')
        if not name:
            return None

        inputs = event.get('inputs', [])
        param_types = []
        for inp in inputs:
            param_types.append(self._get_canonical_type(inp))

        signature = f"{name}({','.join(param_types)})"
        return signature

    def _get_canonical_type(self, param: Dict) -> str:
        """
        Get canonical type string for a parameter.

        Handles tuples, arrays, and basic types.
        """
        param_type = param.get('type', '')

        # Handle tuple types
        if param_type.startswith('tuple'):
            components = param.get('components', [])
            if components:
                # Recursively build tuple type
                component_types = [self._get_canonical_type(c) for c in components]
                tuple_str = f"({','.join(component_types)})"
                # Handle arrays of tuples - extract full array suffix
                if '[' in param_type:
                    # Extract everything after 'tuple' (e.g., '[]', '[][]', '[5]', etc.)
                    array_part = param_type[5:]  # Remove 'tuple' prefix
                    return tuple_str + array_part
                else:
                    return tuple_str
            else:
                return param_type

        return param_type

    def add_abi(self, abi: List[Dict], chain_id: int, source_address: str = None) -> Dict[str, int]:
        """
        Add an ABI to the merger.

        Args:
            abi: ABI entries to add
            chain_id: Chain ID where this ABI came from
            source_address: Address where this ABI came from (for Diamond facet tracking)

        Returns dict with counts of new items added:
        - new_functions: Number of new functions
        - new_events: Number of new events
        - duplicate_functions: Number of duplicate functions skipped
        """
        new_functions = 0
        new_events = 0
        duplicate_functions = 0

        for item in abi:
            item_type = item.get('type')

            if item_type == 'function':
                signature = self._get_function_signature(item)
                if signature:
                    if signature not in self.function_signatures:
                        self.function_signatures[signature] = item
                        new_functions += 1
                        logger.debug(f"Added new function from chain {chain_id}: {signature}")
                        
                        # Track selector -> source mapping for Diamond proxy support
                        if source_address:
                            try:
                                selector = self._compute_selector(signature)
                                source_info = {
                                    'facet_address': source_address,
                                    'chain_id': chain_id,
                                    'signature': signature
                                }
                                if selector not in self.selector_sources:
                                    self.selector_sources[selector] = []
                                # Avoid duplicate entries for same address+chain
                                existing = self.selector_sources[selector]
                                if not any(s['facet_address'] == source_address and s['chain_id'] == chain_id for s in existing):
                                    self.selector_sources[selector].append(source_info)
                                    logger.debug(f"Mapped selector {selector} -> facet {source_address} (chain {chain_id})")
                            except Exception as e:
                                logger.warning(f"Could not compute selector for {signature}: {e}")
                    else:
                        duplicate_functions += 1
                        logger.debug(f"Skipped duplicate function: {signature}")
                        
                        # Still track selector source even for duplicates (for fallback)
                        if source_address:
                            try:
                                selector = self._compute_selector(signature)
                                source_info = {
                                    'facet_address': source_address,
                                    'chain_id': chain_id,
                                    'signature': signature
                                }
                                if selector not in self.selector_sources:
                                    self.selector_sources[selector] = []
                                existing = self.selector_sources[selector]
                                if not any(s['facet_address'] == source_address and s['chain_id'] == chain_id for s in existing):
                                    self.selector_sources[selector].append(source_info)
                            except Exception:
                                pass

            elif item_type == 'event':
                signature = self._get_event_signature(item)
                if signature:
                    if signature not in self.event_signatures:
                        self.event_signatures[signature] = item
                        new_events += 1
                        logger.debug(f"Added new event from chain {chain_id}: {signature}")

            elif item_type in ['constructor', 'fallback', 'receive']:
                # These are typically the same across chains, just add once
                if not any(existing.get('type') == item_type for existing in self.other_items):
                    self.other_items.append(item)

        return {
            'new_functions': new_functions,
            'new_events': new_events,
            'duplicate_functions': duplicate_functions
        }
    
    def get_selector_sources(self) -> Dict[str, List[Dict]]:
        """
        Get mapping of selector -> source info list.
        
        Returns:
            Dict mapping selector (e.g., '0x1234abcd') to list of:
            {
                'facet_address': '0x...',
                'chain_id': 1,
                'signature': 'functionName(type1,type2)'
            }
        """
        return self.selector_sources

    def get_merged_abi(self) -> List[Dict]:
        """
        Get the merged ABI containing all unique items.

        Returns sorted ABI: constructor first, then functions, events, other.
        """
        merged = []

        # Add constructor first (if exists)
        for item in self.other_items:
            if item.get('type') == 'constructor':
                merged.append(item)

        # Add all unique functions (sorted by name)
        functions = sorted(self.function_signatures.values(), key=lambda f: f.get('name', ''))
        merged.extend(functions)

        # Add all unique events (sorted by name)
        events = sorted(self.event_signatures.values(), key=lambda e: e.get('name', ''))
        merged.extend(events)

        # Add fallback/receive (if exist)
        for item in self.other_items:
            if item.get('type') in ['fallback', 'receive']:
                merged.append(item)

        return merged

    def get_statistics(self) -> Dict:
        """Get statistics about the merged ABI."""
        return {
            'total_functions': len(self.function_signatures),
            'total_events': len(self.event_signatures),
            'other_items': len(self.other_items)
        }


def merge_abis_from_deployments(
    deployments: List[Dict],
    fetch_abi_func: Callable[[str, int, str], Tuple[Optional[List[Dict]], Dict, bool]],
    api_key: str
) -> Tuple[Optional[List[Dict]], Dict, Dict]:
    """
    Fetch and merge ABIs from multiple chain deployments.

    Args:
        deployments: List of deployment dicts with chainId and address
        fetch_abi_func: Function to fetch ABI (contract_address, chain_id, api_key) -> (abi, selector_sources, is_diamond)
        api_key: API key for blockchain explorers

    Returns:
        (merged_abi, fetch_results, selector_sources)

        merged_abi: Combined ABI with all unique functions, or None if all fetches failed
        fetch_results: Dict with per-chain fetch results
        selector_sources: Dict mapping selector -> list of {facet_address, chain_id, signature}
    """
    merger = ABIMerger()
    fetch_results = {}
    successful_fetches = 0
    failed_fetches = 0
    is_any_diamond = False

    logger.info(f"Fetching ABIs from {len(deployments)} chain(s)...")

    for deployment in deployments:
        chain_id = deployment['chainId']
        address = deployment['address']

        logger.info(f"Fetching ABI from chain {chain_id} for address {address[:10]}...")

        try:
            result = fetch_abi_func(address, chain_id, api_key)
            
            # Handle new tuple return: (abi, selector_sources, is_diamond)
            dep_selector_sources = {}
            is_diamond = False
            if isinstance(result, tuple) and len(result) == 3:
                abi, dep_selector_sources, is_diamond = result
                # Merge selector sources from this deployment
                for sel, info in dep_selector_sources.items():
                    if sel not in merger.selector_sources:
                        merger.selector_sources[sel] = info if isinstance(info, list) else [info]
                    else:
                        # Append new sources
                        existing = merger.selector_sources[sel]
                        if isinstance(info, list):
                            for item in info:
                                if item not in existing:
                                    existing.append(item)
                        elif info not in existing:
                            existing.append(info)
                if is_diamond:
                    is_any_diamond = True
                    logger.info(f"  Diamond proxy: got {len(dep_selector_sources)} selector→facet mappings")
            else:
                abi = result
            
            if abi:
                # For non-Diamond, track source address
                source_addr = address if not is_diamond else None
                stats = merger.add_abi(abi, chain_id, source_address=source_addr)
                fetch_results[chain_id] = {
                    'success': True,
                    'functions_count': len([item for item in abi if item.get('type') == 'function']),
                    'new_functions': stats['new_functions'],
                    'duplicate_functions': stats['duplicate_functions'],
                    'is_diamond': is_diamond
                }
                successful_fetches += 1
                logger.info(f"✓ Chain {chain_id}: {stats['new_functions']} new functions, "
                          f"{stats['duplicate_functions']} duplicates")
            else:
                fetch_results[chain_id] = {
                    'success': False,
                    'error': 'ABI fetch returned None'
                }
                failed_fetches += 1
                logger.warning(f"✗ Chain {chain_id}: Failed to fetch ABI")

        except Exception as e:
            fetch_results[chain_id] = {
                'success': False,
                'error': str(e)
            }
            failed_fetches += 1
            logger.warning(f"✗ Chain {chain_id}: Error fetching ABI: {e}")

    # Get merged ABI
    if successful_fetches == 0:
        logger.error("Failed to fetch ABI from any chain")
        return None, fetch_results, {}

    merged_abi = merger.get_merged_abi()
    selector_sources = merger.get_selector_sources()
    stats = merger.get_statistics()

    logger.info("=" * 60)
    logger.info("ABI Merge Summary:")
    logger.info(f"  Chains queried: {len(deployments)}")
    logger.info(f"  Successful fetches: {successful_fetches}")
    logger.info(f"  Failed fetches: {failed_fetches}")
    logger.info(f"  Total unique functions: {stats['total_functions']}")
    logger.info(f"  Total unique events: {stats['total_events']}")
    if selector_sources:
        logger.info(f"  Selector→Facet mappings: {len(selector_sources)}")
    logger.info("=" * 60)

    return merged_abi, fetch_results, selector_sources
