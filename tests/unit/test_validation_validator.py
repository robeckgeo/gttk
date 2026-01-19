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
Unit tests for validation engine.

This module tests the ValidationEngine class defined in
gttk.utils.validation.validator, which evaluates validation rules
against GeoTIFF metadata.

Test coverage target: 95%+

Organization:
- Tests use mock objects to simulate MetadataExtractor and ValueExtractor
- Tests verify all constraint types are handled correctly
- Tests verify status and message generation
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from gttk.utils.validation.validator import ValidationEngine, validate_file
from gttk.utils.validation.models import (
    ValidationRule,
    ValidationResult,
    ValidationStatus,
)


# =============================================================================
# Mock Data Classes
# =============================================================================

@dataclass
class MockTiffTag:
    """Mock TiffTag for testing."""
    code: int
    value: any
    name: str = ""


@dataclass
class MockGeoKey:
    """Mock GeoKey for testing."""
    id: int
    value: any
    name: str = ""


@dataclass
class MockXmlMetadata:
    """Mock XmlMetadata for testing."""
    content: Optional[str]


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_extractor():
    """Create a mock MetadataExtractor with default values."""
    extractor = Mock()

    # Sample tags
    extractor.extract_tags.return_value = [
        MockTiffTag(code=258, value=32, name="BitsPerSample"),
        MockTiffTag(code=259, value=5, name="Compression"),
        MockTiffTag(code=262, value=1, name="PhotometricInterpretation"),
    ]

    # Sample geokeys
    extractor.extract_geokeys.return_value = [
        MockGeoKey(id=1024, value=1, name="GTModelTypeGeoKey"),
        MockGeoKey(id=3072, value=32610, name="ProjectedCRSGeoKey"),
    ]

    # GDAL metadata
    extractor.extract_gdal_metadata.return_value = MockXmlMetadata(
        content='''<GDALMetadata>
  <Item name="STATISTICS_MINIMUM">-430.0</Item>
  <Item name="STATISTICS_MAXIMUM">8850.0</Item>
</GDALMetadata>'''
    )

    # Empty for other metadata types
    extractor.extract_geo_metadata.return_value = None
    extractor.extract_xmp_metadata.return_value = None
    extractor.extract_xml_metadata.return_value = None
    extractor.extract_projjson_string.return_value = None

    return extractor


@pytest.fixture
def exact_rule():
    """Create an exact constraint rule."""
    return ValidationRule(
        product='TestProduct',
        section='tag',
        key='258',
        key_type='tag',
        description='BitsPerSample',
        data_type='integer',
        constraint='exact',
        expected=32
    )


@pytest.fixture
def enum_rule():
    """Create an enum constraint rule."""
    return ValidationRule(
        product='TestProduct',
        section='tag',
        key='259',
        key_type='tag',
        description='Compression',
        data_type='integer',
        constraint='enum',
        expected=[5, 8]
    )


@pytest.fixture
def regex_rule():
    """Create a regex constraint rule."""
    return ValidationRule(
        product='TestProduct',
        section='gdal',
        key='AREA_OR_POINT',
        key_type='name',
        description='Area or Point',
        data_type='string',
        constraint='regex',
        expected='^(Area|Point)$'
    )


@pytest.fixture
def range_rule():
    """Create a range constraint rule."""
    return ValidationRule(
        product='TestProduct',
        section='geokey',
        key='3072',
        key_type='geokey',
        description='ProjectedCRSGeoKey',
        data_type='integer',
        constraint='range',
        expected={'min': 32601, 'max': 32760}
    )


@pytest.fixture
def ranges_rule():
    """Create a ranges constraint rule."""
    return ValidationRule(
        product='TestProduct',
        section='geokey',
        key='3072',
        key_type='geokey',
        description='ProjectedCRSGeoKey',
        data_type='integer',
        constraint='ranges',
        expected=[
            {'min': 32601, 'max': 32660},
            {'min': 32701, 'max': 32760}
        ]
    )


@pytest.fixture
def exists_rule():
    """Create an exists constraint rule."""
    return ValidationRule(
        product='TestProduct',
        section='tag',
        key='258',
        key_type='tag',
        description='BitsPerSample',
        data_type='integer',
        constraint='exists',
        expected=None
    )


@pytest.fixture
def forbidden_rule():
    """Create a forbidden constraint rule."""
    return ValidationRule(
        product='TestProduct',
        section='tag',
        key='9999',
        key_type='tag',
        description='Forbidden Tag',
        data_type='integer',
        constraint='forbidden',
        expected=None
    )


@pytest.fixture
def optional_rule():
    """Create an optional rule."""
    return ValidationRule(
        product='TestProduct',
        section='tag',
        key='9999',
        key_type='tag',
        description='Optional Tag',
        data_type='integer',
        constraint='exists',
        expected=None,
        optional=True
    )


# =============================================================================
# ValidationEngine Initialization Tests
# =============================================================================

@pytest.mark.unit
class TestValidationEngineInit:
    """Test ValidationEngine initialization."""

    def test_init_stores_extractor(self, mock_extractor):
        """Test that extractor is stored."""
        engine = ValidationEngine(mock_extractor)
        assert engine.extractor is mock_extractor

    def test_init_creates_value_extractor(self, mock_extractor):
        """Test that value extractor is created."""
        engine = ValidationEngine(mock_extractor)
        assert engine.value_extractor is not None


# =============================================================================
# Exact Constraint Tests
# =============================================================================

@pytest.mark.unit
class TestExactConstraint:
    """Test exact constraint validation."""

    def test_exact_pass(self, mock_extractor, exact_rule):
        """Test exact constraint passes with matching value."""
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(exact_rule)

        assert result.passed is True
        assert result.status == ValidationStatus.PASS.value
        assert 'matches expected value' in result.message

    def test_exact_fail(self, mock_extractor, exact_rule):
        """Test exact constraint fails with non-matching value."""
        exact_rule.expected = 16  # Wrong value
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(exact_rule)

        assert result.failed is True
        assert result.status == ValidationStatus.FAIL.value
        assert 'does not match expected value' in result.message


# =============================================================================
# Enum Constraint Tests
# =============================================================================

@pytest.mark.unit
class TestEnumConstraint:
    """Test enum constraint validation."""

    def test_enum_pass(self, mock_extractor, enum_rule):
        """Test enum constraint passes with value in list."""
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(enum_rule)

        assert result.passed is True
        assert 'is in allowed list' in result.message

    def test_enum_fail(self, mock_extractor, enum_rule):
        """Test enum constraint fails with value not in list."""
        enum_rule.expected = [1, 2, 3]  # 5 not in list
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(enum_rule)

        assert result.failed is True
        assert 'is not in allowed list' in result.message

    def test_enum_with_interpretation(self, mock_extractor, enum_rule):
        """Test enum formats values with interpretations (e.g., LZW)."""
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(enum_rule)

        # Compression tag 259 with value 5 should show "LZW" interpretation
        assert 'LZW' in result.message


# =============================================================================
# Regex Constraint Tests
# =============================================================================

@pytest.mark.unit
class TestRegexConstraint:
    """Test regex constraint validation."""

    def test_regex_pass(self, mock_extractor):
        """Test regex constraint passes with matching pattern."""
        # Add AREA_OR_POINT to GDAL metadata
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(
            content='''<GDALMetadata>
  <Item name="AREA_OR_POINT">Area</Item>
</GDALMetadata>'''
        )

        rule = ValidationRule(
            product='TestProduct',
            section='gdal',
            key='AREA_OR_POINT',
            key_type='name',
            description='Area or Point',
            data_type='string',
            constraint='regex',
            expected='^(Area|Point)$'
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        assert result.passed is True
        assert 'matches expected pattern' in result.message

    def test_regex_fail(self, mock_extractor):
        """Test regex constraint fails with non-matching pattern."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(
            content='''<GDALMetadata>
  <Item name="AREA_OR_POINT">Invalid</Item>
</GDALMetadata>'''
        )

        rule = ValidationRule(
            product='TestProduct',
            section='gdal',
            key='AREA_OR_POINT',
            key_type='name',
            description='Area or Point',
            data_type='string',
            constraint='regex',
            expected='^(Area|Point)$'
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        assert result.failed is True
        assert 'does not match pattern' in result.message


# =============================================================================
# Range Constraint Tests
# =============================================================================

@pytest.mark.unit
class TestRangeConstraint:
    """Test range constraint validation."""

    def test_range_pass(self, mock_extractor, range_rule):
        """Test range constraint passes with value in range."""
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(range_rule)

        assert result.passed is True
        assert 'is within range' in result.message

    def test_range_fail_below(self, mock_extractor, range_rule):
        """Test range constraint fails with value below range."""
        range_rule.expected = {'min': 40000, 'max': 50000}
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(range_rule)

        assert result.failed is True
        assert 'is outside range' in result.message

    def test_range_fail_above(self, mock_extractor, range_rule):
        """Test range constraint fails with value above range."""
        range_rule.expected = {'min': 1, 'max': 100}
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(range_rule)

        assert result.failed is True
        assert 'is outside range' in result.message


# =============================================================================
# Ranges Constraint Tests
# =============================================================================

@pytest.mark.unit
class TestRangesConstraint:
    """Test ranges constraint validation."""

    def test_ranges_pass(self, mock_extractor, ranges_rule):
        """Test ranges constraint passes with value in one of the ranges."""
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(ranges_rule)

        assert result.passed is True
        assert 'is within expected ranges' in result.message

    def test_ranges_fail(self, mock_extractor, ranges_rule):
        """Test ranges constraint fails with value outside all ranges."""
        ranges_rule.expected = [
            {'min': 1, 'max': 100},
            {'min': 200, 'max': 300}
        ]
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(ranges_rule)

        assert result.failed is True
        assert 'is not in any of the expected ranges' in result.message


# =============================================================================
# Exists Constraint Tests
# =============================================================================

@pytest.mark.unit
class TestExistsConstraint:
    """Test exists constraint validation."""

    def test_exists_pass(self, mock_extractor, exists_rule):
        """Test exists constraint passes when value present."""
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(exists_rule)

        assert result.passed is True
        assert 'is present with value' in result.message

    def test_exists_fail(self, mock_extractor):
        """Test exists constraint fails when value absent."""
        rule = ValidationRule(
            product='TestProduct',
            section='tag',
            key='9999',  # Non-existent tag
            key_type='tag',
            description='Missing Tag',
            data_type='integer',
            constraint='exists',
            expected=None
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        assert result.failed is True


# =============================================================================
# Forbidden Constraint Tests
# =============================================================================

@pytest.mark.unit
class TestForbiddenConstraint:
    """Test forbidden constraint validation."""

    def test_forbidden_pass(self, mock_extractor, forbidden_rule):
        """Test forbidden constraint passes when value absent."""
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(forbidden_rule)

        assert result.passed is True
        assert 'correctly absent' in result.message

    def test_forbidden_fail(self, mock_extractor):
        """Test forbidden constraint fails when value present."""
        rule = ValidationRule(
            product='TestProduct',
            section='tag',
            key='258',  # Tag exists
            key_type='tag',
            description='BitsPerSample',
            data_type='integer',
            constraint='forbidden',
            expected=None
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        assert result.failed is True
        assert 'must not be present' in result.message


# =============================================================================
# Optional Rule Tests
# =============================================================================

@pytest.mark.unit
class TestOptionalRules:
    """Test optional rule handling."""

    def test_optional_missing_skips(self, mock_extractor, optional_rule):
        """Test optional rule with missing value is skipped."""
        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(optional_rule)

        assert result.skipped is True
        assert result.status == ValidationStatus.SKIP.value
        assert 'Optional' in result.message

    def test_optional_present_validates(self, mock_extractor):
        """Test optional rule with present value is validated."""
        rule = ValidationRule(
            product='TestProduct',
            section='tag',
            key='258',
            key_type='tag',
            description='BitsPerSample',
            data_type='integer',
            constraint='exact',
            expected=32,
            optional=True
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        assert result.passed is True  # Validates because value exists


# =============================================================================
# Section Validation Tests
# =============================================================================

@pytest.mark.unit
class TestValidateSection:
    """Test validate_section method."""

    def test_validate_section_returns_all_results(self, mock_extractor):
        """Test that all rules in section return results."""
        rules = [
            ValidationRule(
                product='TestProduct',
                section='tag',
                key='258',
                key_type='tag',
                description='BitsPerSample',
                data_type='integer',
                constraint='exact',
                expected=32
            ),
            ValidationRule(
                product='TestProduct',
                section='tag',
                key='259',
                key_type='tag',
                description='Compression',
                data_type='integer',
                constraint='enum',
                expected=[5, 8]
            ),
        ]

        engine = ValidationEngine(mock_extractor)
        results = engine.validate_section('tag', rules)

        assert len(results) == 2
        assert all(isinstance(r, ValidationResult) for r in results)

    def test_validate_missing_section(self, mock_extractor):
        """Test validation when entire section is missing."""
        # Make tags return None (section missing)
        mock_extractor.extract_tags.return_value = None

        rules = [
            ValidationRule(
                product='TestProduct',
                section='tag',
                key='258',
                key_type='tag',
                description='BitsPerSample',
                data_type='integer',
                constraint='exact',
                expected=32
            ),
        ]

        engine = ValidationEngine(mock_extractor)
        results = engine.validate_section('tag', rules)

        assert len(results) == 1
        assert results[0].failed is True
        # Message indicates the section is missing (uses get_section_missing_message)
        assert 'missing' in results[0].message.lower()

    def test_validate_missing_section_forbidden_passes(self, mock_extractor):
        """Test forbidden rule passes when section is missing."""
        mock_extractor.extract_tags.return_value = None

        rules = [
            ValidationRule(
                product='TestProduct',
                section='tag',
                key='258',
                key_type='tag',
                description='BitsPerSample',
                data_type='integer',
                constraint='forbidden',
                expected=None
            ),
        ]

        engine = ValidationEngine(mock_extractor)
        results = engine.validate_section('tag', rules)

        assert results[0].passed is True

    def test_validate_missing_section_optional_skips(self, mock_extractor):
        """Test optional rule is skipped when section is missing."""
        mock_extractor.extract_tags.return_value = None

        rules = [
            ValidationRule(
                product='TestProduct',
                section='tag',
                key='258',
                key_type='tag',
                description='BitsPerSample',
                data_type='integer',
                constraint='exact',
                expected=32,
                optional=True
            ),
        ]

        engine = ValidationEngine(mock_extractor)
        results = engine.validate_section('tag', rules)

        assert results[0].skipped is True


# =============================================================================
# All Sections Validation Tests
# =============================================================================

@pytest.mark.unit
class TestValidateAllSections:
    """Test validate_all_sections method."""

    def test_validate_all_sections(self, mock_extractor):
        """Test validating multiple sections."""
        rules_by_section = {
            'tag': [
                ValidationRule(
                    product='TestProduct',
                    section='tag',
                    key='258',
                    key_type='tag',
                    description='BitsPerSample',
                    data_type='integer',
                    constraint='exact',
                    expected=32
                ),
            ],
            'geokey': [
                ValidationRule(
                    product='TestProduct',
                    section='geokey',
                    key='1024',
                    key_type='geokey',
                    description='GTModelTypeGeoKey',
                    data_type='integer',
                    constraint='exact',
                    expected=1
                ),
            ],
        }

        engine = ValidationEngine(mock_extractor)
        results = engine.validate_all_sections(rules_by_section)

        assert 'tag' in results
        assert 'geokey' in results
        assert len(results['tag']) == 1
        assert len(results['geokey']) == 1


# =============================================================================
# Value Interpretation Tests
# =============================================================================

@pytest.mark.unit
class TestValueInterpretation:
    """Test value interpretation for human-readable messages."""

    def test_compression_interpretation(self, mock_extractor):
        """Test compression tag value interpretation."""
        rule = ValidationRule(
            product='TestProduct',
            section='tag',
            key='259',
            key_type='tag',
            description='Compression',
            data_type='integer',
            constraint='enum',
            expected=[5, 8]
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        # Value 5 should show "LZW" interpretation
        assert 'LZW' in result.message

    def test_photometric_interpretation(self, mock_extractor):
        """Test photometric tag value interpretation."""
        rule = ValidationRule(
            product='TestProduct',
            section='tag',
            key='262',
            key_type='tag',
            description='PhotometricInterpretation',
            data_type='integer',
            constraint='enum',
            expected=[1, 2]
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        # Value 1 should show "BlackIsZero" interpretation
        assert 'BlackIsZero' in result.message

    def test_model_type_interpretation(self, mock_extractor):
        """Test GTModelTypeGeoKey value interpretation."""
        rule = ValidationRule(
            product='TestProduct',
            section='geokey',
            key='1024',
            key_type='geokey',
            description='GTModelTypeGeoKey',
            data_type='integer',
            constraint='enum',
            expected=[1, 2]
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        # Value 1 should show "Projected" interpretation
        assert 'Projected' in result.message


# =============================================================================
# validate_file Function Tests
# =============================================================================

@pytest.mark.unit
class TestValidateFileFunction:
    """Test validate_file convenience function."""

    def test_validate_file_returns_counts(self, mock_extractor):
        """Test validate_file returns correct counts."""
        rules_by_section = {
            'tag': [
                ValidationRule(
                    product='TestProduct',
                    section='tag',
                    key='258',
                    key_type='tag',
                    description='BitsPerSample',
                    data_type='integer',
                    constraint='exact',
                    expected=32  # Should pass
                ),
                ValidationRule(
                    product='TestProduct',
                    section='tag',
                    key='258',
                    key_type='tag',
                    description='BitsPerSample',
                    data_type='integer',
                    constraint='exact',
                    expected=16  # Should fail
                ),
            ],
        }

        results, total, passed, failed, skipped = validate_file(
            mock_extractor, rules_by_section
        )

        assert total == 2
        assert passed == 1
        assert failed == 1
        assert skipped == 0

    def test_validate_file_with_optional(self, mock_extractor):
        """Test validate_file counts optional rules as skipped."""
        rules_by_section = {
            'tag': [
                ValidationRule(
                    product='TestProduct',
                    section='tag',
                    key='9999',  # Non-existent
                    key_type='tag',
                    description='Missing Tag',
                    data_type='integer',
                    constraint='exists',
                    expected=None,
                    optional=True
                ),
            ],
        }

        results, total, passed, failed, skipped = validate_file(
            mock_extractor, rules_by_section
        )

        assert total == 1
        assert passed == 0
        assert failed == 0
        assert skipped == 1


# =============================================================================
# Unknown Constraint Tests
# =============================================================================

@pytest.mark.unit
class TestUnknownConstraint:
    """Test handling of unknown constraint types."""

    def test_unknown_constraint_fails(self, mock_extractor):
        """Test unknown constraint type fails validation."""
        # Create rule with invalid constraint manually
        rule = ValidationRule.__new__(ValidationRule)
        rule.product = 'TestProduct'
        rule.section = 'tag'
        rule.key = '258'
        rule.key_type = 'tag'
        rule.description = 'BitsPerSample'
        rule.data_type = 'integer'
        rule.constraint = 'unknown_constraint'
        rule.expected = 32
        rule.optional = False
        rule.comment = None

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        assert result.failed is True
        assert 'Unknown constraint type' in result.message


# =============================================================================
# Value Truncation Tests
# =============================================================================

@pytest.mark.unit
class TestValueTruncation:
    """Test value truncation for long values."""

    def test_truncate_long_value(self, mock_extractor):
        """Test that long values are truncated in messages."""
        # Create mock tag with very long string value
        mock_extractor.extract_tags.return_value = [
            MockTiffTag(code=305, value="A" * 200, name="Software"),
        ]

        rule = ValidationRule(
            product='TestProduct',
            section='tag',
            key='305',
            key_type='tag',
            description='Software',
            data_type='string',
            constraint='exists',
            expected=None
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        # Message should contain truncated value with "..."
        assert '...' in result.message
        assert len(result.message) < 300  # Should be truncated

    def test_short_value_not_truncated(self, mock_extractor):
        """Test that short values are not truncated."""
        rule = ValidationRule(
            product='TestProduct',
            section='tag',
            key='258',
            key_type='tag',
            description='BitsPerSample',
            data_type='integer',
            constraint='exists',
            expected=None
        )

        engine = ValidationEngine(mock_extractor)
        result = engine.validate_rule(rule)

        # Short value should not have truncation marker
        assert '...' not in result.message or 'is present with value: 32' in result.message
