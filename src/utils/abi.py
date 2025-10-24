"""
ABI handling for ERC-7730 analyzer.

This module provides ABI parsing and function selector utilities.
"""

import json
import requests
from typing import Dict, List, Optional
from eth_utils import keccak


class ABI:
    """
    Class to interact with contract ABI.
    Handles function selector calculation and ABI lookups.
    """

    def __init__(self, abi: list):
        """
        Initialize with an ABI.

        Args:
            abi: Contract ABI as a list of dictionaries
        """
        self.abi = abi

    @staticmethod
    def _function_signature_to_selector(signature: str) -> str:
        """
        Convert a function signature to a function selector.

        Args:
            signature: Function signature (e.g., "transfer(address,uint256)")

        Returns:
            Function selector as hex string (e.g., "0xa9059cbb")
        """
        return "0x" + keccak(text=signature).hex()[:8]

    def _param_abi_type_to_str(self, param) -> str:
        """
        Recursively convert ABI input types into signature strings.

        Args:
            param: Parameter definition from ABI

        Returns:
            Type string for signature (e.g., "address", "(uint256,address)")
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
        Find function by selector in ABI.

        The selector is the first 4 bytes of the keccak256 hash of the function signature,
        e.g., keccak256("transfer(address,uint256)") = '0xa9059cbb'.

        Args:
            selector: Function selector as hex string

        Returns:
            Dictionary with function metadata:
            - name: Function name
            - param_names: List of parameter names
            - param_internal_types: List of parameter internal types
            - signature: Full function signature
            - selector: Function selector
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


def fetch_contract_abi(
    contract_address: str,
    chain_id: int,
    etherscan_api_key: str
) -> Optional[List[Dict]]:
    """
    Fetch contract ABI from Etherscan.

    Args:
        contract_address: Ethereum contract address
        chain_id: Chain ID for the contract
        etherscan_api_key: Etherscan API key

    Returns:
        Contract ABI as a list of dictionaries, or None if fetch fails
    """
    params = {
        'module': 'contract',
        'action': 'getabi',
        'address': contract_address,
        'apikey': etherscan_api_key
    }

    try:
        base_url = f"https://api.etherscan.io/v2/api?chainid={chain_id}"
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        if data['status'] == '1':
            abi = json.loads(data['result'])
            return abi
        else:
            return None
    except Exception:
        return None
