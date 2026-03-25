"""Task preparation and concurrent OpenAI audit execution."""

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from .agentic import generate_multi_agent_audit_async, record_completed_analysis
from .models import AuditReport, AuditResult, AuditTask
from .rules import SCREENSHOT_INSTRUCTIONS, SYSTEM_INSTRUCTIONS

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.4-nano"
DEFAULT_REASONING_EFFORT = "low"


def _build_user_content_with_screenshots(
    payload_json: str,
    screenshot_data: list[dict[str, Any]] | None,
) -> str | list[dict[str, Any]]:
    """Build OpenAI user content: plain text if no screenshots, multimodal otherwise.

    screenshot_data is a list of {"tx_hash": str, "screenshots": [path, ...]}.
    """
    if not screenshot_data:
        return payload_json

    # Flatten all screenshot paths from all transactions
    all_paths: list[str] = []
    for entry in screenshot_data:
        all_paths.extend(entry.get("screenshots", []))

    if not all_paths:
        return payload_json

    content_blocks: list[dict[str, Any]] = [{"type": "input_text", "text": payload_json}]

    for screenshot_path in all_paths:
        path = Path(screenshot_path)
        if not path.exists() or not path.suffix.lower() == ".png":
            continue
        try:
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            content_blocks.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{b64}",
                }
            )
        except Exception as exc:
            logger.warning("[SCREENSHOTS] Failed to encode %s: %s", path.name, exc)

    if len(content_blocks) == 1:
        return payload_json
    return content_blocks


def prepare_audit_task(
    selector: str,
    decoded_transactions: list[dict],
    erc7730_format: dict,
    function_signature: str,
    source_code: dict = None,
    use_smart_referencing: bool = True,
    erc4626_context: dict = None,
    erc20_context: dict = None,
    protocol_name: str = None,
    descriptor_context: dict = None,
    abi_resolution: dict = None,
    source_resolution: dict = None,
    analysis_mode: str = "single",
    tool_context: dict = None,
    screenshot_data: list[dict] = None,
    llm_model: str = DEFAULT_MODEL,
    llm_reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> AuditTask:
    """
    Prepare an audit task with ONLY dynamic data for optimal prompt caching.
    Static rules are in SYSTEM_INSTRUCTIONS and cached by OpenAI.

    Args:
        selector: Function selector
        decoded_transactions: List of decoded transactions with receipt logs
        erc7730_format: ERC-7730 format definition for this selector
        function_signature: Function signature
        source_code: Optional dictionary with extracted source code
        use_smart_referencing: Whether to use smart rule referencing
        erc4626_context: Optional ERC4626 vault context
        erc20_context: Optional ERC20 token context
        protocol_name: Optional protocol name from descriptor ($id, contractName, owner, or legacy legalName)
        descriptor_context: Contract-specific descriptor context for this selector
        source_resolution: Metadata explaining how the source snippet was resolved
        analysis_mode: single-pass or multi-agent analysis strategy
        tool_context: Internal-only context used by multi-agent helper tools

    Returns:
        AuditTask with minimal payload (only dynamic data)
    """
    # Build minimal payload with ONLY dynamic data
    # Static rules (validation_rules, critical_issues, etc.) are in SYSTEM_INSTRUCTIONS
    # NOTE: We include ALL source code fields (docstrings, libraries, parent_functions, etc.)
    # because they provide critical context for accurate analysis
    audit_payload = {
        "function_signature": function_signature,
        "selector": selector,
        "erc7730_format": erc7730_format,
        "decoded_transactions": decoded_transactions if decoded_transactions else [],  # Empty list if no txs
        "source_code": source_code if source_code else {},  # Include ALL source code fields
        "descriptor_context": descriptor_context if descriptor_context else {},
        "abi_resolution": abi_resolution if abi_resolution else {},
        "source_resolution": source_resolution if source_resolution else {},
        "erc4626_context": erc4626_context if erc4626_context else {},
        "erc20_context": erc20_context if erc20_context else {},
    }

    # Add protocol_name only if it exists (optional field)
    if protocol_name:
        audit_payload["protocol_name"] = protocol_name

    return AuditTask(
        selector=selector,
        function_signature=function_signature,
        decoded_transactions=decoded_transactions,
        erc7730_format=erc7730_format,
        source_code=source_code,
        use_smart_referencing=use_smart_referencing,
        erc4626_context=erc4626_context,
        erc20_context=erc20_context,
        descriptor_context=descriptor_context,
        abi_resolution=abi_resolution,
        source_resolution=source_resolution,
        analysis_mode=analysis_mode,
        audit_payload=audit_payload,
        optimization_note=None,
        tool_context=tool_context,
        screenshot_data=screenshot_data,
        llm_model=llm_model,
        llm_reasoning_effort=llm_reasoning_effort,
    )


async def generate_clear_signing_audit_async(
    task: AuditTask, client: AsyncOpenAI, semaphore: asyncio.Semaphore, max_retries: int = 3
) -> AuditResult:
    """
    Async version of generate_clear_signing_audit with retry logic.
    Uses a semaphore to limit concurrent API calls.

    Args:
        task: Pre-prepared AuditTask with payload
        client: AsyncOpenAI client (shared across all calls)
        semaphore: Semaphore to limit concurrency
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        AuditResult with the API response or error
    """
    async with semaphore:
        last_error = None

        for attempt in range(max_retries + 1):
            user_payload = ""
            try:
                if attempt == 0:
                    logger.info(f"[SINGLE] Starting API call for selector {task.selector}")
                else:
                    logger.warning(f"[SINGLE] Retry {attempt}/{max_retries} for selector {task.selector}")

                user_payload = json.dumps(task.audit_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

                has_screenshots = bool(task.screenshot_data)
                user_content = _build_user_content_with_screenshots(
                    user_payload, task.screenshot_data if has_screenshots else None
                )
                system_prompt = SYSTEM_INSTRUCTIONS
                if has_screenshots and isinstance(user_content, list):
                    system_prompt = SYSTEM_INSTRUCTIONS + "\n\n" + SCREENSHOT_INSTRUCTIONS
                    n_imgs = sum(1 for b in user_content if b.get("type") == "input_image")
                    logger.info("[SINGLE] Including %d Ledger screenshot(s) for %s", n_imgs, task.selector)

                model = task.llm_model or DEFAULT_MODEL
                effort = task.llm_reasoning_effort or DEFAULT_REASONING_EFFORT
                cache_key = f"erc7730_audit_v2_single_{model.replace('.', '').replace('-', '')}"

                response = await client.responses.parse(
                    model=model,
                    input=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
                    text_format=AuditReport,
                    reasoning={"effort": effort},
                    text={"verbosity": "low"},
                    store=False,
                    prompt_cache_key=cache_key,
                )

                # Log successful response with usage stats
                logger.info(f"[SINGLE] ✅ Received response for {task.selector}")
                if hasattr(response, "usage") and response.usage:
                    usage = response.usage
                    # Extract cached tokens from input_tokens_details
                    cached_tokens = 0
                    if hasattr(usage, "input_tokens_details") and usage.input_tokens_details:
                        cached_tokens = getattr(usage.input_tokens_details, "cached_tokens", 0)

                    # Extract reasoning tokens from output_tokens_details
                    reasoning_tokens = 0
                    if hasattr(usage, "output_tokens_details") and usage.output_tokens_details:
                        reasoning_tokens = getattr(usage.output_tokens_details, "reasoning_tokens", 0)

                    logger.info(f"[SINGLE]   Input tokens: {getattr(usage, 'input_tokens', 0):,}")
                    logger.info(f"[SINGLE]   Cached tokens: {cached_tokens:,}")
                    logger.info(f"[SINGLE]   Output tokens: {getattr(usage, 'output_tokens', 0):,}")
                    if reasoning_tokens > 0:
                        logger.info(f"[SINGLE]   Reasoning tokens: {reasoning_tokens:,}")
                    logger.info(f"[SINGLE]   Total tokens: {getattr(usage, 'total_tokens', 0):,}")

                report_data = response.output_parsed.model_dump()

                # Force key identifiers back into the structured output
                report_data["function_signature"] = task.function_signature
                report_data["selector"] = task.selector
                report_data["erc7730_format"] = task.erc7730_format
                report_data["descriptor_format_key"] = (task.descriptor_context or {}).get("format_key")
                report_data["abi_resolution"] = task.abi_resolution or {}

                # Enrich transaction samples with actual decoded data
                if "transaction_samples" in report_data and task.decoded_transactions:
                    for sample in report_data["transaction_samples"]:
                        tx_hash = sample.get("transaction_hash", "")
                        matching_tx = next((tx for tx in task.decoded_transactions if tx.get("hash") == tx_hash), None)
                        if matching_tx:
                            sample["native_value"] = matching_tx.get("value", "0")
                            sample["decoded_parameters"] = matching_tx.get("decoded_input", {})

                # Format using markdown_formatter
                from ..reporting.markdown_formatter import format_audit_reports

                critical_report, detailed_report = format_audit_reports(report_data)
                record_completed_analysis(task, report_data)

                return AuditResult(
                    selector=task.selector,
                    function_signature=task.function_signature,
                    critical_report=critical_report,
                    detailed_report=detailed_report,
                    report_data=report_data,
                    success=True,
                )

            except Exception as e:
                last_error = e
                error_type = type(e).__name__

                # Detailed error logging
                logger.error(f"[SINGLE] Attempt {attempt + 1} failed for {task.selector}")
                logger.error(f"[SINGLE]   Error Type: {error_type}")
                logger.error(f"[SINGLE]   Error Message: {e!s}")

                # Log additional details based on error type
                if hasattr(e, "status_code"):
                    logger.error(f"[SINGLE]   HTTP Status Code: {e.status_code}")
                if hasattr(e, "response"):
                    logger.error(f"[SINGLE]   Response: {e.response}")
                if hasattr(e, "body"):
                    logger.error(f"[SINGLE]   Response Body: {e.body}")

                # Log request details for debugging
                payload_size = len(user_payload) if user_payload else 0
                logger.error(f"[SINGLE]   Payload size: ~{payload_size:,} chars")
                logger.error(f"[SINGLE]   Model: {task.llm_model}")
                logger.error(f"[SINGLE]   Transactions in payload: {len(task.decoded_transactions or [])}")

                # Log stack trace for non-network errors
                import traceback

                if error_type not in ["ConnectionError", "Timeout", "TimeoutError", "APIConnectionError"]:
                    logger.error(f"[SINGLE]   Stack trace:\n{traceback.format_exc()}")

                # If this is not the last attempt, wait before retrying with exponential backoff
                if attempt < max_retries:
                    wait_time = min(2**attempt, 30)  # Exponential backoff, max 30s
                    logger.info(f"[SINGLE] Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    # All retries exhausted
                    logger.error(f"[SINGLE] ❌ All {max_retries + 1} attempts failed for {task.selector}")
                    logger.error(f"[SINGLE]   Final error: {error_type} - {e!s}")

        # If we get here, all retries failed
        error_msg = f"Error generating audit after {max_retries + 1} attempts: {last_error!s}"
        return AuditResult(
            selector=task.selector,
            function_signature=task.function_signature,
            critical_report=error_msg,
            detailed_report=error_msg,
            report_data={},
            success=False,
            error=str(last_error),
        )


async def generate_clear_signing_audits_batch_async(
    tasks: list[AuditTask], max_concurrent: int = 20, max_retries: int = 3
) -> list[AuditResult]:
    """
    Execute multiple audit API calls concurrently with retry logic.

    Args:
        tasks: List of pre-prepared AuditTasks
        max_concurrent: Maximum number of concurrent API calls (default: 20)
        max_retries: Maximum number of retry attempts per task (default: 3)

    Returns:
        List of AuditResults in the same order as input tasks
    """
    if not tasks:
        return []

    import time

    start_time = time.time()

    logger.info("[BATCH] ═══════════════════════════════════════════════════════")
    logger.info(f"[BATCH] Starting batch processing of {len(tasks)} audit tasks")
    logger.info(f"[BATCH] Max concurrent calls: {max_concurrent}")
    logger.info(f"[BATCH] Max retries per task: {max_retries}")
    logger.info("[BATCH] ═══════════════════════════════════════════════════════")

    # Use async context manager to properly manage client resources
    async with AsyncOpenAI() as client:
        semaphore = asyncio.Semaphore(max_concurrent)

        # Create coroutines for all tasks
        coroutines = [_run_task_with_selected_mode(task, client, semaphore, max_retries) for task in tasks]

        # Execute all concurrently and gather results
        results = await asyncio.gather(*coroutines, return_exceptions=True)

    # Convert any exceptions to AuditResult with error
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[BATCH] Task {i} raised unexpected exception: {result}")
            final_results.append(
                AuditResult(
                    selector=tasks[i].selector,
                    function_signature=tasks[i].function_signature,
                    critical_report=f"Error: {result!s}",
                    detailed_report=f"Error: {result!s}",
                    report_data={},
                    success=False,
                    error=str(result),
                )
            )
        else:
            final_results.append(result)

    # Log detailed summary
    elapsed_time = time.time() - start_time
    successful = sum(1 for r in final_results if r.success)
    failed = len(final_results) - successful

    logger.info("[BATCH] ═══════════════════════════════════════════════════════")
    logger.info(f"[BATCH] Batch processing completed in {elapsed_time:.1f}s")
    logger.info(f"[BATCH] ✅ Successful: {successful}/{len(tasks)} ({successful / len(tasks) * 100:.1f}%)")
    logger.info(f"[BATCH] ❌ Failed: {failed}/{len(tasks)} ({failed / len(tasks) * 100:.1f}%)")

    if successful > 0:
        logger.info(f"[BATCH] Average time per successful task: {elapsed_time / successful:.1f}s")

    if failed > 0:
        logger.warning("[BATCH] ⚠️  Failed selectors and errors:")
        for r in final_results:
            if not r.success:
                logger.warning(f"[BATCH]   • {r.selector}: {r.error}")

    logger.info("[BATCH] ═══════════════════════════════════════════════════════")

    return final_results


async def _run_task_with_selected_mode(
    task: AuditTask,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    max_retries: int,
) -> AuditResult:
    analysis_mode = task.analysis_mode or "single"
    if analysis_mode != "multi":
        return await generate_clear_signing_audit_async(task, client, semaphore, max_retries)

    tool_context = task.tool_context or {}
    max_rounds = int(tool_context.get("max_selector_tool_rounds", 2) or 2)
    max_requests_per_round = int(tool_context.get("max_tool_requests_per_round", 2) or 2)
    logger.info(
        "[BATCH] Using multi-agent mode for %s (rounds=%s, requests_per_round=%s)",
        task.selector,
        max_rounds,
        max_requests_per_round,
    )
    try:
        return await generate_multi_agent_audit_async(
            task,
            client,
            semaphore,
            max_retries=max_retries,
            max_rounds=max_rounds,
            max_requests_per_round=max_requests_per_round,
        )
    except Exception as exc:
        logger.exception(
            "[BATCH] Multi-agent mode failed for %s, falling back to single-pass: %s",
            task.selector,
            exc,
        )
        return await generate_clear_signing_audit_async(task, client, semaphore, max_retries)


def generate_clear_signing_audits_batch(
    tasks: list[AuditTask], max_concurrent: int = 20, max_retries: int = 3
) -> list[AuditResult]:
    """
    Synchronous wrapper for batch processing with retry logic.
    Runs the async batch function using asyncio.run().

    Args:
        tasks: List of pre-prepared AuditTasks
        max_concurrent: Maximum number of concurrent API calls (default: 20)
        max_retries: Maximum number of retry attempts per task (default: 3)

    Returns:
        List of AuditResults in the same order as input tasks
    """
    return asyncio.run(generate_clear_signing_audits_batch_async(tasks, max_concurrent, max_retries))
