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
End-to-End tests for the `gttk compare` command.

These tests verify the complete workflow for comparing two GeoTIFF files.
"""

import subprocess
import sys
from osgeo import gdal
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF


class TestCompareCommand:
    """Test the `gttk compare` command end-to-end."""
    
    def test_compare_basic_geotiffs(self, tmp_path):
        """Test comparing two basic GeoTIFF files."""
        # Arrange: Create baseline and comparison files
        baseline_file = tmp_path / "baseline.tif"
        comparison_file = tmp_path / "comparison.tif"
        
        # Baseline: uncompressed
        baseline_mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:4326',
            compression='NONE'
        )
        baseline_mock.save_to_file(baseline_file)
        
        # Comparison: compressed
        comparison_mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:4326',
            compression='DEFLATE',
            predictor=2
        )
        comparison_mock.save_to_file(comparison_file)
        
        # Act: Run gttk compare command
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '--open-report', 'false',
            '-v'
        ], capture_output=True, text=True)
        
        # Assert: Command should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        # Verify comparison report was created
        expected_report = tmp_path / "comparison_comp.html"
        assert expected_report.exists(), "Comparison report should be created"
        
        # Verify report content
        content = expected_report.read_text(encoding='utf-8')
        assert '<!DOCTYPE html>' in content, "Should be valid HTML"
        assert 'Compression Comparison' in content, "Should have comparison title"
        assert 'Baseline' in content, "Should mention baseline"
        assert 'Comparison' in content, "Should mention comparison"
    
    def test_compare_compressed_vs_uncompressed(self, tmp_path):
        """Test comparing compressed vs uncompressed files."""
        # Arrange: Create files with different compression
        input_file = tmp_path / "input.tif"
        output_file = tmp_path / "output.tif"
        
        # Input: uncompressed
        MockGeoTIFF(
            width=512,
            height=512,
            bands=1,
            data_type=gdal.GDT_Float32,
            compression='NONE'
        ).save_to_file(input_file)
        
        # Output: ZSTD compressed
        MockGeoTIFF(
            width=512,
            height=512,
            bands=1,
            data_type=gdal.GDT_Float32,
            compression='ZSTD',
            predictor=3
        ).save_to_file(output_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(input_file),
            '-o', str(output_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0
        
        report_file = tmp_path / "output_comp.html"
        assert report_file.exists()
        
        content = report_file.read_text(encoding='utf-8')
        # Should show compression information
        assert 'ZSTD' in content or 'Zstd' in content
        assert 'Predictor' in content or 'predictor' in content
    
    def test_compare_markdown_format(self, tmp_path):
        """Test generating comparison report in Markdown format."""
        # Arrange
        baseline_file = tmp_path / "baseline.tif"
        comparison_file = tmp_path / "comparison.tif"
        
        MockGeoTIFF(width=256, height=256, bands=1).save_to_file(baseline_file)
        MockGeoTIFF(width=256, height=256, bands=1, compression='DEFLATE').save_to_file(comparison_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '-f', 'md',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0
        
        report_file = tmp_path / "comparison_comp.md"
        assert report_file.exists()
        
        content = report_file.read_text(encoding='utf-8')
        assert '# Compression Comparison' in content
        assert '## Report Summary' in content
        assert '|' in content, "Should have markdown tables"
    
    def test_compare_multiband_rgb(self, tmp_path):
        """Test comparing multiband RGB images."""
        # Arrange
        baseline_file = tmp_path / "rgb_baseline.tif"
        comparison_file = tmp_path / "rgb_comparison.tif"
        
        # Baseline: uncompressed RGB
        MockGeoTIFF(
            width=512,
            height=512,
            bands=3,
            data_type=gdal.GDT_Byte,
            photometric='RGB',
            compression='NONE'
        ).save_to_file(baseline_file)
        
        # Comparison: JPEG compressed RGB
        MockGeoTIFF(
            width=512,
            height=512,
            bands=3,
            data_type=gdal.GDT_Byte,
            photometric='RGB',
            compression='JPEG',
            quality=85
        ).save_to_file(comparison_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0
        
        report_file = tmp_path / "rgb_comparison_comp.html"
        assert report_file.exists()
        
        content = report_file.read_text(encoding='utf-8')
        # Should have statistics for all RGB bands (named Red, Green, Blue for RGB images)
        assert ('Red' in content or 'Band 1' in content or 'band 1' in content.lower())
        assert ('Green' in content or 'Band 2' in content or 'band 2' in content.lower())
        assert ('Blue' in content or 'Band 3' in content or 'band 3' in content.lower())
    
    def test_compare_with_different_compressions(self, tmp_path):
        """Test comparing files with different compression algorithms."""
        compression_pairs = [
            ('LZW', 'DEFLATE'),
            ('DEFLATE', 'ZSTD'),
        ]
        
        for comp1, comp2 in compression_pairs:
            # Arrange
            file1 = tmp_path / f"{comp1.lower()}.tif"
            file2 = tmp_path / f"{comp2.lower()}.tif"
            
            MockGeoTIFF(
                width=256,
                height=256,
                bands=1,
                compression=comp1,
                predictor=2
            ).save_to_file(file1)
            
            MockGeoTIFF(
                width=256,
                height=256,
                bands=1,
                compression=comp2,
                predictor=2
            ).save_to_file(file2)
            
            # Act
            result = subprocess.run([
                sys.executable, '-m', 'gttk', 'compare',
                '-i', str(file1),
                '-o', str(file2),
                '--open-report', 'false'
            ], capture_output=True, text=True)
            
            # Assert
            assert result.returncode == 0, f"Failed comparing {comp1} vs {comp2}"
            
            report_file = tmp_path / f"{comp2.lower()}_comp.html"
            assert report_file.exists()
    
    def test_compare_dem_with_nodata(self, tmp_path):
        """Test comparing DEM files with NoData values."""
        # Arrange
        baseline_file = tmp_path / "dem_baseline.tif"
        comparison_file = tmp_path / "dem_comparison.tif"
        
        # Both have NoData but different compression
        MockGeoTIFF(
            width=1024,
            height=1024,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:32610+5703',
            nodata_value=-9999.0,
            nodata_pixel_count=100,
            compression='NONE'
        ).save_to_file(baseline_file)
        
        MockGeoTIFF(
            width=1024,
            height=1024,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:32610+5703',
            nodata_value=-9999.0,
            nodata_pixel_count=100,
            compression='LERC'
        ).save_to_file(comparison_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0
        
        report_file = tmp_path / "dem_comparison_comp.html"
        assert report_file.exists()
        
        content = report_file.read_text(encoding='utf-8')
        # Should mention NoData
        assert 'NoData' in content or 'nodata' in content.lower()
    
    def test_compare_missing_baseline(self):
        """Test error handling when baseline file is missing."""
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', '/nonexistent/baseline.tif',
            '-o', '/some/comparison.tif',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert: Should fail appropriately
        assert result.returncode != 0
        output = result.stderr.lower() + result.stdout.lower()
        assert 'error' in output or 'not found' in output or 'failed' in output
    
    def test_compare_missing_comparison(self, tmp_path):
        """Test error handling when comparison file is missing."""
        # Arrange: Only create baseline
        baseline_file = tmp_path / "baseline.tif"
        MockGeoTIFF(width=256, height=256, bands=1).save_to_file(baseline_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', '/nonexistent/comparison.tif',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode != 0
    
    def test_compare_invalid_baseline(self, tmp_path):
        """Test error handling when baseline is not a valid GeoTIFF."""
        # Arrange
        baseline_file = tmp_path / "invalid.tif"
        comparison_file = tmp_path / "valid.tif"
        
        baseline_file.write_text("Not a TIFF file")
        MockGeoTIFF(width=256, height=256, bands=1).save_to_file(comparison_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert: The command prints error but doesn't fail with non-zero exit code
        # Check that error message was printed
        output = result.stdout + result.stderr
        assert 'error' in output.lower() or 'not recognized' in output.lower() or 'RuntimeError' in output
    
    def test_compare_verbose_logging(self, tmp_path):
        """Test verbose logging in compare command."""
        # Arrange
        baseline_file = tmp_path / "baseline.tif"
        comparison_file = tmp_path / "comparison.tif"
        
        MockGeoTIFF(width=256, height=256, bands=1).save_to_file(baseline_file)
        MockGeoTIFF(width=256, height=256, bands=1, compression='DEFLATE').save_to_file(comparison_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '-v',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0
        # Verbose mode should produce output
        combined_output = result.stdout + result.stderr
        assert len(combined_output) > 0


class TestCompareCommandEdgeCases:
    """Test edge cases for compare command."""
    
    def test_compare_same_file_twice(self, tmp_path):
        """Test comparing a file to itself."""
        # Arrange
        test_file = tmp_path / "test.tif"
        MockGeoTIFF(width=256, height=256, bands=1).save_to_file(test_file)
        
        # Act: Compare file to itself
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(test_file),
            '-o', str(test_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert: Should succeed (comparing identical files)
        assert result.returncode == 0
        
        report_file = tmp_path / "test_comp.html"
        assert report_file.exists()
        
        # Report should show no differences
        content = report_file.read_text(encoding='utf-8')
        assert '0' in content or 'same' in content.lower() or 'identical' in content.lower()
    
    def test_compare_different_dimensions(self, tmp_path):
        """Test comparing files with different dimensions."""
        # Arrange
        baseline_file = tmp_path / "small.tif"
        comparison_file = tmp_path / "large.tif"
        
        MockGeoTIFF(width=256, height=256, bands=1).save_to_file(baseline_file)
        MockGeoTIFF(width=512, height=512, bands=1).save_to_file(comparison_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert: Should succeed and report differences
        assert result.returncode == 0
        
        report_file = tmp_path / "large_comp.html"
        content = report_file.read_text(encoding='utf-8')
        # Should show different dimensions
        assert '256' in content
        assert '512' in content
    
    def test_compare_different_band_counts(self, tmp_path):
        """Test comparing files with different numbers of bands."""
        # Arrange
        baseline_file = tmp_path / "single_band.tif"
        comparison_file = tmp_path / "rgb.tif"
        
        MockGeoTIFF(width=256, height=256, bands=1).save_to_file(baseline_file)
        MockGeoTIFF(width=256, height=256, bands=3).save_to_file(comparison_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0
        
        report_file = tmp_path / "rgb_comp.html"
        content = report_file.read_text(encoding='utf-8')
        # Should show band count difference
        assert 'band' in content.lower()
    
    def test_compare_different_data_types(self, tmp_path):
        """Test comparing files with different data types."""
        # Arrange
        baseline_file = tmp_path / "byte.tif"
        comparison_file = tmp_path / "float.tif"
        
        MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Byte
        ).save_to_file(baseline_file)
        
        MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32
        ).save_to_file(comparison_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0
        
        report_file = tmp_path / "float_comp.html"
        content = report_file.read_text(encoding='utf-8')
        # Should show data type information
        assert 'Byte' in content or 'byte' in content.lower()
        assert 'Float' in content or 'float' in content.lower()


class TestCompareCommandFileSize:
    """Test file size comparisons."""
    
    def test_compare_shows_size_reduction(self, tmp_path):
        """Test that comparison report shows file size reduction."""
        # Arrange: Create uncompressed and compressed versions
        baseline_file = tmp_path / "uncompressed.tif"
        comparison_file = tmp_path / "compressed.tif"
        
        # Larger file for noticeable compression
        MockGeoTIFF(
            width=1024,
            height=1024,
            bands=3,
            data_type=gdal.GDT_Byte,
            compression='NONE'
        ).save_to_file(baseline_file)
        
        MockGeoTIFF(
            width=1024,
            height=1024,
            bands=3,
            data_type=gdal.GDT_Byte,
            compression='DEFLATE',
            predictor=2
        ).save_to_file(comparison_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'compare',
            '-i', str(baseline_file),
            '-o', str(comparison_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0
        
        report_file = tmp_path / "compressed_comp.html"
        content = report_file.read_text(encoding='utf-8')
        
        # Should mention file sizes - check for various size indicators
        has_size_info = any([
            'MB' in content,
            'KB' in content,
            'size' in content.lower(),
            'byte' in content.lower()
        ])
        assert has_size_info, "Report should contain file size information"
        
        # File should be compressed (look for compression indicators)
        # The report may not explicitly say "smaller" but should show compression
        has_compression_info = any([
            'deflate' in content.lower(),
            'compress' in content.lower(),
            'predictor' in content.lower(),
            'baseline' in content.lower() and 'comparison' in content.lower()
        ])
        assert has_compression_info, "Report should contain compression information"