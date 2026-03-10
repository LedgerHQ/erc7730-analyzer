"""Task preparation and concurrent LLM audit execution."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import traceback

from ..llm import LLMClient, LLMConfig
from .models import AuditReport, AuditResult, AuditTask
from .rules import SYSTEM_INSTRUCTIONS


def _progress(msg: str, end: str = "\n") -> None:
    """Write a progress line to stderr."""
    sys.stderr.write(msg + end)
    sys.stderr.flush()


logger = logging.getLogger(__name__)


def prepare_audit_task(
    selector: str,
    decoded_transactions: list[dict],
    erc7730_format: dict,
    function_signature: str,
    source_code: dict | None = None,
    use_smart_referencing: bool = True,
    erc4626_context: dict | None = None,
    erc20_context: dict | None = None,
    protocol_name: str | None = None,
) -> AuditTask:
    """
    Prepare an audit task with ONLY dynamic data for optimal prompt caching.
    Static rules are in SYSTEM_INSTRUCTIONS and cached by the LLM backend.

    Args:
        selector: Function selector
        decoded_transactions: List of decoded transactions with receipt logs
        erc7730_format: ERC-7730 format definition for this selector
        function_signature: Function signature
        source_code: Optional dictionary with extracted source code
        use_smart_referencing: Whether to use smart rule referencing
        erc4626_context: Optional ERC4626 vault context
        erc20_context: Optional ERC20 token context
        protocol_name: Optional protocol name from descriptor ($id, owner, or legalname)

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
        "decoded_transactions": decoded_transactions if decoded_transactions else [],
        "source_code": source_code if source_code else {},
        "erc4626_context": erc4626_context if erc4626_context else {},
        "erc20_context": erc20_context if erc20_context else {},
    }

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
        audit_payload=audit_payload,
        optimization_note=None,
    )


async def generate_clear_signing_audit_async(
    task: AuditTask,
    llm_client: LLMClient,
    semaphore: asyncio.Semaphore,
    max_retries: int = 3,
    task_index: int = 0,
    total_tasks: int = 1,
) -> AuditResult:
    """
    Async audit of a single selector with retry logic.
    Uses a semaphore to limit concurrent API calls.

    Args:
        task: Pre-prepared AuditTask with payload
        llm_client: LLMClient configured for the chosen backend
        semaphore: Semaphore to limit concurrency
        max_retries: Maximum number of retry attempts (default: 3)
        task_index: 0-based index of this task in the batch
        total_tasks: Total number of tasks in the batch

    Returns:
        AuditResult with the API response or error
    """
    label = f"[{task_index + 1}/{total_tasks}]"

    async with semaphore:
        last_error = None

        for attempt in range(max_retries + 1):
            user_payload = ""
            try:
                if attempt == 0:
                    _progress(f"      {label} Auditing {task.function_signature}...")
                    logger.info(f"[ASYNC] Starting API call for selector {task.selector}")
                else:
                    _progress(f"      {label} Retry {attempt}/{max_retries} for {task.function_signature}...")
                    logger.warning(f"[ASYNC] Retry {attempt}/{max_retries} for selector {task.selector}")

                user_payload = json.dumps(
                    task.audit_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )

                report: AuditReport = await llm_client.invoke(
                    system_prompt=SYSTEM_INSTRUCTIONS,
                    user_content=user_payload,
                    output_schema=AuditReport,
                )

                _progress(f"      {label} Done.")
                logger.info(f"[ASYNC] Received response for {task.selector}")

                report_data = report.model_dump()

                # Force key identifiers back into the structured output
                report_data["function_signature"] = task.function_signature
                report_data["selector"] = task.selector
                report_data["erc7730_format"] = task.erc7730_format

                # Enrich transaction samples with actual decoded data
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

                logger.error(f"[ASYNC] Attempt {attempt + 1} failed for {task.selector}")
                logger.error(f"[ASYNC]   Error Type: {error_type}")
                logger.error(f"[ASYNC]   Error Message: {e!s}")

                if hasattr(e, "status_code"):
                    logger.error(f"[ASYNC]   HTTP Status Code: {e.status_code}")
                if hasattr(e, "response"):
                    logger.error(f"[ASYNC]   Response: {e.response}")
                if hasattr(e, "body"):
                    logger.error(f"[ASYNC]   Response Body: {e.body}")

                payload_size = len(user_payload) if user_payload else 0
                logger.error(f"[ASYNC]   Payload size: ~{payload_size:,} chars")
                logger.error(f"[ASYNC]   Backend: {llm_client.config.backend} ({llm_client.config.model})")
                logger.error(f"[ASYNC]   Transactions in payload: {len(task.decoded_transactions or [])}")

                if error_type not in ("ConnectionError", "Timeout", "TimeoutError", "APIConnectionError"):
                    logger.error(f"[ASYNC]   Stack trace:\n{traceback.format_exc()}")

                if attempt < max_retries:
                    wait_time = min(2**attempt, 30)
                    logger.info(f"[ASYNC] Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    _progress(f"      {label} Failed ({error_type}).")
                    logger.error(f"[ASYNC] All {max_retries + 1} attempts failed for {task.selector}")
                    logger.error(f"[ASYNC]   Final error: {error_type} - {e!s}")

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
    tasks: list[AuditTask],
    llm_config: LLMConfig | None = None,
    max_concurrent: int = 6,
    max_retries: int = 3,
) -> list[AuditResult]:
    """
    Execute multiple audit API calls concurrently with retry logic.

    Args:
        tasks: List of pre-prepared AuditTasks
        llm_config: LLM backend configuration (defaults to OpenAI if None)
        max_concurrent: Maximum number of concurrent API calls
        max_retries: Maximum number of retry attempts per task

    Returns:
        List of AuditResults in the same order as input tasks
    """
    if not tasks:
        return []

    start_time = time.time()

    if llm_config is None:
        llm_config = LLMConfig().resolve()

    llm_client = LLMClient(llm_config)

    # Cursor backend spawns heavy subprocesses; cap concurrency to 1 to avoid
    # overwhelming the system with multiple large prompts simultaneously.
    if llm_config.backend == "cursor":
        max_concurrent = min(max_concurrent, 1)

    logger.info("[BATCH] ═══════════════════════════════════════════════════════")
    logger.info(f"[BATCH] Starting batch processing of {len(tasks)} audit tasks")
    logger.info(f"[BATCH] Backend: {llm_config.backend} (model: {llm_config.model})")
    logger.info(f"[BATCH] Max concurrent calls: {max_concurrent}")
    logger.info(f"[BATCH] Max retries per task: {max_retries}")
    logger.info("[BATCH] ═══════════════════════════════════════════════════════")

    semaphore = asyncio.Semaphore(max_concurrent)

    total = len(tasks)
    coroutines = [
        generate_clear_signing_audit_async(
            task,
            llm_client,
            semaphore,
            max_retries,
            task_index=i,
            total_tasks=total,
        )
        for i, task in enumerate(tasks)
    ]

    results = await asyncio.gather(*coroutines, return_exceptions=True)

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

    elapsed_time = time.time() - start_time
    successful = sum(1 for r in final_results if r.success)
    failed = len(final_results) - successful

    _progress(f"      Audits finished: {successful} ok, {failed} failed ({elapsed_time:.1f}s)")

    logger.info("[BATCH] ═══════════════════════════════════════════════════════")
    logger.info(f"[BATCH] Batch processing completed in {elapsed_time:.1f}s")
    logger.info(f"[BATCH] Successful: {successful}/{len(tasks)} ({successful / len(tasks) * 100:.1f}%)")
    logger.info(f"[BATCH] Failed: {failed}/{len(tasks)} ({failed / len(tasks) * 100:.1f}%)")

    if successful > 0:
        logger.info(f"[BATCH] Average time per successful task: {elapsed_time / successful:.1f}s")

    if failed > 0:
        logger.warning("[BATCH] Failed selectors and errors:")
        for r in final_results:
            if not r.success:
                _progress(f"        - {r.selector}: {r.error}")
                logger.warning(f"[BATCH]   {r.selector}: {r.error}")

    logger.info("[BATCH] ═══════════════════════════════════════════════════════")

    return final_results


def generate_clear_signing_audits_batch(
    tasks: list[AuditTask],
    llm_config: LLMConfig | None = None,
    max_concurrent: int = 6,
    max_retries: int = 3,
) -> list[AuditResult]:
    """
    Synchronous wrapper for batch processing with retry logic.
    Runs the async batch function using asyncio.run().

    Args:
        tasks: List of pre-prepared AuditTasks
        llm_config: LLM backend configuration (defaults to OpenAI if None)
        max_concurrent: Maximum number of concurrent API calls
        max_retries: Maximum number of retry attempts per task

    Returns:
        List of AuditResults in the same order as input tasks
    """
    return asyncio.run(generate_clear_signing_audits_batch_async(tasks, llm_config, max_concurrent, max_retries))
