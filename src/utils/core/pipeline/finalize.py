"""Pipeline stage: attach audit results to selector output structure."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class AnalyzerPipelineFinalizeMixin:
    def _finalize_results(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Merge prepared selector data and audit output into final results."""
        prepared_selectors = context['prepared_selectors']
        audit_results_map = context['audit_results_map']
        results = context['results']
        # ====================================================================
        # PHASE 3: POST-PROCESSING (Sequential - maintains log coherence)
        # ====================================================================
        # Process results in order, logging each report to maintain coherent output.

        logger.info(f"\n{'='*60}")
        logger.info(f"PHASE 3: Processing results for {len(prepared_selectors)} selectors...")
        logger.info(f"{'='*60}")

        for prepared in prepared_selectors:
            selector = prepared['selector']
            function_name = prepared['function_name']
            function_data = prepared['function_data']
            selector_deployment = prepared['selector_deployment']
            decoded_txs = prepared['decoded_txs']
            erc7730_format = prepared['erc7730_format']
            function_source = prepared['function_source']

            logger.info(f"\n{'='*60}")
            logger.info(f"Processing results for: {selector} ({function_name})")
            logger.info(f"{'='*60}")

            # Get the audit result for this selector
            audit_result = audit_results_map.get(selector)

            audit_report_critical = None
            audit_report_detailed = None
            audit_report_json = {}

            if audit_result:
                audit_report_critical = audit_result.critical_report
                audit_report_detailed = audit_result.detailed_report
                audit_report_json = audit_result.report_data

                if audit_result.success:
                    logger.info(f"\nCritical Report:\n{audit_report_critical}\n")
                    logger.info(f"\nDetailed Report:\n{audit_report_detailed}\n")
                else:
                    logger.error(f"Audit failed for {selector}: {audit_result.error}")
            else:
                logger.warning(f"No audit result found for selector {selector}")

            # Store results
            results['selectors'][selector] = {
                'function_name': function_name,
                'function_signature': function_data['signature'],
                'contract_address': selector_deployment['address'],
                'chain_id': selector_deployment['chainId'],
                'transactions': decoded_txs,
                'erc7730_format': erc7730_format,
                'audit_report_critical': audit_report_critical,
                'audit_report_detailed': audit_report_detailed,
                'audit_report_json': audit_report_json,
                'source_code': function_source  # Store source code for reports
            }

        logger.info(f"\n{'='*60}")
        logger.info(f"PHASE 3 COMPLETE: All results processed")
        logger.info(f"{'='*60}")

        logger.info(f"\n{'='*60}")
        logger.info("Analysis complete!")
        logger.info(f"{'='*60}")

        return results
