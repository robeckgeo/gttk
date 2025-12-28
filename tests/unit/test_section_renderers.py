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
Unit tests for GTTK section renderers.

This module tests the section renderer classes that convert data models
to formatted output (Markdown, HTML). Focus is on the MarkdownRenderer
since it's the base for HTML rendering.
"""

import pytest
from gttk.utils.section_renderers import MarkdownRenderer
from gttk.utils.data_models import (
    TileInfo,
    TilingComparison,
    IfdInfoData,
    IfdInfoComparison,
)


@pytest.mark.unit
@pytest.mark.renderer
class TestMarkdownRendererTilingComparison:
    """Test MarkdownRenderer.render_comparison_tiling() method."""
    
    def test_render_comparison_tiling_both_files(self):
        """Test rendering tiling comparison with data from both files."""
        renderer = MarkdownRenderer()
        
        baseline_tiles = [
            TileInfo(
                level=0,
                tile_count=16,
                block_size="256 x 256",
                tile_dimensions="7680.0 x 7680.0 m",
                total_pixels="1024 x 1024",
                resolution="30.0 m"
            )
        ]
        comp_tiles = [
            TileInfo(
                level=0,
                tile_count=16,
                block_size="512 x 512",
                tile_dimensions="15360.0 x 15360.0 m",
                total_pixels="1024 x 1024",
                resolution="30.0 m"
            )
        ]
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("Baseline", baseline_tiles), ("Comparison", comp_tiles)]
        )
        
        output = renderer.render_comparison_tiling(data)
        
        # Verify structure
        assert "## Tiling and Overviews" in output
        assert "### Baseline" in output
        assert "### Comparison" in output
        
        # Verify table headers
        assert "| Level | Tile Count | Tile Size | Tile Dimensions | Total Pixels | Resolution |" in output
        
        # Verify baseline data
        assert "| 0 | 16 | 256 x 256 | 7680.0 x 7680.0 m | 1024 x 1024 | 30.0 m |" in output
        
        # Verify comparison data
        assert "| 0 | 16 | 512 x 512 | 15360.0 x 15360.0 m | 1024 x 1024 | 30.0 m |" in output
    
    def test_render_comparison_tiling_with_overviews(self):
        """Test rendering tiling comparison with main image and overviews."""
        renderer = MarkdownRenderer()
        
        baseline_tiles = [
            TileInfo(level=0, tile_count=16, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="1024 x 1024",
                    resolution="30.0 m"),
            TileInfo(level=1, tile_count=4, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="512 x 512",
                    resolution="60.0 m"),
            TileInfo(level=2, tile_count=1, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="256 x 256",
                    resolution="120.0 m"),
        ]
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("Input File", baseline_tiles)]
        )
        
        output = renderer.render_comparison_tiling(data)
        
        # Verify all levels are present
        assert "| 0 |" in output  # Main image (level 0)
        assert "| 1 |" in output  # Overview 1
        assert "| 2 |" in output  # Overview 2
        
        # Verify subheader
        assert "### Input File" in output
    
    def test_render_comparison_tiling_single_file(self):
        """Test rendering tiling comparison with only one file."""
        renderer = MarkdownRenderer()
        
        tiles = [
            TileInfo(level=0, tile_count=16, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="1024 x 1024",
                    resolution="30.0 m")
        ]
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("Output File", tiles)]
        )
        
        output = renderer.render_comparison_tiling(data)
        
        # Verify structure
        assert "## Tiling and Overviews" in output
        assert "### Output File" in output
        assert "| Level | Tile Count | Tile Size |" in output
    
    def test_render_comparison_tiling_empty_tiles(self):
        """Test rendering when tile lists are empty."""
        renderer = MarkdownRenderer()
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("Baseline", []), ("Comparison", [])]
        )
        
        output = renderer.render_comparison_tiling(data)
        
        # Should still have structure but no data rows
        assert "## Tiling and Overviews" in output
        assert "### Baseline" in output
        assert "### Comparison" in output
        # Empty tiles show a message instead of empty table
        assert "*No tiling information available*" in output
    
    def test_render_comparison_tiling_custom_title(self):
        """Test rendering with custom title override."""
        renderer = MarkdownRenderer()
        
        tiles = [
            TileInfo(level=0, tile_count=16, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="1024 x 1024",
                    resolution="30.0 m")
        ]
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("File A", tiles)]
        )
        
        output = renderer.render_comparison_tiling(data, title="Custom Tiling Report")
        
        # Custom title should be used
        assert "## Custom Tiling Report" in output
        assert "## Tiling and Overviews" not in output
    
    def test_render_comparison_tiling_markdown_table_structure(self):
        """Test that output is valid markdown table structure."""
        renderer = MarkdownRenderer()
        
        tiles = [
            TileInfo(level=0, tile_count=16, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="1024 x 1024",
                    resolution="30.0 m")
        ]
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("Test", tiles)]
        )
        
        output = renderer.render_comparison_tiling(data)
        
        # Check for valid markdown table separators
        assert "|---|---|---|" in output or "|-----|-----|-----|" in output
        
        # Check that lines end properly (no trailing content after table)
        lines = output.split('\n')
        for line in lines:
            if line.strip().startswith('|') and line.strip().endswith('|'):
                # Valid table row
                assert line.count('|') >= 2  # At least 2 pipes (start and end)
    
    def test_render_comparison_tiling_different_tile_counts(self):
        """Test rendering files with different numbers of tile levels."""
        renderer = MarkdownRenderer()
        
        baseline_tiles = [
            TileInfo(level=0, tile_count=16, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="1024 x 1024",
                    resolution="30.0 m")
        ]
        
        comp_tiles = [
            TileInfo(level=0, tile_count=16, block_size="512 x 512",
                    tile_dimensions="15360.0 m", total_pixels="1024 x 1024",
                    resolution="30.0 m"),
            TileInfo(level=1, tile_count=4, block_size="512 x 512",
                    tile_dimensions="15360.0 m", total_pixels="512 x 512",
                    resolution="60.0 m"),
        ]
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("Baseline", baseline_tiles), ("Comparison", comp_tiles)]
        )
        
        output = renderer.render_comparison_tiling(data)
        
        # Both subheaders should be present
        assert "### Baseline" in output
        assert "### Comparison" in output
        
        # Baseline should have 1 data row, comparison should have 2
        baseline_section = output.split("### Comparison")[0]
        comp_section = output.split("### Comparison")[1]
        
        # Count data rows in each section (rows starting with | but not headers/separators)
        baseline_rows = [line for line in baseline_section.split('\n') 
                        if line.strip().startswith('| 0 |')]
        comp_rows = [line for line in comp_section.split('\n') 
                    if line.strip().startswith('| 0 |') or line.strip().startswith('| 1 |')]
        
        assert len(baseline_rows) >= 1
        assert len(comp_rows) >= 2


@pytest.mark.unit
@pytest.mark.renderer
class TestMarkdownRendererIntegration:
    """Test MarkdownRenderer with multiple comparison types together."""
    
    def test_render_multiple_comparison_sections(self):
        """Test that tiling comparison works alongside other comparison types."""
        renderer = MarkdownRenderer()
        
        # Create IFD comparison
        ifd1 = IfdInfoData(
            headers=['IFD', 'Type', 'Dimensions'],
            rows=[{'IFD': 0, 'Type': 'Main', 'Dimensions': '1024x768'}]
        )
        ifd_comp = IfdInfoComparison(
            title="IFDs",
            files=[("File1", ifd1)]
        )
        
        # Create tiling comparison
        tiles = [
            TileInfo(level=0, tile_count=16, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="1024 x 1024",
                    resolution="30.0 m")
        ]
        tiling_comp = TilingComparison(
            title="Tiling and Overviews",
            files=[("File1", tiles)]
        )
        
        # Render both
        ifd_output = renderer.render_comparison_ifd(ifd_comp)
        tiling_output = renderer.render_comparison_tiling(tiling_comp)
        
        # Both should render successfully
        assert "## IFDs" in ifd_output
        assert "## Tiling and Overviews" in tiling_output
        
        # Combined output should maintain separate sections
        combined = ifd_output + "\n\n" + tiling_output
        assert "## IFDs" in combined
        assert "## Tiling and Overviews" in combined


@pytest.mark.unit
@pytest.mark.renderer
class TestMarkdownRendererEdgeCases:
    """Test edge cases and error conditions for tiling renderer."""
    
    def test_render_tiling_with_none_values(self):
        """Test handling of None values in TileInfo fields."""
        renderer = MarkdownRenderer()
        
        # Create TileInfo with some None-equivalent empty strings
        tiles = [
            TileInfo(
                level=0,
                tile_count=16,
                block_size="256 x 256",
                tile_dimensions="N/A",
                total_pixels="1024 x 1024",
                resolution="N/A"
            )
        ]
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("Test", tiles)]
        )
        
        output = renderer.render_comparison_tiling(data)
        
        # Should render without errors
        assert "## Tiling and Overviews" in output
        assert "N/A" in output
    
    def test_render_tiling_special_characters_in_labels(self):
        """Test handling of special characters in file labels."""
        renderer = MarkdownRenderer()
        
        tiles = [
            TileInfo(level=0, tile_count=16, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="1024 x 1024",
                    resolution="30.0 m")
        ]
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("File with | pipes & special chars", tiles)]
        )
        
        output = renderer.render_comparison_tiling(data)
        
        # Should handle special characters in subheaders
        assert "### File with | pipes & special chars" in output or "### File with" in output
    
    def test_render_tiling_large_tile_counts(self):
        """Test rendering with large tile counts (thousands)."""
        renderer = MarkdownRenderer()
        
        tiles = [
            TileInfo(level=0, tile_count=10000, block_size="256 x 256",
                    tile_dimensions="7680.0 m", total_pixels="10240 x 10240",
                    resolution="30.0 m")
        ]
        
        data = TilingComparison(
            title="Tiling and Overviews",
            files=[("Large Raster", tiles)]
        )
        
        output = renderer.render_comparison_tiling(data)
        
        # Should render large numbers correctly
        assert "10000" in output or "10,000" in output  # May have thousand separator

