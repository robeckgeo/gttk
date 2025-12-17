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
In-Memory GeoTIFF Preprocessing Pipeline.

This module contains the core logic for the optimization preprocessing pipeline.
It orchestrates a series of in-memory operations using GDAL's virtual file system
(`/vsimem/`), including NoData value handling, alpha-to-mask conversion, data
rounding, and metadata updates, before the final compression stage.

Classes:
    VirtualFileManager: A context manager for handling temporary in-memory files.
"""
import logging
import numpy as np
import uuid
from importlib import metadata
from osgeo import gdal, osr
from pathlib import Path
from typing import Optional, List
from gttk.utils.exceptions import ProcessingStepFailedError
from gttk.utils.optimize_constants import CompressionAlgorithm as CA, ProductType as PT
from gttk.utils.geotiff_processor import remap_nodata_value, mask_nodata_value, normalize_existing_mask, is_nodata_valid, GeoTiffInfo
from gttk.utils.geo_metadata_writer import write_geo_metadata
from gttk.utils.path_helpers import find_xml_metadata_file
from gttk.utils.script_arguments import OptimizeArguments
from gttk.utils.statistics_calculator import calculate_statistics

logger = logging.getLogger(__name__)

try:
    __version__ = metadata.version("geotiff-toolkit")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"

# --- Virtual File Manager ---
class VirtualFileManager:
    """
    Manages an in-memory workspace using GDAL's /vsimem/ virtual file system.

    This class creates a unique virtual directory for each instance, providing a
    sandboxed environment for temporary files. When used as a context manager, it
    automatically cleans up all registered virtual files upon exiting the context,
    preventing memory leaks.
    """
    def __init__(self):
        self.vsi_prefix = f"/vsimem/compress_{uuid.uuid4().hex}/"
        self.virtual_files: List[str] = []

    def get_temp_path(self, filename: str) -> str:
        """Generates and registers a new path within the virtual directory."""
        vsi_path = self.vsi_prefix + filename
        if not vsi_path.startswith("/vsimem/"):
            raise ValueError(f"Generated path {vsi_path} is not a /vsimem/ path.")
        self.virtual_files.append(vsi_path)
        logger.debug(f"VirtualFileManager: Registered virtual path: {vsi_path}")
        return vsi_path

    def cleanup(self):
        """Unlinks all registered virtual files from memory."""
        logger.info(f"VirtualFileManager: Cleaning up {len(self.virtual_files)} virtual files...")
        cleaned_count = 0
        failed_to_unlink_paths: List[str] = []
        for vsi_file in reversed(self.virtual_files):
            try:
                if gdal.VSIStatL(vsi_file):
                    gdal.Unlink(vsi_file)
                    cleaned_count += 1
            except Exception as e:
                logger.error(f"    Error unlinking virtual file {vsi_file}: {e}")
                failed_to_unlink_paths.append(vsi_file)
        
        self.virtual_files = failed_to_unlink_paths
        
        if failed_to_unlink_paths:
            logger.warning(f"VirtualFileManager: Cleanup finished. {len(failed_to_unlink_paths)} files failed to unlink.")
        else:
            logger.info(f"VirtualFileManager: Cleanup finished. All {cleaned_count} registered virtual files unlinked.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

def _create_intermediate_with_mask(temp_ds: gdal.Dataset, vfm: VirtualFileManager) -> gdal.Dataset:
    """Handles the alpha to mask conversion and creates an intermediate dataset."""
    # Apply threshold to the alpha band of the in-memory/temp dataset
    threshold = 230
    logger.info(f"Applying threshold of {threshold}/255 (90% opaque) to alpha band to reduce edge effects.")
    alpha_band = temp_ds.GetRasterBand(4)
    alpha_data = alpha_band.ReadAsArray()
    
    alpha_data[alpha_data < threshold] = 0
    alpha_data[alpha_data >= threshold] = 255
    
    # Keep the processed alpha data for manual mask creation
    mask_data = alpha_data.copy()

    logger.info("Creating intermediate file with RGB bands only.")
    # First, create output with just RGB bands (no mask yet)
    translate_options = gdal.TranslateOptions(
        format='GTiff',
        bandList=[1, 2, 3],
        creationOptions=['TILED=YES', 'COMPRESS=LZW']
    )
    masked_path = vfm.get_temp_path("masked.tif")
    masked_ds = gdal.Translate(masked_path, temp_ds, options=translate_options)
    if masked_ds is None:
        raise ProcessingStepFailedError("Failed to create intermediate file.")
    
    # Now manually create the per-dataset mask and write the alpha data to it
    logger.info("Creating per-dataset internal mask from processed alpha band.")
    masked_ds.CreateMaskBand(gdal.GMF_PER_DATASET)
    mask_band = masked_ds.GetRasterBand(1).GetMaskBand()
    mask_band.WriteArray(mask_data)
    mask_band.FlushCache()
    masked_ds.FlushCache()
    
    return masked_ds

def preprocess_geotiff(
    original_ds: gdal.Dataset,
    vfm: VirtualFileManager,
    args: OptimizeArguments,
    info: GeoTiffInfo,
    srs: Optional[osr.SpatialReference],
    metadata: dict
) -> gdal.Dataset:
    """
    Performs all in-place preprocessing operations on a GDAL dataset.

    This function is designed to be called by both the CLI and ArcGIS scripts
    to ensure that the core logic is consistent.

    Args:
        ds: The GDAL dataset to preprocess (can be in-memory or on-disk).
        args: The validated script arguments.
        info: The GeoTiffInfo object for the input dataset.
        srs: The target spatial reference system.
        metadata: The source metadata.

    Returns:
        The preprocessed GDAL dataset.
    """
    # --- 1. Create Intermediate File ---
    temp_path = vfm.get_temp_path("intermediate.tif")
    logger.info(f"Creating intermediate file at virtual path: {temp_path}")
    ds = gdal.GetDriverByName('GTiff').CreateCopy(temp_path, original_ds, options=['TILED=YES', 'COMPRESS=LZW'])
    if ds is None:
        raise ProcessingStepFailedError("Failed to create intermediate tiled copy.")

    if info.has_alpha and args.mask_alpha:
        ds = _create_intermediate_with_mask(ds, vfm)

    # --- 2. Process NoData Values ---
    
    # Ensure any existing mask is normalized (0/1 -> 0/255) and clean of NoData values
    if info.transparency_info.get('Mask') or info.has_alpha:
        normalize_existing_mask(ds)
    
    # Step 2a: Resolve argument conflicts
    # Conflict 1: args.nodata vs args.mask_nodata
    if args.mask_nodata and args.nodata is not None:
        logger.warning(
            "Both --mask_nodata and --nodata were specified. "
            "--mask_nodata takes precedence. "
            "--nodata argument will be ignored."
        )
        args.nodata = None  # Force to None when masking
    
    # Conflict 2: args.nodata vs args.mask_alpha
    if info.has_alpha and args.mask_alpha and args.nodata is not None:
        logger.warning(
            "Both --mask-alpha (band) and --nodata (value) were specified. "
            "When converting alpha band to mask, NoData pixels will be added to mask. "
            "--nodata argument will be ignored."
        )
        args.nodata = None  # Force to None when stripping alpha band
    
    # Step 2b: Check if source NoData is valid
    # If invalid, it might be a special case (like -inf) that needs remapping or it might be junk
    if info.nodata is not None and info.data_type is not None and not is_nodata_valid(info.nodata, info.data_type):
        logger.warning(
            f"Source NoData value {info.nodata} is invalid or extreme for {info.data_type}. "
            f"Checking if pixels with this value exist..."
        )
        
        source_nodata_val = float(info.nodata)
        for i in range(1, ds.RasterCount + 1):
            band = ds.GetRasterBand(i)
            # Read small chunk or statistics to verify? Ideally just read array if small enough or use ComputeStatistics?
            # For now, we rely on remap_nodata_value to handle the actual pixel scan efficiently.
            pass

        # Determine target NoData for this specific case
        # If user provided a NoData value, we remap the invalid source NoData to that.
        # If NOT, we must remap to a safe value (NaN for float) if pixels exist, because -inf is bad.
        
        target_safe_nodata = None
        if args.nodata is not None:
             target_safe_nodata = float(args.nodata)
        elif 'Float' in info.data_type:
             target_safe_nodata = float('nan')
        
        if target_safe_nodata is not None:
             logger.info(f"Attempting to remap potential extreme NoData values ({info.nodata}) to {target_safe_nodata}")
             ds = remap_nodata_value(ds, source_nodata_val, target_safe_nodata)
             
             # After remapping, update the dataset's NoData value to the new safe one
             for i in range(1, ds.RasterCount + 1):
                 ds.GetRasterBand(i).SetNoDataValue(target_safe_nodata)
             info.nodata = target_safe_nodata
        else:
            # Fallback for non-float or if we can't determine a safe target (unlikely for float issues)
            # Just unset the tag as before
            logger.info("Unsetting invalid NoData value tag (no remapping performed).")
            for i in range(1, ds.RasterCount + 1):
                ds.GetRasterBand(i).DeleteNoDataValue()
            info.nodata = None
    
    # Step 2c: Determine if we should keep NoData or convert to mask
    should_mask = False
    if args.mask_nodata is True:
        # User explicitly requested masking
        should_mask = True
    elif args.mask_nodata is None:
        # Not explicitly set, determine based on context
        if args.mask_alpha and info.has_alpha:
            # If we are converting alpha band to an internal mask, we should also mask NoData
            # so all transparency is handled in the same way
            should_mask = True
        elif args.product_type == PT.IMAGE.value:
            # For standard RGB/Image products, we prefer masking over NoData values
            # unless the user explicitly set mask_nodata=False
            should_mask = True
        # else: Default to False for DEM, SCIENTIFIC, ERROR, THEMATIC types to preserve NoData values
    # else: args.mask_nodata is False, so we keep NoData
    
    # Step 2d: Determine target NoData value
    target_nodata = None
    if should_mask:
        # When masking, use source NoData as the value to mask
        # After masking, NoData will be unset
        if info.nodata is not None:
            target_nodata = info.nodata
        # else: No source NoData, nothing to mask
    elif args.nodata is not None:
        # User specified a NoData value and NOT masking
        target_nodata = args.nodata
    elif info.nodata is not None:
        # Keep existing valid NoData
        target_nodata = info.nodata
    # else: No target NoData
    
    # Step 2e: Remap NoData if needed (before masking)
    # Only remap if source and target differ
    if (info.nodata is not None and target_nodata is not None and
        info.nodata != target_nodata and not should_mask):
        logger.info(f"Remapping NoData from {info.nodata} to {target_nodata}")
        ds = remap_nodata_value(ds, float(info.nodata), float(target_nodata))
    
    # Step 2f: Convert NoData to mask if requested
    if should_mask and target_nodata is not None:
        logger.info("Converting NoData to transparency mask.")
        ds = mask_nodata_value(ds, float(target_nodata))
        target_nodata = None  # NoData is now in mask, unset the value

    # --- 3. Round floating point data ---
    if args.algorithm in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value] and \
       args.product_type in [PT.DEM.value, PT.ERROR.value, PT.SCIENTIFIC.value] and args.decimals is not None:
        if 'Float' in str(info.data_type):
            for i in range(1, ds.RasterCount + 1):
                band = ds.GetRasterBand(i)
                array = band.ReadAsArray()
                array = np.round(array, int(args.decimals))
                band.WriteArray(array)
                band.FlushCache()

    # --- 4. Set Final NoData Value ---
    if target_nodata is not None:
        logger.info(f"Setting NoData value to {target_nodata}")
        for i in range(1, ds.RasterCount + 1):
            # Handle NaN specially for float datasets
            if isinstance(target_nodata, float) and np.isnan(target_nodata):
                ds.GetRasterBand(i).SetNoDataValue(float('nan'))
            else:
                ds.GetRasterBand(i).SetNoDataValue(float(target_nodata))
    else:
        # Explicitly unset NoData (either masked or just no NoData)
        for i in range(1, ds.RasterCount + 1):
            ds.GetRasterBand(i).DeleteNoDataValue()

    # --- 5. Transfer source metadata ---
    if metadata:
        # if the input has a vertical SRS but the output will not, remove UNITTYPE from the metadata
        if info.vertical_srs and not args.vertical_srs:
            for key in list(metadata.keys()):
                if key == 'UNITTYPE':
                    metadata.pop(key)
        
        # Remove AREA_OR_POINT from source metadata to prevent overwriting the calculated value in the next step
        if 'AREA_OR_POINT' in metadata:
            metadata.pop('AREA_OR_POINT')

        software_tag = metadata.get('TIFFTAG_SOFTWARE', '')
        metadata['TIFFTAG_SOFTWARE'] = f"{software_tag.strip()} - optimized by GeoTIFF ToolKit v{__version__}" if software_tag else f"GeoTIFF ToolKit v{__version__}"
        ds.SetMetadata(metadata)

    # --- 6. Set Area/Point Metadata ---
    # This is done AFTER transferring source metadata to ensure our explicit choice takes precedence
    default_raster_type = 'Point' if args.product_type in [PT.DEM.value, PT.ERROR.value, PT.SCIENTIFIC.value] else 'Area'
    final_raster_type = args.raster_type if args.raster_type else default_raster_type
    ds.SetMetadataItem('AREA_OR_POINT', final_raster_type)
    if srs:
        # Set the projection using WKT2
        wkt2_full = srs.ExportToWkt(['FORMAT=WKT2_2019'])
        ds.SetProjection(wkt2_full)
        
        # For custom vertical CRSs (without EPSG codes), also store the full WKT in metadata
        # This preserves datum names and axis information that GeoTIFF's GeoKey encoding loses
        if srs.IsCompound():
            # Check if the vertical component has an EPSG authority code
            vert_auth_name = srs.GetAuthorityName('COMPD_CS|VERT_CS')
            vert_auth_code = srs.GetAuthorityCode('COMPD_CS|VERT_CS')
            
            # Only skip metadata storage if we have a valid EPSG code
            is_epsg_vertical = (vert_auth_name == 'EPSG' and vert_auth_code is not None)
            
            if not is_epsg_vertical:
                # No EPSG code for vertical CRS - store full WKT to preserve custom datum info
                logger.info("Custom vertical CRS detected (non-EPSG). Storing full WKT2 in metadata to preserve datum information.")
                ds.SetMetadataItem('COMPOUND_CRS_WKT2', wkt2_full)

    # --- 7. Write GEO_METADATA tag if requested ---
    if args.geo_metadata:
        xml_path = find_xml_metadata_file(Path(info.filepath))
        if xml_path:
            ds.FlushCache()
            write_geo_metadata(ds, xml_path)
            ds = gdal.Open(ds.GetDescription(), gdal.GA_Update)
            logger.info(f"XML metadata file {str(xml_path)} was embedded in the GEO_METADATA tag.")
        else:
            logger.info("XML metadata file not found. Skipping metadata embedding.")

    # --- 8. Embed Statistics ---
    stats = calculate_statistics(ds)
    if stats:
        for i, band_stats in enumerate(stats, 1):
            band = ds.GetRasterBand(i)
            if band:
                stats_dict = {
                    'STATISTICS_MINIMUM': str(band_stats.minimum),
                    'STATISTICS_MAXIMUM': str(band_stats.maximum),
                    'STATISTICS_MEAN': str(band_stats.mean),
                    'STATISTICS_STDDEV': str(band_stats.std_dev),
                }
                band.SetMetadata(stats_dict, 'STATISTICS')

    ds.FlushCache()
    return ds