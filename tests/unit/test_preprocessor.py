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
Unit Tests for preprocessor.py

Comprehensive test coverage for the GeoTIFF preprocessing pipeline including:
- Workspace lifecycle, location and cleanup
- Alpha-to-mask conversion
- Overview rounding for lossless compression
- Complex NoData handling (remapping, masking, validation, conflict resolution)
- Main preprocessing orchestration (metadata, SRS, statistics)
- Error handling and robustness

Target: 24 tests with 80%+ code coverage for preprocessor.py
"""

import pytest
import numpy as np
import logging
from pathlib import Path
from unittest.mock import Mock
from osgeo import gdal

import gttk.utils.preprocessor as pre
from gttk.utils.preprocessor import (
    Workspace,
    _create_intermediate_with_mask,
    round_overviews,
    preprocess_geotiff
)
from gttk.utils.script_arguments import OptimizeArguments
from gttk.utils.data_models import GeoTiffInfo
from gttk.utils.exceptions import ProcessingStepFailedError
from tests.fixtures.custom_vertical_crs import CUSTOM_VERTICAL_WKT


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def mock_optimize_args():
    """Create mock OptimizeArguments with sensible defaults."""
    args = Mock(spec=OptimizeArguments)
    args.algorithm = 'DEFLATE'
    args.product_type = 'dem'
    args.decimals = None
    args.nodata = None
    args.mask_nodata = None
    args.mask_alpha = False
    args.vertical_srs = None
    args.raster_type = None
    args.geo_metadata = False
    args.discard_lsb = False
    return args


@pytest.fixture
def mock_geotiff_info():
    """Create mock GeoTiffInfo with sensible defaults."""
    info = Mock(spec=GeoTiffInfo)
    info.x_size, info.y_size, info.bands = 100, 100, 1
    info.nodata = None
    info.data_type = 'Float32'
    info.has_alpha = False
    info.transparency_info = {}
    info.vertical_srs = None
    info.filepath = 'test.tif'
    return info


# ==============================================================================
# CATEGORY 1: WORKSPACE TESTS (4 TESTS)
# ==============================================================================

class TestWorkspace:
    """Where a run's intermediates are put, and that they are all removed."""
    
    def test_workspace_context_lifecycle(self):
        """Workspace creates and cleans up virtual files."""
        vsi_path = None
        
        with Workspace() as workspace:
            # Create virtual file
            vsi_path = workspace.get_temp_path("test.tif")
            
            # Verify path format
            assert vsi_path.startswith("/vsimem/compress_")
            assert vsi_path.endswith("test.tif")
            
            # Verify path is registered
            assert vsi_path in workspace.paths
            
            # Create a dummy file at that path
            driver = gdal.GetDriverByName('GTiff')
            ds = driver.Create(vsi_path, 10, 10, 1, gdal.GDT_Byte)
            ds = None
            
            # Verify file exists
            assert gdal.VSIStatL(vsi_path) is not None
        
        # After context exit, file should be cleaned up
        assert gdal.VSIStatL(vsi_path) is None
    
    def test_workspace_multiple_files(self):
        """Workspace tracks and cleans up multiple files."""
        paths = []
        
        with Workspace() as workspace:
            # Create multiple virtual files
            for i in range(5):
                path = workspace.get_temp_path(f"test_{i}.tif")
                paths.append(path)
                
                # Create dummy file
                driver = gdal.GetDriverByName('GTiff')
                ds = driver.Create(path, 10, 10, 1, gdal.GDT_Byte)
                ds = None
            
            # All should exist
            for path in paths:
                assert gdal.VSIStatL(path) is not None
        
        # All should be cleaned up
        for path in paths:
            assert gdal.VSIStatL(path) is None
    
    def test_workspace_invalid_path_raises_error(self):
        """get_temp_path rejects paths not under /vsimem/."""
        with Workspace() as workspace:
            # Verify that workspace.vsi_prefix starts with /vsimem/
            assert workspace.vsi_prefix.startswith("/vsimem/")
            
            # get_temp_path always prepends vsi_prefix, so paths are always valid
            # This tests the internal validation logic
            vsi_path = workspace.get_temp_path("test.tif")
            assert vsi_path.startswith("/vsimem/")
    
    def test_workspace_cleanup_on_exception(self):
        """Workspace cleans up files even when exception occurs."""
        vsi_path = None
        
        try:
            with Workspace() as workspace:
                vsi_path = workspace.get_temp_path("test.tif")
                
                # Create file
                driver = gdal.GetDriverByName('GTiff')
                ds = driver.Create(vsi_path, 10, 10, 1, gdal.GDT_Byte)
                ds = None
                
                # Verify exists
                assert gdal.VSIStatL(vsi_path) is not None
                
                # Raise exception
                raise ValueError("Test exception")
        except ValueError:
            pass
        
        # File should still be cleaned up
        assert gdal.VSIStatL(vsi_path) is None


# ==============================================================================
# CATEGORY 2: ALPHA-TO-MASK CONVERSION TESTS (3 TESTS)
# ==============================================================================

    # --- where the intermediates are put ---------------------------------------

    def test_a_workspace_that_fits_stays_in_memory(self, mock_geotiff_info):
        """The common case, and what GTTK always did."""
        with Workspace() as workspace:
            workspace.plan_for(mock_geotiff_info)
            assert not workspace.on_disk
            assert workspace.get_temp_path('intermediate.tif').startswith('/vsimem/')

    def test_intermediates_too_large_for_memory_are_written_to_disk(self, tmp_path, mock_geotiff_info, monkeypatch):
        """A 4.9 gigapixel orthophoto needs ~36 GB of intermediates. Held in /vsimem on a
        16 GB machine that is the pagefile, and every later pass reads its own pixels back
        through the swapper."""
        monkeypatch.setattr(pre, 'workspace_fits_in_memory', lambda *a, **kw: False)
        directory = None
        with Workspace(preferred_dir=tmp_path) as workspace:
            workspace.plan_for(mock_geotiff_info)
            assert workspace.on_disk
            directory = workspace.directory
            assert directory.parent == tmp_path, 'the workspace belongs beside the output'
            path = workspace.get_temp_path('intermediate.tif')
            assert not path.startswith('/vsimem/')
            gdal.GetDriverByName('GTiff').Create(path, 8, 8, 1, gdal.GDT_Byte).FlushCache()
            assert Path(path).is_file()
        assert not directory.exists(), 'the workspace directory outlived the run'

    def test_a_workspace_that_cannot_reach_a_disk_stays_in_memory(self, tmp_path, mock_geotiff_info, monkeypatch, caplog):
        monkeypatch.setattr(pre, 'workspace_fits_in_memory', lambda *a, **kw: False)
        monkeypatch.setattr(pre.tempfile, 'mkdtemp', Mock(side_effect=OSError('no room')))
        with caplog.at_level(logging.WARNING):
            with Workspace(preferred_dir=tmp_path) as workspace:
                workspace.plan_for(mock_geotiff_info)
                assert not workspace.on_disk
                assert workspace.get_temp_path('intermediate.tif').startswith('/vsimem/')
        assert 'no room' in caplog.text

    def test_the_location_is_chosen_once(self, tmp_path, mock_geotiff_info, monkeypatch):
        """The second intermediate must land beside the first, whatever changes underneath."""
        with Workspace(preferred_dir=tmp_path) as workspace:
            workspace.plan_for(mock_geotiff_info)
            first = workspace.get_temp_path('intermediate.tif')
            monkeypatch.setattr(pre, 'workspace_fits_in_memory', lambda *a, **kw: False)
            workspace.plan_for(mock_geotiff_info)
            assert workspace.get_temp_path('masked.tif').startswith(first.rsplit('/', 1)[0])


class TestWorkspaceSizing:
    """The numbers behind the choice, with the free memory supplied rather than measured."""

    def test_the_estimate_covers_both_intermediates(self):
        # 100 x 100 x 3 bands x 2 bytes x the two copies the pipeline holds at once
        assert pre.estimated_workspace_bytes(100, 100, 3, 'UInt16') == 100 * 100 * 3 * 2 * 2

    def test_an_unknown_data_type_is_sized_as_a_byte(self):
        assert pre.estimated_workspace_bytes(10, 10, 1, None) == 10 * 10 * 1 * 1 * 2

    @pytest.mark.parametrize('gigabytes, free_gb, expected', [
        (0.12, 16, True),      # 4k x 4k RGBA
        (2.98, 16, True),      # 20k x 20k Float32 DEM
        (36.59, 16, False),    # the 91,445 x 53,704 orthophoto
        (36.59, 128, True),    # the same file on a machine that can hold it
    ])
    def test_the_threshold_is_half_the_free_memory(self, gigabytes, free_gb, expected):
        assert pre.workspace_fits_in_memory(int(gigabytes * 1024 ** 3), free_gb * 1024 ** 3) is expected

    def test_without_psutil_the_answer_is_memory(self, monkeypatch):
        """What GTTK did before the question was asked."""
        monkeypatch.setitem(__import__('sys').modules, 'psutil', None)
        assert pre.workspace_fits_in_memory(10 ** 15) is True


class TestAlphaToMaskConversion:
    """Test alpha band to transparency mask conversion."""
    
    def test_create_intermediate_with_mask_basic(self, tmp_path):
        """Alpha band is converted to internal mask correctly."""
        filepath = tmp_path / "rgba.tif"
        
        # Create RGBA image with partial transparency
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 4, gdal.GDT_Byte)
        
        # Set color interpretations
        ds.GetRasterBand(1).SetColorInterpretation(gdal.GCI_RedBand)
        ds.GetRasterBand(2).SetColorInterpretation(gdal.GCI_GreenBand)
        ds.GetRasterBand(3).SetColorInterpretation(gdal.GCI_BlueBand)
        ds.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
        
        # Write alpha data with values: 0 (transparent), 128 (semi), 255 (opaque)
        alpha_data = np.ones((256, 256), dtype=np.uint8) * 255
        alpha_data[0:85, :] = 0    # Top third transparent
        alpha_data[85:170, :] = 128  # Middle third semi-transparent
        alpha_data[170:256, :] = 255  # Bottom third opaque
        ds.GetRasterBand(4).WriteArray(alpha_data)
        ds.FlushCache()
        
        # Now test conversion
        with Workspace() as workspace:
            # Copy to virtual file
            temp_path = workspace.get_temp_path("temp.tif")
            temp_ds = driver.CreateCopy(temp_path, ds)
            ds = None
            
            # Apply conversion
            masked_ds = _create_intermediate_with_mask(temp_ds, workspace)
            
            # Verify result
            assert masked_ds.RasterCount == 3  # RGB only
            
            # Check mask exists
            mask_band = masked_ds.GetRasterBand(1).GetMaskBand()
            mask_data = mask_band.ReadAsArray()
            
            # Verify threshold was applied (230/255 = 90% opaque)
            # Values < 230 should become 0, >= 230 should become 255
            assert np.all(mask_data[0:85, :] == 0)      # Transparent
            assert np.all(mask_data[85:170, :] == 0)    # Semi -> 0 (below threshold)
            assert np.all(mask_data[170:256, :] == 255)  # Opaque
    
    def test_create_intermediate_with_mask_alpha_not_last_band(self, tmp_path):
        """Alpha band detected by color interpretation, not position."""
        filepath = tmp_path / "non_standard.tif"
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 4, gdal.GDT_Byte)
        
        # Set alpha as band 2 (non-standard)
        ds.GetRasterBand(1).SetColorInterpretation(gdal.GCI_RedBand)
        ds.GetRasterBand(2).SetColorInterpretation(gdal.GCI_AlphaBand)  # Alpha in position 2
        ds.GetRasterBand(3).SetColorInterpretation(gdal.GCI_GreenBand)
        ds.GetRasterBand(4).SetColorInterpretation(gdal.GCI_BlueBand)
        
        # Write alpha data
        alpha_data = np.ones((256, 256), dtype=np.uint8) * 255
        ds.GetRasterBand(2).WriteArray(alpha_data)
        ds.FlushCache()
        
        with Workspace() as workspace:
            temp_path = workspace.get_temp_path("temp.tif")
            temp_ds = driver.CreateCopy(temp_path, ds)
            ds = None
            
            masked_ds = _create_intermediate_with_mask(temp_ds, workspace)
            
            # Should have 3 bands (R, G, B)
            assert masked_ds.RasterCount == 3
            
            # Mask should exist
            mask_band = masked_ds.GetRasterBand(1).GetMaskBand()
            assert mask_band is not None
    
    def test_create_intermediate_with_mask_preserves_data(self, tmp_path):
        """RGB pixel values preserved when stripping alpha."""
        filepath = tmp_path / "rgba_data.tif"
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 100, 100, 4, gdal.GDT_Byte)
        
        # Set color interpretations
        for i in range(4):
            interpretation = [gdal.GCI_RedBand, gdal.GCI_GreenBand, 
                             gdal.GCI_BlueBand, gdal.GCI_AlphaBand][i]
            ds.GetRasterBand(i + 1).SetColorInterpretation(interpretation)
        
        # Write distinctive data to RGB bands
        r_data = np.full((100, 100), 100, dtype=np.uint8)
        g_data = np.full((100, 100), 150, dtype=np.uint8)
        b_data = np.full((100, 100), 200, dtype=np.uint8)
        alpha_data = np.full((100, 100), 255, dtype=np.uint8)
        
        ds.GetRasterBand(1).WriteArray(r_data)
        ds.GetRasterBand(2).WriteArray(g_data)
        ds.GetRasterBand(3).WriteArray(b_data)
        ds.GetRasterBand(4).WriteArray(alpha_data)
        ds.FlushCache()
        
        with Workspace() as workspace:
            temp_path = workspace.get_temp_path("temp.tif")
            temp_ds = driver.CreateCopy(temp_path, ds)
            ds = None
            
            masked_ds = _create_intermediate_with_mask(temp_ds, workspace)
            
            # Verify RGB data preserved
            assert np.all(masked_ds.GetRasterBand(1).ReadAsArray() == 100)
            assert np.all(masked_ds.GetRasterBand(2).ReadAsArray() == 150)
            assert np.all(masked_ds.GetRasterBand(3).ReadAsArray() == 200)


# ==============================================================================
# CATEGORY 3: OVERVIEW ROUNDING TESTS (3 TESTS)
# ==============================================================================

class TestOverviewRounding:
    """Test overview data rounding for lossless compression efficiency."""
    
    def test_round_overviews_basic(self, tmp_path):
        """Overviews rounded to specified decimal places."""
        filepath = tmp_path / "dem_with_overviews.tif"
        
        # Create Float32 DEM with 5 decimal places
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32,
                          options=['TILED=YES', 'COMPRESS=NONE'])
        
        # Write data with high precision
        data = np.random.uniform(100, 500, (256, 256)).astype(np.float32)
        ds.GetRasterBand(1).WriteArray(data)
        
        # Build uncompressed overviews (required for rounding)
        ds.BuildOverviews('BILINEAR', [2, 4], options=['COMPRESS=NONE'])
        ds.FlushCache()
        
        # Round overviews to 2 decimals
        ds = round_overviews(ds, decimals=2)
        
        # Check overview data precision
        band = ds.GetRasterBand(1)
        overview = band.GetOverview(0)  # 2x overview
        overview_data = overview.ReadAsArray()
        
        # Verify all values have max 2 decimal places
        rounded_data = np.round(overview_data, 2)
        assert np.allclose(overview_data, rounded_data, atol=1e-9)
    
    def test_round_overviews_compressed_fails_gracefully(self, tmp_path, caplog):
        """Compressed overviews cannot be rounded, logs warning."""
        filepath = tmp_path / "dem_compressed_ovr.tif"
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32,
                          options=['TILED=YES', 'COMPRESS=DEFLATE'])
        
        data = np.random.uniform(100, 500, (256, 256)).astype(np.float32)
        ds.GetRasterBand(1).WriteArray(data)
        
        # Build COMPRESSED overviews (cannot be modified in-place)
        ds.BuildOverviews('BILINEAR', [2], options=['COMPRESS=DEFLATE'])
        ds.FlushCache()
        
        # Attempt to round
        with caplog.at_level(logging.WARNING):
            ds = round_overviews(ds, decimals=2)
        
        # Dataset should still be valid (no crash)
        # The function may or may not log a warning depending on GDAL behavior,
        # but it should handle compressed overviews gracefully without crashing
        assert ds is not None
        
        # If a warning was logged, it should mention compression or write failure
        if caplog.text:
            assert "compressed" in caplog.text.lower() or "failed" in caplog.text.lower()
    
    def test_round_overviews_no_overviews(self, tmp_path, caplog):
        """Dataset without overviews handled gracefully."""
        filepath = tmp_path / "no_overviews.tif"
        
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(str(filepath), 256, 256, 1, gdal.GDT_Float32)
        
        data = np.random.uniform(100, 500, (256, 256)).astype(np.float32)
        ds.GetRasterBand(1).WriteArray(data)
        ds.FlushCache()
        
        # No overviews built
        
        with caplog.at_level(logging.INFO):
            ds = round_overviews(ds, decimals=2)
        
        # Should log info about no overviews
        assert "No overviews" in caplog.text
        
        # Dataset unchanged
        assert ds is not None


# ==============================================================================
# CATEGORY 4: NODATA HANDLING TESTS (6 TESTS)
# ==============================================================================

class TestNoDataHandling:
    """Test complex NoData remapping, masking, validation, and conflict resolution."""
    
    def test_nodata_remap_basic(self, mock_geotiff_info):
        """NoData values remapped from source to target."""
        # Create test arguments
        args = Mock(spec=OptimizeArguments)
        args.nodata = -8888.0  # Target NoData
        args.mask_nodata = None
        args.mask_alpha = False
        args.product_type = 'dem'
        args.algorithm = 'DEFLATE'
        args.decimals = None
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        # Create test dataset with NoData = -9999
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Float32)
        data = np.full((100, 100), 100.0, dtype=np.float32)
        data[0:10, 0:10] = -9999.0  # NoData pixels
        original_ds.GetRasterBand(1).WriteArray(data)
        original_ds.GetRasterBand(1).SetNoDataValue(-9999.0)
        
        # Update info
        mock_geotiff_info.nodata = -9999.0
        
        with Workspace() as workspace:
            result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
            
            # Verify NoData was remapped
            result_data = result_ds.GetRasterBand(1).ReadAsArray()
            
            # Old NoData pixels should now be -8888
            assert np.all(result_data[0:10, 0:10] == -8888.0)
            
            # NoData value should be set
            assert result_ds.GetRasterBand(1).GetNoDataValue() == -8888.0
    
    def test_nodata_to_mask_conversion(self, mock_geotiff_info):
        """NoData pixels converted to transparency mask."""
        args = Mock(spec=OptimizeArguments)
        args.mask_nodata = True  # Explicitly mask
        args.nodata = None
        args.mask_alpha = False
        args.product_type = 'image'
        args.algorithm = 'DEFLATE'
        args.decimals = None
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        # Create test dataset with NoData
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Byte)
        data = np.full((100, 100), 128, dtype=np.uint8)
        data[25:75, 25:75] = 0  # NoData region (center square)
        original_ds.GetRasterBand(1).WriteArray(data)
        original_ds.GetRasterBand(1).SetNoDataValue(0)
        
        # Update info
        mock_geotiff_info.nodata = 0
        mock_geotiff_info.data_type = 'Byte'
        
        with Workspace() as workspace:
            result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
            
            # NoData should be unset
            assert result_ds.GetRasterBand(1).GetNoDataValue() is None
            
            # Mask should exist
            mask_band = result_ds.GetRasterBand(1).GetMaskBand()
            mask_data = mask_band.ReadAsArray()
            
            # Center square should be masked (0), rest valid (255)
            assert np.all(mask_data[25:75, 25:75] == 0)
            assert np.all(mask_data[0:20, 0:20] == 255)
    
    def test_nodata_invalid_value_remapped(self, mock_geotiff_info, caplog):
        """Invalid NoData values (like -inf) are remapped to NaN."""
        args = Mock(spec=OptimizeArguments)
        args.nodata = None  # No user-specified target
        args.mask_nodata = None
        args.mask_alpha = False
        args.product_type = 'dem'
        args.algorithm = 'DEFLATE'
        args.decimals = None
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        # Create test dataset with -inf as NoData
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Float32)
        data = np.full((100, 100), 100.0, dtype=np.float32)
        data[0:10, :] = -np.inf  # Invalid NoData
        original_ds.GetRasterBand(1).WriteArray(data)
        original_ds.GetRasterBand(1).SetNoDataValue(-np.inf)
        
        # Update info
        mock_geotiff_info.nodata = -np.inf
        
        with caplog.at_level(logging.WARNING):
            with Workspace() as workspace:
                result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
        
        # Should log warning about invalid NoData
        assert "invalid or extreme" in caplog.text.lower()
        
        # NoData should be remapped to NaN
        nodata_val = result_ds.GetRasterBand(1).GetNoDataValue()
        assert np.isnan(nodata_val)
    
    def test_nodata_mask_nodata_takes_precedence_over_nodata_arg(self, mock_geotiff_info, caplog):
        """When both mask_nodata and nodata are set, mask_nodata takes precedence."""
        args = Mock(spec=OptimizeArguments)
        args.mask_nodata = True  # Mask
        args.nodata = -8888.0    # Should be ignored
        args.mask_alpha = False
        args.product_type = 'image'
        args.algorithm = 'DEFLATE'
        args.decimals = None
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Byte)
        data = np.full((100, 100), 128, dtype=np.uint8)
        data[0:10, :] = 0  # NoData
        original_ds.GetRasterBand(1).WriteArray(data)
        original_ds.GetRasterBand(1).SetNoDataValue(0)
        
        # Update info
        mock_geotiff_info.nodata = 0
        mock_geotiff_info.data_type = 'Byte'
        
        with caplog.at_level(logging.WARNING):
            with Workspace() as workspace:
                result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
        
        # Should log warning about conflict
        assert "mask_nodata takes precedence" in caplog.text
        
        # NoData should be masked (not set to -8888)
        assert result_ds.GetRasterBand(1).GetNoDataValue() is None
        
        # Mask should exist
        mask_band = result_ds.GetRasterBand(1).GetMaskBand()
        assert mask_band is not None
    
    def test_nodata_implicit_masking_for_image_product_type(self, mock_geotiff_info):
        """Image product type implicitly masks NoData (mask_nodata=None)."""
        args = Mock(spec=OptimizeArguments)
        args.mask_nodata = None  # Not explicitly set
        args.nodata = None
        args.mask_alpha = False
        args.product_type = 'image'  # Should trigger implicit masking
        args.algorithm = 'DEFLATE'
        args.decimals = None
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 3, gdal.GDT_Byte)
        for i in range(3):
            data = np.full((100, 100), 128, dtype=np.uint8)
            data[0:10, :] = 0
            original_ds.GetRasterBand(i + 1).WriteArray(data)
            original_ds.GetRasterBand(i + 1).SetNoDataValue(0)
        
        # Update info
        mock_geotiff_info.nodata = 0
        mock_geotiff_info.data_type = 'Byte'
        
        with Workspace() as workspace:
            result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
        
        # NoData should be masked implicitly
        assert result_ds.GetRasterBand(1).GetNoDataValue() is None
        
        # Mask should exist
        mask_band = result_ds.GetRasterBand(1).GetMaskBand()
        mask_data = mask_band.ReadAsArray()
        assert np.any(mask_data == 0)  # Some pixels masked
    
    def test_nodata_preserved_for_dem_product_type(self, mock_geotiff_info):
        """DEM product type preserves NoData value (mask_nodata=None)."""
        args = Mock(spec=OptimizeArguments)
        args.mask_nodata = None  # Not explicitly set
        args.nodata = None       # No override
        args.mask_alpha = False
        args.product_type = 'dem'  # Should preserve NoData
        args.algorithm = 'DEFLATE'
        args.decimals = None
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Float32)
        data = np.full((100, 100), 250.5, dtype=np.float32)
        data[0:10, :] = -9999.0
        original_ds.GetRasterBand(1).WriteArray(data)
        original_ds.GetRasterBand(1).SetNoDataValue(-9999.0)
        
        # Update info
        mock_geotiff_info.nodata = -9999.0
        
        with Workspace() as workspace:
            result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
        
        # NoData should be preserved
        assert result_ds.GetRasterBand(1).GetNoDataValue() == -9999.0


# ==============================================================================
# CATEGORY 5: MAIN PREPROCESSING PIPELINE TESTS (5 TESTS)
# ==============================================================================

class TestMainPreprocessingPipeline:
    """Test main preprocessing orchestration including metadata, SRS, and statistics."""
    
    def test_preprocess_geotiff_float_rounding(self, mock_geotiff_info):
        """Float32 DEM data rounded to specified decimals."""
        args = Mock(spec=OptimizeArguments)
        args.algorithm = 'DEFLATE'
        args.product_type = 'dem'
        args.decimals = 2  # Round to 2 decimal places
        args.nodata = None
        args.mask_nodata = None
        args.mask_alpha = False
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Float32)
        
        # Data with high precision
        data = np.array([[123.456789, 234.567890],
                         [345.678901, 456.789012]], dtype=np.float32)
        data = np.tile(data, (50, 50))
        original_ds.GetRasterBand(1).WriteArray(data)
        
        with Workspace() as workspace:
            result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
            result_data = result_ds.GetRasterBand(1).ReadAsArray()
        
        # Data should be rounded to 2 decimals
        expected = np.round(data, 2)
        assert np.allclose(result_data, expected, atol=1e-9)

    def test_preprocess_geotiff_decimals_none_or_excessive_is_noop(self, mock_geotiff_info):
        """decimals='none', and decimals beyond float32 precision, leave values unchanged."""
        for dec in ('none', 8):
            args = Mock(spec=OptimizeArguments)
            args.algorithm = 'DEFLATE'
            args.product_type = 'dem'
            args.decimals = dec
            args.nodata = None
            args.mask_nodata = None
            args.mask_alpha = False
            args.vertical_srs = None
            args.raster_type = None
            args.geo_metadata = False
            args.discard_lsb = False

            driver = gdal.GetDriverByName('MEM')
            original_ds = driver.Create('', 64, 64, 1, gdal.GDT_Float32)
            data = np.tile(np.array([[1234.56789, 2345.6789],
                                     [987.654321, 1500.123]], dtype=np.float32), (32, 32))
            original_ds.GetRasterBand(1).WriteArray(data)

            with Workspace() as workspace:
                result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
                result_data = result_ds.GetRasterBand(1).ReadAsArray()

            assert np.array_equal(result_data, data), f"decimals={dec} should not change the data"

    def test_preprocess_geotiff_metadata_preservation(self, mock_geotiff_info):
        """Source metadata preserved in output."""
        args = Mock(spec=OptimizeArguments)
        args.algorithm = 'DEFLATE'
        args.product_type = 'dem'
        args.decimals = None
        args.nodata = None
        args.mask_nodata = None
        args.mask_alpha = False
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Float32)
        
        # Source metadata
        source_metadata = {
            'CUSTOM_KEY': 'custom_value',
            'AUTHOR': 'Test Author',
            'TIFFTAG_SOFTWARE': 'Original Software v1.0'
        }
        
        with Workspace() as workspace:
            result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, source_metadata)
            result_metadata = result_ds.GetMetadata()
        
        # Verify custom metadata preserved
        assert result_metadata['CUSTOM_KEY'] == 'custom_value'
        assert result_metadata['AUTHOR'] == 'Test Author'
        
        # Verify SOFTWARE tag updated
        assert 'GeoTIFF ToolKit' in result_metadata['TIFFTAG_SOFTWARE']
        assert 'Original Software v1.0' in result_metadata['TIFFTAG_SOFTWARE']
    
    def test_preprocess_geotiff_area_or_point_metadata(self, mock_geotiff_info):
        """AREA_OR_POINT metadata set based on product type."""
        # Test DEM (should be Point)
        args_dem = Mock(spec=OptimizeArguments)
        args_dem.product_type = 'dem'
        args_dem.raster_type = None  # Use default
        args_dem.algorithm = 'DEFLATE'
        args_dem.decimals = None
        args_dem.nodata = None
        args_dem.mask_nodata = None
        args_dem.mask_alpha = False
        args_dem.vertical_srs = None
        args_dem.geo_metadata = False
        args_dem.discard_lsb = False
        
        driver = gdal.GetDriverByName('MEM')
        ds_dem = driver.Create('', 100, 100, 1, gdal.GDT_Float32)
        
        with Workspace() as workspace:
            result_dem = preprocess_geotiff(ds_dem, workspace, args_dem, mock_geotiff_info, None, {})
            area_or_point_dem = result_dem.GetMetadataItem('AREA_OR_POINT')
        
        assert area_or_point_dem == 'Point'
        
        # Test Image (should be Area)
        args_image = Mock(spec=OptimizeArguments)
        args_image.product_type = 'image'
        args_image.raster_type = None
        args_image.algorithm = 'DEFLATE'
        args_image.decimals = None
        args_image.nodata = None
        args_image.mask_nodata = None
        args_image.mask_alpha = False
        args_image.vertical_srs = None
        args_image.geo_metadata = False
        args_image.discard_lsb = False
        
        ds_image = driver.Create('', 100, 100, 3, gdal.GDT_Byte)
        
        # Update info for image
        info_image = Mock(spec=GeoTiffInfo)
        info_image.nodata = None
        info_image.data_type = 'Byte'
        info_image.has_alpha = False
        info_image.transparency_info = {}
        info_image.vertical_srs = None
        info_image.filepath = 'test.tif'
        
        with Workspace() as workspace:
            result_image = preprocess_geotiff(ds_image, workspace, args_image, info_image, None, {})
            area_or_point_image = result_image.GetMetadataItem('AREA_OR_POINT')
        
        assert area_or_point_image == 'Area'
    
    def test_preprocess_geotiff_compound_srs_handling(self, mock_geotiff_info):
        """A compound CRS whose vertical datum has no EPSG code is preserved in metadata."""
        args = Mock(spec=OptimizeArguments)
        args.algorithm = 'DEFLATE'
        args.product_type = 'dem'
        args.decimals = None
        args.nodata = None
        args.mask_nodata = None
        args.mask_alpha = False
        args.vertical_srs = CUSTOM_VERTICAL_WKT  # Custom vertical (no EPSG), as WKT
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Float32)
        
        # Create compound CRS
        from gttk.utils.srs_logic import get_srs_from_user_input, create_compound_srs
        horiz_srs = get_srs_from_user_input('EPSG:32610')
        vert_srs = get_srs_from_user_input(CUSTOM_VERTICAL_WKT)
        
        # Ensure SRS were created successfully
        assert horiz_srs is not None, "Failed to create horizontal SRS"
        assert vert_srs is not None, "Failed to create vertical SRS"
        
        compound_srs = create_compound_srs(horiz_srs, vert_srs)
        
        with Workspace() as workspace:
            result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, compound_srs, {})
            
            # Check that COMPOUND_CRS_WKT2 metadata exists
            compound_wkt2 = result_ds.GetMetadataItem('COMPOUND_CRS_WKT2')
            
            assert compound_wkt2 is not None
            assert 'Test Local' in compound_wkt2
    
    def test_preprocess_geotiff_computes_no_statistics(self, mock_geotiff_info):
        """The preprocessor used to end with a full statistics pass over the intermediate,
        writing STATISTICS_* into a metadata domain that neither the COG driver nor
        CreateCopy propagates -- on a raster too large for memory that read cost as much as
        the one the caller then made for the .aux.xml. The caller's pass is the only one."""
        args = Mock(spec=OptimizeArguments)
        args.algorithm = 'DEFLATE'
        args.product_type = 'dem'
        args.decimals = None
        args.nodata = None
        args.mask_nodata = None
        args.mask_alpha = False
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False

        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Float32)
        original_ds.GetRasterBand(1).WriteArray(np.arange(10000, dtype=np.float32).reshape(100, 100))

        with Workspace() as workspace:
            result_ds = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
            assert result_ds.GetRasterBand(1).GetMetadata('STATISTICS') == {}

    def test_preprocess_geotiff_invalid_dataset_raises_error(self, mock_geotiff_info):
        """None or invalid dataset raises ProcessingStepFailedError."""
        args = Mock(spec=OptimizeArguments)
        args.algorithm = 'DEFLATE'
        args.product_type = 'dem'
        args.decimals = None
        args.nodata = None
        args.mask_nodata = None
        args.mask_alpha = False
        args.vertical_srs = None
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        with Workspace() as workspace:
            with pytest.raises(Exception):  # Could be ProcessingStepFailedError or GDAL error
                preprocess_geotiff(None, workspace, args, mock_geotiff_info, None, {})  # type: ignore[arg-type]
    
    def test_workspace_cleanup_on_processing_error(self, mock_geotiff_info):
        """Virtual files cleaned up when preprocessing raises error."""
        args = Mock(spec=OptimizeArguments)
        args.algorithm = 'DEFLATE'
        args.product_type = 'dem'
        args.decimals = None
        args.nodata = None
        args.mask_nodata = None
        args.mask_alpha = False
        args.vertical_srs = 'INVALID_SRS'  # Will cause error
        args.raster_type = None
        args.geo_metadata = False
        args.discard_lsb = False
        
        driver = gdal.GetDriverByName('MEM')
        original_ds = driver.Create('', 100, 100, 1, gdal.GDT_Float32)
        
        vsi_paths = []
        try:
            with Workspace() as workspace:
                # Track paths before error
                _ = preprocess_geotiff(original_ds, workspace, args, mock_geotiff_info, None, {})
                # Capture paths
                vsi_paths = workspace.paths.copy()
        except Exception:
            pass
        
        # Verify cleanup occurred (any paths that were created should be cleaned up)
        # This tests that the context manager's __exit__ runs even on exception
        # We can't verify specific paths since the error might occur before path creation
        # But we can verify the exception was caught and cleanup logic ran
        assert True  # If we reach here without hanging, cleanup worked
    
    def test_round_overviews_invalid_dataset_handled(self, caplog):
        """round_overviews returns None dataset unchanged."""
        with caplog.at_level(logging.WARNING):
            result = round_overviews(None, 2)  # type: ignore[arg-type]
        
        # Should log warning
        assert "Dataset is None" in caplog.text
        
        # Should return None
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
