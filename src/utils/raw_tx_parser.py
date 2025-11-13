"""
Raw transaction parser for manual transaction analysis.

This module handles parsing of raw RLP-encoded transactions to extract:
- Contract address (to)
- Input data (calldata)
- Function selector (first 4 bytes of input)
- Transaction value (msg.value)
- Chain ID
"""

import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import rlp
from eth_utils import to_hex

logger = logging.getLogger(__name__)


def parse_raw_transaction(raw_tx_hex: str) -> Optional[Dict[str, Any]]:
    """
    Parse a raw RLP-encoded transaction to extract key fields.

    Supports both legacy and EIP-1559 (Type 2) transactions.

    Args:
        raw_tx_hex: Raw transaction as hex string (with or without 0x prefix)

    Returns:
        Dictionary with parsed transaction fields or None if parsing fails:
        {
            'to': '0x...',           # Contract address
            'value': int,            # Transaction value in wei
            'input': '0x...',        # Full input data (calldata)
            'selector': '0x...',     # Function selector (first 4 bytes)
            'chain_id': int,         # Chain ID (if available)
            'type': 'legacy' | 'eip1559' | 'eip2930'
        }
    """
    try:
        # Remove 0x prefix if present
        if raw_tx_hex.startswith('0x'):
            raw_tx_hex = raw_tx_hex[2:]

        tx_bytes = bytes.fromhex(raw_tx_hex)

        # Check transaction type (first byte for typed transactions)
        # EIP-2718: If first byte < 0x7f, it's a typed transaction
        if tx_bytes[0] <= 0x7f:
            tx_type = tx_bytes[0]
            tx_payload = tx_bytes[1:]

            if tx_type == 0x02:  # EIP-1559 transaction
                return _parse_eip1559_transaction(tx_payload)
            elif tx_type == 0x01:  # EIP-2930 transaction
                return _parse_eip2930_transaction(tx_payload)
            else:
                logger.warning(f"Unknown transaction type: {tx_type}")
                return None
        else:
            # Legacy transaction
            return _parse_legacy_transaction(tx_bytes)

    except Exception as e:
        logger.error(f"Failed to parse raw transaction: {e}")
        logger.debug(f"Raw TX: {raw_tx_hex[:100]}...")
        return None


def _parse_eip1559_transaction(tx_payload: bytes) -> Optional[Dict[str, Any]]:
    """Parse EIP-1559 (Type 2) transaction."""
    try:
        # EIP-1559 structure: [chainId, nonce, maxPriorityFeePerGas, maxFeePerGas,
        #                      gasLimit, to, value, data, accessList, signatureYParity, signatureR, signatureS]
        decoded = rlp.decode(tx_payload)

        chain_id = int.from_bytes(decoded[0], byteorder='big') if decoded[0] else None
        to_address = to_hex(decoded[5]) if decoded[5] else None
        value = int.from_bytes(decoded[6], byteorder='big') if decoded[6] else 0
        input_data = to_hex(decoded[7]) if decoded[7] else '0x'

        # Extract selector (first 4 bytes of input data)
        selector = input_data[:10] if len(input_data) >= 10 else input_data

        result = {
            'to': to_address,
            'value': value,
            'input': input_data,
            'selector': selector,
            'chain_id': chain_id,
            'type': 'eip1559'
        }

        logger.debug(f"Parsed EIP-1559 TX: to={to_address}, selector={selector}, value={value}")
        return result

    except Exception as e:
        logger.error(f"Failed to parse EIP-1559 transaction: {e}")
        return None


def _parse_eip2930_transaction(tx_payload: bytes) -> Optional[Dict[str, Any]]:
    """Parse EIP-2930 (Type 1) transaction."""
    try:
        # EIP-2930 structure: [chainId, nonce, gasPrice, gasLimit, to, value,
        #                      data, accessList, signatureYParity, signatureR, signatureS]
        decoded = rlp.decode(tx_payload)

        chain_id = int.from_bytes(decoded[0], byteorder='big') if decoded[0] else None
        to_address = to_hex(decoded[4]) if decoded[4] else None
        value = int.from_bytes(decoded[5], byteorder='big') if decoded[5] else 0
        input_data = to_hex(decoded[6]) if decoded[6] else '0x'

        # Extract selector
        selector = input_data[:10] if len(input_data) >= 10 else input_data

        result = {
            'to': to_address,
            'value': value,
            'input': input_data,
            'selector': selector,
            'chain_id': chain_id,
            'type': 'eip2930'
        }

        logger.debug(f"Parsed EIP-2930 TX: to={to_address}, selector={selector}, value={value}")
        return result

    except Exception as e:
        logger.error(f"Failed to parse EIP-2930 transaction: {e}")
        return None


def _parse_legacy_transaction(tx_bytes: bytes) -> Optional[Dict[str, Any]]:
    """Parse legacy (pre-EIP-2718) transaction."""
    try:
        # Legacy structure: [nonce, gasPrice, gasLimit, to, value, data, v, r, s]
        decoded = rlp.decode(tx_bytes)

        to_address = to_hex(decoded[3]) if decoded[3] else None
        value = int.from_bytes(decoded[4], byteorder='big') if decoded[4] else 0
        input_data = to_hex(decoded[5]) if decoded[5] else '0x'

        # Extract chain ID from v (EIP-155)
        v = int.from_bytes(decoded[6], byteorder='big') if decoded[6] else None
        chain_id = None
        if v and v >= 37:  # EIP-155 signature
            chain_id = (v - 35) // 2

        # Extract selector
        selector = input_data[:10] if len(input_data) >= 10 else input_data

        result = {
            'to': to_address,
            'value': value,
            'input': input_data,
            'selector': selector,
            'chain_id': chain_id,
            'type': 'legacy'
        }

        logger.debug(f"Parsed legacy TX: to={to_address}, selector={selector}, value={value}")
        return result

    except Exception as e:
        logger.error(f"Failed to parse legacy transaction: {e}")
        return None


def load_raw_transactions(file_path: Path) -> List[Dict[str, Any]]:
    """
    Load and parse raw transactions from a JSON file.

    Expected JSON format:
    [
        {
            "txHash": "0x..." (optional),
            "rawTx": "0x..." (required),
            "description": "..." (optional)
        }
    ]

    Args:
        file_path: Path to JSON file containing raw transactions

    Returns:
        List of parsed transactions with metadata
    """
    try:
        with open(file_path, 'r') as f:
            raw_txs = json.load(f)

        if not isinstance(raw_txs, list):
            logger.error("Raw transactions file must contain a JSON array")
            return []

        parsed_txs = []
        for idx, raw_tx_entry in enumerate(raw_txs):
            if not isinstance(raw_tx_entry, dict):
                logger.warning(f"Skipping invalid entry at index {idx}: not a dictionary")
                continue

            if 'rawTx' not in raw_tx_entry:
                logger.warning(f"Skipping entry at index {idx}: missing 'rawTx' field")
                continue

            # Parse the raw transaction
            parsed = parse_raw_transaction(raw_tx_entry['rawTx'])

            if parsed:
                # Add metadata from the JSON entry
                parsed['tx_hash'] = raw_tx_entry.get('txHash', f"manual_tx_{idx}")
                parsed['description'] = raw_tx_entry.get('description', '')
                parsed['source'] = 'manual'
                parsed_txs.append(parsed)

                logger.info(f"✓ Parsed manual TX {idx + 1}: {parsed['selector']} -> {parsed['to']}")
            else:
                logger.warning(f"✗ Failed to parse raw transaction at index {idx}")

        logger.info(f"Loaded {len(parsed_txs)}/{len(raw_txs)} manual transactions from {file_path}")
        return parsed_txs

    except FileNotFoundError:
        logger.error(f"Raw transactions file not found: {file_path}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in raw transactions file: {e}")
        return []
    except Exception as e:
        logger.error(f"Failed to load raw transactions: {e}")
        return []


def group_transactions_by_selector(parsed_txs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group parsed transactions by their function selector.

    Args:
        parsed_txs: List of parsed transactions

    Returns:
        Dictionary mapping selector -> list of transactions
    """
    grouped = {}

    for tx in parsed_txs:
        selector = tx.get('selector')
        if selector:
            if selector not in grouped:
                grouped[selector] = []
            grouped[selector].append(tx)

    return grouped
