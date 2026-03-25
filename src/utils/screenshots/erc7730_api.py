"""Local ERC-7730 descriptor processing API.

Replaces the remote Vercel-hosted API at app.devicesdk.ledger-test.com.
Runs as a background thread inside the analyzer process so cs-tester can
convert ERC-7730 descriptors to CAL calldata/EIP-712 payloads locally.
"""

import hashlib
import json
import logging
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import ecdsa
import requests
from ecdsa.util import sigencode_der
from pydantic import ValidationError

from erc7730.common.output import ListOutputAdder
from erc7730.convert.calldata.convert_erc7730_input_to_calldata import (
    erc7730_descriptor_to_calldata_descriptors,
)
from erc7730.convert.calldata.convert_erc7730_v2_input_to_calldata import (
    erc7730_v2_descriptor_to_calldata_descriptors,
)
from erc7730.convert.ledger.eip712.convert_erc7730_to_eip712 import (
    ERC7730toEIP712Converter,
)
from erc7730.convert.ledger.eip712.convert_erc7730_v2_to_eip712 import (
    ERC7730V2toEIP712Converter,
)
from erc7730.convert.resolved.convert_erc7730_input_to_resolved import (
    ERC7730InputToResolved,
)
from erc7730.model.input.descriptor import InputERC7730Descriptor
from erc7730.model.input.v2.descriptor import (
    InputERC7730Descriptor as InputERC7730DescriptorV2,
)
from eip712.convert.input_to_resolved import EIP712InputToResolvedConverter
from eip712.convert.resolved_to_instructions import (
    EIP712ResolvedToInstructionsConverter,
)
from eip712.model.input.descriptor import InputEIP712DAppDescriptor
from eip712.model.types import EIP712Version
from eip712.serialize import serialize_instruction

logger = logging.getLogger(__name__)

DEFAULT_CAL_URL = "https://crypto-assets-service.api.ledger.com/v1"
TEST_SIGNING_KEY = "b1ed47ef58f782e2bc4d5abe70ef66d9009c2957967017054470e0f3e10f5833"
TEST_VERIFYING_KEY = "0320da62003c0ce097e33644a10fe4c30454069a4454f0fa9d4e84f45091429b52"
TEST_SIGNING_KEY_CERTIFICATE = "f7aeb3d0f44f1bf50d89a1996bbb2bf0544dce2e0a2d0ff67eea0fa9c750f3d0"
CAL_CERTIFICATES_OVERRIDES = {
    "cal_calldata_key",
    "erc20_metadata_key",
    "cal_network",
    "plugin_selector_key",
    "cal_trusted_name",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_v2(data: dict[str, Any]) -> bool:
    return "v2" in (data.get("$schema") or "")


def _remove_nulls(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _remove_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_remove_nulls(i) for i in obj if i is not None]
    return obj


def _normalize_etherscan(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize_etherscan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_etherscan(i) for i in obj]
    if isinstance(obj, str):
        old = "https://api.etherscan.io/api?module=contract&action=getabi&address="
        if obj.startswith(old):
            obj = obj.replace(old, "https://api.etherscan.io/v2/api?chainid=1&module=contract&action=getabi&address=", 1)
        if obj.startswith("https://api.etherscan.io/v2/api"):
            key = os.getenv("ETHERSCAN_API_KEY")
            if key:
                obj = f"{obj}&apikey={key}"
    return obj


def _sign(payload: str, key: str = TEST_SIGNING_KEY) -> dict[str, Any]:
    sk = ecdsa.SigningKey.from_string(bytes.fromhex(key), curve=ecdsa.SECP256k1)
    sig = sk.sign(bytes.fromhex(payload), hashfunc=hashlib.sha256, sigencode=sigencode_der)
    return {"data": payload, "signatures": {"test": sig.hex(), "prod": sig.hex()}}


def _sign_enums(enums: list[dict]) -> dict[str, dict]:
    signed: dict[str, dict] = {}
    for e in enums:
        signed.setdefault(e["id"], {})[e["value"]] = _sign(e["descriptor"])
    return signed


def _format_calldata(descriptor: Any) -> dict[str, Any]:
    d = descriptor.model_dump(mode="json")
    if "transaction_info" in d and "descriptor" in d["transaction_info"]:
        d["transaction_info"]["descriptor"] = _sign(d["transaction_info"]["descriptor"])
    if "enums" in d:
        d["enums"] = _sign_enums(d["enums"])
    return _remove_nulls(d)


def _group_calldata(descriptors: list) -> dict[str, Any]:
    grouped: dict[tuple[int, str], list] = {}
    for d in descriptors:
        grouped.setdefault((d.chain_id, d.address.lower()), []).append(d)
    result: dict[str, Any] = {}
    for (cid, addr), descs in grouped.items():
        selectors = {d.selector: _format_calldata(d) for d in descs}
        result[f"{cid}:{addr}"] = [{"descriptors_calldata": {addr: selectors}}]
    return result


def _format_eip712_instruction(instr: Any) -> dict[str, Any]:
    d = instr.model_dump(mode="json")
    if d.get("name_types") is not None:
        d["name_types"] = [
            EIP712ResolvedToInstructionsConverter.int_to_name_type(v).value if isinstance(v, int) else v
            for v in d["name_types"]
        ]
    if d.get("name_sources") is not None:
        d["name_sources"] = [
            EIP712ResolvedToInstructionsConverter.int_to_name_source(v).value if isinstance(v, int) else v
            for v in d["name_sources"]
        ]
    serialized = serialize_instruction(instr, EIP712Version.V2)
    sig = _sign(serialized)
    d["descriptor"] = serialized
    d["signatures"] = sig["signatures"]
    return _remove_nulls(d)


def _eip712_from_descriptor(desc_in: InputEIP712DAppDescriptor) -> dict[str, dict]:
    resolved = EIP712InputToResolvedConverter().convert(desc_in)
    instructions = EIP712ResolvedToInstructionsConverter().convert(resolved)
    result: dict[str, dict] = {}
    for addr, instr_dict in instructions.items():
        for schema_hash, instr_list in instr_dict.items():
            if not instr_list:
                continue
            cid = instr_list[0].chain_id
            result[f"{cid}:{addr}"] = {
                addr: {schema_hash: {"instructions": [_format_eip712_instruction(i) for i in instr_list]}}
            }
    return result


# ---------------------------------------------------------------------------
# Descriptor processing
# ---------------------------------------------------------------------------

def _process_descriptor(data: dict[str, Any]) -> tuple[dict[str, Any], int]:
    try:
        data = _normalize_etherscan(data)
        is_v2 = _is_v2(data)

        if is_v2:
            desc = InputERC7730DescriptorV2.model_validate(data, strict=False)
            ctx = desc.context
            if not ctx:
                return {"error": "Missing context in v2 descriptor"}, 400
            if hasattr(ctx, "contract") and ctx.contract is not None:
                cds = erc7730_v2_descriptor_to_calldata_descriptors(desc)
                if not cds:
                    return {"error": "No calldata descriptors generated from v2 descriptor."}, 400
                return {"message": "ok", "descriptors": _group_calldata(cds)}, 200
            if hasattr(ctx, "eip712") and ctx.eip712 is not None:
                out = ListOutputAdder()
                eip712_descs = ERC7730V2toEIP712Converter().convert(desc, out)
                if not eip712_descs:
                    return {"error": "No eip712 descriptors from v2 descriptor."}, 400
                processed = {}
                for d in eip712_descs.values():
                    for k, v in _eip712_from_descriptor(d).items():
                        processed[k] = [{"descriptors_eip712": v}]
                return {"message": "ok", "descriptors": processed}, 200
            return {"error": "Unknown v2 context type"}, 400
        else:
            desc = InputERC7730Descriptor.model_validate(data, strict=False)
            ctx = desc.context
            if not ctx:
                return {"error": "Missing context"}, 400
            if hasattr(ctx, "contract") and ctx.contract is not None:
                cds = erc7730_descriptor_to_calldata_descriptors(desc)
                if not cds:
                    return {"error": "No calldata descriptors generated."}, 400
                return {"message": "ok", "descriptors": _group_calldata(cds)}, 200
            if hasattr(ctx, "eip712") and ctx.eip712 is not None:
                out = ListOutputAdder()
                resolved = ERC7730InputToResolved().convert(desc, out)
                if resolved is None:
                    return {"error": f"Resolution failed: {out}"}, 400
                eip712_descs = ERC7730toEIP712Converter().convert(resolved, out)
                if not eip712_descs:
                    return {"error": "No eip712 descriptors generated."}, 400
                processed = {}
                for d in eip712_descs.values():
                    for k, v in _eip712_from_descriptor(d).items():
                        processed[k] = [{"descriptors_eip712": v}]
                return {"message": "ok", "descriptors": processed}, 200
            return {"error": "Unknown context type"}, 400

    except ValidationError as e:
        return {"error": f"Invalid descriptor: {e}"}, 400
    except ValueError as e:
        return {"error": str(e)}, 400
    except Exception as e:
        logger.exception("ERC-7730 local API error")
        return {"error": f"Internal error: {e}"}, 500


def _fetch_certificates() -> tuple[dict[str, Any] | list, int]:
    try:
        resp = requests.get(
            f"{DEFAULT_CAL_URL}/certificates",
            params={"ref": "branch:main", "output": "public_key,target_device,public_key_id,public_key_usage,descriptor"},
            timeout=10,
        )
        resp.raise_for_status()
        certs = resp.json()
        if not isinstance(certs, list):
            return {"error": "Bad CAL response"}, 502

        result: dict[str, list] = {}
        for cert in certs:
            if cert.get("public_key_id") not in CAL_CERTIFICATES_OVERRIDES:
                continue
            td = cert.get("target_device", "")
            pk_id = cert.get("public_key_id", "")
            pk_usage = cert.get("public_key_usage", "")
            orig_pk = cert.get("public_key", "")
            key = f"{td}:{pk_id}:{pk_usage}"
            d = dict(cert.get("descriptor", {}))
            if "data" in d and orig_pk:
                new_data = d["data"].replace(orig_pk, TEST_VERIFYING_KEY)
                d["data"] = new_data
                signed = _sign(new_data, TEST_SIGNING_KEY_CERTIFICATE)
                d["signatures"] = {"test": signed["signatures"]["test"], "prod": signed["signatures"]["test"]}
            result[key] = [{"descriptor": d}]
        return result, 200
    except Exception as e:
        return {"error": f"Certificate fetch failed: {e}"}, 502


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        logger.debug("ERC7730-API: %s", fmt % args)

    def _send_json(self, body: Any, status: int) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path.startswith("/api/certificates"):
            body, status = _fetch_certificates()
            self._send_json(body, status)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        if self.path.startswith("/api/process-erc7730-descriptor"):
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            body, status = _process_descriptor(data)
            self._send_json(body, status)
        else:
            self._send_json({"error": "not found"}, 404)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_server_instance: HTTPServer | None = None
_server_port: int | None = None
_server_lock = threading.Lock()


def ensure_running() -> int:
    """Start the local API if not already running. Returns the port number."""
    global _server_instance, _server_port
    with _server_lock:
        if _server_instance is not None and _server_port is not None:
            return _server_port

        port = _find_free_port()
        server = HTTPServer(("127.0.0.1", port), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True, name="erc7730-local-api")
        thread.start()
        _server_instance = server
        _server_port = port
        logger.info("[ERC7730-API] Local descriptor API started on http://127.0.0.1:%d", port)
        return port
