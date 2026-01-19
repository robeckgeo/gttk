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
Data Models for Validation Package.

This module defines strongly-typed data classes for representing validation
rules, results, and summaries. These classes provide type safety,
self-documentation, and clear contracts between modules.

Classes:
    ValidationStatus: Enum for validation result status (PASS, FAIL, SKIP)
    ConstraintType: Enum for supported constraint types
    SectionType: Enum for metadata section types
    ValidationRule: Represents a single validation rule from TOML
    ValidationResult: Represents the result of validating a single rule
    ValidationSummary: Summary statistics for a validation report
    ValidationTableData: Presentation data for validation results table
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ValidationStatus(Enum):
    """Validation result status."""
    PASS = 'PASS'
    FAIL = 'FAIL'
    SKIP = 'SKIP'


class ConstraintType(Enum):
    """Supported constraint types for validation rules."""
    EXACT = 'exact'
    ENUM = 'enum'
    REGEX = 'regex'
    RANGE = 'range'
    RANGES = 'ranges'
    EXISTS = 'exists'
    FORBIDDEN = 'forbidden'


class SectionType(Enum):
    """Metadata section types (simplified names for readability)."""
    TAG = 'tag'
    GEOKEY = 'geokey'
    GDAL = 'gdal'
    GEO = 'geo'
    XMP = 'xmp'
    XML = 'xml'
    PROJJSON = 'projjson'


@dataclass
class ValidationRule:
    """
    Represents a single validation rule from TOML configuration.

    Attributes:
        product: Name of the validation product (e.g., 'DGED5', '3DEP', 'GLO-30')
        section: Metadata section type (e.g., 'tag', 'geokey', 'gdal', 'xml')
        key: The identifier (tag number, GeoKey number, GDAL Metadata name, XPath, JSONPath)
        key_type: Type of key ('tag', 'geokey', 'name', 'xpath', 'jsonpath')
        description: Human-readable description of what's being validated
        data_type: Expected data type. Basic: 'string', 'integer', 'float', 'boolean'.
                   Extended (Phase 5): 'date', 'datetime', 'url', 'email'.
        constraint: Validation method ('exact', 'enum', 'regex', 'range', etc.)
        expected: Expected value(s) for validation (varies by constraint type)
        optional: Whether the field is optional (default: False)
        comment: Additional notes/documentation about the rule

    Example:
        >>> rule = ValidationRule(
        ...     product='DGED5',
        ...     section='tag',
        ...     key='258',
        ...     key_type='Tag',
        ...     description='BitsPerSample',
        ...     data_type='integer',
        ...     constraint='exact',
        ...     expected=32
        ... )
    """
    product: str
    section: str
    key: str
    key_type: str
    description: str
    data_type: str
    constraint: str
    expected: Optional[Any] = None
    optional: bool = False
    comment: Optional[str] = None

    # Valid data types: basic + extended (Phase 5)
    VALID_DATA_TYPES = [
        'string', 'integer', 'float', 'boolean',  # Basic types
        'date', 'datetime', 'url', 'email'  # Extended types (Phase 5)
    ]

    def __post_init__(self):
        """Validate rule configuration."""
        # Validate section type
        valid_sections = [s.value for s in SectionType]
        if self.section not in valid_sections:
            raise ValueError(
                f"Invalid section: '{self.section}'. "
                f"Valid sections: {valid_sections}"
            )

        # Validate constraint type
        valid_constraints = [c.value for c in ConstraintType]
        if self.constraint not in valid_constraints:
            raise ValueError(
                f"Invalid constraint: '{self.constraint}'. "
                f"Valid constraints: {valid_constraints}"
            )

        # Validate that expected is provided when required
        requires_expected = [
            ConstraintType.EXACT.value,
            ConstraintType.ENUM.value,
            ConstraintType.REGEX.value,
            ConstraintType.RANGE.value,
            ConstraintType.RANGES.value
        ]
        if self.constraint in requires_expected and self.expected is None:
            raise ValueError(
                f"Constraint '{self.constraint}' requires 'expected' value"
            )

        # Validate data_type
        if self.data_type not in self.VALID_DATA_TYPES:
            raise ValueError(
                f"Invalid data_type: '{self.data_type}'. "
                f"Valid types: {self.VALID_DATA_TYPES}"
            )


@dataclass
class ValidationResult:
    """
    Represents the result of validating a single rule against actual metadata.

    Attributes:
        rule: The ValidationRule that was evaluated
        value: The actual value retrieved from the GeoTIFF (None if not found)
        status: Validation outcome ('PASS', 'FAIL', 'SKIP')
        message: Human-readable message explaining the result

    Example:
        >>> result = ValidationResult(
        ...     rule=rule,
        ...     value=32,
        ...     status='PASS',
        ...     message='Tag 258 value matches expected value: 32'
        ... )
        >>> result.passed
        True
    """
    rule: ValidationRule
    value: Optional[Any] = None
    status: str = field(default=ValidationStatus.SKIP.value)
    message: str = ''

    def __post_init__(self):
        """Validate status value."""
        valid_statuses = [s.value for s in ValidationStatus]
        if self.status not in valid_statuses:
            raise ValueError(
                f"Invalid status: '{self.status}'. "
                f"Valid statuses: {valid_statuses}"
            )

    @property
    def passed(self) -> bool:
        """Check if validation passed."""
        return self.status == ValidationStatus.PASS.value

    @property
    def failed(self) -> bool:
        """Check if validation failed."""
        return self.status == ValidationStatus.FAIL.value

    @property
    def skipped(self) -> bool:
        """Check if validation was skipped."""
        return self.status == ValidationStatus.SKIP.value

    def get_icon(self) -> str:
        """Get status icon for display."""
        icons = {
            ValidationStatus.PASS.value: '\u2705',  # ✅
            ValidationStatus.FAIL.value: '\u274c',  # ❌
            ValidationStatus.SKIP.value: '\u26a0\ufe0f'  # ⚠️
        }
        return icons.get(self.status, '\u2753')  # ❓


@dataclass
class ValidationSummary:
    """
    Summary statistics for a validation report.

    Attributes:
        product: Validation product name (e.g., 'DGED5', '3DEP', 'GLO-30')
        input_file: Name of the validated GeoTIFF file
        rules_file: Name of the TOML rules file used
        report_date: ISO 8601 date of report generation
        total_rules: Total number of rules evaluated
        passed: Number of rules that passed
        failed: Number of rules that failed
        skipped: Number of rules that were skipped
        results_by_section: Dict mapping section names to lists of ValidationResult
        report_path: Path to generated report file

    Example:
        >>> summary = ValidationSummary(
        ...     product='DGED5',
        ...     input_file='example.tif',
        ...     rules_file='dged5_rules.toml',
        ...     report_date='2026-01-15'
        ... )
    """
    product: str
    input_file: str
    rules_file: str
    report_date: str
    total_rules: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results_by_section: Dict[str, List[ValidationResult]] = field(default_factory=dict)
    report_path: Optional[Path] = None

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate percentage."""
        if self.total_rules == 0:
            return 0.0
        return (self.passed / self.total_rules) * 100

    @property
    def fail_rate(self) -> float:
        """Calculate fail rate percentage."""
        if self.total_rules == 0:
            return 0.0
        return (self.failed / self.total_rules) * 100

    @property
    def overall_status(self) -> str:
        """
        Get overall validation status.

        Returns:
            'FAIL' if any rule failed, 'PASS' if at least one passed with no failures,
            'SKIP' if all rules were skipped
        """
        if self.failed > 0:
            return ValidationStatus.FAIL.value
        elif self.passed > 0:
            return ValidationStatus.PASS.value
        else:
            return ValidationStatus.SKIP.value


@dataclass
class ValidationTableData:
    """
    Presentation data for validation results table.

    Used by section renderers to format validation results consistently.

    Attributes:
        section_name: Display name for this section
        section_type: Section type identifier (e.g., 'tag')
        results: List of ValidationResult objects for this section
        icon: Icon name for the section menu

    Example:
        >>> table_data = ValidationTableData(
        ...     section_name='TIFF Tags',
        ...     section_type='tag',
        ...     results=[result1, result2]
        ... )
        >>> table_data.passed_count
        1
    """
    section_name: str
    section_type: str
    results: List[ValidationResult]
    icon: str = 'checkbox'

    @property
    def passed_count(self) -> int:
        """Count of passed validations."""
        return sum(1 for r in self.results if r.passed)

    @property
    def failed_count(self) -> int:
        """Count of failed validations."""
        return sum(1 for r in self.results if r.failed)

    @property
    def skipped_count(self) -> int:
        """Count of skipped validations."""
        return sum(1 for r in self.results if r.skipped)


# =============================================================================
# Message Generation Functions
# =============================================================================

def get_missing_key_message(rule: ValidationRule) -> str:
    """
    Generate appropriate message for missing key based on section type.

    Args:
        rule: The validation rule for which the key is missing

    Returns:
        Human-readable message explaining that the key is missing
    """
    if rule.section in ['geo', 'xmp', 'xml']:
        # XPath-based sections
        return f"XPath '{rule.key}' is required but not present in the file"
    elif rule.section == 'projjson':
        # JSONPath-based section
        return f"JSONPath '{rule.key}' is required but not present"
    elif rule.section == 'tag':
        return f"Tag {rule.key} ({rule.description}) is required but not present in the file"
    elif rule.section == 'geokey':
        return f"GeoKey {rule.key} ({rule.description}) is required but not found"
    elif rule.section == 'gdal':
        return f"Metadata item '{rule.key}' ({rule.description}) is required but not present"
    else:
        return f"{rule.key_type} {rule.key} is required but not found"


def get_section_missing_message(section_type: str) -> str:
    """
    Get appropriate message for missing section.

    Args:
        section_type: The type of section that is missing

    Returns:
        Human-readable message explaining that the section is missing
    """
    messages = {
        'tag': 'TIFF tags are missing - file is not a TIFF',
        'geokey': 'GeoKeyDirectoryTag (34735) is missing - file is not a GeoTIFF',
        'gdal': 'GDAL_METADATA tag (42112) is not present',
        'geo': 'GEO_METADATA tag (50909) is not present',
        'xmp': 'XMLPacket tag (700) is not present',
        'xml': 'No matching external XML metadata file was found',
        'projjson': 'PROJJSON string could not be generated - file is not a GeoTIFF',
    }
    return messages.get(section_type, f'{section_type} section is not available')


# =============================================================================
# Section Display Names and Icons
# =============================================================================

SECTION_DISPLAY_NAMES = {
    'tag': 'TIFF Tags',
    'geokey': 'GeoKeys',
    'gdal': 'GDAL Metadata',
    'geo': 'GEO Metadata',
    'xmp': 'XMP Metadata',
    'xml': 'External XML Metadata',
    'projjson': 'PROJJSON',
}

SECTION_ICONS = {
    'tag': 'tag',
    'geokey': 'key',
    'gdal': 'earth',
    'geo': 'geo',
    'xmp': 'xmp',
    'xml': 'xml',
    'projjson': 'json',
}


def get_section_display_name(section_type: str) -> str:
    """Get display name for a section type."""
    return SECTION_DISPLAY_NAMES.get(section_type, section_type.upper())


def get_section_icon(section_type: str) -> str:
    """Get icon name for a section type."""
    return SECTION_ICONS.get(section_type, 'checkbox')
