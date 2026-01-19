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
Integration tests for validation workflow.

This module tests the complete validation workflow from GeoTIFF files
through the ValidationEngine to ValidationResults. Uses MockGeoTIFF
factory to create test files.

Test coverage:
- Full validation workflow with real GeoTIFF files
- Tag, GeoKey, and GDAL metadata extraction and validation
- Multiple constraint types with actual file data
- Section-level validation behavior
"""

import pytest
import tempfile
from pathlib import Path
from osgeo import gdal

from tests.fixtures.mock_geotiff_factory import MockGeoTIFF
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.validation import (
    ValidationEngine,
    ValidationRule,
    ValidationResult,
    ValidationStatus,
    validate_file,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def basic_geotiff(temp_dir):
    """Create a basic test GeoTIFF file."""
    mock = MockGeoTIFF(
        width=256,
        height=256,
        bands=1,
        data_type=gdal.GDT_Float32,
        crs='EPSG:32610',
        compression='DEFLATE',
        predictor=3,
    )
    filepath = temp_dir / 'basic.tif'
    mock.save_to_file(filepath)
    return filepath


@pytest.fixture
def multiband_geotiff(temp_dir):
    """Create a 3-band test GeoTIFF file."""
    mock = MockGeoTIFF(
        width=512,
        height=512,
        bands=3,
        data_type=gdal.GDT_Byte,
        crs='EPSG:4326',
        compression='LZW',
        predictor=2,
    )
    filepath = temp_dir / 'multiband.tif'
    mock.save_to_file(filepath)
    return filepath


@pytest.fixture
def dem_geotiff(temp_dir):
    """Create a DEM-style test GeoTIFF file with nodata."""
    mock = MockGeoTIFF(
        width=100,
        height=100,
        bands=1,
        data_type=gdal.GDT_Float32,
        crs='EPSG:32610',
        nodata_value=-9999.0,
        compression='DEFLATE',
    )
    filepath = temp_dir / 'dem.tif'
    mock.save_to_file(filepath)
    return filepath


# =============================================================================
# Basic Validation Workflow Tests
# =============================================================================

@pytest.mark.integration
class TestBasicValidationWorkflow:
    """Test basic validation workflow with real files."""

    def test_validate_tag_exact(self, basic_geotiff):
        """Test exact tag validation with real file."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='259',  # Compression
            key_type='tag',
            description='Compression',
            data_type='integer',
            constraint='exact',
            expected=8  # DEFLATE
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True
        assert result.value == 8

    def test_validate_tag_enum(self, basic_geotiff):
        """Test enum tag validation with real file."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='259',  # Compression
            key_type='tag',
            description='Compression',
            data_type='integer',
            constraint='enum',
            expected=[5, 8, 1]  # LZW, DEFLATE, None
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True

    def test_validate_geokey_exact(self, basic_geotiff):
        """Test exact geokey validation with real file."""
        rule = ValidationRule(
            product='Test',
            section='geokey',
            key='1024',  # GTModelTypeGeoKey
            key_type='geokey',
            description='GTModelTypeGeoKey',
            data_type='integer',
            constraint='exact',
            expected=1  # Projected
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True
        assert result.value == 1

    def test_validate_geokey_range(self, basic_geotiff):
        """Test range geokey validation with real file."""
        rule = ValidationRule(
            product='Test',
            section='geokey',
            key='3072',  # ProjectedCRSGeoKey (EPSG code)
            key_type='geokey',
            description='ProjectedCRSGeoKey',
            data_type='integer',
            constraint='range',
            expected={'min': 32601, 'max': 32660}  # UTM zones 1-60N
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True
        assert result.value == 32610


# =============================================================================
# Multi-Section Validation Tests
# =============================================================================

@pytest.mark.integration
class TestMultiSectionValidation:
    """Test validation across multiple sections."""

    def test_validate_all_sections(self, basic_geotiff):
        """Test validating rules across tag and geokey sections."""
        rules_by_section = {
            'tag': [
                ValidationRule(
                    product='Test',
                    section='tag',
                    key='259',
                    key_type='tag',
                    description='Compression',
                    data_type='integer',
                    constraint='exact',
                    expected=8
                ),
                ValidationRule(
                    product='Test',
                    section='tag',
                    key='339',  # SampleFormat
                    key_type='tag',
                    description='SampleFormat',
                    data_type='integer',
                    constraint='exact',
                    expected=3  # Float
                ),
            ],
            'geokey': [
                ValidationRule(
                    product='Test',
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

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            results = engine.validate_all_sections(rules_by_section)

        assert 'tag' in results
        assert 'geokey' in results
        assert len(results['tag']) == 2
        assert len(results['geokey']) == 1

        # All should pass
        for section_results in results.values():
            for result in section_results:
                assert result.passed is True

    def test_validate_file_function(self, basic_geotiff):
        """Test the validate_file convenience function."""
        rules_by_section = {
            'tag': [
                ValidationRule(
                    product='Test',
                    section='tag',
                    key='259',
                    key_type='tag',
                    description='Compression',
                    data_type='integer',
                    constraint='exact',
                    expected=8
                ),
            ],
            'geokey': [
                ValidationRule(
                    product='Test',
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

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            results, total, passed, failed, skipped = validate_file(
                extractor, rules_by_section
            )

        assert total == 2
        assert passed == 2
        assert failed == 0
        assert skipped == 0


# =============================================================================
# Constraint Type Tests with Real Files
# =============================================================================

@pytest.mark.integration
class TestConstraintTypesWithRealFiles:
    """Test all constraint types with real GeoTIFF files."""

    def test_exists_constraint(self, basic_geotiff):
        """Test exists constraint with real file."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='256',  # ImageWidth
            key_type='tag',
            description='ImageWidth',
            data_type='integer',
            constraint='exists',
            expected=None
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True
        assert result.value == 256  # Should have the actual width

    def test_forbidden_constraint_pass(self, basic_geotiff):
        """Test forbidden constraint passes when tag absent."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='65000',  # Non-existent tag
            key_type='tag',
            description='NonexistentTag',
            data_type='integer',
            constraint='forbidden',
            expected=None
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True

    def test_ranges_constraint(self, basic_geotiff):
        """Test ranges constraint with UTM zones."""
        rule = ValidationRule(
            product='Test',
            section='geokey',
            key='3072',  # ProjectedCRSGeoKey
            key_type='geokey',
            description='ProjectedCRSGeoKey',
            data_type='integer',
            constraint='ranges',
            expected=[
                {'min': 32601, 'max': 32660},  # UTM N
                {'min': 32701, 'max': 32760},  # UTM S
            ]
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True


# =============================================================================
# Multiband File Tests
# =============================================================================

@pytest.mark.integration
class TestMultibandValidation:
    """Test validation with multiband GeoTIFF files."""

    def test_validate_byte_compression(self, multiband_geotiff):
        """Test validation of byte data with LZW compression."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='259',
            key_type='tag',
            description='Compression',
            data_type='integer',
            constraint='exact',
            expected=5  # LZW
        )

        with MetadataExtractor(str(multiband_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True

    def test_validate_geographic_crs(self, multiband_geotiff):
        """Test validation of geographic CRS."""
        rule = ValidationRule(
            product='Test',
            section='geokey',
            key='1024',
            key_type='geokey',
            description='GTModelTypeGeoKey',
            data_type='integer',
            constraint='exact',
            expected=2  # Geographic
        )

        with MetadataExtractor(str(multiband_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True


# =============================================================================
# Failure Scenario Tests
# =============================================================================

@pytest.mark.integration
class TestFailureScenarios:
    """Test validation failure scenarios."""

    def test_wrong_compression_fails(self, basic_geotiff):
        """Test validation fails when compression doesn't match."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='259',
            key_type='tag',
            description='Compression',
            data_type='integer',
            constraint='exact',
            expected=5  # Expected LZW but file has DEFLATE
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.failed is True
        assert result.value == 8  # Actual value is DEFLATE

    def test_missing_tag_fails(self, basic_geotiff):
        """Test validation fails when required tag is missing."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='65000',  # Non-existent tag
            key_type='tag',
            description='NonexistentTag',
            data_type='integer',
            constraint='exact',
            expected=1
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.failed is True
        assert result.value is None

    def test_out_of_range_fails(self, basic_geotiff):
        """Test validation fails when value is out of range."""
        rule = ValidationRule(
            product='Test',
            section='geokey',
            key='3072',  # ProjectedCRSGeoKey
            key_type='geokey',
            description='ProjectedCRSGeoKey',
            data_type='integer',
            constraint='range',
            expected={'min': 1, 'max': 100}  # EPSG 32610 is outside this
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.failed is True


# =============================================================================
# Optional Rule Tests
# =============================================================================

@pytest.mark.integration
class TestOptionalRulesWithRealFiles:
    """Test optional rule handling with real files."""

    def test_optional_missing_tag_skips(self, basic_geotiff):
        """Test optional rule is skipped when tag is missing."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='65000',  # Non-existent tag
            key_type='tag',
            description='Optional Tag',
            data_type='integer',
            constraint='exists',
            expected=None,
            optional=True
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.skipped is True
        assert result.status == ValidationStatus.SKIP.value

    def test_optional_present_tag_validates(self, basic_geotiff):
        """Test optional rule validates when tag is present."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='259',
            key_type='tag',
            description='Compression',
            data_type='integer',
            constraint='exact',
            expected=8,
            optional=True
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True


# =============================================================================
# Result Structure Tests
# =============================================================================

@pytest.mark.integration
class TestResultStructure:
    """Test ValidationResult structure with real validation."""

    def test_result_contains_rule(self, basic_geotiff):
        """Test result contains the original rule."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='259',
            key_type='tag',
            description='Compression',
            data_type='integer',
            constraint='exact',
            expected=8
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.rule is rule
        assert result.rule.key == '259'
        assert result.rule.constraint == 'exact'

    def test_result_message_is_descriptive(self, basic_geotiff):
        """Test result message is descriptive."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='259',
            key_type='tag',
            description='Compression',
            data_type='integer',
            constraint='exact',
            expected=8
        )

        with MetadataExtractor(str(basic_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        # Message should mention the tag and result
        assert 'Tag' in result.message
        assert '259' in result.message


# =============================================================================
# DEM Validation Tests
# =============================================================================

@pytest.mark.integration
class TestDEMValidation:
    """Test validation with DEM-style files."""

    def test_validate_dem_float_format(self, dem_geotiff):
        """Test DEM has correct float sample format."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='339',  # SampleFormat
            key_type='tag',
            description='SampleFormat',
            data_type='integer',
            constraint='exact',
            expected=3  # IEEE floating point
        )

        with MetadataExtractor(str(dem_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True

    def test_validate_dem_bits_per_sample(self, dem_geotiff):
        """Test DEM has correct bits per sample."""
        rule = ValidationRule(
            product='Test',
            section='tag',
            key='258',  # BitsPerSample
            key_type='tag',
            description='BitsPerSample',
            data_type='integer',
            constraint='exact',
            expected=32
        )

        with MetadataExtractor(str(dem_geotiff)) as extractor:
            engine = ValidationEngine(extractor)
            result = engine.validate_rule(rule)

        assert result.passed is True
