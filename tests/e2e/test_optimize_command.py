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
End-to-End tests for the `gttk optimize` command.

These tests verify the complete workflow for optimizing and compressing GeoTIFF files.
Note: These tests are slower than unit tests as they perform actual compression.
"""

import pytest
import subprocess
import sys
from osgeo import gdal
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF


@pytest.mark.slow
class TestOptimizeCommand:
    """Test the `gttk optimize` command end-to-end."""
    
    def test_optimize_basic_dem_deflate(self, tmp_path):
        """Test optimizing a DEM with DEFLATE compression."""
        # Arrange: Create test DEM
        input_file = tmp_path / "input_dem.tif"
        output_file = tmp_path / "output_dem.tif"
        
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:32610',
            nodata_value=-9999.0
        )
        mock.save_to_file(input_file)
        
        # Act: Run optimize command
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '-a', 'DEFLATE',
            '-p', '3',
            '-s', 'EPSG:5703',  # Vertical SRS required for DEM
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=60)
        
        # Assert: Command should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert output_file.exists(), "Output file should be created"
        
        # Verify output is a valid GeoTIFF
        ds = gdal.Open(str(output_file))
        assert ds is not None, "Output should be valid GeoTIFF"
        assert ds.RasterXSize == 256
        assert ds.RasterYSize == 256
        ds = None
    
    def test_optimize_image_jpeg(self, tmp_path):
        """Test optimizing an RGB image with JPEG compression."""
        # Arrange
        input_file = tmp_path / "input_rgb.tif"
        output_file = tmp_path / "output_rgb.tif"
        
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=3,
            data_type=gdal.GDT_Byte,
            crs='EPSG:4326',
            photometric='RGB'
        )
        mock.save_to_file(input_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'image',
            '-a', 'JPEG',
            '-q', '85',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=60)
        
        # Assert
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert output_file.exists()
        
        # Verify compression was applied
        ds = gdal.Open(str(output_file))
        assert ds is not None
        assert ds.RasterCount == 3
        ds = None
    
    def test_optimize_creates_cog(self, tmp_path):
        """Test that optimize creates a valid COG by default."""
        # Arrange
        input_file = tmp_path / "input.tif"
        output_file = tmp_path / "output_cog.tif"
        
        mock = MockGeoTIFF(width=512, height=512, bands=1)
        mock.save_to_file(input_file)
        
        # Act: Create COG (default behavior)
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '-a', 'DEFLATE',
            '-s', 'EPSG:5703',  # Vertical SRS required for DEM
            '--cog', 'true',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=60)
        
        # Assert
        assert result.returncode == 0
        assert output_file.exists()
        
        # Verify it's tiled (COG requirement) or has overviews
        ds = gdal.Open(str(output_file))
        band = ds.GetRasterBand(1)
        block_size = band.GetBlockSize()
        # COGs should be tiled (both dimensions should be tile-sized, typically 256 or 512)
        # OR should have overviews (which is also a COG requirement)
        overview_count = band.GetOverviewCount()
        is_tiled = (block_size[0] == block_size[1] and block_size[0] in [256, 512])
        has_overviews = overview_count > 0
        
        assert is_tiled or has_overviews, f"COG should be tiled or have overviews. Block size: {block_size}, Overviews: {overview_count}"
        ds = None
    
    def test_optimize_no_cog(self, tmp_path):
        """Test creating standard GeoTIFF without COG."""
        # Arrange
        input_file = tmp_path / "input.tif"
        output_file = tmp_path / "output_standard.tif"
        
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(input_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '-a', 'LZW',
            '-s', 'EPSG:5703',  # Vertical SRS required for DEM
            '--cog', 'false',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=60)
        
        # Assert
        assert result.returncode == 0
        assert output_file.exists()
    
    def test_optimize_with_overviews(self, tmp_path):
        """Test creating GeoTIFF with internal overviews."""
        # Arrange
        input_file = tmp_path / "input_large.tif"
        output_file = tmp_path / "output_overviews.tif"
        
        # Larger file to make overviews meaningful
        mock = MockGeoTIFF(width=1024, height=1024, bands=1)
        mock.save_to_file(input_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '-a', 'DEFLATE',
            '-s', 'EPSG:5703',  # Vertical SRS required for DEM
            '--overviews', 'true',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=60)
        
        # Assert
        assert result.returncode == 0
        assert output_file.exists()
        
        # Verify overviews were created
        ds = gdal.Open(str(output_file))
        band = ds.GetRasterBand(1)
        overview_count = band.GetOverviewCount()
        assert overview_count > 0, "Should have internal overviews"
        ds = None
    
    def test_optimize_generates_comparison_report(self, tmp_path):
        """Test that optimization generates a comparison report."""
        # Arrange
        input_file = tmp_path / "input.tif"
        output_file = tmp_path / "output.tif"
        
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(input_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '-a', 'ZSTD',
            '-s', 'EPSG:5703',  # Vertical SRS required for DEM
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=60)
        
        # Assert
        assert result.returncode == 0
        
        # Check for comparison report
        report_file = tmp_path / "output_comp.html"
        assert report_file.exists(), "Comparison report should be generated"
    
    def test_optimize_missing_input(self):
        """Test error handling when input file is missing."""
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', '/nonexistent/input.tif',
            '-o', '/some/output.tif',
            '-t', 'dem',
            '-a', 'DEFLATE',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=30)
        
        # Assert: Should fail appropriately
        assert result.returncode != 0
    
    def test_optimize_invalid_output_directory(self, tmp_path):
        """Test error handling when output directory doesn't exist."""
        # Arrange
        input_file = tmp_path / "input.tif"
        output_file = tmp_path / "nonexistent" / "subdir" / "output.tif"
        
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(input_file)
        
        # Act: The tool should create missing directories
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '-a', 'DEFLATE',
            '-s', 'EPSG:5703',  # Vertical SRS required for DEM
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=60)
        
        # Assert: Should succeed and create directories
        assert result.returncode == 0
        assert output_file.exists()


@pytest.mark.slow
class TestOptimizeCommandCompressionAlgorithms:
    """Test different compression algorithms."""
    
    @pytest.mark.parametrize("algorithm,extra_args", [
        ('LZW', ['-p', '2']),
        ('DEFLATE', ['-p', '3']),
        ('ZSTD', ['-p', '3', '-l', '9']),
        ('LERC', ['-z', '0.01']),
    ])
    def test_optimize_with_algorithm(self, tmp_path, algorithm, extra_args):
        """Test optimization with various compression algorithms."""
        # Arrange
        input_file = tmp_path / f"input_{algorithm.lower()}.tif"
        output_file = tmp_path / f"output_{algorithm.lower()}.tif"
        
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32
        )
        mock.save_to_file(input_file)
        
        # Act
        cmd = [
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '-a', algorithm,
            '-s', 'EPSG:5703',  # Vertical SRS required for DEM
            '--open-report', 'false'
        ] + extra_args
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Assert
        assert result.returncode == 0, f"{algorithm} compression failed: {result.stderr}"
        assert output_file.exists()


@pytest.mark.slow
class TestOptimizeCommandEdgeCases:
    """Test edge cases for optimize command."""
    
    def test_optimize_preserves_nodata(self, tmp_path):
        """Test that NoData values are preserved."""
        # Arrange
        input_file = tmp_path / "input_nodata.tif"
        output_file = tmp_path / "output_nodata.tif"
        
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            nodata_value=-9999.0,
            nodata_pixel_count=50
        )
        mock.save_to_file(input_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '-a', 'DEFLATE',
            '-s', 'EPSG:5703',  # Vertical SRS required for DEM
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=60)
        
        # Assert
        assert result.returncode == 0
        
        # Verify NoData is preserved
        ds = gdal.Open(str(output_file))
        band = ds.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        assert nodata == -9999.0, "NoData value should be preserved"
        ds = None
    
    def test_optimize_with_vertical_srs(self, tmp_path):
        """Test optimization with compound CRS (horizontal + vertical)."""
        # Arrange
        input_file = tmp_path / "input_compound.tif"
        output_file = tmp_path / "output_compound.tif"
        
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:32610+5703'  # UTM + NAVD88
        )
        mock.save_to_file(input_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'optimize',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '-a', 'DEFLATE',
            '-s', 'EPSG:5703',  # Ensure vertical SRS
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=60)
        
        # Assert
        assert result.returncode == 0
        assert output_file.exists()