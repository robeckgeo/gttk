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
        ], capture_output=True, text=True, timeout=180, cwd=tmp_path)  # Longer timeout for compression testing
        
        # Assert: Command should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        assert output_file.exists(), "Excel report should be created"
        # The scratch directory sits beside the workbook, named after the input; nothing
        # is written relative to the working directory (it used to be ./temp).
        assert (tmp_path / 'test_input_gttk_test').is_dir()
        assert not (tmp_path / 'temp').exists()
    
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
        # Each run works in its own run_* directory under --temp-dir
        temp_files = list(temp_dir.glob('run_*/*.tif'))
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

@pytest.mark.slow
class TestConcurrentRuns:

    def test_two_runs_on_one_input_do_not_disturb_each_other(self, tmp_path):
        """Candidate names are deterministic, so two runs sharing a scratch directory used
        to delete and overwrite each other's files; each run now works in its own
        subdirectory of the scratch root."""
        input_file = tmp_path / 'shared.tif'
        MockGeoTIFF(width=64, height=64, data_type=gdal.GDT_Float32, crs='EPSG:32610').save_to_file(input_file)
        runs = []
        for label in ('one', 'two'):
            runs.append(subprocess.Popen([
                sys.executable, '-m', 'gttk', 'test', '-i', str(input_file),
                '-o', str(tmp_path / f'{label}.xlsx'), '-t', 'dem',
                '--delete-test-files', 'true', '--open-report', 'false',
            ], cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True))
        outputs = [run.communicate(timeout=900)[0] for run in runs]
        assert [run.returncode for run in runs] == [0, 0], outputs
        assert (tmp_path / 'one.xlsx').exists() and (tmp_path / 'two.xlsx').exists()
        run_dirs = sorted(p.name for p in (tmp_path / 'shared_gttk_test').iterdir() if p.is_dir())
        assert len(run_dirs) == 2 and all(name.startswith('run_') for name in run_dirs)
        # Nothing -- the reference baseline included -- is written at the root the runs share.
        assert list((tmp_path / 'shared_gttk_test').glob('*.tif')) == []
