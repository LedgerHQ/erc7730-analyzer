"""Task preparation and concurrent OpenAI audit execution."""

import asyncio
import json
import logging
from typing import Dict, List

from openai import AsyncOpenAI

from .models import AuditReport, AuditResult, AuditTask
from .rules import SYSTEM_INSTRUCTIONS

logger = logging.getLogger(__name__)
def prepare_audit_task(
    selector: str,
    decoded_transactions: List[Dict],
    erc7730_format: Dict,
    function_signature: str,
    source_code: Dict = None,
    use_smart_referencing: bool = True,
    erc4626_context: Dict = None,
    erc20_context: Dict = None,
    protocol_name: str = None
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
        "decoded_transactions": decoded_transactions if decoded_transactions else [],  # Empty list if no txs
        "source_code": source_code if source_code else {},  # Include ALL source code fields
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
        audit_payload=audit_payload,
        optimization_note=None  # Not needed anymore
    )


async def generate_clear_signing_audit_async(
    task: AuditTask,
    client: AsyncOpenAI,
    semaphore: asyncio.Semaphore,
    max_retries: int = 3
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
                    logger.info(f"[ASYNC] Starting API call for selector {task.selector}")
                else:
                    logger.warning(f"[ASYNC] Retry {attempt}/{max_retries} for selector {task.selector}")

                PROMPT_CACHE_KEY = "erc7730_audit_v1"

                # Deterministic JSON for user payload (ensures cache hits)
                user_payload = json.dumps(
                    task.audit_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False
                )

                response = await client.responses.parse(
                    model="gpt-5.2",
                    input=[
                        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": user_payload}
                    ],
                    text_format=AuditReport,
                    reasoning={"effort": "medium"},
                    text={"verbosity": "low"},
                    store=False,
                    prompt_cache_key=PROMPT_CACHE_KEY
                )

                # Log successful response with usage stats
                logger.info(f"[ASYNC] ✅ Received response for {task.selector}")
                if hasattr(response, 'usage') and response.usage:
                    usage = response.usage
                    # Extract cached tokens from input_tokens_details
                    cached_tokens = 0
                    if hasattr(usage, 'input_tokens_details') and usage.input_tokens_details:
                        cached_tokens = getattr(usage.input_tokens_details, 'cached_tokens', 0)

                    # Extract reasoning tokens from output_tokens_details
                    reasoning_tokens = 0
                    if hasattr(usage, 'output_tokens_details') and usage.output_tokens_details:
                        reasoning_tokens = getattr(usage.output_tokens_details, 'reasoning_tokens', 0)

                    logger.info(f"[ASYNC]   Input tokens: {getattr(usage, 'input_tokens', 0):,}")
                    logger.info(f"[ASYNC]   Cached tokens: {cached_tokens:,}")
                    logger.info(f"[ASYNC]   Output tokens: {getattr(usage, 'output_tokens', 0):,}")
                    if reasoning_tokens > 0:
                        logger.info(f"[ASYNC]   Reasoning tokens: {reasoning_tokens:,}")
                    logger.info(f"[ASYNC]   Total tokens: {getattr(usage, 'total_tokens', 0):,}")

                report_data = response.output_parsed.model_dump()

                # Force key identifiers back into the structured output
                report_data["function_signature"] = task.function_signature
                report_data["selector"] = task.selector
                report_data["erc7730_format"] = task.erc7730_format

                # Enrich transaction samples with actual decoded data
                if 'transaction_samples' in report_data and task.decoded_transactions:
                    for sample in report_data['transaction_samples']:
                        tx_hash = sample.get('transaction_hash', '')
                        matching_tx = next(
                            (tx for tx in task.decoded_transactions if tx.get('hash') == tx_hash),
                            None
                        )
                        if matching_tx:
                            sample['native_value'] = matching_tx.get('value', '0')
                            sample['decoded_parameters'] = matching_tx.get('decoded_input', {})

                # Format using markdown_formatter
                from ..reporting.markdown_formatter import format_audit_reports
                critical_report, detailed_report = format_audit_reports(report_data)

                return AuditResult(
                    selector=task.selector,
                    function_signature=task.function_signature,
                    critical_report=critical_report,
                    detailed_report=detailed_report,
                    report_data=report_data,
                    success=True
                )

            except Exception as e:
                last_error = e
                error_type = type(e).__name__

                # Detailed error logging
                logger.error(f"[ASYNC] Attempt {attempt + 1} failed for {task.selector}")
                logger.error(f"[ASYNC]   Error Type: {error_type}")
                logger.error(f"[ASYNC]   Error Message: {str(e)}")

                # Log additional details based on error type
                if hasattr(e, 'status_code'):
                    logger.error(f"[ASYNC]   HTTP Status Code: {e.status_code}")
                if hasattr(e, 'response'):
                    logger.error(f"[ASYNC]   Response: {e.response}")
                if hasattr(e, 'body'):
                    logger.error(f"[ASYNC]   Response Body: {e.body}")

                # Log request details for debugging
                payload_size = len(user_payload) if user_payload else 0
                logger.error(f"[ASYNC]   Payload size: ~{payload_size:,} chars")
                logger.error(f"[ASYNC]   Model: gpt-5.2")
                logger.error(f"[ASYNC]   Transactions in payload: {len(task.decoded_transactions or [])}")

                # Log stack trace for non-network errors
                import traceback
                if error_type not in ['ConnectionError', 'Timeout', 'TimeoutError', 'APIConnectionError']:
                    logger.error(f"[ASYNC]   Stack trace:\n{traceback.format_exc()}")

                # If this is not the last attempt, wait before retrying with exponential backoff
                if attempt < max_retries:
                    wait_time = min(2 ** attempt, 30)  # Exponential backoff, max 30s
                    logger.info(f"[ASYNC] Waiting {wait_time}s before retry...")
                    await asyncio.sleep(wait_time)
                else:
                    # All retries exhausted
                    logger.error(f"[ASYNC] ❌ All {max_retries + 1} attempts failed for {task.selector}")
                    logger.error(f"[ASYNC]   Final error: {error_type} - {str(e)}")

        # If we get here, all retries failed
        error_msg = f"Error generating audit after {max_retries + 1} attempts: {str(last_error)}"
        return AuditResult(
            selector=task.selector,
            function_signature=task.function_signature,
            critical_report=error_msg,
            detailed_report=error_msg,
            report_data={},
            success=False,
            error=str(last_error)
        )


async def generate_clear_signing_audits_batch_async(
    tasks: List[AuditTask],
    max_concurrent: int = 6,
    max_retries: int = 3
) -> List[AuditResult]:
    """
    Execute multiple audit API calls concurrently with retry logic.

    Args:
        tasks: List of pre-prepared AuditTasks
        max_concurrent: Maximum number of concurrent API calls (default: 10)
        max_retries: Maximum number of retry attempts per task (default: 3)

    Returns:
        List of AuditResults in the same order as input tasks
    """
    if not tasks:
        return []

    import time
    start_time = time.time()

    logger.info(f"[BATCH] ═══════════════════════════════════════════════════════")
    logger.info(f"[BATCH] Starting batch processing of {len(tasks)} audit tasks")
    logger.info(f"[BATCH] Max concurrent calls: {max_concurrent}")
    logger.info(f"[BATCH] Max retries per task: {max_retries}")
    logger.info(f"[BATCH] ═══════════════════════════════════════════════════════")

    # Use async context manager to properly manage client resources
    async with AsyncOpenAI() as client:
        semaphore = asyncio.Semaphore(max_concurrent)

        # Create coroutines for all tasks
        coroutines = [
            generate_clear_signing_audit_async(task, client, semaphore, max_retries)
            for task in tasks
        ]

        # Execute all concurrently and gather results
        results = await asyncio.gather(*coroutines, return_exceptions=True)

    # Convert any exceptions to AuditResult with error
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[BATCH] Task {i} raised unexpected exception: {result}")
            final_results.append(AuditResult(
                selector=tasks[i].selector,
                function_signature=tasks[i].function_signature,
                critical_report=f"Error: {str(result)}",
                detailed_report=f"Error: {str(result)}",
                report_data={},
                success=False,
                error=str(result)
            ))
        else:
            final_results.append(result)

    # Log detailed summary
    elapsed_time = time.time() - start_time
    successful = sum(1 for r in final_results if r.success)
    failed = len(final_results) - successful

    logger.info(f"[BATCH] ═══════════════════════════════════════════════════════")
    logger.info(f"[BATCH] Batch processing completed in {elapsed_time:.1f}s")
    logger.info(f"[BATCH] ✅ Successful: {successful}/{len(tasks)} ({successful/len(tasks)*100:.1f}%)")
    logger.info(f"[BATCH] ❌ Failed: {failed}/{len(tasks)} ({failed/len(tasks)*100:.1f}%)")

    if successful > 0:
        logger.info(f"[BATCH] Average time per successful task: {elapsed_time/successful:.1f}s")

    if failed > 0:
        logger.warning(f"[BATCH] ⚠️  Failed selectors and errors:")
        for r in final_results:
            if not r.success:
                logger.warning(f"[BATCH]   • {r.selector}: {r.error}")

    logger.info(f"[BATCH] ═══════════════════════════════════════════════════════")

    return final_results


def generate_clear_signing_audits_batch(
    tasks: List[AuditTask],
    max_concurrent: int = 6,
    max_retries: int = 3
) -> List[AuditResult]:
    """
    Synchronous wrapper for batch processing with retry logic.
    Runs the async batch function using asyncio.run().

    Args:
        tasks: List of pre-prepared AuditTasks
        max_concurrent: Maximum number of concurrent API calls (default: 10)
        max_retries: Maximum number of retry attempts per task (default: 3)

    Returns:
        List of AuditResults in the same order as input tasks
    """
    return asyncio.run(generate_clear_signing_audits_batch_async(tasks, max_concurrent, max_retries))
