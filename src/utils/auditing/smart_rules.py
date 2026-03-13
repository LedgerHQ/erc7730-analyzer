"""
Smart format specification optimizer for ERC-7730 audits.

The optimizer only trims the static format reference. Validation, critical issue,
recommendation, limitation, and display issue rule sets are always loaded in full.
"""

import json
import logging
from collections.abc import Iterable
from typing import Any

from .rules import (
    get_critical_issues,
    get_display_issues,
    get_recommendations,
    get_spec_limitations,
    get_validation_rules,
    read_rule,
)

logger = logging.getLogger(__name__)

CORE_FORMAT_SECTIONS = [
    "overview",
    "path_syntax",
    "display_format_keys",
    "display_structure",
    "visible_semantics",
    "xor_constraints",
    "validation_notes",
    "container_values",
]

FORMAT_TYPE_SECTIONS = {
    "raw": ["format_types"],
    "amount": ["format_types", "container_values"],
    "tokenAmount": ["format_types", "map_references"],
    "nftName": ["format_types"],
    "addressName": ["format_types", "address_sources", "address_types"],
    "interoperableAddressName": ["format_types", "address_sources", "address_types"],
    "tokenTicker": ["format_types"],
    "date": ["format_types"],
    "duration": ["format_types"],
    "unit": ["format_types"],
    "enum": ["format_types", "metadata_section"],
    "chainId": ["format_types", "container_values"],
    "calldata": ["format_types", "map_references", "display_format_keys", "container_values"],
}

FEATURE_SECTIONS = {
    "has_arrays": ["field_structures"],
    "has_nested_paths": ["field_structures"],
    "has_field_groups": ["field_structures"],
    "uses_containers": ["container_values"],
    "uses_maps": ["map_references", "metadata_section"],
    "uses_visibility": ["visible_semantics"],
    "uses_interpolated_intent": ["display_structure"],
    "uses_encryption": ["encrypted_fields", "field_structures"],
}

COMPLEXITY_FALLBACK_THRESHOLD = 8


def _load_format_reference() -> dict:
    return json.loads(read_rule("erc7730_format_reference.json"))


def _extract_format_definition(erc7730_format: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(erc7730_format, dict):
        return {}

    if "display" in erc7730_format:
        formats = erc7730_format.get("display", {}).get("formats", {})
        if isinstance(formats, dict) and formats:
            return next(iter(formats.values()))

    if "format" in erc7730_format and isinstance(erc7730_format["format"], dict):
        return erc7730_format["format"]

    return erc7730_format


def _iter_field_nodes(fields: Iterable[Any]) -> Iterable[dict[str, Any]]:
    for field in fields or []:
        if not isinstance(field, dict):
            continue
        yield field
        nested_fields = field.get("fields")
        if isinstance(nested_fields, list):
            yield from _iter_field_nodes(nested_fields)


def _contains_container_reference(value: Any) -> bool:
    if isinstance(value, str):
        return "@." in value
    if isinstance(value, dict):
        return any(_contains_container_reference(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_container_reference(v) for v in value)
    return False


def _contains_map_reference(value: Any) -> bool:
    if isinstance(value, dict):
        if "map" in value:
            return True
        return any(_contains_map_reference(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_map_reference(v) for v in value)
    if isinstance(value, str):
        return "$.metadata.maps." in value
    return False


def analyze_descriptor_features(erc7730_format: dict) -> dict:
    format_def = _extract_format_definition(erc7730_format)
    fields = format_def.get("fields", []) if isinstance(format_def, dict) else []

    features = {
        "format_types": set(),
        "has_arrays": False,
        "has_nested_paths": False,
        "has_field_groups": False,
        "uses_containers": False,
        "uses_maps": False,
        "uses_visibility": False,
        "uses_interpolated_intent": bool(format_def.get("interpolatedIntent"))
        if isinstance(format_def, dict)
        else False,
        "uses_encryption": False,
        "complexity_score": 0,
    }

    for field in _iter_field_nodes(fields):
        fmt = field.get("format")
        if isinstance(fmt, str):
            features["format_types"].add(fmt)

        path = field.get("path", "")
        if isinstance(path, str):
            if "[" in path or "]" in path:
                features["has_arrays"] = True
            if path.startswith("@.") or _contains_container_reference(path):
                features["uses_containers"] = True
            stripped = path[2:] if path.startswith("#.") else path
            if "." in stripped:
                features["has_nested_paths"] = True

        if "visible" in field:
            features["uses_visibility"] = True

        if "encryption" in field:
            features["uses_encryption"] = True

        if isinstance(field.get("fields"), list):
            features["has_field_groups"] = True

        params = field.get("params")
        if _contains_map_reference(params) or _contains_map_reference(field):
            features["uses_maps"] = True
        if _contains_container_reference(params):
            features["uses_containers"] = True

    metadata = erc7730_format.get("metadata", {}) if isinstance(erc7730_format, dict) else {}
    if isinstance(metadata, dict) and metadata.get("maps"):
        features["uses_maps"] = True

    complexity_weights = {
        "has_arrays": 1,
        "has_nested_paths": 1,
        "has_field_groups": 2,
        "uses_containers": 1,
        "uses_maps": 2,
        "uses_visibility": 1,
        "uses_interpolated_intent": 1,
        "uses_encryption": 2,
    }
    features["complexity_score"] = min(
        10,
        len(features["format_types"])
        + sum(weight for feature, weight in complexity_weights.items() if features[feature]),
    )

    logger.info("📊 Descriptor analysis:")
    logger.info(
        "  - Format types: %s",
        sorted(features["format_types"]) if features["format_types"] else "none",
    )
    logger.info("  - Complexity score: %s/10", features["complexity_score"])

    detected_features = [
        feature.replace("_", " ")
        for feature in (
            "has_arrays",
            "has_nested_paths",
            "has_field_groups",
            "uses_containers",
            "uses_maps",
            "uses_visibility",
            "uses_interpolated_intent",
            "uses_encryption",
        )
        if features[feature]
    ]
    logger.info(
        "  - Features detected: %s",
        ", ".join(detected_features) if detected_features else "none (simple descriptor)",
    )

    return features


def load_optimized_format_spec(
    descriptor_features: dict,
    use_smart_referencing: bool = True,
) -> tuple[dict, dict]:
    full_format_ref = _load_format_reference()
    complexity = descriptor_features["complexity_score"]
    should_fallback = not use_smart_referencing or complexity >= COMPLEXITY_FALLBACK_THRESHOLD

    if should_fallback:
        reason = "high_complexity" if complexity >= COMPLEXITY_FALLBACK_THRESHOLD else "disabled"
        logger.info(
            "Using FULL format spec (complexity=%s, smart_ref=%s)",
            complexity,
            use_smart_referencing,
        )
        return full_format_ref, {
            "mode": "full",
            "reason": reason,
            "complexity": complexity,
        }

    sections_to_include = set(CORE_FORMAT_SECTIONS)
    for fmt_type in descriptor_features["format_types"]:
        sections_to_include.update(FORMAT_TYPE_SECTIONS.get(fmt_type, ["format_types"]))

    for feature, section_names in FEATURE_SECTIONS.items():
        if descriptor_features.get(feature):
            sections_to_include.update(section_names)

    if complexity >= 5:
        sections_to_include.add("complete_examples")

    special_keys = {"$schema", "title", "description", "version"}
    available_sections = {key for key in full_format_ref if key not in special_keys}
    included_section_names = available_sections & sections_to_include
    excluded_section_names = available_sections - included_section_names

    filtered_format_ref = {
        key: value for key, value in full_format_ref.items() if key in special_keys or key in included_section_names
    }

    metadata = {
        "mode": "smart",
        "complexity": complexity,
        "format_types": sorted(descriptor_features["format_types"]),
        "total_format_sections": len(available_sections),
        "included_format_sections": len(included_section_names),
        "excluded_format_sections": len(excluded_section_names),
        "reduction_percent": round((len(excluded_section_names) / len(available_sections)) * 100, 1)
        if available_sections
        else 0.0,
        "sections_included": sorted(included_section_names),
        "sections_excluded": sorted(excluded_section_names),
    }

    logger.info(
        "Smart format spec: %s/%s sections (%s%% reduction)",
        metadata["included_format_sections"],
        metadata["total_format_sections"],
        metadata["reduction_percent"],
    )
    return filtered_format_ref, metadata


def load_relevant_rules(
    descriptor_features: dict,
    use_smart_referencing: bool = True,
) -> tuple[dict, dict]:
    format_spec, metadata = load_optimized_format_spec(
        descriptor_features,
        use_smart_referencing=use_smart_referencing,
    )
    rules_dict = {
        "erc7730_format_reference": format_spec,
        "validation_rules": get_validation_rules(),
        "critical_issues": get_critical_issues(),
        "recommendations": get_recommendations(),
        "spec_limitations": get_spec_limitations(),
        "display_issues": get_display_issues(),
    }
    return rules_dict, metadata


def format_optimization_note(metadata: dict) -> str:
    if metadata["mode"] == "full":
        reason_text = {
            "high_complexity": f"descriptor complexity is high ({metadata['complexity']}/10)",
            "disabled": "smart referencing is disabled",
        }.get(metadata["reason"], metadata["reason"])
        return f"""
**📋 Format Specification: FULL**

All format reference sections are included because {reason_text}.
"""

    format_types_text = ", ".join(sorted(metadata["format_types"])) if metadata["format_types"] else "none"
    return f"""
**🎯 Format Specification: OPTIMIZED**

Based on descriptor features:
- Format types detected: {format_types_text}
- Complexity score: {metadata["complexity"]}/10
- Format sections included: {metadata["included_format_sections"]}/{metadata["total_format_sections"]} ({100 - metadata["reduction_percent"]:.0f}%)

Only the relevant v2 format-reference sections are included. Validation, critical issue, recommendation, limitation, and display issue rule sets are still loaded in full.
"""


def format_smart_rules_note(metadata: dict) -> str:
    return format_optimization_note(metadata)
