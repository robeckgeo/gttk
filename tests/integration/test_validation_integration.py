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
import shutil
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
    load_validation_rules,
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


# =============================================================================
# File-name placeholders, against a real file and a real rules file
# =============================================================================

TILE_RULES = r'''
[TILE-PLACEHOLDERS-TEST]
title = "Tiled DEM with file-name placeholders"
author = "GeoTIFF ToolKit tests"
updated = "2026-10-21"

[TILE-PLACEHOLDERS-TEST.filename]
pattern = "^TILE_(?P<geocell>[NS]\\d{2}[EW]\\d{3})_(?P<edition>\\d{2})_DEM$"

[[TILE-PLACEHOLDERS-TEST.tag]]
tag = 258
description = "BitsPerSample"
data_type = "integer"
constraint = "exact"
expected = 32

[[TILE-PLACEHOLDERS-TEST.gdal]]
name = "IDENTIFIER"
description = "Identifier is the file stem"
data_type = "string"
constraint = "exact"
expected = "{stem}"

[[TILE-PLACEHOLDERS-TEST.gdal]]
name = "TILE_ID"
description = "Tile id is the geocell from the file name"
data_type = "string"
constraint = "exact"
expected = "{geocell}"

[[TILE-PLACEHOLDERS-TEST.geo]]
xpath = "/gmd:MD_Metadata/gmd:fileIdentifier/gco:CharacterString"
description = "The embedded record names the tile"
data_type = "string"
constraint = "regex"
expected = "^SRC_{geocell}_\\d{2}(\\.xml)?$"
'''

# ISO 19139 in the GEO_METADATA tag (50909), naming the tile's source record.
TILE_RECORD = '''<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco">
  <gmd:fileIdentifier>
    <gco:CharacterString>SRC_N00E000_01.xml</gco:CharacterString>
  </gmd:fileIdentifier>
</gmd:MD_Metadata>
'''


@pytest.fixture
def tile_geotiff(temp_dir):
    """TILE_N00E000_01_DEM.tif: a DEM whose metadata names its own tile."""
    filepath = temp_dir / 'TILE_N00E000_01_DEM.tif'
    MockGeoTIFF(width=64, height=64, bands=1, data_type=gdal.GDT_Float32, crs='EPSG:4326').save_to_file(filepath)

    ds = gdal.Open(str(filepath), gdal.GA_Update)
    ds.SetMetadataItem('IDENTIFIER', 'TILE_N00E000_01_DEM')
    ds.SetMetadataItem('TILE_ID', 'N00E000')
    # GDAL stores the GEO_METADATA item in tag 50909, the tag the geo section reads.
    ds.SetMetadataItem('GEO_METADATA', TILE_RECORD)
    ds.FlushCache()
    ds = None
    return filepath


@pytest.fixture
def tile_rules_dir(temp_dir):
    """A rules directory holding only TILE-PLACEHOLDERS-TEST."""
    rules_dir = temp_dir / 'rules'
    rules_dir.mkdir()
    (rules_dir / 'tile_rules.toml').write_text(TILE_RULES, encoding='utf-8')
    return rules_dir


@pytest.mark.integration
class TestFilenamePlaceholdersWithRealFiles:
    """The rules file, the loader, the extractor and the engine, end to end."""

    def test_rules_loaded_from_toml_resolve_against_the_file(self, tile_geotiff, tile_rules_dir):
        rules, _ = load_validation_rules(tile_rules_dir, 'TILE-PLACEHOLDERS-TEST')
        with MetadataExtractor(str(tile_geotiff)) as extractor:
            results, total, passed, failed, skipped = validate_file(extractor, rules)

        messages = [r.message for section in results.values() for r in section]
        assert (total, passed, failed, skipped) == (4, 4, 0, 0), messages
        assert results['gdal'][0].rule.expected == 'TILE_N00E000_01_DEM'
        assert results['gdal'][1].rule.expected == 'N00E000'
        assert results['geo'][0].rule.expected == r'^SRC_N00E000_\d{2}(\.xml)?$'
        assert [m.endswith(' (from filename)') for m in messages] == [False, True, True, True]
        # The loaded rules still read as written, ready for the next file
        assert rules['gdal'][1].expected == '{geocell}'

    def test_a_tile_named_outside_the_pattern_fails_only_the_placeholder_rules(self, tile_geotiff, tile_rules_dir):
        misnamed = tile_geotiff.with_name('TILE_bad.tif')
        shutil.copy(tile_geotiff, misnamed)
        rules, _ = load_validation_rules(tile_rules_dir, 'TILE-PLACEHOLDERS-TEST')
        with MetadataExtractor(str(misnamed)) as extractor:
            results, total, passed, failed, skipped = validate_file(extractor, rules)

        assert (total, passed, failed, skipped) == (4, 1, 3, 0)
        assert results['tag'][0].passed
        for result in results['gdal'] + results['geo']:
            assert result.failed
            assert result.value is not None
            assert "Filename 'TILE_bad.tif' does not match filename.pattern" in result.message

    def test_validate_single_file_json_reports_the_resolved_expected(self, tile_geotiff, tile_rules_dir):
        from gttk.tools.validate_metadata import validate_single_file

        rules, rules_file = load_validation_rules(tile_rules_dir, 'TILE-PLACEHOLDERS-TEST')
        report = validate_single_file(tile_geotiff, rules, 'TILE-PLACEHOLDERS-TEST', rules_file)

        assert (report['total_rules'], report['passed'], report['failed']) == (4, 4, 0)
        identifier = report['validation']['gdal'][0]
        assert identifier['key'] == 'IDENTIFIER'
        assert identifier['expected'] == 'TILE_N00E000_01_DEM'
        assert identifier['actual'] == 'TILE_N00E000_01_DEM'
        assert identifier['status'] == 'PASS'
        assert 'from filename' in identifier['message']
        assert report['validation']['geo'][0]['expected'] == r'^SRC_N00E000_\d{2}(\.xml)?$'
