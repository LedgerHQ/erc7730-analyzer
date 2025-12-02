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
from pathlib import Path
from typing import Dict, Tuple

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
    rules_path = Path(__file__).parent / "audit_rules"
    format_ref_path = rules_path / 'erc7730_format_reference.json'

    # Load full format reference
    with open(format_ref_path, 'r') as f:
        full_format_ref = json.load(f)

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

    # Add format-type-specific sections
    for fmt_type in descriptor_features['format_types']:
        if fmt_type in FORMAT_TYPE_SECTIONS:
            sections_to_include.update(FORMAT_TYPE_SECTIONS[fmt_type])

    # Add feature-specific sections
    for feature, is_present in descriptor_features.items():
        if is_present and feature in FEATURE_SECTIONS:
            sections_to_include.update(FEATURE_SECTIONS[feature])

    # Always include complete_examples if complexity >= 5
    if complexity >= 5:
        sections_to_include.add('complete_examples')

    # Filter to selected sections
    filtered_format_ref = {
        k: v for k, v in full_format_ref.items()
        if k.startswith('$') or k in ['title', 'description', 'version'] or k in sections_to_include
    }

    # Calculate metadata
    total_sections = len([
        k for k in full_format_ref.keys()
        if not k.startswith('$') and k not in ['title', 'description', 'version']
    ])
    included_sections = len(sections_to_include)
    excluded_sections = total_sections - included_sections

    metadata = {
        'mode': 'smart',
        'complexity': complexity,
        'format_types': list(descriptor_features['format_types']),
        'total_format_sections': total_sections,
        'included_format_sections': included_sections,
        'excluded_format_sections': excluded_sections,
        'reduction_percent': round((excluded_sections / total_sections) * 100, 1),
        'sections_included': list(sections_to_include),
        'sections_excluded': list(
            set(full_format_ref.keys()) - set(filtered_format_ref.keys()) -
            {'$schema', 'title', 'description', 'version'}
        )
    }

    logger.info(
        f"Smart format spec: {included_sections}/{total_sections} sections "
        f"({metadata['reduction_percent']}% reduction)"
    )

    return filtered_format_ref, metadata


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
