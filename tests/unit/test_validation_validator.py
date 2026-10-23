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

import logging
import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any

from gttk.utils.validation.validator import ValidationEngine, validate_file
from gttk.utils.validation.models import (
    FilenamePattern,
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


class TestMessagesSayWhenAValueCouldNotBeCompared:

    def test_range_against_text(self):
        from gttk.utils.validation.validator import _with_comparison_failure
        message = _with_comparison_failure('Tag 258 value abc is outside range 0 to 255', 'abc', {'min': 0, 'max': 255}, 'range')
        assert message.endswith('(could not be compared: not a number)')

    def test_a_real_mismatch_is_left_alone(self):
        from gttk.utils.validation.validator import _with_comparison_failure
        message = _with_comparison_failure('Tag 258 value 300 is outside range 0 to 255', 300, {'min': 0, 'max': 255}, 'range')
        assert 'could not be compared' not in message


# =============================================================================
# File-name placeholders in expected
# =============================================================================

TILE_PATTERN = FilenamePattern(r'^TILE_(?P<geocell>[NS]\d{2}[EW]\d{3})_(?P<edition>\d{2})_DEM$')

TILE_GDAL = '''<GDALMetadata>
  <Item name="IDENTIFIER">TILE_N00E000_01_DEM</Item>
  <Item name="TILE_ID">N00E000</Item>
</GDALMetadata>'''


def tile_record(file_identifier):
    """A minimal ISO 19139 record whose fileIdentifier names a source record."""
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco">
  <gmd:fileIdentifier>
    <gco:CharacterString>{file_identifier}</gco:CharacterString>
  </gmd:fileIdentifier>
</gmd:MD_Metadata>
'''


@pytest.mark.unit
class TestPlaceholdersInExpected:
    """
    A rule's expected value may name the file being validated: {stem}, {name} and the
    named groups of the product's filename.pattern, resolved per file by the engine.
    """

    @pytest.fixture
    def tile_extractor(self, mock_extractor):
        mock_extractor.filepath = Path('/data/TILE_N00E000_01_DEM.tif')
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content=TILE_GDAL)
        mock_extractor.extract_geo_metadata.return_value = MockXmlMetadata(
            content=tile_record('SRC_N00E000_01.xml'))
        return mock_extractor

    @pytest.fixture
    def misnamed_extractor(self, tile_extractor):
        """The same metadata in a file whose stem the pattern does not match."""
        tile_extractor.filepath = Path('/data/TILE_bad.tif')
        return tile_extractor

    @staticmethod
    def gdal_rule(name, expected, constraint='exact', pattern=TILE_PATTERN, **kwargs):
        return ValidationRule(
            product='TILE', section='gdal', key=name, key_type='name',
            description=f'{name} from the file name', data_type='string',
            constraint=constraint, expected=expected, filename_pattern=pattern, **kwargs
        )

    @staticmethod
    def geo_rule(expected, pattern=TILE_PATTERN):
        return ValidationRule(
            product='TILE', section='geo',
            key='/gmd:MD_Metadata/gmd:fileIdentifier/gco:CharacterString', key_type='xpath',
            description='The embedded record names the tile', data_type='string',
            constraint='regex', expected=expected, filename_pattern=pattern
        )

    def test_stem_resolves_without_a_filename_pattern(self, tile_extractor):
        rule = self.gdal_rule('IDENTIFIER', '{stem}', pattern=None)
        result = ValidationEngine(tile_extractor).validate_rule(rule)
        assert result.passed, result.message
        assert result.rule.expected == 'TILE_N00E000_01_DEM'
        assert result.message == 'Name IDENTIFIER value matches expected value: TILE_N00E000_01_DEM (from filename)'

    def test_named_group_resolves_for_exact(self, tile_extractor):
        result = ValidationEngine(tile_extractor).validate_rule(self.gdal_rule('TILE_ID', '{geocell}'))
        assert result.passed, result.message
        assert result.rule.expected == 'N00E000'
        assert result.value == 'N00E000'
        assert result.message.endswith(' (from filename)')

    def test_named_group_is_escaped_inside_regex(self, tile_extractor):
        rule = self.geo_rule(r'^SRC_{geocell}_\d{2}(\.xml)?$')
        result = ValidationEngine(tile_extractor).validate_rule(rule)
        assert result.passed, result.message
        assert result.rule.expected == r'^SRC_N00E000_\d{2}(\.xml)?$'
        assert result.message.endswith(' (from filename)')

        tile_extractor.extract_geo_metadata.return_value = MockXmlMetadata(
            content=tile_record('SRC_N00E001_01.xml'))
        result = ValidationEngine(tile_extractor).validate_rule(rule)
        assert result.failed
        assert "value 'SRC_N00E001_01.xml' does not match pattern '^SRC_N00E000_\\d{2}(\\.xml)?$'" in result.message
        assert result.message.endswith(' (from filename)')

    def test_shared_rule_is_not_mutated(self, tile_extractor):
        rule = self.gdal_rule('TILE_ID', '{geocell}')
        result = ValidationEngine(tile_extractor).validate_rule(rule)
        assert rule.expected == '{geocell}'
        assert result.rule is not rule
        assert result.rule.expected == 'N00E000'
        assert result.rule.filename_pattern is rule.filename_pattern

    def test_plain_rule_keeps_the_same_rule_object_and_message(self, tile_extractor, exact_rule):
        engine = ValidationEngine(tile_extractor)
        result = engine.validate_rule(exact_rule)
        assert result.rule is exact_rule
        assert result.message == 'Tag 258 value matches expected value: 32'

        literal = self.gdal_rule('TILE_ID', 'N00E000')   # the pattern is attached, but nothing uses it
        result = engine.validate_rule(literal)
        assert result.rule is literal
        assert result.message == 'Name TILE_ID value matches expected value: N00E000'

    def test_filename_mismatch_fails_every_placeholder_rule_and_names_the_pattern(self, misnamed_extractor):
        engine = ValidationEngine(misnamed_extractor)
        rules = [
            self.gdal_rule('TILE_ID', '{geocell}'),
            self.gdal_rule('IDENTIFIER', '{stem}'),            # built-in, but the product's pattern governs
            self.geo_rule(r'^SRC_{geocell}_\d{2}(\.xml)?$'),
        ]
        for rule in rules:
            result = engine.validate_rule(rule)
            assert result.failed, result.message
            assert result.rule is rule
            assert result.value is not None   # the metadata was read; the name is what is wrong
            assert result.message.startswith(
                f"Filename 'TILE_bad.tif' does not match filename.pattern '{TILE_PATTERN.pattern}'; cannot resolve ")
            assert 'from filename' not in result.message
        assert engine.validate_rule(rules[0]).message.endswith("cannot resolve {geocell} in expected '{geocell}'")
        assert engine.validate_rule(rules[1]).message.endswith("cannot resolve {stem} in expected '{stem}'")

    def test_filename_mismatch_leaves_plain_rules_alone(self, misnamed_extractor, exact_rule):
        engine = ValidationEngine(misnamed_extractor)
        literal = self.gdal_rule('TILE_ID', 'N00E000')
        for rule in (exact_rule, literal):
            result = engine.validate_rule(rule)
            assert result.passed, result.message
            assert result.rule is rule
            assert 'filename' not in result.message

    def test_filename_mismatch_fails_an_optional_rule_with_a_missing_value(self, misnamed_extractor):
        rule = self.gdal_rule('NOT_THERE', '{geocell}', optional=True)
        result = ValidationEngine(misnamed_extractor).validate_rule(rule)
        assert result.failed
        assert result.value is None
        assert 'cannot resolve {geocell}' in result.message

    def test_mismatch_is_logged_once_per_file(self, misnamed_extractor, caplog):
        engine = ValidationEngine(misnamed_extractor)
        with caplog.at_level(logging.WARNING):
            engine.validate_rule(self.gdal_rule('TILE_ID', '{geocell}'))
            # An equal pattern parsed separately is the same key in the engine's cache
            engine.validate_rule(self.gdal_rule('IDENTIFIER', '{stem}', pattern=FilenamePattern(TILE_PATTERN.pattern)))
            engine.validate_rule(self.geo_rule(r'^SRC_{geocell}_\d{2}$'))
        warnings = [r for r in caplog.records
                    if r.levelno == logging.WARNING and r.name == 'gttk.utils.validation.validator']
        assert [r.getMessage() for r in warnings] == [
            f"TILE_bad.tif does not match filename.pattern '{TILE_PATTERN.pattern}'"]

    def test_enum_with_placeholders(self, tile_extractor):
        rule = self.gdal_rule('TILE_ID', ['{geocell}', 'GLOBAL'], constraint='enum')
        result = ValidationEngine(tile_extractor).validate_rule(rule)
        assert result.passed, result.message
        assert result.rule.expected == ['N00E000', 'GLOBAL']
        assert rule.expected == ['{geocell}', 'GLOBAL']
        assert result.message == 'Name TILE_ID value N00E000 is in allowed list (from filename)'

    def test_two_engines_resolve_the_same_rule_against_their_own_files(self, tile_extractor):
        rule = self.gdal_rule('TILE_ID', '{geocell}')
        first = ValidationEngine(tile_extractor).validate_rule(rule)

        other = Mock()
        other.filepath = Path('/data/TILE_S10W020_02_DEM.tif')
        other.extract_gdal_metadata.return_value = MockXmlMetadata(
            content='<GDALMetadata>\n  <Item name="TILE_ID">S10W020</Item>\n</GDALMetadata>')
        second = ValidationEngine(other).validate_rule(rule)

        assert first.passed and second.passed, (first.message, second.message)
        assert first.rule.expected == 'N00E000'
        assert second.rule.expected == 'S10W020'
        assert rule.expected == '{geocell}'
