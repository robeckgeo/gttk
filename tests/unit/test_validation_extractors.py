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
Unit tests for validation value extractors.

This module tests the ValueExtractor class defined in
gttk.utils.validation.extractors, which extracts values from
GeoTIFF files for validation against rules.

Test coverage target: 95%+

Organization:
- Tests use mock objects to simulate MetadataExtractor
- Tests verify extraction from all supported section types
- Tests verify caching behavior and error handling
"""

import pytest
from unittest.mock import Mock, MagicMock
from dataclasses import dataclass
from typing import Optional, List

from gttk.utils.validation.extractors import ValueExtractor


# =============================================================================
# Mock Data Classes
# =============================================================================

@dataclass
class MockTiffTag:
    """Mock TiffTag for testing."""
    code: int
    value: any
    name: str = ""
    type_name: str = ""


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


@dataclass
class MockJsonString:
    """Mock JsonString for testing."""
    json_string: Optional[str]


# =============================================================================
# Test Fixtures
# =============================================================================

@dataclass
class MockStatisticsBand:
    """Mock StatisticsBand for testing."""
    minimum: float = 0.0
    maximum: float = 255.0
    mean: float = 127.5
    std_dev: float = 50.0
    valid_percent: float = 100.0


@pytest.fixture
def mock_extractor():
    """Create a mock MetadataExtractor."""
    extractor = Mock()

    # Default returns for methods
    extractor.extract_tags.return_value = []
    extractor.extract_geokeys.return_value = []
    extractor.extract_gdal_metadata.return_value = None
    extractor.extract_geo_metadata.return_value = None
    extractor.extract_xmp_metadata.return_value = None
    extractor.extract_xml_metadata.return_value = None
    extractor.extract_projjson_string.return_value = None
    extractor.extract_statistics.return_value = []  # Default to empty list
    extractor.filepath = '/tmp/test.tif'

    return extractor


@pytest.fixture
def sample_tags():
    """Sample TIFF tags for testing."""
    return [
        MockTiffTag(code=256, value=1024, name="ImageWidth"),
        MockTiffTag(code=257, value=768, name="ImageLength"),
        MockTiffTag(code=258, value=32, name="BitsPerSample"),
        MockTiffTag(code=259, value=5, name="Compression"),
        MockTiffTag(code=262, value=1, name="PhotometricInterpretation"),
        MockTiffTag(code=305, value="GTTK 1.0", name="Software"),
    ]


@pytest.fixture
def sample_geokeys():
    """Sample GeoKeys for testing."""
    return [
        MockGeoKey(id=1024, value=1, name="GTModelTypeGeoKey"),
        MockGeoKey(id=1025, value=1, name="GTRasterTypeGeoKey"),
        MockGeoKey(id=3072, value=32610, name="ProjectedCRSGeoKey"),
        MockGeoKey(id=3076, value=9001, name="ProjLinearUnitsGeoKey"),
    ]


@pytest.fixture
def sample_gdal_xml():
    """Sample GDAL metadata XML - uses non-statistics keys for testing."""
    return '''<GDALMetadata>
  <Item name="AREA_OR_POINT">Area</Item>
  <Item name="TIFFTAG_DATETIME">2026-01-15</Item>
  <Item name="TIFFTAG_SOFTWARE">GTTK 1.0</Item>
</GDALMetadata>'''


@pytest.fixture
def sample_gdal_xml_with_samples():
    """Sample GDAL metadata XML with sample-specific items."""
    return '''<GDALMetadata>
  <Item name="AREA_OR_POINT">Point</Item>
  <Item name="COLORINTERP" sample="0">Red</Item>
  <Item name="COLORINTERP" sample="1">Green</Item>
  <Item name="COLORINTERP" sample="2">Blue</Item>
</GDALMetadata>'''


@pytest.fixture
def sample_geo_xml():
    """Sample GEO_METADATA XML."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<mdb:MD_Metadata xmlns:mdb="http://standards.iso.org/iso/19115/-3/mdb/2.0">
  <mdb:metadataIdentifier>test-id</mdb:metadataIdentifier>
</mdb:MD_Metadata>'''


@pytest.fixture
def sample_projjson():
    """Sample PROJJSON string."""
    return '''{
  "type": "ProjectedCRS",
  "name": "WGS 84 / UTM zone 10N",
  "id": {
    "authority": "EPSG",
    "code": 32610
  }
}'''


# =============================================================================
# ValueExtractor Initialization Tests
# =============================================================================

@pytest.mark.unit
class TestValueExtractorInit:
    """Test ValueExtractor initialization."""

    def test_init_stores_extractor(self, mock_extractor):
        """Test that extractor is stored."""
        ve = ValueExtractor(mock_extractor)
        assert ve.extractor is mock_extractor

    def test_init_caches_empty(self, mock_extractor):
        """Test that caches are initialized as None."""
        ve = ValueExtractor(mock_extractor)
        assert ve._tags_cache is None
        assert ve._geokeys_cache is None
        assert ve._gdal_metadata_cache is None
        assert ve._gdal_items_cache is None


# =============================================================================
# Tag Extraction Tests
# =============================================================================

@pytest.mark.unit
class TestExtractTag:
    """Test extract_tag method."""

    def test_extract_tag_success(self, mock_extractor, sample_tags):
        """Test successful tag extraction."""
        mock_extractor.extract_tags.return_value = sample_tags
        ve = ValueExtractor(mock_extractor)

        # Test extracting BitsPerSample (tag 258)
        value = ve.extract_tag('258')
        assert value == 32

    def test_extract_tag_string_value(self, mock_extractor, sample_tags):
        """Test extracting string tag value."""
        mock_extractor.extract_tags.return_value = sample_tags
        ve = ValueExtractor(mock_extractor)

        # Test extracting Software tag (tag 305)
        value = ve.extract_tag('305')
        assert value == "GTTK 1.0"

    def test_extract_tag_not_found(self, mock_extractor, sample_tags):
        """Test extracting non-existent tag returns None."""
        mock_extractor.extract_tags.return_value = sample_tags
        ve = ValueExtractor(mock_extractor)

        # Tag 999 doesn't exist
        value = ve.extract_tag('999')
        assert value is None

    def test_extract_tag_empty_tags(self, mock_extractor):
        """Test extracting from empty tags list returns None."""
        mock_extractor.extract_tags.return_value = []
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_tag('258')
        assert value is None

    def test_extract_tag_caches_result(self, mock_extractor, sample_tags):
        """Test that tags are cached after first extraction."""
        mock_extractor.extract_tags.return_value = sample_tags
        ve = ValueExtractor(mock_extractor)

        # First extraction
        ve.extract_tag('258')
        # Second extraction
        ve.extract_tag('259')

        # extract_tags should only be called once due to caching
        assert mock_extractor.extract_tags.call_count == 1


# =============================================================================
# GeoKey Extraction Tests
# =============================================================================

@pytest.mark.unit
class TestExtractGeokey:
    """Test extract_geokey method."""

    def test_extract_geokey_success(self, mock_extractor, sample_geokeys):
        """Test successful geokey extraction."""
        mock_extractor.extract_geokeys.return_value = sample_geokeys
        ve = ValueExtractor(mock_extractor)

        # Test extracting GTModelTypeGeoKey (id 1024)
        value = ve.extract_geokey('1024')
        assert value == 1

    def test_extract_geokey_epsg_code(self, mock_extractor, sample_geokeys):
        """Test extracting EPSG code from geokey."""
        mock_extractor.extract_geokeys.return_value = sample_geokeys
        ve = ValueExtractor(mock_extractor)

        # Test extracting ProjectedCRSGeoKey (id 3072)
        value = ve.extract_geokey('3072')
        assert value == 32610

    def test_extract_geokey_not_found(self, mock_extractor, sample_geokeys):
        """Test extracting non-existent geokey returns None."""
        mock_extractor.extract_geokeys.return_value = sample_geokeys
        ve = ValueExtractor(mock_extractor)

        # GeoKey 9999 doesn't exist
        value = ve.extract_geokey('9999')
        assert value is None

    def test_extract_geokey_empty(self, mock_extractor):
        """Test extracting from empty geokeys returns None."""
        mock_extractor.extract_geokeys.return_value = []
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_geokey('1024')
        assert value is None

    def test_extract_geokey_caches_result(self, mock_extractor, sample_geokeys):
        """Test that geokeys are cached after first extraction."""
        mock_extractor.extract_geokeys.return_value = sample_geokeys
        ve = ValueExtractor(mock_extractor)

        # First extraction
        ve.extract_geokey('1024')
        # Second extraction
        ve.extract_geokey('1025')

        # extract_geokeys should only be called once due to caching
        assert mock_extractor.extract_geokeys.call_count == 1


# =============================================================================
# GDAL Metadata Extraction Tests
# =============================================================================

@pytest.mark.unit
class TestExtractGdal:
    """Test extract_gdal method."""

    def test_extract_gdal_success(self, mock_extractor, sample_gdal_xml):
        """Test successful GDAL metadata extraction for standard items."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content=sample_gdal_xml)
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_gdal('AREA_OR_POINT')
        assert value == 'Area'

    def test_extract_gdal_multiple_items(self, mock_extractor, sample_gdal_xml):
        """Test extracting multiple GDAL metadata items."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content=sample_gdal_xml)
        ve = ValueExtractor(mock_extractor)

        assert ve.extract_gdal('AREA_OR_POINT') == 'Area'
        assert ve.extract_gdal('TIFFTAG_DATETIME') == '2026-01-15'
        assert ve.extract_gdal('TIFFTAG_SOFTWARE') == 'GTTK 1.0'

    def test_extract_gdal_not_found(self, mock_extractor, sample_gdal_xml):
        """Test extracting non-existent GDAL item returns None."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content=sample_gdal_xml)
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_gdal('NONEXISTENT_ITEM')
        assert value is None

    def test_extract_gdal_no_metadata(self, mock_extractor):
        """Test extracting standard item when no GDAL metadata exists."""
        mock_extractor.extract_gdal_metadata.return_value = None
        ve = ValueExtractor(mock_extractor)

        # Standard items return None when metadata is missing
        value = ve.extract_gdal('AREA_OR_POINT')
        assert value is None

    def test_extract_gdal_empty_content(self, mock_extractor):
        """Test extracting when GDAL metadata content is empty."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content=None)
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_gdal('AREA_OR_POINT')
        assert value is None

    def test_extract_gdal_invalid_xml(self, mock_extractor):
        """Test extracting from invalid XML returns None."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content='<invalid xml')
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_gdal('AREA_OR_POINT')
        assert value is None

    def test_extract_gdal_caches_items(self, mock_extractor, sample_gdal_xml):
        """Test that GDAL items are cached after first parse."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content=sample_gdal_xml)
        ve = ValueExtractor(mock_extractor)

        # First extraction
        ve.extract_gdal('AREA_OR_POINT')
        # Second extraction
        ve.extract_gdal('TIFFTAG_DATETIME')

        # extract_gdal_metadata should only be called once due to caching
        assert mock_extractor.extract_gdal_metadata.call_count == 1


@pytest.mark.unit
class TestExtractGdalOnDemandStatistics:
    """Test extract_gdal on-demand statistics calculation."""

    def test_extract_statistics_single_band(self, mock_extractor):
        """Test on-demand statistics extraction for single band."""
        mock_extractor.extract_statistics.return_value = [
            MockStatisticsBand(minimum=-430.0, maximum=8850.0, mean=150.5, std_dev=1000.0, valid_percent=99.5)
        ]
        ve = ValueExtractor(mock_extractor)

        # With band suffix
        assert ve.extract_gdal('STATISTICS_MINIMUM:0') == -430.0
        assert ve.extract_gdal('STATISTICS_MAXIMUM:0') == 8850.0
        assert ve.extract_gdal('STATISTICS_MEAN:0') == 150.5
        assert ve.extract_gdal('STATISTICS_STDDEV:0') == 1000.0
        assert ve.extract_gdal('STATISTICS_VALID_PERCENT:0') == 99.5

    def test_extract_statistics_all_bands(self, mock_extractor):
        """Test on-demand statistics extraction for all bands (no suffix)."""
        mock_extractor.extract_statistics.return_value = [
            MockStatisticsBand(minimum=0.0, maximum=255.0),
            MockStatisticsBand(minimum=10.0, maximum=250.0),
            MockStatisticsBand(minimum=20.0, maximum=240.0),
        ]
        ve = ValueExtractor(mock_extractor)

        # Without band suffix - returns list of all band values
        result = ve.extract_gdal('STATISTICS_MINIMUM')
        assert result == [0.0, 10.0, 20.0]

        result = ve.extract_gdal('STATISTICS_MAXIMUM')
        assert result == [255.0, 250.0, 240.0]

    def test_extract_statistics_no_bands(self, mock_extractor):
        """Test statistics extraction when no bands available."""
        mock_extractor.extract_statistics.return_value = []
        ve = ValueExtractor(mock_extractor)

        # No bands available - returns None
        assert ve.extract_gdal('STATISTICS_MINIMUM') is None
        assert ve.extract_gdal('STATISTICS_MINIMUM:0') is None

    def test_extract_statistics_band_out_of_range(self, mock_extractor):
        """Test statistics extraction with invalid band index."""
        mock_extractor.extract_statistics.return_value = [
            MockStatisticsBand(minimum=0.0, maximum=255.0)
        ]
        ve = ValueExtractor(mock_extractor)

        # Band 1 doesn't exist (only band 0)
        assert ve.extract_gdal('STATISTICS_MINIMUM:1') is None
        assert ve.extract_gdal('STATISTICS_MINIMUM:99') is None


@pytest.mark.unit
class TestExtractGdalColorInterp:
    """Test extract_gdal COLORINTERP functionality."""

    def test_extract_colorinterp_from_metadata(self, mock_extractor, sample_gdal_xml_with_samples):
        """Test COLORINTERP extraction from GDAL_METADATA XML."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content=sample_gdal_xml_with_samples)
        mock_extractor.extract_statistics.return_value = [
            MockStatisticsBand(), MockStatisticsBand(), MockStatisticsBand()
        ]
        ve = ValueExtractor(mock_extractor)

        assert ve.extract_gdal('COLORINTERP:0') == 'Red'
        assert ve.extract_gdal('COLORINTERP:1') == 'Green'
        assert ve.extract_gdal('COLORINTERP:2') == 'Blue'

    def test_extract_colorinterp_all_bands(self, mock_extractor, sample_gdal_xml_with_samples):
        """Test COLORINTERP extraction for all bands."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content=sample_gdal_xml_with_samples)
        mock_extractor.extract_statistics.return_value = [
            MockStatisticsBand(), MockStatisticsBand(), MockStatisticsBand()
        ]
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_gdal('COLORINTERP')
        assert result == ['Red', 'Green', 'Blue']


# =============================================================================
# Section Content Tests
# =============================================================================

@pytest.mark.unit
class TestGetSectionContent:
    """Test get_section_content method."""

    def test_get_tag_section(self, mock_extractor, sample_tags):
        """Test getting tag section content."""
        mock_extractor.extract_tags.return_value = sample_tags
        ve = ValueExtractor(mock_extractor)

        content = ve.get_section_content('tag')
        assert content == sample_tags

    def test_get_geokey_section(self, mock_extractor, sample_geokeys):
        """Test getting geokey section content."""
        mock_extractor.extract_geokeys.return_value = sample_geokeys
        ve = ValueExtractor(mock_extractor)

        content = ve.get_section_content('geokey')
        assert content == sample_geokeys

    def test_get_gdal_section(self, mock_extractor):
        """Test getting GDAL section content always returns True.

        GDAL section is always available because statistics can be computed
        on-demand even without GDAL_METADATA tag.
        """
        ve = ValueExtractor(mock_extractor)

        # GDAL section always returns True (statistics can be computed on-demand)
        content = ve.get_section_content('gdal')
        assert content is True

    def test_get_geo_section(self, mock_extractor, sample_geo_xml):
        """Test getting geo section content."""
        mock_extractor.extract_geo_metadata.return_value = MockXmlMetadata(content=sample_geo_xml)
        ve = ValueExtractor(mock_extractor)

        content = ve.get_section_content('geo')
        assert content == sample_geo_xml

    def test_get_projjson_section(self, mock_extractor, sample_projjson):
        """Test getting projjson section content."""
        mock_extractor.extract_projjson_string.return_value = MockJsonString(json_string=sample_projjson)
        ve = ValueExtractor(mock_extractor)

        content = ve.get_section_content('projjson')
        assert content == sample_projjson

    def test_get_missing_section(self, mock_extractor):
        """Test getting missing section returns None."""
        mock_extractor.extract_tags.return_value = None
        ve = ValueExtractor(mock_extractor)

        content = ve.get_section_content('tag')
        assert content is None

    def test_get_unknown_section(self, mock_extractor):
        """Test getting unknown section type returns None."""
        ve = ValueExtractor(mock_extractor)

        content = ve.get_section_content('unknown_section')
        assert content is None


# =============================================================================
# XPath Extraction Tests
# =============================================================================

@pytest.mark.unit
class TestExtractXpath:
    """Test extract_xpath method."""

    def test_extract_xpath_simple(self, mock_extractor):
        """Test simple XPath extraction."""
        xml = '<root><item>value</item></root>'
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_xpath('//item', xml)
        assert value == 'value'

    def test_extract_xpath_with_namespace(self, mock_extractor, sample_geo_xml):
        """Test XPath extraction with namespace."""
        ve = ValueExtractor(mock_extractor)

        # This will require namespace handling
        value = ve.extract_xpath('//mdb:metadataIdentifier', sample_geo_xml)
        assert value == 'test-id'

    def test_extract_xpath_not_found(self, mock_extractor):
        """Test XPath extraction returns None when not found."""
        xml = '<root><item>value</item></root>'
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_xpath('//nonexistent', xml)
        assert value is None

    def test_extract_xpath_empty_content(self, mock_extractor):
        """Test XPath extraction on empty content returns None."""
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_xpath('//item', '')
        assert value is None

    def test_extract_xpath_none_content(self, mock_extractor):
        """Test XPath extraction on None content returns None."""
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_xpath('//item', None)
        assert value is None

    def test_extract_xpath_invalid_xml(self, mock_extractor):
        """Test XPath extraction on invalid XML returns None."""
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_xpath('//item', '<invalid')
        assert value is None


# =============================================================================
# PROJJSON Extraction Tests
# =============================================================================

@pytest.mark.unit
class TestExtractProjjson:
    """Test extract_projjson method."""

    def test_extract_projjson_simple(self, mock_extractor, sample_projjson):
        """Test simple PROJJSON extraction."""
        mock_extractor.extract_projjson_string.return_value = MockJsonString(json_string=sample_projjson)
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_projjson('$.type')
        assert value == 'ProjectedCRS'

    def test_extract_projjson_nested(self, mock_extractor, sample_projjson):
        """Test nested PROJJSON extraction."""
        mock_extractor.extract_projjson_string.return_value = MockJsonString(json_string=sample_projjson)
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_projjson('$.id.code')
        assert value == 32610

    def test_extract_projjson_no_prefix(self, mock_extractor, sample_projjson):
        """Test PROJJSON extraction without $. prefix."""
        mock_extractor.extract_projjson_string.return_value = MockJsonString(json_string=sample_projjson)
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_projjson('name')
        assert value == 'WGS 84 / UTM zone 10N'

    def test_extract_projjson_not_found(self, mock_extractor, sample_projjson):
        """Test PROJJSON extraction returns None when path not found."""
        mock_extractor.extract_projjson_string.return_value = MockJsonString(json_string=sample_projjson)
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_projjson('$.nonexistent')
        assert value is None

    def test_extract_projjson_no_content(self, mock_extractor):
        """Test PROJJSON extraction when no content exists."""
        mock_extractor.extract_projjson_string.return_value = None
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_projjson('$.type')
        assert value is None

    def test_extract_projjson_invalid_json(self, mock_extractor):
        """Test PROJJSON extraction on invalid JSON returns None."""
        mock_extractor.extract_projjson_string.return_value = MockJsonString(json_string='{invalid}')
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_projjson('$.type')
        assert value is None


# =============================================================================
# Generic Extract Value Tests
# =============================================================================

@pytest.mark.unit
class TestExtractValue:
    """Test extract_value method."""

    def test_extract_value_tag(self, mock_extractor, sample_tags):
        """Test extract_value for tag section."""
        mock_extractor.extract_tags.return_value = sample_tags
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_value('tag', '258')
        assert value == 32

    def test_extract_value_geokey(self, mock_extractor, sample_geokeys):
        """Test extract_value for geokey section."""
        mock_extractor.extract_geokeys.return_value = sample_geokeys
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_value('geokey', '1024')
        assert value == 1

    def test_extract_value_gdal(self, mock_extractor, sample_gdal_xml):
        """Test extract_value for gdal section."""
        mock_extractor.extract_gdal_metadata.return_value = MockXmlMetadata(content=sample_gdal_xml)
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_value('gdal', 'AREA_OR_POINT')
        assert value == 'Area'

    def test_extract_value_projjson(self, mock_extractor, sample_projjson):
        """Test extract_value for projjson section."""
        mock_extractor.extract_projjson_string.return_value = MockJsonString(json_string=sample_projjson)
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_value('projjson', '$.type')
        assert value == 'ProjectedCRS'

    def test_extract_value_unknown_section(self, mock_extractor):
        """Test extract_value for unknown section returns None."""
        ve = ValueExtractor(mock_extractor)

        value = ve.extract_value('unknown', 'key')
        assert value is None


# =============================================================================
# Type Conversion Tests
# =============================================================================

@pytest.mark.unit
class TestConvertValue:
    """Test convert_value static method."""

    def test_convert_to_integer(self):
        """Test converting to integer."""
        assert ValueExtractor.convert_value('42', 'integer') == 42
        assert ValueExtractor.convert_value(42.5, 'integer') == 42

    def test_convert_list_to_integer(self):
        """Test converting list to integers."""
        result = ValueExtractor.convert_value(['1', '2', '3'], 'integer')
        assert result == [1, 2, 3]

    def test_convert_to_float(self):
        """Test converting to float."""
        assert ValueExtractor.convert_value('3.14', 'float') == 3.14
        assert ValueExtractor.convert_value(42, 'float') == 42.0

    def test_convert_list_to_float(self):
        """Test converting list to floats."""
        result = ValueExtractor.convert_value(['1.5', '2.5'], 'float')
        assert result == [1.5, 2.5]

    def test_convert_to_string(self):
        """Test converting to string."""
        assert ValueExtractor.convert_value(42, 'string') == '42'
        assert ValueExtractor.convert_value(3.14, 'string') == '3.14'

    def test_convert_to_boolean(self):
        """Test converting to boolean."""
        assert ValueExtractor.convert_value('true', 'boolean') is True
        assert ValueExtractor.convert_value('yes', 'boolean') is True
        assert ValueExtractor.convert_value('1', 'boolean') is True
        assert ValueExtractor.convert_value('false', 'boolean') is False
        assert ValueExtractor.convert_value('no', 'boolean') is False
        assert ValueExtractor.convert_value(True, 'boolean') is True

    def test_convert_none_returns_none(self):
        """Test converting None returns None."""
        assert ValueExtractor.convert_value(None, 'integer') is None
        assert ValueExtractor.convert_value(None, 'string') is None

    def test_convert_unknown_type(self):
        """Test converting with unknown type returns original."""
        assert ValueExtractor.convert_value('test', 'unknown') == 'test'

    def test_convert_invalid_value(self):
        """Test converting invalid value returns original."""
        # 'abc' cannot be converted to integer, should return original
        assert ValueExtractor.convert_value('abc', 'integer') == 'abc'
