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
Unit tests for MockGeoTIFF factory.

This module tests the mock GeoTIFF generator to ensure it creates
valid in-memory GDAL datasets with the correct properties.

Test coverage target: 95%+

These tests ensure the testing infrastructure itself is reliable,
which is critical for all other tests to be meaningful.
"""

import pytest
from osgeo import gdal

from tests.fixtures.mock_geotiff_factory import MockGeoTIFF


@pytest.mark.unit
class TestMockGeoTIFFBasic:
    """Test basic MockGeoTIFF instantiation and properties."""
    
    def test_create_default_geotiff(self):
        """Test creating MockGeoTIFF with default parameters."""
        mock = MockGeoTIFF()
        
        assert mock.width == 256
        assert mock.height == 256
        assert mock.bands == 1
        assert mock.data_type == gdal.GDT_Float32
    
    def test_create_custom_size(self):
        """Test creating MockGeoTIFF with custom dimensions."""
        mock = MockGeoTIFF(width=1024, height=512)
        
        assert mock.width == 1024
        assert mock.height == 512
    
    def test_create_multiband(self):
        """Test creating multi-band MockGeoTIFF."""
        mock = MockGeoTIFF(bands=3)
        
        assert mock.bands == 3


@pytest.mark.unit
class TestMockGeoTIFFToGDAL:
    """Test converting MockGeoTIFF to GDAL Dataset."""
    
    def test_to_gdal_dataset_creates_valid_dataset(self, mock_geotiff_basic):
        """Test that to_gdal_dataset creates a valid GDAL dataset."""
        ds = mock_geotiff_basic.to_gdal_dataset()
        
        assert ds is not None
        assert ds.RasterCount > 0
        assert ds.RasterXSize == 256
        assert ds.RasterYSize == 256
    
    def test_gdal_dataset_has_correct_data_type(self):
        """Test that GDAL dataset has correct data type."""
        mock = MockGeoTIFF(data_type=gdal.GDT_UInt16)
        ds = mock.to_gdal_dataset()
        band = ds.GetRasterBand(1)
        
        # GDAL data type constants
        assert band.DataType == gdal.GDT_UInt16
    
    def test_gdal_dataset_has_projection(self):
        """Test that GDAL dataset has projection information."""
        mock = MockGeoTIFF(crs="EPSG:4326")
        ds = mock.to_gdal_dataset()
        
        proj = ds.GetProjection()
        assert proj is not None
        assert len(proj) > 0
    
    def test_gdal_dataset_has_geotransform(self):
        """Test that GDAL dataset has geotransform."""
        mock = MockGeoTIFF()
        ds = mock.to_gdal_dataset()
        
        gt = ds.GetGeoTransform()
        assert gt is not None
        assert len(gt) == 6
    
    def test_gdal_dataset_has_nodata(self):
        """Test that GDAL dataset NoData value is set correctly."""
        mock = MockGeoTIFF(nodata_value=-9999.0)
        ds = mock.to_gdal_dataset()
        band = ds.GetRasterBand(1)
        
        nodata = band.GetNoDataValue()
        assert nodata == -9999.0
    
    def test_gdal_dataset_multiband(self):
        """Test that multi-band datasets are created correctly."""
        mock = MockGeoTIFF(bands=4)
        ds = mock.to_gdal_dataset()
        
        assert ds.RasterCount == 4
        
        # Test all bands exist and are accessible
        for i in range(1, 5):
            band = ds.GetRasterBand(i)
            assert band is not None


@pytest.mark.unit
class TestMockGeoTIFFCompression:
    """Test MockGeoTIFF with various compression options."""
    
    @pytest.mark.parametrize("compression", [
        "NONE",
        "LZW",
        "DEFLATE",
        "ZSTD",
    ])
    def test_compression_options(self, compression):
        """Test creating MockGeoTIFF with different compression methods."""
        mock = MockGeoTIFF(compression=compression)
        assert mock.compression == compression
    
    def test_deflate_compression_with_predictor(self):
        """Test DEFLATE compression with predictor."""
        mock = MockGeoTIFF(
            data_type=gdal.GDT_Float32,
            compression="DEFLATE",
            predictor=3
        )
        ds = mock.to_gdal_dataset()
        
        # Verify dataset was created successfully
        assert ds is not None


@pytest.mark.unit
class TestMockGeoTIFFTiling:
    """Test MockGeoTIFF with tiling options."""
    
    def test_create_tiled_geotiff(self):
        """Test creating a tiled GeoTIFF."""
        mock = MockGeoTIFF(
            width=1024,
            height=1024,
            tiled=True,
            tile_size=256
        )
        
        assert mock.tiled is True
        assert mock.tile_size == 256
    
    def test_create_striped_geotiff(self):
        """Test creating a striped (non-tiled) GeoTIFF."""
        mock = MockGeoTIFF(tiled=False)
        
        assert mock.tiled is False


@pytest.mark.unit
class TestMockGeoTIFFFixtures:
    """Test the MockGeoTIFF fixtures from conftest.py."""
    
    def test_basic_fixture(self, mock_geotiff_basic):
        """Test the basic GeoTIFF fixture."""
        assert mock_geotiff_basic.width == 256
        assert mock_geotiff_basic.height == 256
        assert mock_geotiff_basic.bands == 1
        assert mock_geotiff_basic.data_type == gdal.GDT_Float32
    
    def test_multiband_fixture(self, mock_geotiff_multiband):
        """Test the multi-band GeoTIFF fixture."""
        assert mock_geotiff_multiband.bands == 3
        assert mock_geotiff_multiband.data_type == gdal.GDT_Byte
        assert mock_geotiff_multiband.compression == "DEFLATE"
    
    def test_with_nodata_fixture(self, mock_geotiff_with_nodata):
        """Test the NoData GeoTIFF fixture."""
        assert mock_geotiff_with_nodata.nodata_value == -9999.0
        assert mock_geotiff_with_nodata.nodata_pixel_count == 42


@pytest.mark.unit
class TestMockGeoTIFFDataGeneration:
    """Test that MockGeoTIFF generates appropriate raster data."""
    
    def test_data_is_readable(self, mock_geotiff_basic):
        """Test that generated data can be read from GDAL dataset."""
        ds = mock_geotiff_basic.to_gdal_dataset()
        band = ds.GetRasterBand(1)
        
        # Read a small window of data
        data = band.ReadAsArray(0, 0, 10, 10)
        
        assert data is not None
        assert data.shape == (10, 10)
    
    def test_data_has_variation(self, mock_geotiff_basic):
        """Test that generated data has realistic variation."""
        ds = mock_geotiff_basic.to_gdal_dataset()
        band = ds.GetRasterBand(1)
        
        # Read full band
        data = band.ReadAsArray()
        
        # Check that data has variation (not all same value)
        assert data.min() != data.max()


@pytest.mark.unit
class TestMockGeoTIFFMemoryEfficiency:
    """Test that MockGeoTIFF is memory-efficient."""
    
    def test_creates_in_memory_dataset(self, mock_geotiff_basic):
        """Test that MockGeoTIFF creates in-memory (not file-based) datasets."""
        ds = mock_geotiff_basic.to_gdal_dataset()
        
        # GDAL MEM driver datasets don't have file paths
        file_list = ds.GetFileList()
        assert file_list is None or len(file_list) == 0
    
    def test_multiple_instances_independent(self):
        """Test that multiple MockGeoTIFF instances are independent."""
        mock1 = MockGeoTIFF(width=256, height=256)
        mock2 = MockGeoTIFF(width=512, height=512)
        
        ds1 = mock1.to_gdal_dataset()
        ds2 = mock2.to_gdal_dataset()
        
        # Datasets should have different dimensions
        assert ds1.RasterXSize != ds2.RasterXSize
        assert ds1.RasterYSize != ds2.RasterYSize


@pytest.mark.unit
class TestMockGeoTIFFEdgeCases:
    """Test MockGeoTIFF edge cases and validation."""
    
    def test_minimum_size(self):
        """Test creating minimum-sized GeoTIFF."""
        mock = MockGeoTIFF(width=1, height=1)
        ds = mock.to_gdal_dataset()
        
        assert ds.RasterXSize == 1
        assert ds.RasterYSize == 1
    
    def test_single_band(self):
        """Test creating single-band GeoTIFF."""
        mock = MockGeoTIFF(bands=1)
        ds = mock.to_gdal_dataset()
        
        assert ds.RasterCount == 1
    
    def test_float_nodata_value(self):
        """Test NoData with float value."""
        mock = MockGeoTIFF(
            data_type=gdal.GDT_Float32,
            nodata_value=-9999.0
        )
        ds = mock.to_gdal_dataset()
        band = ds.GetRasterBand(1)
        
        nodata = band.GetNoDataValue()
        assert abs(nodata - (-9999.0)) < 0.001
    
    def test_integer_nodata_value(self):
        """Test NoData with integer value."""
        mock = MockGeoTIFF(
            data_type=gdal.GDT_UInt16,
            nodata_value=0
        )
        ds = mock.to_gdal_dataset()
        band = ds.GetRasterBand(1)
        
        nodata = band.GetNoDataValue()
        assert nodata == 0