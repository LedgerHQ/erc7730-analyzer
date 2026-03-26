"""Selector-level multi-agent audit orchestration."""

from __future__ import annotations

import asyncio
import atexit
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from eth_utils import keccak
from web3 import Web3

from ..abi import ABI
from ..extraction.source_code import RPC_URLS
from ..reporting.reporter.expansion import expand_erc7730_format_with_refs
from ..reporting.reporter.formatting import format_source_code_section
from .models import (
    AuditReport,
    AuditResult,
    AuditTask,
    PrimaryAuditorOutput,
    ToolRequest,
    ValidatorOutput,
)
from .rules import SCREENSHOT_INSTRUCTIONS, SYSTEM_INSTRUCTIONS

if TYPE_CHECKING:
    from openai import AsyncOpenAI
    from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4-nano"
DEFAULT_REASONING_EFFORT = "low"

TOOL_CATALOG = """\
Available evidence tools:
- `get_related_source_context`
  Purpose: fetch source/dependency context for another useful function, not the main selector snippet already in the packet.
  arguments_json shape:
  {"function_name":"foo"} or {"function_signature":"foo(uint256)"} or {"selector":"0x12345678"}
  Optional keys: "chain_id", "address", "max_lines"

- `search_cached_source`
  Purpose: regex/text search across cached extracted source outside the current selector snippet.
  arguments_json shape:
  {"query":"transferFrom|approve"}
  Optional keys: "chain_id", "address", "context_lines", "max_matches"

- `get_other_selector_descriptor`
  Purpose: fetch another selector/signature descriptor from the same ERC-7730 file.
  arguments_json shape:
  {"selector":"0xa9059cbb"} or {"function_signature":"transfer(address to,uint256 amount)"}

- `get_previous_selector_analysis`
  Purpose: fetch the completed analysis summary for a different selector already processed in this run.
  arguments_json shape:
  {"selector":"0xa9059cbb"} or {"function_signature":"transfer(address,uint256)"}

- `get_external_contract_source_context`
  Purpose: resolve an external contract target, optionally from a storage slot on the analyzed contract, then fetch source/dependency context for a function on that external contract.
  arguments_json shape:
  {"function_signature":"balanceOf(address)","target_address":"0x..."} or {"function_name":"foo","storage_slot":"0x3"}
  Optional keys: "selector", "chain_id", "contract_address", "block_number", "tx_hash", "max_lines"

- `anvil_read_storage`
  Purpose: read one storage slot against a pinned fork or direct RPC fallback.
  arguments_json shape:
  {"chain_id":1,"address":"0x...","slot":"0x0"}
  Optional keys: "block_number", "tx_hash"

- `anvil_call_view`
  Purpose: execute one view/pure function against a pinned fork or direct RPC fallback.
  arguments_json shape:
  {"chain_id":1,"address":"0x...","function_signature":"balanceOf(address)","args":["0x..."]}
  Optional keys: "block_number", "tx_hash", "from_address", "value_wei"

Rules for tool requests:
- Request tools only when the selector packet is genuinely insufficient.
- Keep requests precise and bounded.
- `arguments_json` must be a valid JSON object string.
"""

PRIMARY_SYSTEM_INSTRUCTIONS = (
    f"{SYSTEM_INSTRUCTIONS}\n\n"
    "ADDITIONAL ROLE: You are the PRIMARY selector auditor for a single contract-bound selector.\n"
    "The selector packet already includes the expanded current descriptor, decoded transaction samples, and the main extracted source slice.\n"
    "Explicitly verify that the selector, ABI function_signature, and descriptor format key are consistent before trusting the descriptor.\n"
    "Do NOT request tools for facts that are already clearly present in the selector packet.\n"
    "Use tools only when you need evidence outside the current packet: related code, another selector descriptor, a prior selector analysis, or a targeted on-chain state check.\n"
    "Apply the packaged rule files conservatively and avoid overclaiming from partial evidence.\n"
    "If you need more evidence, return status='need_tools' with precise tool requests. Otherwise return status='ready' with a complete draft_report.\n\n"
    f"{TOOL_CATALOG}"
)

VALIDATOR_SYSTEM_INSTRUCTIONS = (
    f"{SYSTEM_INSTRUCTIONS}\n\n"
    "ADDITIONAL ROLE: You are the SKEPTICAL validator for a single contract-bound selector.\n"
    "Your job is to challenge the primary auditor's draft. Prefer conservative conclusions when evidence is mixed.\n"
    "Specifically challenge any selector/function_signature/descriptor-key mismatch before accepting the draft.\n"
    "Challenge unsupported assumptions, weak fixability, and overconfident severity escalations using the packaged rule files.\n"
    "Use tools only for a specific unresolved contradiction, not for re-reading context already in the selector packet.\n"
    "If you need more evidence, return status='need_tools'. Otherwise return status='ready' with a validated_report.\n\n"
    f"{TOOL_CATALOG}"
)

REDUCER_SYSTEM_INSTRUCTIONS = (
    f"{SYSTEM_INSTRUCTIONS}\n\n"
    "ADDITIONAL ROLE: You are the FINAL reducer for a single contract-bound selector.\n"
    "You receive the raw selector packet, the primary draft, the validator's summary/change list, and any gathered tool evidence.\n"
    "Use the validator change list as critique against the primary draft. A full alternate validator report may be omitted when unnecessary.\n"
    "Produce the final AuditReport conservatively. Prefer the better-supported conclusion when the two disagree, using the packaged rule files and gathered evidence."
)


def _trim_text(value: str, max_chars: int = 12000) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "\n... [truncated]"


def _single_line(value: Any, max_chars: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _summarize_report_model(report: AuditReport | None) -> str:
    if report is None:
        return "no_report"

    return (
        f"crit={len(report.critical_issues)} "
        f"missing={len(report.missing_parameters)} "
        f"display={len(report.display_issues)} "
        f"coverage={report.overall_assessment.coverage_score.score} "
        f"risk={report.overall_assessment.security_risk.level}"
    )


def _log_phase_report(phase: str, selector: str, report: AuditReport | None, summary: str = "") -> None:
    """Log a detailed breakdown of one agent phase's report."""
    if report is None:
        logger.debug("[AGENTIC][%s][%s] No report produced.", phase, selector)
        return

    sep = "─" * 60
    lines = [
        f"\n{sep}",
        f"[AGENTIC][{phase.upper()}][{selector}] Agent Report",
        sep,
    ]
    if summary:
        lines.append(f"  Summary : {summary}")

    lines.append(
        f"  Coverage: {report.overall_assessment.coverage_score.score}/100 "
        f"— {report.overall_assessment.coverage_score.explanation}"
    )
    lines.append(
        f"  Risk    : {report.overall_assessment.security_risk.level} "
        f"— {report.overall_assessment.security_risk.reasoning}"
    )

    if report.critical_issues:
        lines.append(f"  Critical Issues ({len(report.critical_issues)}):")
        for ci in report.critical_issues:
            lines.append(f"    • {ci.issue}")
            lines.append(f"      shows : {ci.details.what_descriptor_shows}")
            lines.append(f"      actual: {ci.details.what_actually_happens}")
            lines.append(f"      why   : {ci.details.why_critical}")
    else:
        lines.append("  Critical Issues: none")

    if report.missing_parameters:
        lines.append(f"  Missing Parameters ({len(report.missing_parameters)}):")
        for mp in report.missing_parameters:
            lines.append(f"    • [{mp.risk_level}] {mp.parameter} — {mp.importance}")
    else:
        lines.append("  Missing Parameters: none")

    if report.display_issues:
        lines.append(f"  Display Issues ({len(report.display_issues)}):")
        for di in report.display_issues:
            lines.append(f"    • [{di.severity}] {di.type}: {di.description}")
    else:
        lines.append("  Display Issues: none")

    lines.append(f"  Intent  : {report.intent_analysis.declared_intent} — {report.intent_analysis.assessment}")

    if report.recommendations.fixes:
        lines.append(f"  Fixes ({len(report.recommendations.fixes)}):")
        for fix in report.recommendations.fixes:
            lines.append(f"    • {fix.title}: {fix.description}")

    if report.recommendations.spec_limitations:
        lines.append(f"  Spec Limitations ({len(report.recommendations.spec_limitations)}):")
        for sl in report.recommendations.spec_limitations:
            lines.append(f"    • {sl.parameter}: {sl.explanation} (impact: {sl.impact})")

    lines.append(sep)
    logger.debug("\n".join(lines))


def _summarize_tool_result(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return _single_line(result)

    error = result.get("error")
    if error:
        return f"error={_single_line(error)}"

    if "matches" in result:
        return f"matches={len(result.get('matches', []))}"

    if "expanded_descriptor" in result:
        descriptor = result.get("expanded_descriptor") or {}
        fields = descriptor.get("fields", []) if isinstance(descriptor, dict) else []
        return f"format_key={result.get('format_key')} fields={len(fields)}"

    if "critical_issues" in result and "coverage_score" in result:
        return (
            f"previous_analysis crit={len(result.get('critical_issues', []))} "
            f"coverage={result.get('coverage_score')} risk={result.get('security_risk')}"
        )

    if "content" in result and "function_signature" in result:
        return (
            f"function_signature={result.get('function_signature')} "
            f"lines={result.get('total_lines')} truncated={result.get('truncated')}"
        )

    if "resolved_target_address" in result:
        return (
            f"target={result.get('resolved_target_address')} "
            f"function_signature={result.get('function_signature')} "
            f"lines={result.get('total_lines')} truncated={result.get('truncated')}"
        )

    if "value_hex" in result:
        return (
            f"backend={result.get('backend')} "
            f"slot={result.get('slot')} "
            f"value={_single_line(result.get('value_hex'), 80)}"
        )

    if "raw_result" in result:
        decoded = result.get("decoded_output")
        decoded_preview = decoded if decoded is not None else result.get("raw_result")
        return (
            f"backend={result.get('backend')} "
            f"function_signature={result.get('function_signature')} "
            f"decoded={_single_line(decoded_preview, 120)}"
        )

    return _single_line(result, 180)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if isinstance(value, tuple):
        return [_normalize_value(item) for item in value]
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_value(item) for key, item in value.items()}
    return value


def _canonical_signature(signature: str) -> str:
    return "".join(signature.split())


def _split_signature_types(signature: str) -> list[str]:
    start = signature.find("(")
    end = signature.rfind(")")
    if start == -1 or end == -1 or end <= start:
        return []
    params_body = signature[start + 1 : end].strip()
    if not params_body:
        return []

    params: list[str] = []
    current: list[str] = []
    depth = 0
    for char in params_body:
        if char == "," and depth == 0:
            param = "".join(current).strip()
            if param:
                params.append(param)
            current = []
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(depth - 1, 0)
        current.append(char)

    tail = "".join(current).strip()
    if tail:
        params.append(tail)
    return params


def _resolve_signature_from_request(
    *,
    abi_helper: ABI | None,
    selector: str | None,
    function_signature: str | None,
    function_name: str | None,
) -> tuple[str | None, str | None]:
    resolved_signature = function_signature
    resolved_name = function_name

    if selector and abi_helper:
        match = abi_helper.find_function_by_selector(selector.lower())
        if match:
            resolved_signature = match["signature"]
            resolved_name = match["name"]

    if resolved_signature and not resolved_name:
        resolved_name = resolved_signature.split("(", 1)[0].strip()

    return resolved_signature, resolved_name


def _summarize_report(report_data: dict[str, Any]) -> dict[str, Any]:
    overall = report_data.get("overall_assessment", {})
    coverage = overall.get("coverage_score", {})
    security = overall.get("security_risk", {})
    return {
        "selector": report_data.get("selector"),
        "function_signature": report_data.get("function_signature"),
        "critical_issues": [issue.get("issue", "") for issue in report_data.get("critical_issues", [])[:6]],
        "missing_parameters": [item.get("parameter", "") for item in report_data.get("missing_parameters", [])[:8]],
        "display_issues": [item.get("type", "") for item in report_data.get("display_issues", [])[:8]],
        "fix_titles": [item.get("title", "") for item in report_data.get("recommendations", {}).get("fixes", [])[:6]],
        "spec_limitations": [
            item.get("parameter", "") for item in report_data.get("recommendations", {}).get("spec_limitations", [])[:6]
        ],
        "coverage_score": coverage.get("score"),
        "coverage_explanation": coverage.get("explanation", ""),
        "security_risk": security.get("level"),
        "security_reasoning": security.get("reasoning", ""),
    }


def record_completed_analysis(task: AuditTask, report_data: dict[str, Any]) -> None:
    tool_context = task.tool_context or {}
    analysis_memory = tool_context.get("analysis_memory")
    if not isinstance(analysis_memory, dict) or not report_data:
        return

    entry = _summarize_report(report_data)
    selector_key = str(report_data.get("selector") or task.selector).lower()
    signature_key = str(report_data.get("function_signature") or task.function_signature)
    analysis_memory.setdefault("by_selector", {})[selector_key] = entry
    analysis_memory.setdefault("by_signature", {})[signature_key] = entry


@dataclass
class _ForkHandle:
    chain_id: int
    block_number: int | None
    rpc_url: str
    backend: str
    web3: Web3
    process: subprocess.Popen[str] | None
    endpoint: str


class AnvilForkManager:
    _forks: ClassVar[dict[tuple[int, int | None], _ForkHandle]] = {}
    _cleanup_registered: ClassVar[bool] = False

    @classmethod
    def _register_cleanup(cls) -> None:
        if cls._cleanup_registered:
            return
        atexit.register(cls.cleanup_all)
        cls._cleanup_registered = True

    @classmethod
    def cleanup_all(cls) -> None:
        for handle in list(cls._forks.values()):
            process = handle.process
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
        cls._forks.clear()

    @classmethod
    def _resolve_infura_url(cls, chain_id: int) -> str | None:
        infura_key = (
            os.getenv(f"INFURA_RPC_KEY_{chain_id}") or os.getenv("INFURA_RPC_KEY") or os.getenv("INFURA_API_KEY")
        )
        if not infura_key:
            return None

        if chain_id == 1:
            return f"https://mainnet.infura.io/v3/{infura_key}"

        return None

    @classmethod
    def _resolve_rpc_url(cls, chain_id: int) -> str | None:
        candidates = [
            os.getenv(f"RPC_URL_{chain_id}"),
            os.getenv(f"CHAIN_RPC_URL_{chain_id}"),
            os.getenv("RPC_URL") if chain_id == 1 else None,
            os.getenv("ETH_RPC_URL") if chain_id == 1 else None,
            cls._resolve_infura_url(chain_id),
            RPC_URLS.get(chain_id),
        ]
        for candidate in candidates:
            if candidate:
                return candidate
        return None

    @staticmethod
    def _find_free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @classmethod
    def _wait_for_web3(cls, web3: Web3, timeout: float = 20.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if web3.is_connected():
                    _ = web3.client_version
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    @classmethod
    def _resolve_anvil_binary(cls) -> str:
        candidates = [
            os.getenv("ANVIL_BIN"),
            shutil.which("anvil"),
            os.path.expanduser("~/.foundry/bin/anvil"),
        ]
        for candidate in candidates:
            if candidate and os.path.exists(candidate):
                return candidate
        return "anvil"

    @classmethod
    def get_web3(cls, chain_id: int, block_number: int | None) -> _ForkHandle:
        cls._register_cleanup()
        key = (chain_id, block_number)
        if key in cls._forks:
            return cls._forks[key]

        rpc_url = cls._resolve_rpc_url(chain_id)
        if not rpc_url:
            raise ValueError(
                f"No RPC URL configured for chain {chain_id}. "
                f"Set RPC_URL_{chain_id}, CHAIN_RPC_URL_{chain_id}, or INFURA_RPC_KEY (mainnet only)."
            )

        port = cls._find_free_port()
        endpoint = f"http://127.0.0.1:{port}"
        anvil_bin = cls._resolve_anvil_binary()
        command = [anvil_bin, "--host", "127.0.0.1", "--port", str(port), "--fork-url", rpc_url]
        if block_number is not None:
            command.extend(["--fork-block-number", str(block_number)])

        logger.info(
            "[AGENTIC][ANVIL] Starting fork",
            extra={"chain_id": chain_id, "block_number": block_number, "port": port},
        )
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            web3 = Web3(Web3.HTTPProvider(endpoint, request_kwargs={"timeout": 15}))
            if not cls._wait_for_web3(web3):
                raise RuntimeError("anvil fork did not become ready")
            handle = _ForkHandle(
                chain_id=chain_id,
                block_number=block_number,
                rpc_url=rpc_url,
                backend="anvil",
                web3=web3,
                process=process,
                endpoint=endpoint,
            )
        except Exception as exc:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
            logger.warning(
                "[AGENTIC][ANVIL] Falling back to direct RPC for chain %s at block %s: %s",
                chain_id,
                block_number,
                exc,
            )
            web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 15}))
            if not web3.is_connected():
                raise RuntimeError(f"Could not connect to RPC for chain {chain_id}: {rpc_url}") from exc
            handle = _ForkHandle(
                chain_id=chain_id,
                block_number=block_number,
                rpc_url=rpc_url,
                backend="direct_rpc",
                web3=web3,
                process=None,
                endpoint=rpc_url,
            )

        cls._forks[key] = handle
        return handle


class SelectorToolRunner:
    """Narrow evidence-gathering tools for selector-level agent runs."""

    def __init__(self, task: AuditTask) -> None:
        self.task = task
        self.tool_context = task.tool_context or {}
        abi = self.tool_context.get("abi")
        self.abi_helper = ABI(abi) if isinstance(abi, list) and abi else None

    _NETWORK_TOOLS = frozenset(
        {
            "get_external_contract_source_context",
            "anvil_read_storage",
            "anvil_call_view",
        }
    )

    async def execute_requests(self, requests: list[ToolRequest], max_requests: int) -> list[dict[str, Any]]:
        bounded = requests[:max_requests]

        for request in bounded:
            logger.debug(
                "[AGENTIC][TOOL][%s] Running %s rationale=%s args=%s",
                self.task.selector,
                request.tool,
                _single_line(request.rationale),
                _single_line(request.arguments_json, 280),
            )

        coros = [self._execute_single(req) for req in bounded]
        results = await asyncio.gather(*coros, return_exceptions=False)
        return list(results)

    async def _execute_single(self, request: ToolRequest) -> dict[str, Any]:
        """Execute one tool request, returning the result dict."""
        arguments: dict[str, Any] = {}
        try:
            arguments = json.loads(request.arguments_json or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must decode to an object")
        except Exception as exc:
            result = {"error": f"Invalid tool arguments JSON: {exc}"}
        else:
            try:
                result = await self._dispatch(request.tool, arguments)
            except Exception as exc:
                result = {"error": str(exc)}

        entry = {
            "tool": request.tool,
            "rationale": request.rationale,
            "arguments": arguments,
            "result": result,
        }
        if isinstance(result, dict) and result.get("error"):
            logger.warning(
                "[AGENTIC][TOOL][%s] %s failed: %s",
                self.task.selector,
                request.tool,
                _single_line(result.get("error")),
            )
        else:
            logger.debug(
                "[AGENTIC][TOOL][%s] %s complete: %s",
                self.task.selector,
                request.tool,
                _summarize_tool_result(result),
            )
        return entry

    async def _dispatch(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route a tool call, offloading network-bound tools to a thread."""
        if tool_name == "get_related_source_context":
            return self._get_related_source_context(arguments)
        if tool_name == "search_cached_source":
            return self._search_cached_source(arguments)
        if tool_name == "get_other_selector_descriptor":
            return self._get_other_selector_descriptor(arguments)
        if tool_name == "get_previous_selector_analysis":
            return self._get_previous_selector_analysis(arguments)
        if tool_name == "get_external_contract_source_context":
            return await asyncio.to_thread(self._get_external_contract_source_context, arguments)
        if tool_name == "anvil_read_storage":
            return await asyncio.to_thread(self._anvil_read_storage, arguments)
        if tool_name == "anvil_call_view":
            return await asyncio.to_thread(self._anvil_call_view, arguments)
        return {"error": f"Unsupported tool: {tool_name}"}

    def _iter_extracted_codes(
        self,
        chain_id: int | None = None,
        address: str | None = None,
    ) -> list[dict[str, Any]]:
        extracted_codes = self.tool_context.get("extracted_codes", {}) or {}
        selected: list[dict[str, Any]] = []
        normalized_address = address.lower() if isinstance(address, str) else None
        for extracted_code in extracted_codes.values():
            if chain_id is not None and extracted_code.get("chain_id") != chain_id:
                continue
            if normalized_address and str(extracted_code.get("address", "")).lower() != normalized_address:
                continue
            selected.append(extracted_code)
        return selected

    def _resolve_block_number(self, arguments: dict[str, Any]) -> int | None:
        block_number = arguments.get("block_number")
        if block_number is not None:
            return int(block_number)
        tx_hash = arguments.get("tx_hash")
        if tx_hash:
            for tx in self.task.decoded_transactions or []:
                if str(tx.get("hash", "")).lower() == str(tx_hash).lower():
                    try:
                        return int(tx.get("block"))
                    except Exception:
                        return None
        return None

    def _resolve_function_outputs(self, function_signature: str) -> list[str]:
        abi = self.tool_context.get("abi") or []
        canonical = _canonical_signature(function_signature)
        for item in abi:
            if item.get("type") != "function":
                continue
            inputs = item.get("inputs", [])
            signature = f"{item['name']}({','.join(param['type'] for param in inputs)})"
            if _canonical_signature(signature) == canonical:
                return [output["type"] for output in item.get("outputs", [])]
        return []

    def _default_chain_and_address(self) -> tuple[int | None, str | None]:
        selector_deployment = self.tool_context.get("selector_deployment") or {}
        chain_id = selector_deployment.get("chainId")
        address = selector_deployment.get("address")
        return (
            int(chain_id) if chain_id is not None else None,
            str(address) if address else None,
        )

    def _remember_extracted_code(self, extracted_code: dict[str, Any]) -> None:
        if not isinstance(extracted_code, dict):
            return
        chain_id = extracted_code.get("chain_id")
        address = extracted_code.get("address")
        if chain_id is None or not address:
            return

        extracted_codes = self.tool_context.setdefault("extracted_codes", {})
        extracted_codes[f"{int(chain_id)}:{str(address).lower()}"] = extracted_code

    def _get_related_source_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        source_extractor = self.tool_context.get("source_extractor")
        if source_extractor is None:
            return {"error": "Source extractor is not available."}

        function_signature, function_name = _resolve_signature_from_request(
            abi_helper=self.abi_helper,
            selector=arguments.get("selector"),
            function_signature=arguments.get("function_signature"),
            function_name=arguments.get("function_name"),
        )
        if not function_name:
            return {"error": "Provide function_name, function_signature, or selector."}

        chain_id = arguments.get("chain_id")
        chain_id = int(chain_id) if chain_id is not None else None
        address = arguments.get("address")
        max_lines = max(80, min(int(arguments.get("max_lines", 500)), 1200))

        for extracted_code in self._iter_extracted_codes(chain_id=chain_id, address=address):
            context = source_extractor.get_function_with_dependencies(
                function_name,
                extracted_code,
                function_signature=function_signature,
                max_lines=max_lines,
                selector_only=bool(arguments.get("selector")),
                selector=arguments.get("selector"),
            )
            if context and context.get("function"):
                formatted = _trim_text(format_source_code_section(context), max_chars=14000)
                return {
                    "function_name": function_name,
                    "function_signature": function_signature,
                    "chain_id": extracted_code.get("chain_id"),
                    "address": extracted_code.get("address"),
                    "total_lines": context.get("total_lines"),
                    "truncated": bool(context.get("truncated")),
                    "content": formatted,
                }

        return {"error": f"Could not resolve related source context for {function_name}."}

    def _search_cached_source(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return {"error": "query is required."}

        chain_id = arguments.get("chain_id")
        chain_id = int(chain_id) if chain_id is not None else None
        address = arguments.get("address")
        context_lines = max(0, min(int(arguments.get("context_lines", 2)), 6))
        max_matches = max(1, min(int(arguments.get("max_matches", 6)), 12))

        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        matches: list[dict[str, Any]] = []
        for extracted_code in self._iter_extracted_codes(chain_id=chain_id, address=address):
            sources = []
            source_code = extracted_code.get("source_code")
            if isinstance(source_code, str):
                sources.append(("merged", source_code))
            for facet_addr, facet_data in (extracted_code.get("_per_facet_codes") or {}).items():
                facet_source = facet_data.get("source_code")
                if isinstance(facet_source, str):
                    sources.append((facet_addr, facet_source))

            for source_label, source_text in sources:
                lines = source_text.splitlines()
                for line_index, line in enumerate(lines):
                    if not pattern.search(line):
                        continue
                    start = max(0, line_index - context_lines)
                    end = min(len(lines), line_index + context_lines + 1)
                    snippet = "\n".join(lines[start:end])
                    matches.append(
                        {
                            "chain_id": extracted_code.get("chain_id"),
                            "address": extracted_code.get("address"),
                            "source": source_label,
                            "line_number": line_index + 1,
                            "snippet": _trim_text(snippet, max_chars=1200),
                        }
                    )
                    if len(matches) >= max_matches:
                        return {"query": query, "matches": matches, "total_returned": len(matches)}

        return {"query": query, "matches": matches, "total_returned": len(matches)}

    def _get_other_selector_descriptor(self, arguments: dict[str, Any]) -> dict[str, Any]:
        selector_or_signature = str(arguments.get("selector") or arguments.get("function_signature") or "").strip()
        if not selector_or_signature:
            return {"error": "Provide selector or function_signature."}

        erc7730_data = self.tool_context.get("erc7730_data") or {}
        selector_to_format_key = self.tool_context.get("selector_to_format_key") or {}
        format_key = selector_to_format_key.get(selector_or_signature.lower(), selector_or_signature)
        selector_format = erc7730_data.get("display", {}).get("formats", {}).get(format_key)
        if not selector_format:
            return {"error": f"No descriptor found for {selector_or_signature}."}

        expanded = expand_erc7730_format_with_refs(selector_format, erc7730_data, format_key)
        return {
            "selector_lookup": selector_or_signature,
            "format_key": format_key,
            "expanded_descriptor": expanded,
        }

    def _get_previous_selector_analysis(self, arguments: dict[str, Any]) -> dict[str, Any]:
        selector_or_signature = str(arguments.get("selector") or arguments.get("function_signature") or "").strip()
        if not selector_or_signature:
            return {"error": "Provide selector or function_signature."}

        analysis_memory = self.tool_context.get("analysis_memory") or {}
        by_selector = analysis_memory.get("by_selector", {})
        by_signature = analysis_memory.get("by_signature", {})
        entry = by_selector.get(selector_or_signature.lower()) or by_signature.get(selector_or_signature)
        if not entry:
            return {"error": f"No completed selector analysis is available yet for {selector_or_signature}."}
        return entry

    def _get_external_contract_source_context(self, arguments: dict[str, Any]) -> dict[str, Any]:
        source_extractor = self.tool_context.get("source_extractor")
        if source_extractor is None:
            return {"error": "Source extractor is not available."}

        function_signature, function_name = _resolve_signature_from_request(
            abi_helper=None,
            selector=arguments.get("selector"),
            function_signature=arguments.get("function_signature"),
            function_name=arguments.get("function_name"),
        )
        if not function_name:
            return {"error": "Provide the target function via function_name, function_signature, or selector."}

        default_chain_id, default_contract_address = self._default_chain_and_address()
        chain_id_raw = arguments.get("chain_id", default_chain_id)
        if chain_id_raw is None:
            return {"error": "chain_id is required when the selector deployment is unavailable."}
        chain_id = int(chain_id_raw)

        contract_address = arguments.get("contract_address") or default_contract_address
        target_address = arguments.get("target_address")
        storage_lookup: dict[str, Any] | None = None

        if target_address:
            resolved_target_address = Web3.to_checksum_address(str(target_address))
        else:
            slot_raw = arguments.get("storage_slot")
            if slot_raw is None:
                return {"error": "Provide either target_address or storage_slot to resolve the external contract."}
            if not contract_address:
                return {"error": "contract_address is required when resolving an external target from storage."}

            storage_lookup = self._anvil_read_storage(
                {
                    "chain_id": chain_id,
                    "address": contract_address,
                    "slot": slot_raw,
                    "block_number": arguments.get("block_number"),
                    "tx_hash": arguments.get("tx_hash"),
                }
            )
            if storage_lookup.get("error"):
                return storage_lookup

            address_candidate = storage_lookup.get("address_candidate")
            if not address_candidate or int(address_candidate, 16) == 0:
                return {
                    "error": (
                        f"Storage slot {storage_lookup.get('slot')} on {contract_address} "
                        "did not resolve to a non-zero address."
                    ),
                    "storage_lookup": storage_lookup,
                }
            resolved_target_address = Web3.to_checksum_address(address_candidate)

        max_lines = max(80, min(int(arguments.get("max_lines", 500)), 1200))
        selector = arguments.get("selector")
        extracted_code = source_extractor.extract_contract_code(
            resolved_target_address,
            chain_id,
            selectors=[selector] if isinstance(selector, str) and selector else None,
        )
        self._remember_extracted_code(extracted_code)

        if not extracted_code or not extracted_code.get("source_code"):
            return {
                "error": f"Could not fetch source code for external contract {resolved_target_address}.",
                "resolved_target_address": resolved_target_address,
                "chain_id": chain_id,
                "storage_lookup": storage_lookup,
            }

        context = source_extractor.get_function_with_dependencies(
            function_name,
            extracted_code,
            function_signature=function_signature,
            max_lines=max_lines,
            selector_only=bool(selector),
            selector=selector,
        )
        if not context or not context.get("function"):
            return {
                "error": (
                    f"Resolved external contract {resolved_target_address}, but could not find "
                    f"function context for {function_name}."
                ),
                "resolved_target_address": resolved_target_address,
                "chain_id": chain_id,
                "contract_name": extracted_code.get("contract_name"),
                "is_proxy": extracted_code.get("is_proxy"),
                "implementation": extracted_code.get("implementation"),
                "storage_lookup": storage_lookup,
            }

        formatted = _trim_text(format_source_code_section(context), max_chars=14000)
        return {
            "resolved_target_address": resolved_target_address,
            "chain_id": chain_id,
            "contract_name": extracted_code.get("contract_name"),
            "is_proxy": extracted_code.get("is_proxy"),
            "implementation": extracted_code.get("implementation"),
            "function_name": function_name,
            "function_signature": function_signature,
            "total_lines": context.get("total_lines"),
            "truncated": bool(context.get("truncated")),
            "storage_lookup": storage_lookup,
            "content": formatted,
        }

    def _anvil_read_storage(self, arguments: dict[str, Any]) -> dict[str, Any]:
        chain_id = int(arguments["chain_id"])
        address = Web3.to_checksum_address(arguments["address"])
        slot_raw = arguments["slot"]
        if isinstance(slot_raw, str) and slot_raw.startswith("0x"):
            slot = int(slot_raw, 16)
        else:
            slot = int(slot_raw)

        block_number = self._resolve_block_number(arguments)
        handle = AnvilForkManager.get_web3(chain_id, block_number)
        if handle.backend == "anvil":
            storage_value = handle.web3.eth.get_storage_at(address, slot)
        else:
            storage_value = handle.web3.eth.get_storage_at(address, slot, block_identifier=block_number or "latest")

        storage_hex = "0x" + storage_value.hex()
        as_int = int.from_bytes(storage_value, byteorder="big")
        address_candidate = "0x" + storage_hex[-40:] if storage_hex != "0x" + "0" * 64 else None
        return {
            "backend": handle.backend,
            "endpoint": handle.endpoint,
            "chain_id": chain_id,
            "block_number": block_number,
            "address": address,
            "slot": hex(slot),
            "value_hex": storage_hex,
            "value_int": as_int,
            "address_candidate": address_candidate,
        }

    def _anvil_call_view(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from eth_abi import decode as abi_decode
        from eth_abi import encode as abi_encode

        chain_id = int(arguments["chain_id"])
        address = Web3.to_checksum_address(arguments["address"])
        function_signature = _canonical_signature(str(arguments["function_signature"]))
        function_selector = "0x" + keccak(text=function_signature).hex()[:8]
        input_types = _split_signature_types(function_signature)
        args = arguments.get("args", [])
        if len(args) != len(input_types):
            return {"error": f"Function {function_signature} expects {len(input_types)} args but received {len(args)}."}

        calldata = function_selector
        if input_types:
            calldata += abi_encode(input_types, args).hex()

        block_number = self._resolve_block_number(arguments)
        handle = AnvilForkManager.get_web3(chain_id, block_number)
        call_params: dict[str, Any] = {"to": address, "data": calldata}
        if arguments.get("from_address"):
            call_params["from"] = Web3.to_checksum_address(arguments["from_address"])
        if arguments.get("value_wei") is not None:
            call_params["value"] = int(arguments["value_wei"])

        if handle.backend == "anvil":
            raw_result = handle.web3.eth.call(call_params)
        else:
            raw_result = handle.web3.eth.call(call_params, block_identifier=block_number or "latest")

        raw_hex = "0x" + raw_result.hex()
        output_types = self._resolve_function_outputs(function_signature)
        decoded_output: Any = None
        if output_types and raw_result:
            try:
                decoded_output = _normalize_value(abi_decode(output_types, raw_result))
            except Exception:
                decoded_output = None

        return {
            "backend": handle.backend,
            "endpoint": handle.endpoint,
            "chain_id": chain_id,
            "block_number": block_number,
            "address": address,
            "function_signature": function_signature,
            "calldata": calldata,
            "raw_result": raw_hex,
            "output_types": output_types,
            "decoded_output": decoded_output,
        }


async def _parse_structured_response(
    *,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    system_prompt: str,
    user_payload: dict[str, Any],
    text_format: type[BaseModel],
    cache_key: str,
    selector: str,
    phase: str,
    max_retries: int,
    screenshot_data: list[dict[str, Any]] | None = None,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> BaseModel:
    serialized_payload = json.dumps(
        user_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    from .batch import _build_user_content_with_screenshots

    has_screenshots = bool(screenshot_data)
    user_content = _build_user_content_with_screenshots(
        serialized_payload, screenshot_data if has_screenshots else None
    )
    effective_system_prompt = system_prompt
    if has_screenshots and isinstance(user_content, list):
        effective_system_prompt = system_prompt + "\n\n" + SCREENSHOT_INSTRUCTIONS
        n_imgs = sum(1 for b in user_content if b.get("type") == "input_image")
        logger.debug("[AGENTIC][%s][%s] Including %d Ledger screenshot(s)", phase, selector, n_imgs)

    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            async with semaphore:
                logger.debug(
                    "[AGENTIC][%s][%s] Starting model call (attempt %s/%s, payload_chars=%s)",
                    phase,
                    selector,
                    attempt + 1,
                    max_retries + 1,
                    len(serialized_payload),
                )
                effective_model = model or DEFAULT_MODEL
                effective_effort = reasoning_effort or DEFAULT_REASONING_EFFORT
                dynamic_cache_key = f"{cache_key}_{effective_model.replace('.', '').replace('-', '')}"

                response = await client.responses.parse(
                    model=effective_model,
                    input=[
                        {"role": "system", "content": effective_system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    text_format=text_format,
                    reasoning={"effort": effective_effort},
                    text={"verbosity": "low"},
                    store=False,
                    prompt_cache_key=dynamic_cache_key,
                )

            usage = getattr(response, "usage", None)
            if usage:
                input_tokens = getattr(usage, "input_tokens", 0)
                output_tokens = getattr(usage, "output_tokens", 0)
                total_tokens = getattr(usage, "total_tokens", 0)
                cached_tokens = 0
                reasoning_tokens = 0
                if getattr(usage, "input_tokens_details", None):
                    cached_tokens = getattr(usage.input_tokens_details, "cached_tokens", 0)
                if getattr(usage, "output_tokens_details", None):
                    reasoning_tokens = getattr(usage.output_tokens_details, "reasoning_tokens", 0)
                logger.debug(
                    "[AGENTIC][%s][%s] Tokens: input=%s | cached=%s | output=%s | reasoning=%s | total=%s",
                    phase.upper(),
                    selector,
                    f"{input_tokens:,}",
                    f"{cached_tokens:,}",
                    f"{output_tokens:,}",
                    f"{reasoning_tokens:,}",
                    f"{total_tokens:,}",
                )
            return response.output_parsed
        except Exception as exc:
            last_error = exc
            logger.warning(
                "[AGENTIC][%s][%s] Model call failed on attempt %s/%s: %s",
                phase,
                selector,
                attempt + 1,
                max_retries + 1,
                exc,
            )
            if attempt < max_retries:
                await asyncio.sleep(min(2**attempt, 8))

    raise RuntimeError(f"{phase} parse failed for {selector}: {last_error}")


async def _run_phase_with_tools(
    *,
    phase_name: str,
    selector: str,
    system_prompt: str,
    initial_payload: dict[str, Any],
    output_model: type[BaseModel],
    cache_key: str,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    task: AuditTask,
    max_rounds: int,
    max_requests_per_round: int,
    max_retries: int,
    screenshot_data: list[dict[str, Any]] | None = None,
    model: str = DEFAULT_MODEL,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> tuple[BaseModel, list[dict[str, Any]]]:
    tool_runner = SelectorToolRunner(task)
    tool_results: list[dict[str, Any]] = []

    for round_index in range(max_rounds):
        finalize_now = round_index == max_rounds - 1
        logger.debug(
            "[AGENTIC][%s][%s] Round %s/%s start finalize_now=%s accumulated_tool_results=%s",
            phase_name,
            selector,
            round_index + 1,
            max_rounds,
            finalize_now,
            len(tool_results),
        )
        payload = {
            **initial_payload,
            "tool_results": tool_results,
            "round_index": round_index + 1,
            "max_rounds": max_rounds,
            "tool_request_limit": max_requests_per_round,
            "finalize_now": finalize_now,
        }
        parsed = await _parse_structured_response(
            client=client,
            semaphore=semaphore,
            system_prompt=system_prompt,
            user_payload=payload,
            text_format=output_model,
            cache_key=cache_key,
            selector=selector,
            phase=phase_name,
            max_retries=max_retries,
            screenshot_data=screenshot_data if round_index == 0 else None,
            model=model,
            reasoning_effort=reasoning_effort,
        )

        status = getattr(parsed, "status", "ready")
        summary = _single_line(getattr(parsed, "summary", ""))
        requests = getattr(parsed, "tool_requests", []) or []
        logger.debug(
            "[AGENTIC][%s][%s] Model returned status=%s summary=%s tool_requests=%s",
            phase_name,
            selector,
            status,
            summary or "<empty>",
            len(requests),
        )
        if status == "ready":
            report = getattr(parsed, "draft_report", None) or getattr(parsed, "validated_report", None)
            logger.debug(
                "[AGENTIC][%s][%s] Phase ready after round %s report=%s",
                phase_name,
                selector,
                round_index + 1,
                _summarize_report_model(report),
            )
            return parsed, tool_results

        if not requests:
            raise RuntimeError(f"{phase_name} requested tools without any tool requests for {selector}.")

        if len(requests) > max_requests_per_round:
            logger.warning(
                "[AGENTIC][%s][%s] Requested %s tools but limit is %s; truncating",
                phase_name,
                selector,
                len(requests),
                max_requests_per_round,
            )
        for request_index, request in enumerate(requests[:max_requests_per_round], start=1):
            logger.debug(
                "[AGENTIC][%s][%s] Tool request %s/%s tool=%s rationale=%s args=%s",
                phase_name,
                selector,
                request_index,
                min(len(requests), max_requests_per_round),
                request.tool,
                _single_line(request.rationale),
                _single_line(request.arguments_json, 280),
            )
        logger.debug(
            "[AGENTIC][%s][%s] Executing %s tool request(s) in round %s",
            phase_name,
            selector,
            min(len(requests), max_requests_per_round),
            round_index + 1,
        )
        tool_results.extend(await tool_runner.execute_requests(requests, max_requests_per_round))

    raise RuntimeError(f"{phase_name} did not converge for {selector} within {max_rounds} rounds.")


async def generate_multi_agent_audit_async(
    task: AuditTask,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    max_retries: int = 3,
    max_rounds: int = 2,
    max_requests_per_round: int = 2,
) -> AuditResult:
    descriptor_context = task.descriptor_context or {}
    source_resolution = task.source_resolution or {}
    logger.info(
        "[AGENTIC][%s] Starting multi-agent selector audit signature=%s txs=%s source_match=%s key_style=%s format_key=%s rounds=%s requests_per_round=%s",
        task.selector,
        task.function_signature,
        len(task.decoded_transactions or []),
        source_resolution.get("match_mode"),
        descriptor_context.get("descriptor_key_style"),
        descriptor_context.get("format_key"),
        max_rounds,
        max_requests_per_round,
    )

    model = task.llm_model or DEFAULT_MODEL
    effort = task.llm_reasoning_effort or DEFAULT_REASONING_EFFORT
    logger.debug("[AGENTIC][%s] Using model=%s reasoning_effort=%s", task.selector, model, effort)

    primary_output, primary_tool_results = await _run_phase_with_tools(
        phase_name="primary",
        selector=task.selector,
        system_prompt=PRIMARY_SYSTEM_INSTRUCTIONS,
        initial_payload={"selector_packet": task.audit_payload},
        output_model=PrimaryAuditorOutput,
        cache_key="erc7730_audit_v2_primary",
        client=client,
        semaphore=semaphore,
        task=task,
        max_rounds=max_rounds,
        max_requests_per_round=max_requests_per_round,
        max_retries=max_retries,
        screenshot_data=task.screenshot_data,
        model=model,
        reasoning_effort=effort,
    )
    if primary_output.draft_report is None:
        raise RuntimeError(f"Primary auditor returned ready without draft_report for {task.selector}.")
    logger.debug(
        "[AGENTIC][%s] Primary complete report=%s tool_results=%s",
        task.selector,
        _summarize_report_model(primary_output.draft_report),
        len(primary_tool_results),
    )
    _log_phase_report("primary", task.selector, primary_output.draft_report, primary_output.summary)

    validator_output, validator_tool_results = await _run_phase_with_tools(
        phase_name="validator",
        selector=task.selector,
        system_prompt=VALIDATOR_SYSTEM_INSTRUCTIONS,
        initial_payload={
            "selector_packet": task.audit_payload,
            "primary_summary": primary_output.summary,
            "primary_draft_report": primary_output.draft_report.model_dump() if primary_output.draft_report else None,
        },
        output_model=ValidatorOutput,
        cache_key="erc7730_audit_v2_validator",
        client=client,
        semaphore=semaphore,
        task=task,
        max_rounds=max_rounds,
        max_requests_per_round=max_requests_per_round,
        max_retries=max_retries,
        model=model,
        reasoning_effort=effort,
    )
    if validator_output.validated_report is None:
        raise RuntimeError(f"Validator returned ready without validated_report for {task.selector}.")
    logger.debug(
        "[AGENTIC][%s] Validator complete report=%s changes=%s tool_results=%s",
        task.selector,
        _summarize_report_model(validator_output.validated_report),
        len(validator_output.changes),
        len(validator_tool_results),
    )
    _log_phase_report("validator", task.selector, validator_output.validated_report, validator_output.summary)
    primary_report_dict = primary_output.draft_report.model_dump()
    validator_report_dict = validator_output.validated_report.model_dump()
    validator_changes_list = [change.model_dump() for change in validator_output.changes]
    validator_matches_primary = validator_report_dict == primary_report_dict

    if validator_output.changes:
        change_lines = [f"[AGENTIC][VALIDATOR][{task.selector}] Changes vs Primary:"]
        for vc in validator_output.changes:
            change_lines.append(f"  • [{vc.action}] {vc.subject}: {vc.explanation}")
        logger.debug("\n".join(change_lines))

    reducer_skipped = False
    reducer_used_validator_report_fallback = False
    if not validator_changes_list and validator_matches_primary:
        reducer_skipped = True
        final_report = validator_output.validated_report
        logger.info(
            "[AGENTIC][reducer][%s] Skipping reducer: validator fully accepted primary draft",
            task.selector,
        )
    else:
        reducer_payload = {
            "selector_packet": task.audit_payload,
            "primary_summary": primary_output.summary,
            "primary_draft_report": primary_report_dict,
            "primary_tool_results": primary_tool_results,
            "validator_summary": validator_output.summary,
            "validator_changes": validator_changes_list,
            "validator_tool_results": validator_tool_results,
        }
        if not validator_changes_list and not validator_matches_primary:
            reducer_used_validator_report_fallback = True
            reducer_payload["validator_report_fallback"] = validator_report_dict
            logger.warning(
                "[AGENTIC][reducer][%s] Validator report differs from primary but no explicit changes were provided; passing validator_report_fallback",
                task.selector,
            )

        logger.debug(
            "[AGENTIC][reducer][%s] Starting reducer primary_tools=%s validator_tools=%s validator_changes=%s",
            task.selector,
            len(primary_tool_results),
            len(validator_tool_results),
            len(validator_changes_list),
        )
        final_report = await _parse_structured_response(
            client=client,
            semaphore=semaphore,
            system_prompt=REDUCER_SYSTEM_INSTRUCTIONS,
            user_payload=reducer_payload,
            text_format=AuditReport,
            cache_key="erc7730_audit_v2_reducer",
            selector=task.selector,
            phase="reducer",
            max_retries=max_retries,
            model=model,
            reasoning_effort=effort,
        )

        _log_phase_report("reducer", task.selector, final_report)

    report_data = final_report.model_dump()
    report_data["function_signature"] = task.function_signature
    report_data["selector"] = task.selector
    report_data["erc7730_format"] = task.erc7730_format
    report_data["descriptor_format_key"] = (task.descriptor_context or {}).get("format_key")
    report_data["abi_resolution"] = task.abi_resolution or {}
    report_data["agentic_trace"] = {
        "primary_summary": primary_output.summary,
        "primary_report": primary_report_dict,
        "validator_summary": validator_output.summary,
        "validator_report": validator_report_dict,
        "validator_changes": validator_changes_list,
        "validator_matches_primary": validator_matches_primary,
        "reducer_skipped": reducer_skipped,
        "reducer_used_validator_report_fallback": reducer_used_validator_report_fallback,
        "tool_rounds": {
            "primary": len(primary_tool_results),
            "validator": len(validator_tool_results),
        },
        "analysis_mode": task.analysis_mode,
    }

    if "transaction_samples" in report_data and task.decoded_transactions:
        for sample in report_data["transaction_samples"]:
            tx_hash = sample.get("transaction_hash", "")
            matching_tx = next(
                (tx for tx in task.decoded_transactions if tx.get("hash") == tx_hash),
                None,
            )
            if matching_tx:
                sample["native_value"] = matching_tx.get("value", "0")
                sample["decoded_parameters"] = matching_tx.get("decoded_input", {})

    from ..reporting.markdown_formatter import format_audit_reports

    critical_report, detailed_report = format_audit_reports(report_data)
    record_completed_analysis(task, report_data)

    logger.debug(
        "[AGENTIC][%s] Multi-agent selector audit complete report=%s",
        task.selector,
        _summarize_report_model(final_report),
    )
    return AuditResult(
        selector=task.selector,
        function_signature=task.function_signature,
        critical_report=critical_report,
        detailed_report=detailed_report,
        report_data=report_data,
        success=True,
    )
