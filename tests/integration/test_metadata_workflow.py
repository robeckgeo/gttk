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
Integration tests for metadata extraction workflow.

These tests verify that multiple components work together correctly
to extract and process metadata from GeoTIFF files.
"""

import pytest
from pathlib import Path
from osgeo import gdal
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.report_builders import MetadataReportBuilder
from gttk.utils.report_formatters import HtmlReportFormatter, MarkdownReportFormatter


class TestMetadataExtractionWorkflow:
    """Test complete metadata extraction workflow."""
    
    def test_basic_metadata_extraction_workflow(self, tmp_path):
        """Test extracting metadata from a basic GeoTIFF through the full pipeline."""
        # Arrange: Create and save a mock GeoTIFF
        test_file = tmp_path / "test_basic.tif"
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:4326',
            compression='DEFLATE',
            predictor=2
        )
        mock.save_to_file(test_file)
        
        # Act: Extract metadata using MetadataExtractor
        with MetadataExtractor(str(test_file)) as extractor:
            tags = extractor.extract_tags()
            geokeys = extractor.extract_geokeys()
            stats = extractor.extract_statistics()
            
            # Assert: Verify data was extracted
            assert len(tags) > 0, "Should extract TIFF tags"
            assert any(tag.code == 256 for tag in tags), "Should have ImageWidth tag"
            assert any(tag.code == 257 for tag in tags), "Should have ImageLength tag"
            
            # GeoKeys should be present for GeoTIFF
            if extractor.is_geotiff and geokeys is not None:
                assert len(geokeys) > 0, "Should extract GeoKeys for GeoTIFF"
            
            # Statistics should be calculated
            assert stats is not None, "Statistics should not be None"
            assert len(stats) == 1, "Should have statistics for 1 band"
            # Single-band images are named "Gray" not "Band 1"
            assert stats[0].band_name == "Gray"
            assert stats[0].minimum is not None
            assert stats[0].maximum is not None
    
    def test_multiband_metadata_workflow(self, tmp_path):
        """Test metadata extraction for a multiband RGB image."""
        # Arrange: Create RGB image
        test_file = tmp_path / "test_rgb.tif"
        mock = MockGeoTIFF(
            width=512,
            height=512,
            bands=3,
            data_type=gdal.GDT_Byte,
            crs='EPSG:32610',
            compression='JPEG',
            quality=85,
            photometric='RGB'
        )
        mock.save_to_file(test_file)
        
        # Act: Extract metadata
        with MetadataExtractor(str(test_file)) as extractor:
            stats = extractor.extract_statistics()
            tags = extractor.extract_tags()
            
            # Assert: Verify multiband handling
            assert stats is not None, "Statistics should not be None"
            assert len(stats) == 3, "Should have statistics for 3 bands"
            # RGB bands are named "Red", "Green", "Blue" when photometric is RGB
            assert all(s.band_name in ["Red", "Green", "Blue"] for s in stats)
            
            # Check for JPEG-specific tags
            compression_tag = next((t for t in tags if t.code == 259), None)
            assert compression_tag is not None, "Should have compression tag"
    
    def test_dem_with_nodata_workflow(self, tmp_path):
        """Test metadata extraction for DEM with NoData values."""
        # Arrange: Create DEM with NoData
        test_file = tmp_path / "test_dem.tif"
        mock = MockGeoTIFF(
            width=1024,
            height=1024,
            bands=1,
            data_type=gdal.GDT_Float32,
            crs='EPSG:32610+5703',  # Compound CRS
            nodata_value=-9999.0,
            nodata_pixel_count=100,
            compression='ZSTD',
            predictor=3
        )
        mock.save_to_file(test_file)
        
        # Act: Extract metadata
        with MetadataExtractor(str(test_file)) as extractor:
            stats = extractor.extract_statistics()
            
            # Assert: Verify NoData handling
            assert stats is not None, "Statistics should not be None"
            assert len(stats) == 1
            assert stats[0].nodata_value == -9999.0
            assert stats[0].nodata_count == 100
            assert stats[0].has_nodata()
            
            # Verify compound CRS was detected
            assert extractor.is_geotiff
            assert extractor.geotiff_info is not None, "GeoTIFF info should not be None"
            # Vertical CRS info is stored in projection_info, not as separate vertical_srs object
            assert extractor.geotiff_info.projection_info is not None
            assert extractor.geotiff_info.projection_info.get('is_compound') == 1
            assert 'vertical_cs_name' in extractor.geotiff_info.projection_info
            assert extractor.geotiff_info.projection_info['vertical_cs_name'] == 'NAVD88 height'
    
    def test_report_builder_integration(self, tmp_path):
        """Test that MetadataReportBuilder correctly integrates with MetadataExtractor."""
        # Arrange: Create test file
        test_file = tmp_path / "test_report.tif"
        mock = MockGeoTIFF(
            width=256,
            height=256,
            bands=3,
            data_type=gdal.GDT_Byte,
            crs='EPSG:32610'
        )
        mock.save_to_file(test_file)
        
        # Act: Build report sections
        with MetadataExtractor(str(test_file)) as extractor:
            builder = MetadataReportBuilder(extractor, page=0, tag_scope='complete')
            builder.build(['tags', 'geokeys', 'statistics'])
            
            # Assert: Verify sections were built
            assert len(builder.sections) > 0, "Should build report sections"
            
            section_ids = [s.id for s in builder.sections]
            assert 'tags' in section_ids, "Should include tags section"
            assert 'statistics' in section_ids, "Should include statistics section"
            
            # Verify sections have data
            for section in builder.sections:
                if section.id in ['tags', 'statistics']:
                    assert section.has_data(), f"Section {section.id} should have data"
    
    def test_html_formatter_integration(self, tmp_path):
        """Test HTML report generation from extracted metadata."""
        # Arrange: Create test file and extract metadata
        test_file = tmp_path / "test_html.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(test_file)
        
        # Act: Generate HTML report
        with MetadataExtractor(str(test_file)) as extractor:
            builder = MetadataReportBuilder(extractor, page=0, tag_scope='complete')
            builder.build(['tags', 'statistics'])
            
            formatter = HtmlReportFormatter(filename=test_file.name)
            formatter.sections = builder.sections
            formatter.prepare_rendering()
            
            # Generate report content
            parts = []
            for section in formatter.sections:
                if section.has_data():
                    rendered = formatter._render_section(section)
                    if rendered:
                        parts.append(rendered)
            
            markdown_body = "\n\n".join(filter(None, parts))
            html_body = formatter._markdown_to_html(markdown_body)
            final_report = formatter._wrap_in_html_template(html_body)
            
            # Assert: Verify HTML structure
            assert final_report.startswith('<!DOCTYPE html>'), "Should be valid HTML"
            assert '<html' in final_report, "Should have html tag"
            assert '</html>' in final_report, "Should close html tag"
            assert test_file.name in final_report, "Should include filename"
    
    def test_markdown_formatter_integration(self, tmp_path):
        """Test Markdown report generation from extracted metadata."""
        # Arrange: Create test file
        test_file = tmp_path / "test_md.tif"
        mock = MockGeoTIFF(width=256, height=256, bands=1)
        mock.save_to_file(test_file)
        
        # Act: Generate Markdown report
        with MetadataExtractor(str(test_file)) as extractor:
            builder = MetadataReportBuilder(extractor, page=0, tag_scope='complete')
            builder.build(['tags', 'statistics'])
            
            formatter = MarkdownReportFormatter(filename=test_file.name)
            formatter.sections = builder.sections
            formatter.prepare_rendering()
            
            # Generate report
            header_md = formatter._render_header()
            parts = [header_md]
            
            for section in formatter.sections:
                if section.has_data():
                    rendered = formatter._render_section(section)
                    if rendered:
                        parts.append(rendered)
            
            parts.append(formatter._render_footer())
            final_report = "\n\n".join(filter(None, parts))
            
            # Assert: Verify Markdown structure
            # Title is in the header which may not be included in this test
            assert '## Table of Contents' in final_report, "Should have TOC"
            assert '## Complete* TIFF Tags' in final_report or '## Compact* TIFF Tags' in final_report, "Should have tags section"
            assert '## Statistics' in final_report, "Should have statistics section"
    
    def test_error_handling_corrupted_file(self, tmp_path):
        """Test that the workflow handles corrupted files gracefully."""
        # Arrange: Create a corrupted file
        test_file = tmp_path / "corrupted.tif"
        test_file.write_text("This is not a valid TIFF file")
        
        # Act & Assert: Should raise appropriate exception
        with pytest.raises((FileNotFoundError, ValueError, RuntimeError)):
            with MetadataExtractor(str(test_file)) as extractor:
                extractor.extract_tags()
    
    def test_error_handling_missing_file(self):
        """Test that the workflow handles missing files gracefully."""
        # Arrange: Use non-existent file path
        test_file = Path("/nonexistent/path/missing.tif")
        
        # Act & Assert: Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            with MetadataExtractor(str(test_file)) as extractor:
                extractor.extract_tags()
    
    def test_compressed_geotiff_workflow(self, tmp_path):
        """Test metadata extraction from compressed GeoTIFF with various algorithms."""
        compression_algorithms = ['DEFLATE', 'LZW', 'ZSTD']
        
        for algorithm in compression_algorithms:
            # Arrange: Create compressed file
            test_file = tmp_path / f"test_{algorithm.lower()}.tif"
            mock = MockGeoTIFF(
                width=512,
                height=512,
                bands=1,
                data_type=gdal.GDT_Float32,
                crs='EPSG:32610',
                compression=algorithm,
                predictor=3 if algorithm in ['DEFLATE', 'LZW', 'ZSTD'] else None,
                tiled=True,
                tile_size=256
            )
            mock.save_to_file(test_file)
            
            # Act: Extract metadata
            with MetadataExtractor(str(test_file)) as extractor:
                tags = extractor.extract_tags()
                
                # Assert: Verify compression was detected
                compression_tag = next((t for t in tags if t.code == 259), None)
                assert compression_tag is not None, f"Should have compression tag for {algorithm}"


class TestMetadataWorkflowEdgeCases:
    """Test edge cases in metadata extraction workflow."""
    
    def test_very_small_geotiff(self, tmp_path):
        """Test metadata extraction from very small GeoTIFF (1x1 pixel)."""
        # Arrange: Create minimal GeoTIFF
        test_file = tmp_path / "tiny.tif"
        mock = MockGeoTIFF(
            width=1,
            height=1,
            bands=1,
            data_type=gdal.GDT_Float32
        )
        mock.save_to_file(test_file)
        
        # Act: Extract metadata
        with MetadataExtractor(str(test_file)) as extractor:
            stats = extractor.extract_statistics()
            tags = extractor.extract_tags()
            
            # Assert: Should handle tiny images
            assert stats is not None, "Statistics should not be None"
            assert len(stats) == 1
            assert len(tags) > 0
            assert stats[0].valid_count == 1
    
    def test_geotiff_with_overviews(self, tmp_path):
        """Test metadata extraction from GeoTIFF with internal overviews."""
        # Arrange: Create GeoTIFF with overviews
        test_file = tmp_path / "with_overviews.tif"
        mock = MockGeoTIFF(
            width=1024,
            height=1024,
            bands=3,
            data_type=gdal.GDT_Byte,
            compression='DEFLATE',
            tiled=True
        )
        mock.save_to_file(test_file, TILED='YES', COMPRESS='DEFLATE')
        
        # Add overviews using GDAL
        ds = gdal.Open(str(test_file), gdal.GA_Update)
        ds.BuildOverviews('AVERAGE', [2, 4, 8])
        ds = None
        
        # Act: Extract metadata
        with MetadataExtractor(str(test_file)) as extractor:
            tags = extractor.extract_tags()
            
            # Assert: Should detect overviews
            assert len(tags) > 0, "Should extract tags from main image"
            # Additional overview-specific assertions could go here
    
    def test_geographic_vs_projected_crs(self, tmp_path):
        """Test metadata extraction handles both geographic and projected CRS."""
        test_cases = [
            ('EPSG:4326', 'geographic'),  # WGS 84 geographic
            ('EPSG:32610', 'projected'),  # UTM Zone 10N projected
        ]
        
        for crs_code, crs_type in test_cases:
            # Arrange
            test_file = tmp_path / f"test_{crs_type}.tif"
            mock = MockGeoTIFF(
                width=256,
                height=256,
                bands=1,
                crs=crs_code
            )
            mock.save_to_file(test_file)
            
            # Act
            with MetadataExtractor(str(test_file)) as extractor:
                geokeys = extractor.extract_geokeys()
                
                # Assert: Should extract CRS information
                assert geokeys is not None, f"GeoKeys should not be None for {crs_type}"
                assert len(geokeys) > 0, f"Should have GeoKeys for {crs_type} CRS"
                assert extractor.is_geotiff, f"Should recognize as GeoTIFF for {crs_type}"


@pytest.mark.slow
class TestMetadataWorkflowPerformance:
    """Performance tests for metadata extraction workflow."""
    
    def test_large_file_metadata_extraction(self, tmp_path):
        """Test metadata extraction performance on larger files."""
        # Arrange: Create larger test file
        test_file = tmp_path / "large.tif"
        mock = MockGeoTIFF(
            width=2048,
            height=2048,
            bands=3,
            data_type=gdal.GDT_Byte,
            compression='DEFLATE'
        )
        mock.save_to_file(test_file)
        
        # Act: Extract metadata (should complete reasonably quickly)
        with MetadataExtractor(str(test_file)) as extractor:
            import time
            start = time.time()
            
            tags = extractor.extract_tags()
            stats = extractor.extract_statistics()
            
            elapsed = time.time() - start
            
            # Assert: Should complete in reasonable time (< 5 seconds)
            assert elapsed < 5.0, f"Metadata extraction took too long: {elapsed:.2f}s"
            assert len(tags) > 0
            assert stats is not None, "Statistics should not be None"
            assert len(stats) == 3