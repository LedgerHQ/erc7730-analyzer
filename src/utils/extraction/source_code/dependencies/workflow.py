"""Dependency resolution workflow orchestrator."""

from typing import Any, Dict, Optional

from .enrichment import build_dependency_result
from .target import resolve_target_function


class SourceCodeDependencyMixin:
    def get_function_with_dependencies(
        self,
        function_name: str,
        extracted_code: Dict[str, Any],
        function_signature: Optional[str] = None,
        max_lines: int = 300,
        selector_only: bool = False,
        selector: Optional[str] = None,
    ) -> Dict[str, Any]:
        target_function, facet_specific_code, facet_addr, empty_result = resolve_target_function(
            self=self,
            function_name=function_name,
            extracted_code=extracted_code,
            function_signature=function_signature,
            selector_only=selector_only,
            selector=selector,
        )
        if empty_result is not None:
            return empty_result

        return build_dependency_result(
            self=self,
            extracted_code=extracted_code,
            target_function=target_function,
            facet_specific_code=facet_specific_code,
            facet_addr=facet_addr,
            max_lines=max_lines,
        )
