#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit (GTTK)
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2026, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
Validation Engine for GTTK Validation Package.

This module provides the core ValidationEngine class that evaluates validation
rules against GeoTIFF metadata, producing structured results with descriptive
messages.

Classes:
    ValidationEngine: Core validation engine that evaluates rules against metadata
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from gttk.utils.metadata_extractor import MetadataExtractor

from gttk.utils.validation.models import (
    ValidationRule,
    ValidationResult,
    ValidationStatus,
    get_missing_key_message,
    get_section_missing_message,
)
from gttk.utils.validation.constraints import (
    validate_exact,
    validate_enum,
    validate_regex,
    validate_range,
    validate_ranges,
    validate_exists,
    validate_forbidden,
    validate_data_type,
)
from gttk.utils.validation.extractors import ValueExtractor

logger = logging.getLogger(__name__)

# Capitalized key field types for messages
KEY_FIELD_CAPS = {
    'tag': 'Tag',
    'geokey': 'GeoKey',
    'name': 'Name',
    'xpath': 'XPath',
    'jsonpath': 'JSONPath'
}

class ValidationEngine:
    """
    Core validation engine that evaluates rules against GeoTIFF metadata.

    The engine extracts values from GeoTIFF files using the ValueExtractor,
    applies constraint validation, and produces structured ValidationResult
    objects with descriptive messages.

    Attributes:
        extractor: MetadataExtractor instance with open file handles
        value_extractor: ValueExtractor for retrieving values by key

    Example:
        >>> from gttk.utils.metadata_extractor import MetadataExtractor
        >>> rule = ValidationRule(
        ...     product='DGED5', section='tag', key='258', key_type='Tag',
        ...     description='BitsPerSample', data_type='integer',
        ...     constraint='exact', expected=32
        ... )
        >>> with MetadataExtractor('example.tif') as extractor:
        ...     engine = ValidationEngine(extractor)
        ...     results = engine.validate_all_sections({'tag': [rule]})
        ...     for section, section_results in results.items():
        ...         for result in section_results:
        ...             print(f"{result.status}: {result.message}")
        PASS: Tag 258 value matches expected value: 32
    """

    def __init__(self, extractor: "MetadataExtractor") -> None:
        """
        Initialize the ValidationEngine.

        Args:
            extractor: MetadataExtractor instance with open file handles
        """
        self.extractor = extractor
        self.value_extractor = ValueExtractor(extractor)

    def validate_all_sections(
        self,
        rules_by_section: Dict[str, List[ValidationRule]]
    ) -> Dict[str, List[ValidationResult]]:
        """
        Validate all sections with rules.

        Args:
            rules_by_section: Dict mapping section names to rule lists

        Returns:
            Dict mapping section names to ValidationResult lists
        """
        results_by_section: Dict[str, List[ValidationResult]] = {}

        for section, rules in rules_by_section.items():
            section_results = self.validate_section(section, rules)
            results_by_section[section] = section_results

        return results_by_section

    def validate_section(
        self,
        section_type: str,
        rules: List[ValidationRule]
    ) -> List[ValidationResult]:
        """
        Validate a section's rules.

        Returns results for ALL rules, even if the entire section is missing.
        This ensures complete audit trails in validation reports.

        Args:
            section_type: The type of section ('tag', 'geokey', 'gdal', etc.)
            rules: List of ValidationRule objects for this section

        Returns:
            List of ValidationResult objects, one per rule
        """
        results = []

        # Try to get section content
        section_content = self.value_extractor.get_section_content(section_type)

        if section_content is None:
            # Entire section is missing - fail all required rules with section-level message
            section_missing_msg = get_section_missing_message(section_type)

            for rule in rules:
                if rule.constraint == 'forbidden':
                    # Forbidden field correctly absent when section missing
                    result = ValidationResult(
                        rule=rule,
                        value=None,
                        status=ValidationStatus.PASS.value,
                        message=f"{rule.key_type} {rule.key} ({rule.description}) is correctly absent"
                    )
                elif rule.optional:
                    # Optional field - skip
                    result = ValidationResult(
                        rule=rule,
                        value=None,
                        status=ValidationStatus.SKIP.value,
                        message=section_missing_msg
                    )
                else:
                    # Required field - fail
                    result = ValidationResult(
                        rule=rule,
                        value=None,
                        status=ValidationStatus.FAIL.value,
                        message=section_missing_msg
                    )
                results.append(result)

            return results

        # Section exists - validate each rule individually
        for rule in rules:
            result = self.validate_rule(rule)
            results.append(result)

        return results

    def validate_rule(self, rule: ValidationRule) -> ValidationResult:
        """
        Validate a single rule against the GeoTIFF metadata.

        Args:
            rule: The ValidationRule to evaluate

        Returns:
            ValidationResult with appropriate status and message
        """
        # Extract value for this rule
        value = self.value_extractor.extract_value(rule.section, rule.key)

        # Handle missing value cases
        if value is None:
            return self._handle_missing_value(rule)

        # For extended data types (date, datetime, url, email), validate format first
        extended_types = ['date', 'datetime', 'url', 'email']
        if rule.data_type in extended_types:
            type_valid, type_error = validate_data_type(value, rule.data_type)
            if not type_valid:
                return ValidationResult(
                    rule=rule,
                    value=value,
                    status=ValidationStatus.FAIL.value,
                    message=type_error or f"Value does not match expected data type: {rule.data_type}"
                )

        # Value exists and passes type check - apply constraint validation
        passed, message = self._apply_constraint(value, rule)

        return ValidationResult(
            rule=rule,
            value=value,
            status=ValidationStatus.PASS.value if passed else ValidationStatus.FAIL.value,
            message=message
        )

    def _handle_missing_value(self, rule: ValidationRule) -> ValidationResult:
        """
        Handle the case where a value is missing (None).

        Args:
            rule: The ValidationRule for the missing value

        Returns:
            ValidationResult with appropriate status for missing value
        """
        if rule.constraint == 'forbidden':
            # Missing is good for forbidden fields
            return ValidationResult(
                rule=rule,
                value=None,
                status=ValidationStatus.PASS.value,
                message=f"{rule.key_type} {rule.key} ({rule.description}) is correctly absent"
            )
        elif rule.optional:
            # Missing is OK for optional fields
            return ValidationResult(
                rule=rule,
                value=None,
                status=ValidationStatus.SKIP.value,
                message=f"Optional {rule.key_type} {rule.key} ({rule.description}) is not present"
            )
        else:
            # Missing is FAIL for required fields
            return ValidationResult(
                rule=rule,
                value=None,
                status=ValidationStatus.FAIL.value,
                message=get_missing_key_message(rule)
            )

    def _apply_constraint(
        self,
        value: Any,
        rule: ValidationRule
    ) -> Tuple[bool, str]:
        """
        Apply constraint validation and generate a descriptive message.

        Args:
            value: The actual value from the GeoTIFF
            rule: The ValidationRule to apply

        Returns:
            Tuple of (passed: bool, message: str)
        """
        constraint = rule.constraint
        key_type = KEY_FIELD_CAPS.get(rule.key_type, rule.key_type)
        key = rule.key
        description = rule.description
        expected = rule.expected

        if constraint == 'exact':
            # expected is validated as not None in ValidationRule.__post_init__
            passed = validate_exact(value, expected)
            # Format with interpretations if available
            value_str = self._format_value_with_interpretation(value, rule)
            expected_str = self._format_value_with_interpretation(expected, rule)

            if passed:
                message = f"{key_type} {key} value matches expected value: {value_str}"
            else:
                message = f"{key_type} {key} value {value_str} does not match expected value {expected_str}"

        elif constraint == 'enum':
            # expected is validated as list in ValidationRule.__post_init__
            assert isinstance(expected, list), f"enum constraint requires list expected, got {type(expected)}"
            passed = validate_enum(value, expected)
            # Format with interpretations if available
            value_str = self._format_value_with_interpretation(value, rule)
            expected_str = self._format_expected_enum(expected, rule)

            if passed:
                message = f"{key_type} {key} value {value_str} is in allowed list"
            else:
                message = f"{key_type} {key} value {value_str} is not in allowed list: {expected_str}"

        elif constraint == 'regex':
            # expected is validated as string in ValidationRule.__post_init__
            assert isinstance(expected, str), f"regex constraint requires string expected, got {type(expected)}"
            passed = validate_regex(value, expected)
            if passed:
                message = f"{key_type} {key} value '{value}' matches expected pattern"
            else:
                message = f"{key_type} {key} value '{value}' does not match pattern '{expected}'"

        elif constraint == 'range':
            # expected is validated as dict in ValidationRule.__post_init__
            assert isinstance(expected, dict), f"range constraint requires dict expected, got {type(expected)}"
            passed = validate_range(value, expected)
            min_val = expected.get('min', '-inf')
            max_val = expected.get('max', '+inf')
            display_value = self._format_value_for_display(value)
            if passed:
                message = f"{key_type} {key} value {display_value} is within range {min_val} to {max_val}"
            else:
                message = f"{key_type} {key} value {display_value} is outside range {min_val} to {max_val}"

        elif constraint == 'ranges':
            # expected is validated as list in ValidationRule.__post_init__
            assert isinstance(expected, list), f"ranges constraint requires list expected, got {type(expected)}"
            passed = validate_ranges(value, expected)
            display_value = self._format_value_for_display(value)
            if passed:
                message = f"{key_type} {key} value {display_value} is within expected ranges"
            else:
                # Format ranges for display
                formatted_ranges = []
                for r in expected:
                    min_v = r.get('min', '-inf')
                    max_v = r.get('max', '+inf')
                    formatted_ranges.append(f"{min_v}-{max_v}")
                message = f"{key_type} {key} value {display_value} is not in any of the expected ranges: [{', '.join(formatted_ranges)}]"

        elif constraint == 'exists':
            passed = validate_exists(value)
            if passed:
                # Truncate long values for display
                display_value = self._truncate_value(value)
                message = f"{key_type} {key} ({description}) is present with value: {display_value}"
            else:
                message = f"{key_type} {key} ({description}) must be present but was not found"

        elif constraint == 'forbidden':
            passed = validate_forbidden(value)
            if passed:
                message = f"{key_type} {key} ({description}) is correctly absent"
            else:
                message = f"{key_type} {key} ({description}) must not be present but was found with value: {value}"

        else:
            passed = False
            message = f"Unknown constraint type: {constraint}"

        return passed, message

    def _format_value_with_interpretation(
        self,
        value: Any,
        rule: ValidationRule
    ) -> str:
        """
        Format a value with its interpretation if available.

        For TIFF tags and GeoKeys, we can look up human-readable names
        for code values (e.g., 5 -> "LZW" for Compression tag).

        Args:
            value: The actual value
            rule: The validation rule

        Returns:
            Formatted string like "5 (LZW)" or just "5"
        """
        interp = self._get_value_interpretation(value, rule)
        if interp:
            return f"{value} ({interp})"
        return str(value)

    def _format_expected_enum(
        self,
        expected_list: List[Any],
        rule: ValidationRule
    ) -> str:
        """
        Format expected enum list with interpretations if available.

        Args:
            expected_list: List of expected values
            rule: The validation rule

        Returns:
            Formatted string like "[5 (LZW), 8 (DEFLATE)]" or "[5, 8]"
        """
        formatted_values = []
        has_interpretations = False

        for val in expected_list:
            interp = self._get_value_interpretation(val, rule)
            if interp:
                formatted_values.append(f"{val} ({interp})")
                has_interpretations = True
            else:
                formatted_values.append(str(val))

        if has_interpretations:
            return f"[{', '.join(formatted_values)}]"
        else:
            return str(expected_list)

    def _get_value_interpretation(
        self,
        value: Any,
        rule: ValidationRule
    ) -> Optional[str]:
        """
        Get human-readable interpretation for a value.

        For TIFF tags and GeoKeys, looks up code meanings from
        the existing parser dictionaries.

        Args:
            value: The value to interpret
            rule: The validation rule providing context

        Returns:
            Interpretation string or None
        """
        # Common TIFF tag value interpretations
        if rule.section == 'tag':
            tag_code = int(rule.key)
            return self._get_tag_value_interpretation(tag_code, value)

        # Common GeoKey value interpretations
        elif rule.section == 'geokey':
            geokey_id = int(rule.key)
            return self._get_geokey_value_interpretation(geokey_id, value)

        return None

    def _get_tag_value_interpretation(
        self,
        tag_code: int,
        value: Any
    ) -> Optional[str]:
        """
        Get interpretation for a TIFF tag value.

        Args:
            tag_code: The TIFF tag code
            value: The value to interpret

        Returns:
            Interpretation string or None
        """
        # Common tag value lookups
        if tag_code == 259:  # Compression
            compression_names = {
                1: 'Uncompressed',
                5: 'LZW',
                6: 'Old JPEG',
                7: 'JPEG',
                8: 'DEFLATE',
                32773: 'PackBits',
                34712: 'JPEG2000',
                50000: 'ZSTD',
                50001: 'WebP',
                34887: 'LERC'
            }
            return compression_names.get(value)

        elif tag_code == 262:  # PhotometricInterpretation
            photometric_names = {
                0: 'WhiteIsZero',
                1: 'BlackIsZero',
                2: 'RGB',
                3: 'Palette',
                4: 'Transparency Mask',
                5: 'CMYK',
                6: 'YCbCr',
                8: 'CIELab'
            }
            return photometric_names.get(value)

        elif tag_code == 339:  # SampleFormat
            format_names = {
                1: 'Unsigned integer',
                2: 'Signed integer',
                3: 'IEEE floating point',
                4: 'Undefined'
            }
            return format_names.get(value)

        elif tag_code == 274:  # Orientation
            orientation_names = {
                1: 'Top-left',
                2: 'Top-right',
                3: 'Bottom-right',
                4: 'Bottom-left',
                5: 'Left-top',
                6: 'Right-top',
                7: 'Right-bottom',
                8: 'Left-bottom'
            }
            return orientation_names.get(value)

        elif tag_code == 284:  # PlanarConfiguration
            planar_names = {
                1: 'Chunky',
                2: 'Planar'
            }
            return planar_names.get(value)

        return None

    def _get_geokey_value_interpretation(
        self,
        geokey_id: int,
        value: Any
    ) -> Optional[str]:
        """
        Get interpretation for a GeoKey value.

        Args:
            geokey_id: The GeoKey ID
            value: The value to interpret

        Returns:
            Interpretation string or None
        """
        if geokey_id == 1024:  # GTModelTypeGeoKey
            model_names = {
                0: 'Undefined',
                1: 'Projected',
                2: 'Geographic',
                3: 'Geocentric'
            }
            return model_names.get(value)

        elif geokey_id == 1025:  # GTRasterTypeGeoKey
            raster_names = {
                0: 'Undefined',
                1: 'PixelIsArea',
                2: 'PixelIsPoint'
            }
            return raster_names.get(value)

        return None

    def _truncate_value(self, value: Any, max_length: int = 50) -> str:
        """
        Truncate a value for display in messages.

        Args:
            value: The value to truncate
            max_length: Maximum length before truncation

        Returns:
            Truncated string representation
        """
        str_value = str(value)
        if len(str_value) > max_length:
            return str_value[:max_length] + '...'
        return str_value

    def _format_value_for_display(self, value: Any) -> str:
        """
        Format a value for display in messages.

        Unwraps single-element lists for cleaner display (e.g., from single-band
        statistics). Multi-element lists are displayed as-is.

        Args:
            value: The value to format

        Returns:
            Formatted string representation

        Examples:
            >>> engine = ValidationEngine(None)   # formatting only, no file needed
            >>> engine._format_value_for_display([642.78])
            '642.78'
            >>> engine._format_value_for_display([100, 200, 150])
            '[100, 200, 150]'
            >>> engine._format_value_for_display(42.5)
            '42.5'
        """
        if isinstance(value, (list, tuple)) and len(value) == 1:
            return str(value[0])
        return str(value)


def validate_file(
    extractor: "MetadataExtractor",
    rules_by_section: Dict[str, List[ValidationRule]]
) -> Tuple[Dict[str, List[ValidationResult]], int, int, int, int]:
    """
    Convenience function to validate a single file.

    Args:
        extractor: MetadataExtractor instance with open file handles
        rules_by_section: Dict mapping section names to rule lists

    Returns:
        Tuple of (results_by_section, total_rules, passed, failed, skipped)
    """
    engine = ValidationEngine(extractor)
    results = engine.validate_all_sections(rules_by_section)

    total = 0
    passed = 0
    failed = 0
    skipped = 0

    for section_results in results.values():
        for result in section_results:
            total += 1
            if result.passed:
                passed += 1
            elif result.failed:
                failed += 1
            else:
                skipped += 1

    return results, total, passed, failed, skipped
