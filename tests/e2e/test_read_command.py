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
End-to-End tests for the `gttk read` command.

These tests verify the complete workflow from CLI invocation to report generation.
"""

import subprocess
import sys
from osgeo import gdal
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF


class TestReadCommand:
    """Test the `gttk read` command end-to-end."""
    
    def test_read_basic_geotiff_html(self, tmp_path):
        """Test reading metadata from a basic GeoTIFF and generating HTML report."""
        # Arrange: Create test GeoTIFF
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:4326'
        )
        mock.save_to_file(test_file)
        
        # Act: Run gttk read command
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-f', 'html',
            '--open-report', 'false',
            '-v'
        ], capture_output=True, text=True)
        
        # Assert: Command should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        # Verify HTML report was created
        expected_report = tmp_path / "test_meta.html"
        assert expected_report.exists(), "HTML report should be created"
        
        # Verify HTML content
        content = expected_report.read_text(encoding='utf-8-sig')
        assert '<!DOCTYPE html>' in content, "Should be valid HTML"
        assert 'Metadata Report' in content, "Should have title"
        assert 'test.tif' in content, "Should include filename"
    
    def test_read_basic_geotiff_markdown(self, tmp_path):
        """Test reading metadata and generating Markdown report."""
        # Arrange
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(test_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-f', 'md',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        expected_report = tmp_path / "test_meta.md"
        assert expected_report.exists(), "Markdown report should be created"
        
        content = expected_report.read_text(encoding='utf-8')
        assert '# Metadata Report' in content, "Should have markdown title"
        assert '## Report Summary' in content, "Should have summary section"
    
    def test_read_with_custom_suffix(self, tmp_path):
        """Test read command with custom report suffix."""
        # Arrange
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(test_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '--report-suffix', '_custom',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        expected_report = tmp_path / "test_custom.html"
        assert expected_report.exists(), "Report with custom suffix should be created"
    
    def test_read_multiband_rgb(self, tmp_path):
        """Test reading metadata from RGB image."""
        # Arrange
        test_file = tmp_path / "rgb.tif"
        mock = MockGeoTIFF(
            width=512,
            height=512,
            bands=3,
            data_type=gdal.GDT_Byte,
            crs='EPSG:32610',
            photometric='RGB'
        )
        mock.save_to_file(test_file)
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        report_file = tmp_path / "rgb_meta.html"
        assert report_file.exists()
        
        content = report_file.read_text(encoding='utf-8-sig')
        # Should have statistics for all 3 bands (RGB uses Red/Green/Blue naming)
        assert ('Red' in content or 'Band 1' in content)
        assert ('Green' in content or 'Band 2' in content)
        assert ('Blue' in content or 'Band 3' in content)
    
    def test_read_with_specific_sections(self, tmp_path):
        """Test reading only specific metadata sections."""
        # Arrange
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(test_file)
        
        # Act: Request only tags and statistics
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-s', 'tags', 'statistics',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        report_file = tmp_path / "test_meta.html"
        content = report_file.read_text(encoding='utf-8-sig')
        
        # Should include requested sections
        assert 'Tags' in content or 'TIFF Tags' in content
        assert 'Statistics' in content
    
    def test_read_analyst_vs_producer(self, tmp_path):
        """Test analyst vs producer reader types."""
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            crs='EPSG:32610+5703'  # Compound CRS for more metadata
        )
        mock.save_to_file(test_file)
        
        # Test analyst mode
        result_analyst = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-r', 'analyst',
            '--report-suffix', '_analyst',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        assert result_analyst.returncode == 0
        
        # Test producer mode
        result_producer = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-r', 'producer',
            '--report-suffix', '_producer',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        assert result_producer.returncode == 0
        
        # Both reports should exist
        assert (tmp_path / "test_analyst.html").exists()
        assert (tmp_path / "test_producer.html").exists()
    
    def test_read_compact_vs_complete_tags(self, tmp_path):
        """Test compact vs complete tag scope."""
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(test_file)
        
        # Test compact tags
        result_compact = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-t', 'compact',
            '--report-suffix', '_compact',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        assert result_compact.returncode == 0
        
        # Test complete tags
        result_complete = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-t', 'complete',
            '--report-suffix', '_complete',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        assert result_complete.returncode == 0
        
        # Complete report should be longer (has more tags)
        compact_content = (tmp_path / "test_compact.html").read_text()
        complete_content = (tmp_path / "test_complete.html").read_text()
        
        # This is a simple heuristic - complete should have more content
        assert len(complete_content) >= len(compact_content)
    
    def test_read_with_pam_xml_generation(self, tmp_path):
        """Test PAM XML (.aux.xml) generation."""
        # Arrange
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=3,
            data_type=gdal.GDT_Byte
        )
        mock.save_to_file(test_file)
        
        # Act: Enable PAM XML writing
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-w', 'true',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        # Check for PAM XML file
        pam_file = tmp_path / "test.tif.aux.xml"
        assert pam_file.exists(), "PAM XML file should be created"
        
        # Verify it's valid XML with statistics
        pam_content = pam_file.read_text()
        assert '<PAMDataset>' in pam_content
        assert '<PAMRasterBand' in pam_content
    
    def test_read_invalid_file(self, tmp_path):
        """Test error handling for invalid file."""
        # Arrange: Create invalid file
        invalid_file = tmp_path / "invalid.tif"
        invalid_file.write_text("Not a TIFF file")
        
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(invalid_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert: Should fail gracefully
        assert result.returncode != 0, "Should fail for invalid file"
        # Error message is in stdout, not stderr
        output = result.stdout.lower() + result.stderr.lower()
        assert "error" in output or "not recognized" in output or "runtimeerror" in output
    
    def test_read_missing_file(self):
        """Test error handling for missing file."""
        # Act
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', '/nonexistent/missing.tif',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert: Command prints error but returns 0 (validation happens early)
        # Error message should mention file not found
        output = result.stderr.lower() + result.stdout.lower()
        assert 'not found' in output or 'does not exist' in output or 'validation failed' in output
    
    def test_read_with_banner(self, tmp_path):
        """Test adding classification banner to report."""
        # Arrange
        test_file = tmp_path / "classified.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(test_file)
        
        # Act: Add classification banner
        banner_text = "UNCLASSIFIED"
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-b', banner_text,
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0, f"Command failed: {result.stderr}"
        
        report_file = tmp_path / "classified_meta.html"
        content = report_file.read_text(encoding='utf-8-sig')
        assert banner_text in content, "Banner text should appear in report"
    
    def test_read_verbose_logging(self, tmp_path):
        """Test verbose logging output."""
        # Arrange
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(test_file)
        
        # Act: Run with verbose flag
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-v',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Assert
        assert result.returncode == 0
        # Verbose mode should produce log output
        combined_output = result.stdout + result.stderr
        # Should see some kind of progress/debug messages
        assert len(combined_output) > 0, "Verbose mode should produce output"


class TestReadCommandFormats:
    """Test different output formats for read command."""
    
    def test_read_html_format(self, tmp_path):
        """Test HTML report format specifics."""
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=3)
        mock.save_to_file(test_file)
        
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-f', 'html',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        
        report_file = tmp_path / "test_meta.html"
        content = report_file.read_text(encoding='utf-8-sig')
        
        # Verify HTML structure
        assert '<!DOCTYPE html>' in content
        assert '<html' in content  # May have attributes like lang="en"
        assert '</html>' in content
        assert '<head>' in content
        assert '<body>' in content
        # Should have navigation for multiple sections
        assert 'class="menu-bar"' in content
    
    def test_read_markdown_format(self, tmp_path):
        """Test Markdown report format specifics."""
        test_file = tmp_path / "test.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=3)
        mock.save_to_file(test_file)
        
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '-f', 'md',
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        
        report_file = tmp_path / "test_meta.md"
        # Read with UTF-8 (may have BOM)
        content = report_file.read_text(encoding='utf-8')
        
        # Verify Markdown structure (strip any BOM character)
        content_stripped = content.lstrip('\ufeff')
        assert content_stripped.startswith('#'), "Should start with heading"
        assert '## Table of Contents' in content
        assert '##' in content, "Should have section headings"
        # Markdown tables use pipes
        assert '|' in content, "Should have markdown tables"


class TestReadCommandEdgeCases:
    """Test edge cases for read command."""
    
    def test_read_tiny_geotiff(self, tmp_path):
        """Test reading 1x1 pixel GeoTIFF."""
        test_file = tmp_path / "tiny.tif"
        mock = MockGeoTIFF(width=1, height=1, bands=1)
        mock.save_to_file(test_file)
        
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0, "Should handle tiny images"
        assert (tmp_path / "tiny_meta.html").exists()
    
    def test_read_large_filename_with_spaces(self, tmp_path):
        """Test handling filename with spaces and special characters."""
        test_file = tmp_path / "test file with spaces.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(test_file)
        
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        # Report should use safe filename
        report_file = tmp_path / "test file with spaces_meta.html"
        assert report_file.exists()
    
    def test_read_no_crs(self, tmp_path):
        """Test reading GeoTIFF without coordinate system."""
        test_file = tmp_path / "no_crs.tif"
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            crs=None  # No CRS
        )
        mock.save_to_file(test_file)
        
        result = subprocess.run([
            sys.executable, '-m', 'gttk', 'read',
            '-i', str(test_file),
            '--open-report', 'false'
        ], capture_output=True, text=True)
        
        # Should still succeed even without CRS
        assert result.returncode == 0
        assert (tmp_path / "no_crs_meta.html").exists()