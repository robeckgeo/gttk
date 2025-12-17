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
End-to-End tests for the `gttk test` command.

These tests verify the compression testing workflow that compares multiple
compression algorithms and generates performance reports.

Note: These are slow tests as they perform multiple compression operations.
"""

import pytest
import subprocess
import sys
from osgeo import gdal
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF


@pytest.mark.slow
class TestTestCommand:
    """Test the `gttk test` command end-to-end."""
    
    def test_test_with_product_type_preset(self, tmp_path):
        """Test compression testing with a product type preset."""
        # Arrange: Create test file
        input_file = tmp_path / "test_input.tif"
        output_file = tmp_path / "compression_test.xlsx"
        
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:32610'
        )
        mock.save_to_file(input_file)
        
        # Act: Run test command with product type
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'test',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '--delete-test-files', 'true',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=180)  # Longer timeout for compression testing
        
        # Assert: Command should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert output_file.exists(), "Excel report should be created"
    
    def test_test_missing_input(self):
        """Test error handling when input file is missing."""
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'test',
            '-i', '/nonexistent/input.tif',
            '-t', 'dem',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=30)
        
        # Assert: Command doesn't fail with non-zero (prints "No GeoTIFF files found")
        # But indicates the issue in stdout
        output = result.stdout.lower() + result.stderr.lower()
        assert 'no geotiff files found' in output or 'not found' in output or 'nonexistent' in output
    
    def test_test_invalid_product_type(self, tmp_path):
        """Test error handling with invalid product type."""
        # Arrange
        input_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(input_file)
        
        # Act: Try with invalid product type
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'test',
            '-i', str(input_file),
            '-t', 'invalid_type',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=30)
        
        # Assert: Should fail with error about invalid choice
        assert result.returncode != 0
        assert 'invalid choice' in result.stderr.lower() or 'invalid' in result.stderr.lower()


@pytest.mark.slow  
class TestTestCommandOptions:
    """Test various options for the test command."""
    
    def test_test_with_temp_dir(self, tmp_path):
        """Test specifying custom temporary directory."""
        # Arrange
        input_file = tmp_path / "test.tif"
        output_file = tmp_path / "test_report.xlsx"
        temp_dir = tmp_path / "custom_temp"
        temp_dir.mkdir()
        
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(input_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'test',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '--temp-dir', str(temp_dir),
            '--delete-test-files', 'true',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=180)
        
        # Assert
        assert result.returncode == 0
        assert output_file.exists()
    
    def test_test_keeps_temp_files(self, tmp_path):
        """Test keeping temporary test files."""
        # Arrange
        input_file = tmp_path / "test.tif"
        output_file = tmp_path / "test_report.xlsx"
        temp_dir = tmp_path / "temp_files"
        
        mock = MockGeoTIFF(width=128, height=128, bands=1)
        mock.save_to_file(input_file)
        
        # Act: Don't delete test files
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'test',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '--temp-dir', str(temp_dir),
            '--delete-test-files', 'false',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=180)
        
        # Assert
        assert result.returncode == 0
        assert output_file.exists()
        # Temp directory should still exist with files
        assert temp_dir.exists()
        temp_files = list(temp_dir.glob('*.tif'))
        assert len(temp_files) > 0, "Temporary test files should be kept"


@pytest.mark.slow
class TestTestCommandEdgeCases:
    """Test edge cases for the test command."""
    
    def test_test_with_small_file(self, tmp_path):
        """Test compression testing on very small file."""
        # Arrange: Tiny file
        input_file = tmp_path / "tiny.tif"
        output_file = tmp_path / "tiny_test.xlsx"
        
        mock = MockGeoTIFF(width=64, height=64, bands=1)
        mock.save_to_file(input_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'test',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'dem',
            '--delete-test-files', 'true',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=180)
        
        # Assert: Should succeed even with small file
        assert result.returncode == 0
        assert output_file.exists()
    
    def test_test_with_multiband(self, tmp_path):
        """Test compression testing on multiband image."""
        # Arrange: RGB image
        input_file = tmp_path / "rgb.tif"
        output_file = tmp_path / "rgb_test.xlsx"
        
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=3,
            data_type=gdal.GDT_Byte,
            photometric='RGB'
        )
        mock.save_to_file(input_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'test',
            '-i', str(input_file),
            '-o', str(output_file),
            '-t', 'image',
            '--delete-test-files', 'true',
            '--open-report', 'false'
        ], capture_output=True, text=True, timeout=180)
        
        # Assert
        assert result.returncode == 0
        assert output_file.exists()