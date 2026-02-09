"""
Smart format specification optimizer for ERC-7730 audits.

Dynamically selects relevant sections from erc7730_format_reference.json
based on descriptor features to reduce token usage while maintaining
comprehensive coverage.

Note: This module ONLY optimizes erc7730_format_reference.json.
Other audit rule files (validation_rules.json, critical_issues.json)
should be loaded directly as they are always used in full.
"""

import json
import logging
from importlib import resources
from typing import Dict, Tuple

from .. import audit_rules
from .rules import (
    get_critical_issues,
    get_display_issues,
    get_recommendations,
    get_spec_limitations,
    get_validation_rules,
)

logger = logging.getLogger(__name__)


# Core sections always included in format reference
CORE_FORMAT_SECTIONS = [
    'path_syntax',
    'validation_notes',
    'xor_constraints',
    'special_paths',
    'alternative_field_value',
]

# Map format types to relevant rule sections in erc7730_format_reference.json
FORMAT_TYPE_SECTIONS = {
    'tokenAmount': [
        'format_types',
        'integer_formats',
        'address_formats',
        'container_values',
        'address_sources'
    ],
    'nftName': [
        'format_types',
        'address_formats',
        'address_types',
        'address_sources'
    ],
    'addressName': [
        'format_types',
        'address_formats',
        'address_types',
        'address_sources'
    ],
    'amount': [
        'format_types',
        'integer_formats'
    ],
    'percentage': [
        'format_types',
        'integer_formats'
    ],
    'date': [
        'format_types',
        'integer_formats'
    ],
    'duration': [
        'format_types',
        'integer_formats'
    ],
    'enum': [
        'format_types',
        'integer_formats',
        'string_formats'
    ],
    'unit': [
        'format_types',
        'integer_formats'
    ],
    'calldata': [
        'format_types',
        'bytes_formats',
        'type_casting'
    ],
    'raw': [
        'format_types',
        'type_casting'
    ]
}

# Map structural features to relevant sections
FEATURE_SECTIONS = {
    'has_arrays': ['array_indexing'],
    'has_nested_paths': ['special_paths'],  # Already in core, but emphasize
    'uses_containers': ['container_values'],
    'has_exclusions': [],  # No specific sections needed
    'uses_xor': ['xor_constraints'],  # Already in core
}

# Complexity threshold for fallback to full rules
COMPLEXITY_FALLBACK_THRESHOLD = 8


def _load_format_reference() -> Dict:
    """Load the ERC-7730 format reference JSON from package resources."""
    format_ref_path = resources.files(audit_rules).joinpath("erc7730_format_reference.json")
    return json.loads(format_ref_path.read_text(encoding="utf-8"))


def analyze_descriptor_features(erc7730_format: Dict) -> Dict:
    """
    Extract features from ERC-7730 descriptor for smart rule selection.

    Args:
        erc7730_format: The ERC-7730 format section (expanded with metadata/display)

    Returns:
        Dict containing:
        - format_types: Set of format type strings used
        - has_arrays: bool
        - has_nested_paths: bool
        - has_exclusions: bool
        - uses_containers: bool
        - uses_xor: bool
        - complexity_score: int (0-10)
    """
    features = {
        'format_types': set(),
        'has_arrays': False,
        'has_nested_paths': False,
        'has_exclusions': False,
        'uses_containers': False,
        'uses_xor': False,
        'complexity_score': 0
    }

    # Get the actual format definition
    format_def = erc7730_format.get('format', {})
    fields = format_def.get('fields', [])

    for field in fields:
        # Extract format types
        if 'format' in field:
            fmt = field['format']
            if isinstance(fmt, str):
                features['format_types'].add(fmt)
            elif isinstance(fmt, dict):
                # Handle nested format objects (e.g., {"tokenAmount": {...}})
                for key in fmt.keys():
                    features['format_types'].add(key)

        # Check path complexity
        path = field.get('path', '')
        if '[' in path or ']' in path:
            features['has_arrays'] = True
            features['complexity_score'] += 1

        if '.' in path:
            depth = path.count('.')
            if depth > 1:
                features['has_nested_paths'] = True
                features['complexity_score'] += 1

        # Check for container references ($)
        if '$' in path or ('$ref' in field):
            features['uses_containers'] = True
            features['complexity_score'] += 2

        # Check for XOR (alternative values)
        if 'value' in field and isinstance(field['value'], list):
            features['uses_xor'] = True
            features['complexity_score'] += 2

    # Check for exclusions
    if format_def.get('excluded'):
        features['has_exclusions'] = True
        features['complexity_score'] += 1

    # Cap complexity at 10
    features['complexity_score'] = min(features['complexity_score'], 10)

    # Log detected features
    logger.info(f"📊 Descriptor analysis:")
    logger.info(f"  - Format types: {sorted(features['format_types']) if features['format_types'] else 'none'}")
    logger.info(f"  - Complexity score: {features['complexity_score']}/10")

    detected_features = []
    if features['has_arrays']:
        detected_features.append('arrays')
    if features['has_nested_paths']:
        detected_features.append('nested paths')
    if features['has_exclusions']:
        detected_features.append('exclusions')
    if features['uses_containers']:
        detected_features.append('$ref containers')
    if features['uses_xor']:
        detected_features.append('XOR values')

    if detected_features:
        logger.info(f"  - Features detected: {', '.join(detected_features)}")
    else:
        logger.info(f"  - Features detected: none (simple descriptor)")

    return features


def load_optimized_format_spec(
    descriptor_features: Dict,
    use_smart_referencing: bool = True
) -> Tuple[Dict, Dict]:
    """
    Load optimized ERC-7730 format specification based on descriptor features.

    This function ONLY optimizes erc7730_format_reference.json. Other rule files
    should be loaded directly as they are always used in full.

    Args:
        descriptor_features: Output from analyze_descriptor_features()
        use_smart_referencing: If False, load full format spec

    Returns:
        Tuple of (format_spec_dict, metadata_dict) where:
        - format_spec_dict: Optimized or full format specification
        - metadata_dict: Info about what was included/excluded
    """
    # Load full format reference
    full_format_ref = _load_format_reference()

    # Check for fallback conditions
    complexity = descriptor_features['complexity_score']
    should_fallback = (
        not use_smart_referencing or
        complexity >= COMPLEXITY_FALLBACK_THRESHOLD
    )

    if should_fallback:
        reason = 'high_complexity' if complexity >= COMPLEXITY_FALLBACK_THRESHOLD else 'disabled'
        logger.info(
            f"Using FULL format spec (complexity={complexity}, "
            f"smart_ref={use_smart_referencing})"
        )
        return full_format_ref, {
            'mode': 'full',
            'reason': reason,
            'complexity': complexity
        }

    # Smart referencing: select relevant sections
    logger.info(
        f"Using SMART format spec (complexity={complexity}, "
        f"format_types={descriptor_features['format_types']})"
    )

    # Start with core sections
    sections_to_include = set(CORE_FORMAT_SECTIONS)
    logger.debug(f"  📋 Core sections: {sorted(CORE_FORMAT_SECTIONS)}")

    # Add format-type-specific sections
    format_type_sections_added = {}
    for fmt_type in descriptor_features['format_types']:
        if fmt_type in FORMAT_TYPE_SECTIONS:
            added_sections = FORMAT_TYPE_SECTIONS[fmt_type]
            sections_to_include.update(added_sections)
            format_type_sections_added[fmt_type] = sorted(added_sections)

    if format_type_sections_added:
        logger.info(f"  📦 Format-specific sections added:")
        for fmt_type, sections in format_type_sections_added.items():
            logger.info(f"    - {fmt_type}: {sections}")

    # Add feature-specific sections
    feature_sections_added = {}
    for feature, is_present in descriptor_features.items():
        if is_present and feature in FEATURE_SECTIONS:
            added_sections = FEATURE_SECTIONS[feature]
            sections_to_include.update(added_sections)
            feature_sections_added[feature] = sorted(added_sections)

    if feature_sections_added:
        logger.info(f"  🔧 Feature-specific sections added:")
        for feature, sections in feature_sections_added.items():
            logger.info(f"    - {feature}: {sections}")

    # Always include complete_examples if complexity >= 5
    if complexity >= 5:
        sections_to_include.add('complete_examples')
        logger.info(f"  ⚠️  High complexity ({complexity}), including complete_examples")

    # Filter to selected sections
    special_keys = {'title', 'description', 'version'}
    schema_keys = {k for k in full_format_ref.keys() if k.startswith('$')}
    available_sections = {
        k for k in full_format_ref.keys()
        if k not in schema_keys and k not in special_keys
    }
    included_section_names = available_sections & sections_to_include
    excluded_section_names = available_sections - included_section_names

    filtered_format_ref = {
        k: v for k, v in full_format_ref.items()
        if k in schema_keys or k in special_keys or k in included_section_names
    }

    # Calculate metadata
    total_sections = len(available_sections)
    included_sections = len(included_section_names)
    excluded_sections = len(excluded_section_names)
    reduction_percent = round((excluded_sections / total_sections) * 100, 1) if total_sections else 0.0

    metadata = {
        'mode': 'smart',
        'complexity': complexity,
        'format_types': sorted(descriptor_features['format_types']),
        'total_format_sections': total_sections,
        'included_format_sections': included_sections,
        'excluded_format_sections': excluded_sections,
        'reduction_percent': reduction_percent,
        'sections_included': sorted(included_section_names),
        'sections_excluded': sorted(excluded_section_names),
    }

    logger.info(
        f"Smart format spec: {included_sections}/{total_sections} sections "
        f"({metadata['reduction_percent']}% reduction)"
    )

    # Log detailed breakdown
    logger.info(f"  ✅ Included sections ({included_sections}): {sorted(sections_to_include)}")
    if metadata['sections_excluded']:
        logger.info(f"  ❌ Excluded sections ({excluded_sections}): {sorted(metadata['sections_excluded'])}")

    return filtered_format_ref, metadata


def load_relevant_rules(
    descriptor_features: Dict,
    use_smart_referencing: bool = True,
) -> Tuple[Dict, Dict]:
    """
    Backward-compatible wrapper returning optimized format rules + static rule sets.
    """
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


def format_optimization_note(metadata: Dict) -> str:
    """
    Format a note about format specification optimization for inclusion in prompt.

    Args:
        metadata: Metadata dict from load_optimized_format_spec()

    Returns:
        Formatted string to include in prompt
    """
    if metadata['mode'] == 'full':
        reason_text = {
            'high_complexity': f"descriptor complexity is high ({metadata['complexity']}/10)",
            'disabled': "smart referencing is disabled"
        }.get(metadata['reason'], metadata['reason'])

        return f"""
**📋 Format Specification: FULL**

All format specification sections included because {reason_text}.
"""

    # Smart mode
    format_types_text = ', '.join(sorted(metadata['format_types'])) if metadata['format_types'] else 'none'

    return f"""
**🎯 Format Specification: OPTIMIZED**

Based on descriptor features:
- Format types detected: {format_types_text}
- Complexity score: {metadata['complexity']}/10
- Format sections included: {metadata['included_format_sections']}/{metadata['total_format_sections']} ({100 - metadata['reduction_percent']:.0f}%)

Only format specification sections relevant to detected format types are included.
Validation rules and critical criteria are always loaded in full separately.
"""


def format_smart_rules_note(metadata: Dict) -> str:
    """Backward-compatible alias for optimization note formatting."""
    return format_optimization_note(metadata)
