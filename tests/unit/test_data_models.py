#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit (GTTK)
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2025, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
Unit tests for GTTK data models.

This module tests all dataclasses defined in gttk.utils.data_models, including:
- Report framework classes (MenuItem, ReportSection, SectionConfig)
- Domain model classes (TiffTag, GeoKey, StatisticsBand, etc.)
- Wrapper classes (TiffTagsData, StatisticsData, IfdInfoData)
- Comparison classes (DifferencesComparison, etc.)

Test coverage target: 95%+

Organization:
- Each dataclass gets its own test class
- Tests verify instantiation, field assignments, and helper methods
- Edge cases and validation are tested
- Clear docstrings explain what each test verifies
"""

import pytest
from gttk.utils.data_models import (
    TiffTag,
    GeoKey,
    StatisticsBand,
    HistogramImage,
    GeoReference,
    GeoTransform,
    GeoExtents,
    BoundingBox,
    TileInfo,
    IfdInfo,
    WktString,
    JsonString,
    CogValidation,
    XmlMetadata,
    ReportSection,
    MenuItem,
    SectionConfig,
    TiffTagsData,
    StatisticsData,
    IfdInfoData,
    DifferencesComparison,
    IfdInfoComparison,
    StatisticsComparison,
    HistogramComparison,
    CogValidationComparison,
)


# =============================================================================
# Report Framework Classes Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.models
class TestMenuItem:
    """Test MenuItem data model."""
    
    def test_instantiation_with_all_fields(self):
        """Test creating MenuItem with all required fields."""
        item = MenuItem(
            anchor='statistics',
            name='Stats',
            title='Statistics',
            icon='chart'
        )
        
        assert item.anchor == 'statistics'
        assert item.name == 'Stats'
        assert item.title == 'Statistics'
        assert item.icon == 'chart'
    
    def test_menu_item_is_mutable(self):
        """Test that MenuItem uses correct dataclass configuration."""
        item = MenuItem(anchor='test', name='Test', title='Test', icon='icon')
        # MenuItem is not frozen, so this should work
        item.name = 'Modified'
        assert item.name == 'Modified'


@pytest.mark.unit
@pytest.mark.models
class TestReportSection:
    """Test ReportSection data model."""
    
    def test_instantiation_with_required_fields(self):
        """Test creating ReportSection with minimum required fields."""
        section = ReportSection(
            id='tags',
            title='TIFF Tags',
            menu_name='Tags',
            data=[1, 2, 3]
        )
        
        assert section.id == 'tags'
        assert section.title == 'TIFF Tags'
        assert section.menu_name == 'Tags'
        assert section.data == [1, 2, 3]
        assert section.enabled is True  # Default value
    
    def test_is_enabled_method(self):
        """Test that is_enabled correctly returns enabled status."""
        enabled_section = ReportSection(
            id='test', title='Test', menu_name='Test',
            data=[], enabled=True
        )
        assert enabled_section.is_enabled() is True
        
        disabled_section = ReportSection(
            id='test', title='Test', menu_name='Test',
            data=[], enabled=False
        )
        assert disabled_section.is_enabled() is False
    
    def test_has_data_with_list(self):
        """Test has_data with list data."""
        section_with_data = ReportSection(
            id='test', title='Test', menu_name='Test',
            data=[1, 2, 3]
        )
        assert section_with_data.has_data() is True
        
        section_empty = ReportSection(
            id='test', title='Test', menu_name='Test',
            data=[]
        )
        assert section_empty.has_data() is False
    
    def test_has_data_with_none(self):
        """Test has_data with None data."""
        section = ReportSection(
            id='test', title='Test', menu_name='Test',
            data=None
        )
        assert section.has_data() is False
    
    def test_has_data_with_string(self):
        """Test has_data with string data."""
        section_with_str = ReportSection(
            id='test', title='Test', menu_name='Test',
            data='some content'
        )
        assert section_with_str.has_data() is True
        
        section_empty_str = ReportSection(
            id='test', title='Test', menu_name='Test',
            data=''
        )
        assert section_empty_str.has_data() is False


@pytest.mark.unit
@pytest.mark.models
class TestSectionConfig:
    """Test SectionConfig data model."""
    
    def test_instantiation(self):
        """Test creating SectionConfig with all fields."""
        config = SectionConfig(
            id='geokeys',
            title='GeoKey Directory',
            menu_name='GeoKeys',
            icon='key',
            renderer='render_geokeys'
        )
        
        assert config.id == 'geokeys'
        assert config.title == 'GeoKey Directory'
        assert config.menu_name == 'GeoKeys'
        assert config.icon == 'key'
        assert config.renderer == 'render_geokeys'
    
# =============================================================================
# Domain Model Classes Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.models
class TestTiffTag:
    """Test TiffTag data model."""
    
    def test_instantiation_basic(self):
        """Test creating TiffTag with basic properties."""
        tag = TiffTag(
            code=256,
            name="ImageWidth",
            value=1024
        )
        
        assert tag.code == 256
        assert tag.name == "ImageWidth"
        assert tag.value == 1024
        assert tag.interpretation is None
    
    def test_instantiation_with_interpretation(self):
        """Test creating TiffTag with interpretation."""
        tag = TiffTag(
            code=259,
            name="Compression",
            value=5,
            interpretation="LZW"
        )
        
        assert tag.code == 259
        assert tag.value == 5
        assert tag.interpretation == "LZW"
    
    def test_is_array_with_list(self):
        """Test is_array returns True for list values."""
        tag = TiffTag(code=273, name="StripOffsets", value=[100, 200, 300])
        assert tag.is_array() is True
    
    def test_is_array_with_tuple(self):
        """Test is_array returns True for tuple values."""
        tag = TiffTag(code=273, name="StripOffsets", value=(100, 200, 300))
        assert tag.is_array() is True
    
    def test_is_array_with_scalar(self):
        """Test is_array returns False for scalar values."""
        tag = TiffTag(code=256, name="ImageWidth", value=1024)
        assert tag.is_array() is False
    
    def test_is_numeric_with_int(self):
        """Test is_numeric returns True for integer values."""
        tag = TiffTag(code=256, name="ImageWidth", value=1024)
        assert tag.is_numeric() is True
    
    def test_is_numeric_with_float(self):
        """Test is_numeric returns True for float values."""
        tag = TiffTag(code=282, name="XResolution", value=300.0)
        assert tag.is_numeric() is True
    
    def test_is_numeric_with_string(self):
        """Test is_numeric returns False for string values."""
        tag = TiffTag(code=270, name="ImageDescription", value="Test image")
        assert tag.is_numeric() is False
    
    def test_is_string(self):
        """Test is_string method."""
        tag_string = TiffTag(code=270, name="ImageDescription", value="Test")
        assert tag_string.is_string() is True
        
        tag_int = TiffTag(code=256, name="ImageWidth", value=1024)
        assert tag_int.is_string() is False


@pytest.mark.unit
@pytest.mark.models
class TestGeoKey:
    """Test GeoKey data model."""
    
    def test_instantiation_basic(self):
        """Test creating GeoKey with basic properties."""
        key = GeoKey(
            id=1024,
            name="GTModelTypeGeoKey",
            value=2,
            value_text="2 (ModelTypeGeographic)",
            location=0,
            count=1
        )
        
        assert key.id == 1024
        assert key.name == "GTModelTypeGeoKey"
        assert key.value == 2
        assert key.value_text == "2 (ModelTypeGeographic)"
        assert key.location == 0
        assert key.count == 1
        assert key.is_citation is False
    
    def test_is_citation_key_true(self):
        """Test is_citation_key returns True for citation keys."""
        key = GeoKey(
            id=1026,
            name="GTCitationGeoKey",
            value="WGS 84 / UTM zone 10N",
            value_text="WGS 84 / UTM zone 10N",
            is_citation=True,
            location=34737,
            count=1
        )
        
        assert key.is_citation_key() is True
    
    def test_is_citation_key_false(self):
        """Test is_citation_key returns False for non-citation keys."""
        key = GeoKey(
            id=1024,
            name="GTModelTypeGeoKey",
            value=2,
            value_text="2 (ModelTypeGeographic)",
            is_citation=False
        )
        
        assert key.is_citation_key() is False
    
    def test_is_stored_in_doubles(self):
        """Test is_stored_in_doubles for keys in GeoDoubleParams."""
        key = GeoKey(
            id=2049,
            name="GeogSemiMajorAxisGeoKey",
            value=6378137.0,
            value_text="6378137.0",
            location=34736  # GeoDoubleParams
        )
        
        assert key.is_stored_in_doubles() is True
        assert key.is_stored_in_ascii() is False
    
    def test_is_stored_in_ascii(self):
        """Test is_stored_in_ascii for keys in GeoAsciiParams."""
        key = GeoKey(
            id=1026,
            name="GTCitationGeoKey",
            value="WGS 84",
            value_text="WGS 84",
            location=34737,  # GeoAsciiParams
            is_citation=True
        )
        
        assert key.is_stored_in_ascii() is True
        assert key.is_stored_in_doubles() is False


@pytest.mark.unit
@pytest.mark.models
class TestStatisticsBand:
    """Test StatisticsBand data model."""
    
    def test_instantiation_complete(self):
        """Test creating StatisticsBand with all fields."""
        stats = StatisticsBand(
            band_name="Band 1",
            valid_percent=99.5,
            valid_count=65000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=36,
            nodata_value=-9999.0,
            minimum=0.0,
            maximum=255.0,
            mean=127.5,
            std_dev=45.3,
            median=128.0
        )
        
        assert stats.band_name == "Band 1"
        assert stats.valid_percent == 99.5
        assert stats.minimum == 0.0
        assert stats.maximum == 255.0
        assert stats.nodata_value == -9999.0
    
    def test_range_method(self):
        """Test that range() correctly calculates max - min."""
        stats = StatisticsBand(
            band_name="Band 1",
            valid_percent=100.0,
            valid_count=10000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=0,
            minimum=0.0,
            maximum=255.0,
            mean=127.5,
            std_dev=45.3
        )
        
        assert stats.range() == 255.0
    
    def test_range_returns_none_when_values_missing(self):
        """Test that range() returns None when min/max are not set."""
        stats = StatisticsBand(
            band_name="Band 1",
            valid_percent=100.0,
            valid_count=10000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=0,
            minimum=None,
            maximum=None
        )
        
        assert stats.range() is None
    
    def test_has_nodata_true(self):
        """Test has_nodata returns True when NoData is present."""
        stats = StatisticsBand(
            band_name="Band 1",
            valid_percent=99.5,
            valid_count=9958,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=42,
            nodata_value=-9999.0,
            minimum=0.0,
            maximum=255.0
        )
        
        assert stats.has_nodata() is True
    
    def test_has_nodata_false_when_no_value(self):
        """Test has_nodata returns False when nodata_value is None."""
        stats = StatisticsBand(
            band_name="Band 1",
            valid_percent=100.0,
            valid_count=10000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=0,
            nodata_value=None
        )
        
        assert stats.has_nodata() is False
    
    def test_has_nodata_false_when_count_zero(self):
        """Test has_nodata returns False when nodata_count is 0."""
        stats = StatisticsBand(
            band_name="Band 1",
            valid_percent=100.0,
            valid_count=10000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=0,
            nodata_value=-9999.0  # Value set but count is 0
        )
        
        assert stats.has_nodata() is False
    
    def test_has_histogram_true(self):
        """Test has_histogram returns True when histogram data exists."""
        stats = StatisticsBand(
            band_name="Band 1",
            valid_percent=100.0,
            valid_count=10000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=0,
            histogram_counts=[100, 200, 300, 250, 150]
        )
        
        assert stats.has_histogram() is True
    
    def test_has_histogram_false(self):
        """Test has_histogram returns False when no histogram data."""
        stats = StatisticsBand(
            band_name="Band 1",
            valid_percent=100.0,
            valid_count=10000,
            mask_count=0,
            alpha_0_count=0,
            nodata_count=0,
            histogram_counts=None
        )
        
        assert stats.has_histogram() is False


@pytest.mark.unit
@pytest.mark.models
class TestGeoReference:
    """Test GeoReference data model."""
    
    def test_get_formatted_geographic_cs_with_code(self):
        """Test formatted geographic CS includes EPSG code."""
        georef = GeoReference(
            geographic_cs="WGS 84",
            geographic_cs_code="4326"
        )
        
        assert georef.get_formatted_geographic_cs() == "WGS 84 (EPSG:4326)"
    
    def test_get_formatted_geographic_cs_without_code(self):
        """Test formatted geographic CS without EPSG code."""
        georef = GeoReference(
            geographic_cs="WGS 84"
        )
        
        assert georef.get_formatted_geographic_cs() == "WGS 84"
    
    def test_get_formatted_geographic_cs_returns_none(self):
        """Test formatted geographic CS returns None when not set."""
        georef = GeoReference()
        
        assert georef.get_formatted_geographic_cs() is None
    
    def test_get_formatted_projected_cs_with_code(self):
        """Test formatted projected CS includes EPSG code."""
        georef = GeoReference(
            projected_cs="UTM Zone 10N",
            projected_cs_code="32610"
        )
        
        assert georef.get_formatted_projected_cs() == "UTM Zone 10N (EPSG:32610)"
    
    def test_get_formatted_projected_cs_without_code(self):
        """Test formatted projected CS without EPSG code."""
        georef = GeoReference(
            projected_cs="UTM Zone 10N"
        )
        
        assert georef.get_formatted_projected_cs() == "UTM Zone 10N"
    
    def test_get_formatted_projected_cs_returns_none(self):
        """Test formatted projected CS returns None when not set."""
        georef = GeoReference()
        
        assert georef.get_formatted_projected_cs() is None
    
    def test_get_formatted_datum_with_code(self):
        """Test formatted datum includes EPSG code."""
        georef = GeoReference(
            datum="WGS_1984",
            datum_code="6326"
        )
        
        assert georef.get_formatted_datum() == "WGS_1984 (EPSG:6326)"
    
    def test_get_formatted_datum_without_code(self):
        """Test formatted datum without EPSG code."""
        georef = GeoReference(
            datum="WGS_1984"
        )
        
        assert georef.get_formatted_datum() == "WGS_1984"
    
    def test_get_formatted_datum_returns_none(self):
        """Test formatted datum returns None when not set."""
        georef = GeoReference()
        
        assert georef.get_formatted_datum() is None
    
    def test_get_formatted_vertical_cs_with_code(self):
        """Test formatted vertical CS includes EPSG code."""
        georef = GeoReference(
            vertical_cs="NAVD88",
            vertical_cs_code="5703"
        )
        
        assert georef.get_formatted_vertical_cs() == "NAVD88 (EPSG:5703)"
    
    def test_get_formatted_vertical_cs_without_code(self):
        """Test formatted vertical CS without EPSG code."""
        georef = GeoReference(
            vertical_cs="NAVD88"
        )
        
        assert georef.get_formatted_vertical_cs() == "NAVD88"
    
    def test_get_formatted_vertical_cs_returns_none(self):
        """Test formatted vertical CS returns None when not set."""
        georef = GeoReference()
        
        assert georef.get_formatted_vertical_cs() is None
    
    def test_get_formatted_vertical_datum_with_code(self):
        """Test formatted vertical datum includes EPSG code."""
        georef = GeoReference(
            vertical_datum="North American Vertical Datum 1988",
            vertical_datum_code="5103"
        )
        
        assert georef.get_formatted_vertical_datum() == "North American Vertical Datum 1988 (EPSG:5103)"
    
    def test_get_formatted_vertical_datum_without_code(self):
        """Test formatted vertical datum without EPSG code."""
        georef = GeoReference(
            vertical_datum="North American Vertical Datum 1988"
        )
        
        assert georef.get_formatted_vertical_datum() == "North American Vertical Datum 1988"
    
    def test_get_formatted_vertical_datum_returns_none(self):
        """Test formatted vertical datum returns None when not set."""
        georef = GeoReference()
        
        assert georef.get_formatted_vertical_datum() is None
    
    def test_is_geographic_true(self):
        """Test is_geographic returns True for geographic CRS."""
        georef = GeoReference(
            geographic_cs="WGS 84",
            geographic_cs_code="4326"
        )
        
        assert georef.is_geographic() is True
        assert georef.is_projected() is False
    
    def test_is_projected_true(self):
        """Test is_projected returns True for projected CRS."""
        georef = GeoReference(
            geographic_cs="WGS 84",
            geographic_cs_code="4326",
            projected_cs="UTM Zone 10N",
            projected_cs_code="32610"
        )
        
        assert georef.is_projected() is True
        assert georef.is_geographic() is False
    
    def test_has_vertical_with_cs(self):
        """Test has_vertical returns True when vertical CRS present."""
        georef = GeoReference(
            projected_cs="UTM Zone 10N",
            projected_cs_code="32610",
            vertical_cs="NAVD88",
            vertical_cs_code="5703"
        )
        
        assert georef.has_vertical() is True
    
    def test_has_vertical_with_datum_only(self):
        """Test has_vertical returns True when only vertical datum present."""
        georef = GeoReference(
            projected_cs="UTM Zone 10N",
            vertical_datum="NAVD88"
        )
        
        assert georef.has_vertical() is True
    
    def test_has_vertical_false(self):
        """Test has_vertical returns False when no vertical CRS."""
        georef = GeoReference(
            projected_cs="UTM Zone 10N",
            projected_cs_code="32610"
        )
        
        assert georef.has_vertical() is False


@pytest.mark.unit
@pytest.mark.models
class TestGeoTransform:
    """Test GeoTransform data model."""
    
    def test_instantiation(self):
        """Test creating GeoTransform with all coefficients."""
        gt = GeoTransform(
            x_origin=0.0,
            pixel_width=30.0,
            x_skew=0.0,
            y_origin=100.0,
            y_skew=0.0,
            pixel_height=-30.0,
            unit="metre"
        )
        
        assert gt.x_origin == 0.0
        assert gt.pixel_width == 30.0
        assert gt.pixel_height == -30.0
        assert gt.unit == "metre"
    
    def test_as_tuple(self):
        """Test as_tuple returns correct 6-element tuple."""
        gt = GeoTransform(
            x_origin=0.0,
            pixel_width=30.0,
            x_skew=0.0,
            y_origin=100.0,
            y_skew=0.0,
            pixel_height=-30.0
        )
        
        result = gt.as_tuple()
        
        assert result == (0.0, 30.0, 0.0, 100.0, 0.0, -30.0)
        assert len(result) == 6
    
    def test_is_north_up_true(self):
        """Test is_north_up returns True when no rotation."""
        gt = GeoTransform(
            x_origin=0.0,
            pixel_width=30.0,
            x_skew=0.0,
            y_origin=100.0,
            y_skew=0.0,
            pixel_height=-30.0
        )
        
        assert gt.is_north_up() is True
        assert gt.is_rotated() is False
    
    def test_is_rotated_true(self):
        """Test is_rotated returns True when skew present."""
        gt = GeoTransform(
            x_origin=0.0,
            pixel_width=30.0,
            x_skew=5.0,  # Non-zero skew = rotation
            y_origin=100.0,
            y_skew=0.0,
            pixel_height=-30.0
        )
        
        assert gt.is_rotated() is True
        assert gt.is_north_up() is False
    
    def test_resolution(self):
        """Test resolution returns absolute pixel sizes."""
        gt = GeoTransform(
            x_origin=0.0,
            pixel_width=30.0,
            x_skew=0.0,
            y_origin=100.0,
            y_skew=0.0,
            pixel_height=-30.0  # Negative (common for north-up images)
        )
        
        res_x, res_y = gt.resolution()
        
        assert res_x == 30.0
        assert res_y == 30.0  # Absolute value


@pytest.mark.unit
@pytest.mark.models
class TestGeoExtents:
    """Test GeoExtents data model."""
    
    def test_instantiation(self):
        """Test creating GeoExtents with corner coordinates."""
        extents = GeoExtents(
            upper_left=(-180.0, 90.0),
            lower_left=(-180.0, -90.0),
            upper_right=(180.0, 90.0),
            lower_right=(180.0, -90.0),
            center=(0.0, 0.0)
        )
        
        assert extents.upper_left == (-180.0, 90.0)
        assert extents.lower_left == (-180.0, -90.0)
        assert extents.upper_right == (180.0, 90.0)
        assert extents.lower_right == (180.0, -90.0)
        assert extents.center == (0.0, 0.0)
    
    def test_all_corners(self):
        """Test all_corners returns list of all corner coordinates."""
        extents = GeoExtents(
            upper_left=(-180.0, 90.0),
            lower_left=(-180.0, -90.0),
            upper_right=(180.0, 90.0),
            lower_right=(180.0, -90.0),
            center=(0.0, 0.0)
        )
        
        corners = extents.all_corners()
        
        assert len(corners) == 4
        assert corners[0] == (-180.0, 90.0)
        assert corners[1] == (-180.0, -90.0)
        assert corners[2] == (180.0, 90.0)
        assert corners[3] == (180.0, -90.0)
    
    def test_longitude_range(self):
        """Test longitude_range calculates min and max longitude."""
        extents = GeoExtents(
            upper_left=(-120.0, 45.0),
            lower_left=(-120.0, 40.0),
            upper_right=(-110.0, 45.0),
            lower_right=(-110.0, 40.0),
            center=(-115.0, 42.5)
        )
        
        lon_min, lon_max = extents.longitude_range()
        
        assert lon_min == -120.0
        assert lon_max == -110.0
    
    def test_latitude_range(self):
        """Test latitude_range calculates min and max latitude."""
        extents = GeoExtents(
            upper_left=(-120.0, 45.0),
            lower_left=(-120.0, 40.0),
            upper_right=(-110.0, 45.0),
            lower_right=(-110.0, 40.0),
            center=(-115.0, 42.5)
        )
        
        lat_min, lat_max = extents.latitude_range()
        
        assert lat_min == 40.0
        assert lat_max == 45.0


@pytest.mark.unit
@pytest.mark.models
class TestBoundingBox:
    """Test BoundingBox data model with parametrized tests."""
    
    @pytest.mark.parametrize("west,east,expected_width", [
        (-180.0, 180.0, 360.0),
        (0.0, 100.0, 100.0),
        (-50.0, 50.0, 100.0),
    ])
    def test_width_calculation(self, west, east, expected_width):
        """Test width calculation with various coordinate pairs."""
        bbox = BoundingBox(
            west=west,
            east=east,
            south=-90.0,
            north=90.0
        )
        
        assert bbox.width() == expected_width
    
    @pytest.mark.parametrize("south,north,expected_height", [
        (-90.0, 90.0, 180.0),
        (0.0, 50.0, 50.0),
        (-45.0, 45.0, 90.0),
    ])
    def test_height_calculation(self, south, north, expected_height):
        """Test height calculation with various coordinate pairs."""
        bbox = BoundingBox(
            west=-180.0,
            east=180.0,
            south=south,
            north=north
        )
        
        assert bbox.height() == expected_height
    
    def test_center_calculation(self):
        """Test center point calculation."""
        bbox = BoundingBox(
            west=-180.0,
            east=180.0,
            south=-90.0,
            north=90.0
        )
        
        center_x, center_y = bbox.center()
        
        assert center_x == 0.0
        assert center_y == 0.0
    
    def test_is_3d_true(self):
        """Test is_3d returns True when both bottom and top are set."""
        bbox = BoundingBox(
            west=0.0,
            east=100.0,
            south=0.0,
            north=100.0,
            bottom=0.0,
            top=500.0
        )
        
        assert bbox.is_3d() is True
    
    def test_is_3d_false(self):
        """Test is_3d returns False when elevation not set."""
        bbox = BoundingBox(
            west=0.0,
            east=100.0,
            south=0.0,
            north=100.0
        )
        
        assert bbox.is_3d() is False


@pytest.mark.unit
@pytest.mark.models
class TestHistogramImage:
    """Test HistogramImage data model."""
    
    def test_instantiation(self):
        """Test creating HistogramImage with base64 data."""
        histogram = HistogramImage(
            base64_image="iVBORw0KGgoAAAANSUhEUgA...",
            bands=["Band 1", "Band 2", "Band 3"],
            title="Histogram"
        )
        
        assert histogram.base64_image == "iVBORw0KGgoAAAANSUhEUgA..."
        assert histogram.bands == ["Band 1", "Band 2", "Band 3"]
        assert histogram.title == "Histogram"
    
    def test_has_data_true(self):
        """Test has_data returns True when image data exists."""
        histogram = HistogramImage(
            base64_image="iVBORw0KGgoAAAANSUhEUgA..."
        )
        
        assert histogram.has_data() is True
    
    def test_has_data_false(self):
        """Test has_data returns False when no image data."""
        histogram = HistogramImage(base64_image="")
        
        assert histogram.has_data() is False
    
    def test_band_count(self):
        """Test band_count returns correct number of bands."""
        histogram = HistogramImage(
            base64_image="data",
            bands=["Band 1", "Band 2", "Band 3"]
        )
        
        assert histogram.band_count() == 3
    
    def test_band_count_with_none(self):
        """Test band_count returns 0 when bands is None."""
        histogram = HistogramImage(base64_image="data")
        
        assert histogram.band_count() == 0


@pytest.mark.unit
@pytest.mark.models
class TestTileInfo:
    """Test TileInfo data model."""
    
    def test_instantiation(self):
        """Test creating TileInfo with all fields."""
        tile = TileInfo(
            level=0,
            tile_count=16,
            block_size="256 x 256",
            tile_dimensions="7680.0 x 7680.0 m",
            total_pixels="1024 x 1024",
            resolution="30.0 m"
        )
        
        assert tile.level == 0
        assert tile.tile_count == 16
        assert tile.block_size == "256 x 256"
    
    def test_is_main_image_true(self):
        """Test is_main_image returns True for level 0."""
        tile = TileInfo(
            level=0,
            tile_count=16,
            block_size="256 x 256",
            tile_dimensions="7680 m",
            total_pixels="1024 x 1024",
            resolution="30.0 m"
        )
        
        assert tile.is_main_image() is True
        assert tile.is_overview() is False
    
    def test_is_overview_true(self):
        """Test is_overview returns True for level > 0."""
        tile = TileInfo(
            level=1,
            tile_count=4,
            block_size="256 x 256",
            tile_dimensions="7680 m",
            total_pixels="512 x 512",
            resolution="60.0 m"
        )
        
        assert tile.is_overview() is True
        assert tile.is_main_image() is False


@pytest.mark.unit
@pytest.mark.models
class TestIfdInfo:
    """Test IfdInfo data model."""
    
    def test_instantiation_complete(self):
        """Test creating IfdInfo with all fields."""
        ifd = IfdInfo(
            ifd=0,
            ifd_type="Main Image",
            dimensions="1024 x 768",
            block_size="256 x 256",
            data_type="Float32",
            bands=3,
            bits_per_sample=8,
            decimals=2,
            photometric="RGB",
            compression_algorithm="DEFLATE",
            predictor="2-Horizontal",
            space_saving="75.5%",
            ratio="1.32"
        )
        
        assert ifd.ifd == 0
        assert ifd.ifd_type == "Main Image"
        assert ifd.compression_algorithm == "DEFLATE"
        assert ifd.space_saving == "75.5%"
    
    def test_is_main_image(self):
        """Test is_main_image returns True for IFD 0."""
        ifd = IfdInfo(
            ifd=0,
            ifd_type="Main Image",
            dimensions="1024 x 768",
            block_size="256 x 256",
            data_type="Byte",
            bands=3,
            bits_per_sample=8
        )
        
        assert ifd.is_main_image() is True
    
    def test_is_compressed_true(self):
        """Test is_compressed returns True for compressed IFD."""
        ifd = IfdInfo(
            ifd=0,
            ifd_type="Main Image",
            dimensions="1024 x 768",
            block_size="256 x 256",
            data_type="Float32",
            bands=1,
            bits_per_sample=32,
            compression_algorithm="DEFLATE"
        )
        
        assert ifd.is_compressed() is True
    
    def test_is_compressed_false_for_uncompressed(self):
        """Test is_compressed returns False for uncompressed IFD."""
        ifd = IfdInfo(
            ifd=0,
            ifd_type="Main Image",
            dimensions="1024 x 768",
            block_size="1024 x 1",
            data_type="Byte",
            bands=3,
            bits_per_sample=8,
            compression_algorithm="Uncompressed"
        )
        
        assert ifd.is_compressed() is False
    
    def test_is_compressed_false_for_none(self):
        """Test is_compressed returns False when compression is None."""
        ifd = IfdInfo(
            ifd=0,
            ifd_type="Main Image",
            dimensions="1024 x 768",
            block_size="256 x 256",
            data_type="Byte",
            bands=3,
            bits_per_sample=8,
            compression_algorithm=None
        )
        
        assert ifd.is_compressed() is False
    
    def test_is_tiled_true(self):
        """Test is_tiled returns True for tiled IFD."""
        ifd = IfdInfo(
            ifd=0,
            ifd_type="Main Image",
            dimensions="1024 x 768",
            block_size="256 x 256",  # Tile smaller than image
            data_type="Byte",
            bands=3,
            bits_per_sample=8
        )
        
        assert ifd.is_tiled() is True
    
    def test_is_tiled_false_for_strips(self):
        """Test is_tiled returns False for striped IFD."""
        ifd = IfdInfo(
            ifd=0,
            ifd_type="Main Image",
            dimensions="1024 x 768",
            block_size="1024 x 1",  # Strip width = image width
            data_type="Byte",
            bands=3,
            bits_per_sample=8
        )
        
        assert ifd.is_tiled() is False


@pytest.mark.unit
@pytest.mark.models
class TestWktString:
    """Test WktString data model."""
    
    def test_instantiation(self):
        """Test creating WktString with WKT content."""
        wkt = WktString(
            wkt_string='GEOGCS["WGS 84",DATUM["WGS_1984",...]]',
            format_version="WKT2_2019",
            source_file="test.tif"
        )
        
        assert wkt.wkt_string == 'GEOGCS["WGS 84",DATUM["WGS_1984",...]]'
        assert wkt.format_version == "WKT2_2019"
        assert wkt.source_file == "test.tif"
    
    def test_line_count_single_line(self):
        """Test line_count for single line WKT."""
        wkt = WktString(wkt_string='GEOGCS["WGS 84"]')
        
        assert wkt.line_count() == 1
    
    def test_line_count_multi_line(self):
        """Test line_count for multi-line WKT."""
        wkt_multi = WktString(
            wkt_string='GEOGCS["WGS 84",\n  DATUM["WGS_1984",\n    SPHEROID["WGS 84",6378137,298.257223563]]]'
        )
        
        assert wkt_multi.line_count() == 3
    
    def test_has_content_true(self):
        """Test has_content returns True for non-empty WKT."""
        wkt = WktString(wkt_string='GEOGCS["WGS 84"]')
        
        assert wkt.has_content() is True
    
    def test_has_content_false_empty(self):
        """Test has_content returns False for empty WKT."""
        wkt = WktString(wkt_string='')
        
        assert wkt.has_content() is False
    
    def test_has_content_false_whitespace(self):
        """Test has_content returns False for whitespace-only WKT."""
        wkt = WktString(wkt_string='   \n  ')
        
        assert wkt.has_content() is False


@pytest.mark.unit
@pytest.mark.models
class TestJsonString:
    """Test JsonString data model."""
    
    def test_instantiation(self):
        """Test creating JsonString with JSON content."""
        json_data = JsonString(
            json_string='{"type": "GeographicCRS", "name": "WGS 84"}',
            source_file="test.tif"
        )
        
        assert json_data.json_string == '{"type": "GeographicCRS", "name": "WGS 84"}'
        assert json_data.source_file == "test.tif"
    
    def test_is_valid_json_true(self):
        """Test is_valid_json returns True for valid JSON."""
        json_data = JsonString(
            json_string='{"type": "GeographicCRS", "name": "WGS 84"}'
        )
        
        assert json_data.is_valid_json() is True
    
    def test_is_valid_json_false(self):
        """Test is_valid_json returns False for invalid JSON."""
        json_data = JsonString(
            json_string='{"type": "GeographicCRS", invalid'
        )
        
        assert json_data.is_valid_json() is False
    
    def test_has_content_true(self):
        """Test has_content returns True for non-empty JSON."""
        json_data = JsonString(json_string='{"key": "value"}')
        
        assert json_data.has_content() is True
    
    def test_has_content_false(self):
        """Test has_content returns False for empty JSON."""
        json_data = JsonString(json_string='')
        
        assert json_data.has_content() is False


@pytest.mark.unit
@pytest.mark.models
class TestCogValidation:
    """Test CogValidation data model."""
    
    def test_is_valid_with_no_errors(self):
        """Test is_valid returns True when no errors present."""
        validation = CogValidation(
            warnings=["IFD offsets not sorted"],
            errors=[]
        )
        
        assert validation.is_valid() is True
    
    def test_is_valid_with_errors(self):
        """Test is_valid returns False when errors present."""
        validation = CogValidation(
            warnings=[],
            errors=["Missing overview IFDs"]
        )
        
        assert validation.is_valid() is False
    
    def test_has_warnings_true(self):
        """Test has_warnings returns True when warnings present."""
        validation = CogValidation(
            warnings=["IFD offsets not sorted"],
            errors=[]
        )
        
        assert validation.has_warnings() is True
    
    def test_has_warnings_false(self):
        """Test has_warnings returns False when no warnings."""
        validation = CogValidation(
            warnings=[],
            errors=[]
        )
        
        assert validation.has_warnings() is False
    
    def test_has_errors_true(self):
        """Test has_errors returns True when errors present."""
        validation = CogValidation(
            warnings=[],
            errors=["Critical issue"]
        )
        
        assert validation.has_errors() is True
    
    def test_has_errors_false(self):
        """Test has_errors returns False when no errors."""
        validation = CogValidation(
            warnings=["Minor warning"],
            errors=[]
        )
        
        assert validation.has_errors() is False
    
    def test_get_status_message_valid_no_warnings(self):
        """Test status message for valid COG with no warnings."""
        validation = CogValidation(warnings=[], errors=[])
        
        assert validation.get_status_message() == "Valid Cloud Optimized GeoTIFF"
    
    def test_get_status_message_valid_with_warnings(self):
        """Test status message for valid COG with warnings."""
        validation = CogValidation(
            warnings=["Minor issue"],
            errors=[]
        )
        
        assert validation.get_status_message() == "Valid COG with warnings"
    
    def test_get_status_message_invalid(self):
        """Test status message for invalid COG."""
        validation = CogValidation(
            warnings=[],
            errors=["Critical issue"]
        )
        
        assert validation.get_status_message() == "Not a valid Cloud Optimized GeoTIFF"


@pytest.mark.unit
@pytest.mark.models
class TestXmlMetadata:
    """Test XmlMetadata data model."""
    
    def test_instantiation(self):
        """Test creating XmlMetadata with XML content."""
        xml = XmlMetadata(
            title="GDAL Metadata",
            content="<GDALMetadata><Item>value</Item></GDALMetadata>",
            xml_type="text"
        )
        
        assert xml.title == "GDAL Metadata"
        assert xml.content == "<GDALMetadata><Item>value</Item></GDALMetadata>"
        assert xml.xml_type == "text"
    
    def test_is_table_format_true(self):
        """Test is_table_format returns True for table type."""
        xml = XmlMetadata(
            title="PAM Metadata",
            content="<PAMDataset/>",
            xml_type="table"
        )
        
        assert xml.is_table_format() is True
    
    def test_is_table_format_false(self):
        """Test is_table_format returns False for text type."""
        xml = XmlMetadata(
            title="XMP Metadata",
            content="<rdf:RDF/>",
            xml_type="text"
        )
        
        assert xml.is_table_format() is False
    
    def test_has_content_true(self):
        """Test has_content returns True for non-empty content."""
        xml = XmlMetadata(
            title="Metadata",
            content="<root/>"
        )
        
        assert xml.has_content() is True
    
    def test_has_content_false(self):
        """Test has_content returns False for empty content."""
        xml = XmlMetadata(
            title="Metadata",
            content=""
        )
        
        assert xml.has_content() is False


# =============================================================================
# Wrapper Classes Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.models
class TestTiffTagsData:
    """Test TiffTagsData wrapper class."""
    
    def test_instantiation(self, sample_tiff_tags):
        """Test creating TiffTagsData with tags list."""
        tags_data = TiffTagsData(
            tags=sample_tiff_tags,
            title="Compact* TIFF Tags (IFD 0 – Main Image)",
            footer="* TIFF tags excluded from the report: StripOffsets"
        )
        
        assert len(tags_data.tags) == 8
        assert tags_data.title == "Compact* TIFF Tags (IFD 0 – Main Image)"
        assert tags_data.footer == "* TIFF tags excluded from the report: StripOffsets"
    
    def test_has_footer_true(self):
        """Test has_footer returns True when footer is set."""
        tags_data = TiffTagsData(
            tags=[],
            title="Tags",
            footer="Some footer text"
        )
        
        assert tags_data.has_footer() is True
    
    def test_has_footer_false(self):
        """Test has_footer returns False when footer is None."""
        tags_data = TiffTagsData(
            tags=[],
            title="Tags",
            footer=None
        )
        
        assert tags_data.has_footer() is False


@pytest.mark.unit
@pytest.mark.models
class TestStatisticsData:
    """Test StatisticsData wrapper class."""
    
    def test_instantiation(self):
        """Test creating StatisticsData with table structure."""
        stats = StatisticsData(
            title="Statistics",
            headers=['Statistic', 'Band 1', 'Band 2'],
            data=[
                {'Statistic': 'Mean', 'Band 1': '127.5', 'Band 2': '130.2'},
                {'Statistic': 'Std Dev', 'Band 1': '45.3', 'Band 2': '42.1'}
            ],
            footnote="Note: NoData values excluded"
        )
        
        assert stats.title == "Statistics"
        assert len(stats.headers) == 3
        assert len(stats.data) == 2
        assert stats.footnote == "Note: NoData values excluded"


@pytest.mark.unit
@pytest.mark.models
class TestIfdInfoData:
    """Test IfdInfoData wrapper class."""
    
    def test_instantiation(self):
        """Test creating IfdInfoData with table structure."""
        ifd_data = IfdInfoData(
            headers=['IFD', 'Description', 'Dimensions', 'Algorithm'],
            rows=[
                {'IFD': 0, 'Description': 'Main Image', 'Dimensions': '1024x768', 'Algorithm': 'DEFLATE'},
                {'IFD': 1, 'Description': 'Overview', 'Dimensions': '512x384', 'Algorithm': 'DEFLATE'}
            ],
            title="Image File Directory (IFD) List"
        )
        
        assert len(ifd_data.headers) == 4
        assert len(ifd_data.rows) == 2
        assert ifd_data.title == "Image File Directory (IFD) List"


# =============================================================================
# Comparison Classes Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.models
class TestDifferencesComparison:
    """Test DifferencesComparison data model."""
    
    def test_instantiation(self):
        """Test creating DifferencesComparison with all fields."""
        diff = DifferencesComparison(
            headers=['File', 'Type', 'Size (MB)'],
            base_row=['Float32', '100.0'],
            comp_row=['Float32', '25.0'],
            base_name='Baseline',
            comp_name='Optimized',
            base_size_mb=100.0,
            comp_size_mb=25.0,
            size_difference_mb=-75.0,
            size_difference_pct=-75.0,
            efficiency_difference=5.0
        )
        
        assert diff.base_size_mb == 100.0
        assert diff.comp_size_mb == 25.0
        assert diff.size_difference_mb == -75.0
        assert diff.size_difference_pct == -75.0
    
    def test_get_result_text_decreased(self):
        """Test get_result_text for decreased file size."""
        diff = DifferencesComparison(
            headers=[],
            base_row=[],
            comp_row=[],
            base_size_mb=100.0,
            comp_size_mb=25.0,
            size_difference_mb=-75.0,
            size_difference_pct=-75.0,
            efficiency_difference=5.0
        )
        
        result = diff.get_result_text()
        
        assert "Decreased by 75.00 MB" in result
        assert "75.0% smaller" in result
        assert "5.0% more efficient" in result
    
    def test_get_result_text_increased(self):
        """Test get_result_text for increased file size."""
        diff = DifferencesComparison(
            headers=[],
            base_row=[],
            comp_row=[],
            base_size_mb=25.0,
            comp_size_mb=100.0,
            size_difference_mb=75.0,
            size_difference_pct=300.0,
            efficiency_difference=-5.0
        )
        
        result = diff.get_result_text()
        
        assert "Increased by 75.00 MB" in result
        assert "300.0% larger" in result
        assert "5.0% less efficient" in result
    
    def test_get_result_text_no_efficiency_change(self):
        """Test get_result_text when efficiency change is negligible."""
        diff = DifferencesComparison(
            headers=[],
            base_row=[],
            comp_row=[],
            base_size_mb=100.0,
            comp_size_mb=95.0,
            size_difference_mb=-5.0,
            size_difference_pct=-5.0,
            efficiency_difference=0.01  # Negligible
        )
        
        result = diff.get_result_text()
        
        assert "Decreased by 5.00 MB" in result
        assert "efficient" not in result  # No efficiency text


@pytest.mark.unit
@pytest.mark.models
class TestComparisonContainerClasses:
    """Test comparison container classes."""
    
    def test_ifd_info_comparison(self):
        """Test IfdInfoComparison data model."""
        baseline_ifd = IfdInfoData(headers=['IFD'], rows=[{'IFD': 0}])
        comp_ifd = IfdInfoData(headers=['IFD'], rows=[{'IFD': 0}])
        
        comp = IfdInfoComparison(
            title="IFDs",
            files=[("Baseline", baseline_ifd), ("Comparison", comp_ifd)]
        )
        
        assert comp.title == "IFDs"
        assert len(comp.files) == 2
        assert comp.files[0][0] == "Baseline"
    
    def test_statistics_comparison(self):
        """Test StatisticsComparison data model."""
        baseline_stats = StatisticsData(title="Stats", headers=[], data=[])
        comp_stats = StatisticsData(title="Stats", headers=[], data=[])
        
        comp = StatisticsComparison(
            title="Statistics",
            files=[("Baseline", baseline_stats), ("Comparison", comp_stats)]
        )
        
        assert comp.title == "Statistics"
        assert len(comp.files) == 2
    
    def test_histogram_comparison(self):
        """Test HistogramComparison data model."""
        baseline_hist = HistogramImage(base64_image="data1")
        comp_hist = HistogramImage(base64_image="data2")
        
        comp = HistogramComparison(
            title="Histograms",
            files=[("Baseline", baseline_hist), ("Comparison", comp_hist)]
        )
        
        assert comp.title == "Histograms"
        assert len(comp.files) == 2
    
    def test_cog_validation_comparison(self):
        """Test CogValidationComparison data model."""
        baseline_cog = CogValidation(warnings=[], errors=[])
        comp_cog = CogValidation(warnings=[], errors=[])
        
        comp = CogValidationComparison(
            title="COG Validation",
            files=[("Baseline", baseline_cog), ("Comparison", comp_cog)]
        )
        
        assert comp.title == "COG Validation"
        assert len(comp.files) == 2


# =============================================================================
# Integration-style Unit Tests (Testing multiple components together)
# =============================================================================

@pytest.mark.unit
@pytest.mark.models
class TestDataModelIntegration:
    """Test how data models work together."""
    
    def test_statistics_band_with_sample_fixture(self, sample_statistics):
        """Test using StatisticsBand with fixture data."""
        # This tests that fixtures work correctly
        assert len(sample_statistics) == 3
        assert all(isinstance(s, StatisticsBand) for s in sample_statistics)
        assert sample_statistics[0].band_name == "Band 1"
    
    def test_tiff_tag_with_sample_fixture(self, sample_tiff_tags):
        """Test using TiffTag with fixture data."""
        assert len(sample_tiff_tags) == 8
        
        # Find ImageWidth tag
        width_tag = next((t for t in sample_tiff_tags if t.code == 256), None)
        assert width_tag is not None
        assert width_tag.name == "ImageWidth"
        assert width_tag.value == 1024
        assert width_tag.is_numeric() is True