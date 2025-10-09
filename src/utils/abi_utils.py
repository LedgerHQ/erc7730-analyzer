# flake8: noqa

from collections import defaultdict
import json
from json.decoder import JSONDecodeError
import os
import re
from string import Template

from eth_utils import keccak
from openai import AzureOpenAI
import requests


class SolidityCode:
    """
    Class to interact with Solidity code.
    """

    def __init__(self, code: list):
        # Code can be split into multiple files (sourcify) or single string (etherscan)
        self.code = code

    def stringify(self) -> str:
        """
        Convert the code array to a string representation.
        """
        return "\n\n".join(content for _, content in self.code)

    @staticmethod
    def remove_comments(text) -> str:
        """
        Remove comments from Solidity code.
        Args:
            text: the code

        Returns:
            the code stripped of comments
        """
        # Remove all /** */ block comments
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
        # Remove all // line comments
        text = re.sub(r"//.*", "", text)
        return text

    def parse_parameter_names(self, param_block: str) -> list[str]:
        """
        Parse parameter names from a Solidity function parameter block.
        Args:
            param_block: the param block e.g "address to, uint256 amount" or assembly "emptyPtr, swapAmount, pair"

        Returns:
            the parameter names as a list of strings e.g ["to", "amount"] or ["emptyPtr", "swapAmount", "pair"]
        """
        # Strip comments before processing
        param_block = self.remove_comments(param_block)

        # Check if this looks like an assembly function (no types, just names)
        # Assembly functions have parameters like: emptyPtr, swapAmount, pair, reversed, numerator, dst
        # Solidity functions have parameters like: address executor, SwapDesc calldata desc, bytes calldata data

        if not param_block.strip():
            return []

        # Split on commas (outside of parentheses)
        parts = re.split(r",(?![^\(\)]*\))", param_block)

        param_names = []
        for part in parts:
            part = part.strip()
            if not part:
                continue

            tokens = part.strip().split()

            # Check if this looks like assembly parameter (no type, just identifier)
            if len(tokens) == 1 and not any(keyword in tokens[0] for keyword in ["address", "uint", "int", "bool", "bytes", "string"]):
                # This looks like an assembly parameter - just the identifier
                param_names.append(tokens[0])
            elif not tokens:
                param_names.append("")
            elif tokens[-1] in {
                "calldata",
                "memory",
                "storage",
                "payable",
                "external",
                "internal",
                "view",
                "pure",
            }:
                param_names.append("")  # Unnamed parameter ending with a keyword
            else:
                param_names.append(tokens[-1])  # Assume last token is name

        return param_names

    def extract_enums_from_solidity(self) -> dict:
        """
        Extract enums from Solidity code and return them in the requested format.
        """
        # Collect code from Sourcify or Etherscan
        code = next((content for file, content in self.code if file == "all_code"), "")

        cleaned_code = code.replace("\n", " ")

        # Regex pattern to capture enum declarations and their values, ensuring valid enums
        enum_pattern = r"enum\s+(\w+)\s*\{([^}]+)\}"

        enums = re.findall(enum_pattern, cleaned_code)

        enums_dict = defaultdict(dict)

        for enum_name, enum_values in enums:
            values = [
                value.replace("\\n", "").strip()
                for value in enum_values.split(",")
                if value.strip()
            ]
            if not values:
                continue
            for index, value in enumerate(values, start=1):
                enums_dict[enum_name][str(index)] = value

        return dict(enums_dict)

    def extract_function_body_and_docstring(
        self, function_name: str, param_names: list[str]
    ) -> dict:
        """
        Extracts the function body and docstring from the Solidity code.
        Args:
            function_name: function name (e.g. "swap")
            param_names: parameter names (e.g. ["executor", "desc", "data"])

        Returns:
            The code of the function and its docstring.
        """
        code = self.stringify()

        # First, identify assembly blocks to exclude them from function search
        assembly_blocks = []
        assembly_pattern = re.compile(r'assembly\s*\{', re.DOTALL)

        for assembly_match in assembly_pattern.finditer(code):
            # Find the matching closing brace for this assembly block
            open_braces = 0
            start_pos = assembly_match.start()
            brace_start = assembly_match.end() - 1  # Position of the opening '{'

            i = brace_start
            while i < len(code):
                if code[i] == '{':
                    open_braces += 1
                elif code[i] == '}':
                    open_braces -= 1
                    if open_braces == 0:
                        assembly_blocks.append((start_pos, i + 1))
                        break
                i += 1

        def is_in_assembly_block(position: int) -> bool:
            """Check if a position is inside any assembly block"""
            for assembly_start, assembly_end in assembly_blocks:
                if assembly_start <= position < assembly_end:
                    return True
            return False

        # Match all function declarations with this name, but exclude those in assembly blocks
        function_decl_pattern = re.compile(
            rf"function\s+{re.escape(function_name)}\s*\((.*?)\)", re.DOTALL
        )

        candidates = []
        for match in function_decl_pattern.finditer(code):
            raw_params_block = match.group(1)
            cleaned_params_block = self.remove_comments(raw_params_block)

            # Extract parameter names from the cleaned block
            found_param_names = self.parse_parameter_names(cleaned_params_block)

            print(f"[DEBUG] Found function '{function_name}' at position {match.start()}")
            print(f"[DEBUG] Raw params: '{raw_params_block}'")
            print(f"[DEBUG] Found param names: {found_param_names}")
            print(f"[DEBUG] Expected param names: {param_names}")

            # Skip if this function is inside an assembly block
            if is_in_assembly_block(match.start()):
                print(f"[DEBUG] Skipping function '{function_name}' at position {match.start()} - found inside assembly block")
                continue

            # Additional check: Reject functions that look like assembly functions
            # Assembly functions have simple identifiers as parameters (no types)
            is_assembly_style = False
            if raw_params_block.strip():
                # Check if parameters have no types (suggesting assembly function)
                param_parts = [p.strip() for p in raw_params_block.split(',') if p.strip()]
                is_assembly_style = all(
                    len(p.split()) == 1 and not any(keyword in p for keyword in ["address", "uint", "int", "bool", "bytes", "string", "calldata", "memory", "storage"])
                    for p in param_parts
                )

            if is_assembly_style:
                print(f"[DEBUG] Skipping function '{function_name}' at position {match.start()} - appears to be assembly function (no parameter types)")
                continue

            if found_param_names == param_names:
                # Ensure this is not an interface/abstract method:
                # there needs to be braces to declare the function before
                # the next instance of ';'
                after_decl = code[match.end() :]
                next_brace = after_decl.find("{")
                next_semicolon = after_decl.find(";")

                if 0 <= next_brace < next_semicolon or (
                    next_brace != -1 and next_semicolon == -1
                ):
                    print(f"[DEBUG] Found valid Solidity function '{function_name}' at position {match.start()}")
                    candidates.append(match)
                else:
                    print(f"[DEBUG] Skipping function '{function_name}' at position {match.start()} - appears to be interface/abstract")
            else:
                print(f"[DEBUG] Skipping function '{function_name}' at position {match.start()} - parameter names don't match")

        if not candidates:
            print(f"[DEBUG] No valid Solidity functions found for '{function_name}' with params {param_names}")
            return {"body": None, "docstrings": None}

        match = candidates[-1]
        header_start = match.start()

        # --- Extract full function body with braces ---
        open_braces = 0
        body_start = code.find("{", header_start)
        i = body_start
        while i < len(code):
            if code[i] == "{":
                open_braces += 1
            elif code[i] == "}":
                open_braces -= 1
                if open_braces == 0:
                    body_end = i + 1
                    break
            i += 1
        else:
            body_end = len(code)

        function_body = code[match.start() : body_end].strip()

        # --- Extract last docstring immediately before the function ---
        lines = code[: match.start()].splitlines()

        docstring_lines = []
        inside_doc = False

        for line in reversed(lines):
            stripped = line.strip()
            if stripped.endswith("*/"):
                inside_doc = True
                docstring_lines.insert(0, line)
            elif inside_doc:
                docstring_lines.insert(0, line)
                if stripped.startswith("/**"):
                    break
            elif stripped != "":
                # Abort if code appears between docstring and function
                break
        docstring = "\n".join(docstring_lines).strip() if docstring_lines else None

        return {"function_body": function_body, "docstring": docstring}

    def extract_function_body_and_docstring_by_signature(
        self, function_signature: str
    ) -> dict:
        """
        Extracts the function body and docstring from the Solidity code using full function signature.
        Args:
            function_signature: full function signature (e.g. "swap(address,(address,address,address,address,uint256,uint256,uint256,bytes),bytes)")

        Returns:
            The code of the function and its docstring.
        """
        code = self.stringify()

        # Parse the function signature to extract name and parameter types
        # Format: functionName(type1,type2,type3)
        if '(' not in function_signature:
            print(f"[DEBUG] Invalid function signature format: {function_signature}")
            return {"body": None, "docstrings": None}

        function_name = function_signature.split('(')[0]
        params_part = function_signature[function_signature.find('(') + 1:function_signature.rfind(')')]

        print(f"[DEBUG] Searching for function: {function_name}")
        print(f"[DEBUG] Expected parameter types: {params_part}")

        # Create a more specific regex pattern that matches the function signature pattern in Solidity
        # This will match functions that have types in their parameters (not assembly functions)

        # Match function declarations with typed parameters
        # Pattern: function name(...typed parameters...)
        function_decl_pattern = re.compile(
            rf"function\s+{re.escape(function_name)}\s*\((.*?)\)", re.DOTALL
        )

        candidates = []
        for match in function_decl_pattern.finditer(code):
            raw_params_block = match.group(1)
            cleaned_params_block = self.remove_comments(raw_params_block)

            print(f"[DEBUG] Found function '{function_name}' at position {match.start()}")
            print(f"[DEBUG] Raw params: '{raw_params_block}'")

            # Skip if this looks like an assembly function (no types, just identifiers)
            if raw_params_block.strip():
                param_parts = [p.strip() for p in raw_params_block.split(',') if p.strip()]
                is_assembly_style = all(
                    len(p.split()) == 1 and not any(keyword in p for keyword in ["address", "uint", "int", "bool", "bytes", "string", "calldata", "memory", "storage", "contract", "struct"])
                    for p in param_parts
                )

                if is_assembly_style:
                    print(f"[DEBUG] Skipping function '{function_name}' at position {match.start()} - appears to be assembly function (no parameter types)")
                    continue

            # Check if this function is inside an assembly block
            assembly_blocks = []
            assembly_pattern = re.compile(r'assembly\s*\{', re.DOTALL)

            for assembly_match in assembly_pattern.finditer(code):
                open_braces = 0
                start_pos = assembly_match.start()
                brace_start = assembly_match.end() - 1

                i = brace_start
                while i < len(code):
                    if code[i] == '{':
                        open_braces += 1
                    elif code[i] == '}':
                        open_braces -= 1
                        if open_braces == 0:
                            assembly_blocks.append((start_pos, i + 1))
                            break
                    i += 1

            is_in_assembly = any(start <= match.start() < end for start, end in assembly_blocks)
            if is_in_assembly:
                print(f"[DEBUG] Skipping function '{function_name}' at position {match.start()} - found inside assembly block")
                continue

            # Ensure this is not an interface/abstract method
            after_decl = code[match.end():]
            next_brace = after_decl.find("{")
            next_semicolon = after_decl.find(";")

            if 0 <= next_brace < next_semicolon or (next_brace != -1 and next_semicolon == -1):
                print(f"[DEBUG] Found valid Solidity function '{function_name}' at position {match.start()}")
                candidates.append(match)
            else:
                print(f"[DEBUG] Skipping function '{function_name}' at position {match.start()} - appears to be interface/abstract")

        if not candidates:
            print(f"[DEBUG] No valid Solidity functions found for signature '{function_signature}'")
            return {"body": None, "docstrings": None}

        # Use the last candidate (in case there are multiple, prefer later definitions)
        match = candidates[-1]
        header_start = match.start()

        # Extract full function body with braces
        open_braces = 0
        body_start = code.find("{", header_start)
        i = body_start
        while i < len(code):
            if code[i] == "{":
                open_braces += 1
            elif code[i] == "}":
                open_braces -= 1
                if open_braces == 0:
                    body_end = i + 1
                    break
            i += 1
        else:
            body_end = len(code)

        function_body = code[match.start():body_end].strip()

        # Extract docstring (same logic as before)
        lines = code[:match.start()].splitlines()

        docstring_lines = []
        inside_doc = False

        for line in reversed(lines):
            stripped = line.strip()
            if stripped.endswith("*/"):
                inside_doc = True
                docstring_lines.insert(0, line)
            elif inside_doc:
                docstring_lines.insert(0, line)
                if stripped.startswith("/**"):
                    break
            elif stripped != "":
                break
        docstring = "\n".join(docstring_lines).strip() if docstring_lines else None

        return {"function_body": function_body, "docstring": docstring}


class ABI:
    """
    Class to interact with contract ABI.
    """

    def __init__(self, abi: list):
        self.abi = abi

    @staticmethod
    def _function_signature_to_selector(signature: str) -> str:
        """
        Convert a function signature to a function selector.
        """
        return "0x" + keccak(text=signature).hex()[:8]

    def _param_abi_type_to_str(self, param) -> str:
        """
        Recursively convert ABI input types into signature strings.
        """
        if param["type"] == "tuple":
            inner = ",".join(
                self._param_abi_type_to_str(p) for p in param["components"]
            )
            return f"({inner})" + ("[]" if param.get("type").endswith("[]") else "")
        elif param["type"].startswith("tuple["):
            inner = ",".join(
                self._param_abi_type_to_str(p) for p in param["components"]
            )
            return f"({inner})" + param["type"][5:]
        else:
            return param["type"]

    def find_function_by_selector(self, selector: str) -> dict:
        """
        Find function by selector in ABI. The selector is the first 4 bytes
        of the keccak256 hash of the function signature,
        e.g kekkac256("transfer(address,uint256)") = '0xa9059cbb'.
        On-chain data often contains only selectors, so we require this function to
        find the function in the ABI.
        """
        for item in self.abi:
            if item.get("type") != "function":
                continue
            name = item["name"]
            inputs = item.get("inputs", [])
            native_types = ",".join(self._param_abi_type_to_str(p) for p in inputs)
            signature = f"{name}({native_types})"

            computed_selector = self._function_signature_to_selector(signature)
            if computed_selector == selector.lower():
                return {
                    "name": name,
                    "param_names": [item.get("name") for item in inputs],
                    "param_internal_types": [
                        item.get("internalType") for item in inputs
                    ],
                    "signature": signature,
                    "selector": computed_selector,
                }
        return {}


class ContractCodeDataFetcher:
    """
    Class to fetch contract code and ABI from Sourcify and Etherscan.
    """

    def __init__(self, contract_address: str, chain_id: int = 1):
        self.contract_address = contract_address
        self.chain_id = chain_id
        self.sourcify_data = self.get_data_from_sourcify()
        self.etherscan_data = self.get_data_from_etherscan()
        self.abi = ABI(self.get_abi())
        self.solidity = SolidityCode(self.get_source_code())
        self.contract_name = self.etherscan_data.get("ContractName", "")

    def get_data_from_sourcify(self) -> dict:
        """
        Fetches contract data from Sourcify.
        """
        base_url = f"https://sourcify.dev/server/v2/contract/{self.chain_id}/{self.contract_address}?omit=creationBytecode,runtimeBytecode"
        r = requests.get(base_url, headers={"accept": "application/json"})
        if r.status_code != 200:
            print(
                f"[INFO] Contract {self.contract_address} not found on Sourcify (chain {self.chain_id}), will use Etherscan as fallback"
            )
            return {}
        return r.json()

    def get_data_from_etherscan(self) -> dict:
        """
        Fetches contract data from Etherscan.
        """
        if self.chain_id != 1:
            raise ValueError("Only chain ID 1 is supported for Etherscan API calls")

        # Etherscan API endpoint
        url = "https://api.etherscan.io/v2/api?chainid=1"
        # Accept both env var names
        api_key = (
            os.getenv("SOURCE_ETHERSCAN_API_KEY")
            or os.getenv("ETHERSCAN_API_KEY")
            or ""
        )
        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": self.contract_address,
            "apikey": api_key,
        }
        r = requests.get(url, params=params)
        if r.status_code != 200:
            print(
                f"[ERROR] Failed to fetch data from Etherscan for contract {self.contract_address} on chain {self.chain_id}: {r.status_code} - {r.text}"
            )
            return {}
        # return r.json().get("result", [{}])[0]
        try:
            j = r.json()
            print(f"[DEBUG] Etherscan API response status: {j.get('status')}, message: {j.get('message')}")
        except Exception as e:
            # Fallback to empty structure if we didn't get JSON
            print(f"[ERROR] Failed to parse Etherscan JSON response: {e}")
            return {}
        result = j.get("result", [])
        print(f"[DEBUG] Etherscan result type: {type(result)}, length/value: {len(result) if isinstance(result, (list, str)) else result}")

        # Etherscan returns a list; pick the first item if present
        if isinstance(result, list) and result:
            item = result[0]
            print(f"[DEBUG] First item type: {type(item)}, keys: {list(item.keys()) if isinstance(item, dict) else 'N/A'}")
            # Ensure we return a dict
            return item if isinstance(item, dict) else {}
        # Some failure modes return a string in "result"
        if isinstance(result, str):
            print(f"[DEBUG] Result is a string: {result[:100]}")
            # Try to treat it as a bare ABI JSON string
            try:
                _ = json.loads(result)  # just to see if it's JSON
                return {"ABI": result}
            except Exception:
                return {}
        print(f"[DEBUG] Returning empty dict from get_data_from_etherscan")
        return {}

    def get_abi(self) -> list:
        """
        Returns ABI from either Sourcify or Etherscan
        """
        # try:
        #     return json.loads(self.etherscan_data.get("ABI", "[]"))
        # except JSONDecodeError:
        #     return self.sourcify_data.get("abi", [])
        data = self.etherscan_data
        # If etherscan_data is a dict holding "ABI"
        if isinstance(data, dict):
            abi_raw = data.get("ABI", "[]")
            try:
                return json.loads(abi_raw)
            except JSONDecodeError:
                pass
        # If etherscan_data itself is a raw JSON string (rare fallback)
        if isinstance(data, str):
            try:
                return json.loads(data)
            except JSONDecodeError:
                pass
        # Last resort: Sourcify
        return self.sourcify_data.get("abi", [])

    def get_source_code(self) -> list:
        """
        Returns source code from either Sourcify or Etherscan
        """
        source_code = []
        try:
            source_code = [
                (file, content["content"])
                for file, content in self.sourcify_data["sources"].items()
            ]
            print(f"[DEBUG] Got {len(source_code)} files from Sourcify")
        except KeyError:
            # Fallback to Etherscan
            print(f"[DEBUG] Sourcify data not available, falling back to Etherscan")
            print(f"[DEBUG] etherscan_data keys: {list(self.etherscan_data.keys())}")
            raw_source = self.etherscan_data.get("SourceCode", "")
            if not raw_source:
                print(f"[WARNING] Etherscan SourceCode is empty for contract {self.contract_address}")
                print(f"[DEBUG] Full etherscan_data: {self.etherscan_data}")
                return []

            print(f"[DEBUG] Etherscan raw_source length: {len(raw_source)} chars, starts with: {raw_source[:50] if len(raw_source) > 50 else raw_source}")

            # Etherscan multi-file format starts with {{ and contains JSON
            if raw_source.startswith("{{"):
                # Remove outer braces and parse JSON
                try:
                    json_str = raw_source[1:-1]  # Remove outer {{ }}
                    sources_dict = json.loads(json_str)
                    # Extract sources from the "sources" key
                    if "sources" in sources_dict:
                        source_code = [
                            (filename, filedata.get("content", ""))
                            for filename, filedata in sources_dict["sources"].items()
                        ]
                        print(f"[DEBUG] Parsed {len(source_code)} files from Etherscan multi-file format")
                    else:
                        # Sometimes the structure is different
                        source_code = [
                            (filename, filedata.get("content", ""))
                            for filename, filedata in sources_dict.items()
                            if isinstance(filedata, dict) and "content" in filedata
                        ]
                        print(f"[DEBUG] Parsed {len(source_code)} files from Etherscan alternative format")
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    print(f"[WARNING] Failed to parse Etherscan multi-file JSON: {e}")
                    source_code = [("all_code", raw_source)]
            else:
                # Single file format
                source_code = [("all_code", raw_source)]
                print(f"[DEBUG] Using single-file format from Etherscan ({len(raw_source)} chars)")
        return source_code


class ContractCode(ContractCodeDataFetcher):
    def __init__(self, contract_address: str, chain_id: int = 1):
        super().__init__(contract_address, chain_id)

    def get_function_metadata(self, selector: str) -> dict:
        """
        Fetches function metadata from Sourcify and Etherscan.
        """
        record = {
            "contract_address": self.contract_address,
            "selector": selector,
            "chain_id": self.chain_id,
        }

        function_data = self.abi.find_function_by_selector(selector)
        record.update(function_data)

        # Some user notices are available in the Sourcify data
        user_notice = (
            self.sourcify_data.get("userdoc", {})
            .get("methods", {})
            .get(function_data.get("signature"), {})
            .get("notice")
        )

        code_data = {}
        if function_data.get("signature"):
            code_data = self.solidity.extract_function_body_and_docstring_by_signature(
                function_signature=function_data["signature"],
            )

        record.update(
            {
                "docstring": code_data.get("docstring"),
                "params": code_data.get("params"),
                "function_body": code_data.get("function_body"),
                "user_notice": user_notice,
                "abi": self.abi.abi,
                "source_code": self.solidity.code,
                "status": "success",
            }
        )
        return record

    def get_contract_functions_metadata(self, selectors: list) -> list:
        """
        Fetches metadata for multiple contract functions.
        """
        data_record = {}
        records = []
        for selector in selectors:
            function_metadata = self.get_function_metadata(selector)
            function_metadata.update(data_record)
            records.append(function_metadata)

        return records

    def generate_erc7730(self) -> dict:
        """
        Generates the ERC7730 JSON for Ledger.
        """
        url = "https://get-clear-signed.ledger.com/api/py/generateERC7730"
        params = {
            "abi": json.dumps(self.abi.abi),
            "contract_address": self.contract_address,
            "chain_id": self.chain_id,
        }
        headers = {"accept": "application/json", "Content-Type": "application/json"}

        r = requests.post(url, headers=headers, json=params)
        return r.json()


def fix_erc7730(name: str, content: dict, function_abi: dict, abi: list):
    model = "gpt-4o"
    client = AzureOpenAI(
        api_key="TO FILL",
        api_version="2024-10-21",
        azure_endpoint="https://hackhatonmay2025clearsigning-fpoirier.openai.azure.com/",
    )
    user_prompt = Template(
        """<Function name to analyze>${name}</Function name to analyze>
        <JSON content to analyze>${content} </JSON content to analyze>
        <ABI of the function>${function_abi} </ABI of the function>
        <ABI of the whole smart contract>${abi} </ABI of the whole smart contract>
        """
    )
    system_prompt = """
        I have a JSON object that contains the content of a function of a smart contract, in the ERC7730 format.
        Please fix the content. You can assume it is syntaxically valid JSON.
        - You must update the "intent" key when it's empty, or correct it when unclear, uncomplete.
        - You must update the "format" keys when they are empty or contain an incorrect type. The formats must be
        among those quoted values (in parenthesis, there is a description that should not appear in the output):
            * "raw" (When the value is a raw UINT parameter that you cannot link to any below defined parameters)
            * "amount (Amount in native currency (ETH) -> use amount ONLY if you are sure the currency is Native (ETH))
            * "tokenAmount" (Amount in ERC20 Token)
            * "nftTName" (ID of the NFT in the collection, if the asset referenced to is a NFT)
            * "addressName" (If the parameter is an address)
            * "date" (If the parameter is an UINT referencing a date)
            * "duration" (If the parameter is an UINT referencing a duration)
            * "enum" (Value is converted using referenced constant enumeration values. It's an internal path (starting with root node $.) to an enumerations in metadata.constants)
        - If the "format" is "tokenAmount", there must be a "tokenPath" key nested in the "params".
          If the token amount refers to an token address defined in another parameter, you must define the tokenPath in the "params" of the tokenAmount.
          If the token amount seems to refer to a constant token address not defined in metadata, you must use the function logs to understand what the token address was and specify its address in the "tokenPath" params.
        - Only output the corrected JSON object. No other text before or after.
        - Do not truncate the JSON.

        Example of valid JSON:
        ```json
        {
            "$id": "repay",
            "intent": "Repay loan",
            "fields": [
            {
                "path": "amount",
                "format": "tokenAmount",
                "label": "Amount to repay",
                "params": { "tokenPath": "asset" }
            },
            {
                "path": "asset",
                "format": "addressName",
                "label": "Asset"
            },
            {
                "path": "interestRateMode",
                "format": "enum",
                "label": "Interest rate mode",
                "params": { "$ref": "$.metadata.enums.interestRateMode" }
            }
            ],
            "required": ["amount", "interestRateMode"],
            "excluded": ["asset"]
        }
        ```
        """

    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_prompt.substitute(
                    name=name,
                    content=json.dumps(content),
                    function_abi=json.dumps(function_abi),
                    abi=str(abi),
                ),
            },
        ],
    )

    return completion.choices[0].message


if __name__ == "__main__":
    contract_address = "0x111111125421ca6dc452d289314280a0f8842a65"

    chain_id = 1
    contract_code = ContractCode(contract_address, chain_id)
    selectors = ["0xac9650d8"]

    # metadata = contract_code.get_contract_functions_metadata(selectors)
    erc7730 = contract_code.generate_erc7730()
    abis = {
        content["name"]: content
        for content in erc7730.get("context").get("contract").get("abi")
    }

    results = []
    for function_name, function_content in (
        erc7730.get("display").get("formats").items()
    ):
        print(f"### New function: {function_name}")
        print("Before")
        print(function_content)
        result = fix_erc7730(
            function_name,
            function_content,
            function_abi=abis.get(function_name),
            abi=abis,
        )
        print("After")
        print(result.content)
        results.append(result.content)

    # Write to disk
    with open("new_erc7730.json", "w") as f:
        json.dump(results, f, indent=2)

    # Example usage: 1inch Aggregation Router V6
    # contract_address = "0x111111125421ca6dc452d289314280a0f8842a65"
    # chain_id = 1
    # contract_code = ContractCode(contract_address, chain_id)
    # selectors = [
    #    "0x19367472",  # unoswap2(uint256,uint256,uint256,uint256,uint256)
    #    "0x07ed2379",  # swap(address,(address,address,address,address,uint256,uint256,uint256),bytes)
    # ]
    # metadata = contract_code.get_contract_functions_metadata(selectors)
    # function = contract_code.solidity.extract_function_body_and_docstring(
    #    function_name="swap",
    #    param_names=["executor", "desc", "data"],
    # )
    # print(function)
