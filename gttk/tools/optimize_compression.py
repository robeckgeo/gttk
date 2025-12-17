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
Optimize Compression (CLI).

This script provides a command-line utility to optimize and compress GeoTIFF files
into Cloud-Optimized GeoTIFFs (COGs).

It combines a robust, multi-step processing pipeline with user-friendly reporting
to create a comprehensive tool for preparing geospatial raster data for efficient
cloud-native storage and access. The script handles various processing steps,
including resampling, handling complex vertical and horizontal reference systems,
converting alpha bands to internal masks, performing memory-efficient rounding of
float data, and applying various compression algorithms with intelligent defaults.

All intermediate steps are handled in-memory using GDAL's virtual file system
to maximize performance and avoid creating temporary files on disk.
"""

import logging
import os
import sys
import traceback
from importlib import metadata
from osgeo import gdal
from pathlib import Path
from typing import Any, Optional
from gttk.tools.compare_compression import generate_report_for_datasets
from gttk.utils.exceptions import ProcessingStepFailedError
from gttk.utils.geotiff_processor import read_geotiff
from gttk.utils.log_helpers import init_arcpy
from gttk.utils.optimize_constants import CompressionAlgorithm as CA, ProductType as PT
from gttk.utils.path_helpers import get_geotiff_files, prepare_output_path, copy_folder_structure
from gttk.utils.performance_tracker import PerformanceTracker
from gttk.utils.preprocessor import preprocess_geotiff, VirtualFileManager
from gttk.utils.script_arguments import OptimizeArguments
from gttk.utils.srs_logic import handle_srs_logic, check_vertical_srs_mismatch
from gttk.utils.statistics_calculator import calculate_statistics, build_pam_data_from_stats, write_pam_xml

try:
    __version__ = metadata.version("geotiff-toolkit")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"

# Global logger variables
log_file_path = None  # Path to the log file so it can be deleted by ArcPy
arcMode = False
arcpy = None
base_path = os.path.dirname(os.path.abspath(__file__))

# --- Configuration & Setup ---
gdal.SetConfigOption('GDAL_NUM_THREADS', 'ALL_CPUS')
gdal.SetConfigOption('ESRI_XML_PAM', 'TRUE')
# Force WKT2_2019 formatting and encourage GTiff driver to preserve SRS as WKT2 where possible
gdal.SetConfigOption('OSR_WKT_FORMAT', 'WKT2_2019')
gdal.SetConfigOption('GTIFF_WRITE_SRS_WKT2', 'YES')

logger = logging.getLogger('optimize_compression')

# --- Custom Handlers and Logging Setup ---
report_logger = logging.getLogger('report_logger')

# --- Helper Functions ---
def format_gdal_progress(complete: float, message: str, data: Any) -> int:
    """
    A GDAL progress callback that displays a single-line percentage bar.

    This function is designed to be passed to GDAL functions that support a
    progress callback. It avoids printing a new line for each update, instead
    overwriting the current line to show a clean, updating progress bar.

    Args:
        complete: The fraction of work completed (0.0 to 1.0).
        message: A message string passed from the GDAL function.
        data: A user-supplied dictionary to maintain state, specifically to
              track the 'last_reported_percent' to avoid redundant prints.

    Returns:
        An integer (1) to continue the GDAL operation.
    """
    if arcMode:
        # In ArcGIS mode, suppress the stdout progress bar to avoid clutter.
        # ArcPy has its own progress dialog.
        return 1
    percent = int(complete * 100)
    if data and 'last_reported_percent' in data and data['last_reported_percent'] == percent and percent < 100:
        return 1
    sys.stdout.write(f'\rProgress: {percent}% {message if message else "":<80}')
    sys.stdout.flush()
    if data:
        data['last_reported_percent'] = percent
    if complete >= 1.0:
        sys.stdout.write('\n')
    return 1

progress_callback_data = {'last_reported_percent': -1}

def _process_single_file(args: OptimizeArguments, tracker: Optional[PerformanceTracker] = None):
    """Processes a single GeoTIFF file."""
    if tracker:
        tracker.start("total_processing")
    
    with VirtualFileManager() as vfm:
        try:
            ds = gdal.Open(str(args.input_path))
            if ds:
                check_vertical_srs_mismatch(ds, args.vertical_srs, str(args.input_path))
                ds = None
            _orchestrate_geotiff_optimization(args, vfm, tracker)
            
            if tracker:
                tracker.start("report_generation")
            logger.info("GDAL processing complete. Generating report...")
            
            # Use shared report generation function passing PATHS instead of open datasets
            # to avoid file locking issues affecting tifffile/metadata extraction
            generate_report_for_datasets(
                str(args.input_path),
                str(args.output_path),
                args,
                'Input File',
                'Output File',
                args.report_suffix or '_comp'
            )
            logger.info("Report generation complete.")
            
            if tracker:
                tracker.stop("report_generation")

        except ProcessingStepFailedError as e:
            logger.error(f"ERROR: {e}")
            raise e
    
    if tracker:
        tracker.stop("total_processing")
    return 0

def _get_jxl_options(quality: int, effort: int = 7):
    """
    Maps an integer quality (1-100) to GDAL JXL creation options.
   
    Args:
        quality_int (int): 1-100 (75-100 recommended for JXL).
        effort (int): 1-9 (Speed vs Density). 7 is a strong default for JXL.
       
    Returns:
        list: A list of strings for GDAL creation options.
    """
    options = [f"JXL_EFFORT={effort}"]
   
    if quality == 100:  # Lossless
        options.append("JXL_LOSSLESS=YES")
        # JXL_DISTANCE is ignored when Lossless is YES
    else:  # Lossy
        options.append("JXL_LOSSLESS=NO")
       
        # Calculate Distance using "The Rule of Ten" formula
        # Q90 -> Dist 1.0 (Visually Lossless)
        # Q75 -> Dist 2.5 (Standard Web Quality)
        distance = (100.0 - quality) * 0.1
       
        # Clamp to safe JXL bounds (minimum quality value is 75 -> max distance 2.5)
        distance = max(0.01, distance)
        options.append(f"JXL_DISTANCE={distance:.2f}")
       
        # Explicitly let Alpha follow the main distance
        options.append("JXL_ALPHA_DISTANCE=-1")

    return options


def _orchestrate_geotiff_optimization(args: OptimizeArguments, vfm: VirtualFileManager, tracker: Optional[PerformanceTracker] = None):
    """Orchestrates the end-to-end GeoTIFF optimization and compression workflow."""
    if tracker:
        tracker.start("gdal_processing")
    
    # Print the optimization arguments
    logger.info(f"GeoTIFF ToolKit (GTTK) v{__version__} - Starting optimization with arguments: {args}")
    
    original_input_ds = gdal.Open(str(args.input_path), gdal.GA_ReadOnly)
    if original_input_ds is None:
        raise ProcessingStepFailedError(f"Could not open input file '{args.input_path}'.")

    input_info = read_geotiff(original_input_ds)
    target_srs = handle_srs_logic(args, input_info)
    source_metadata = original_input_ds.GetMetadata()

    with vfm as temp_vfm:
        temp_path = temp_vfm.get_temp_path("intermediate.tif")

        # --- 0. Set base creation options, whether COG or plain GeoTIFF ---
        final_creation_options = [
            'GEOTIFF_VERSION=1.1',
            'BIGTIFF=IF_SAFER',
            'NUM_THREADS=ALL_CPUS',
            f'COMPRESS={args.algorithm}'
        ]
            
        if args.cog:
            final_creation_options += [f'BLOCKSIZE={args.tile_size}']

            if args.overviews:  # Regenerate overviews from optimized base layer
                final_creation_options.append('OVERVIEWS=IGNORE_EXISTING')
                if args.product_type in [PT.IMAGE.value, PT.THEMATIC.value]:
                    final_creation_options.append('OVERVIEW_RESAMPLING=NEAREST')
                else:
                    final_creation_options.append('OVERVIEW_RESAMPLING=BILINEAR')
            else:
                final_creation_options.append('OVERVIEWS=NONE')
        else:
            final_creation_options += [
                'TILED=YES',
                f'BLOCKXSIZE={args.tile_size}',
                f'BLOCKYSIZE={args.tile_size}'
            ]
            if args.overviews:
                final_creation_options.append('COPY_SRC_OVERVIEWS=YES')
            else:
                final_creation_options.append('COPY_SRC_OVERVIEWS=NO')

        # Algorithm-specific creation options
        if args.algorithm in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value] and args.predictor:
            final_creation_options.append(f'PREDICTOR={args.predictor}')
        elif args.algorithm == CA.JPEG.value:
            if args.cog:
                final_creation_options.append(f"QUALITY={args.quality}")
            else:
                final_creation_options.append(f"JPEG_QUALITY={args.quality}")
                final_creation_options.append('PHOTOMETRIC=YCBCR')
        elif args.algorithm == CA.JXL.value and args.quality is not None:
            jxl_options = _get_jxl_options(args.quality)
            final_creation_options.extend(jxl_options)
        elif args.algorithm == CA.LERC.value:
            final_creation_options.append(f'MAX_Z_ERROR={args.max_z_error}')
        if args.level and args.algorithm in [CA.DEFLATE.value, CA.ZSTD.value]:
            final_creation_options.append(f'LEVEL={args.level}')
        logger.info(f"Final creation options set: {final_creation_options}")

        # --- 1. Perform all in-memory preprocessing steps ---
        if tracker:
            tracker.start("intermediate_processing")

        temp_ds = preprocess_geotiff(
            original_ds=original_input_ds,
            vfm=temp_vfm,
            args=args,
            info=input_info,
            srs=target_srs,
            metadata=source_metadata
        )
        
        if tracker:
            tracker.stop("intermediate_processing")

        # --- 3. Prepare overviews on intermediate file for standard GeoTIFF ---
        if args.overviews and not args.cog:
            if tracker:
                tracker.start("overview_creation")
            resample_alg = 'NEAREST' if args.product_type in [PT.IMAGE.value, PT.THEMATIC.value] else 'BILINEAR'
            overview_list = [2, 4, 8, 16, 32]
            overview_options = [
                'TILED=YES',
                f"COMPRESS={args.algorithm}",
                f'BLOCKXSIZE={args.tile_size}',
                f'BLOCKYSIZE={args.tile_size}'
            ]
            if args.algorithm in [CA.JPEG.value, CA.JXL.value]:
                overview_options.append(f"{'JPEG_' if not args.cog else ''}QUALITY={args.quality}")
            if args.algorithm == CA.JPEG.value:
                overview_options.append('PHOTOMETRIC=YCBCR')
            if args.algorithm in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value]:
                overview_options.append(f'PREDICTOR={args.predictor}')
            if args.algorithm == CA.LERC.value:
                overview_options.append(f'MAX_Z_ERROR={args.max_z_error}')
            
            logger.info("Creating overviews for the intermediate GeoTIFF.")
            temp_ds.BuildOverviews(resampling=resample_alg, overviewlist=overview_list, options=overview_options)
            if tracker:
                tracker.stop("overview_creation")

        # --- 4. Create final COG or GeoTIFF ---
        if tracker:
            tracker.start("final_translate")
            
        final_options_dict = {
            'format': 'COG' if args.cog else 'GTiff',
            'creationOptions': final_creation_options,
            'stats': True,
            'callback': format_gdal_progress if not arcMode else None,
            'callback_data': progress_callback_data if not arcMode else None
        }

        # Note: Alpha band stripping is handled entirely by the preprocessor via _create_intermediate_with_mask()
        # which converts alpha to an internal mask. The final translate will preserve this structure automatically.

        # Handle NoData value for final output
        # Note: preprocessor may have unset NoData if it was invalid
        if input_info.nodata is not None:
            if args.mask_nodata:
                # Unset NoData value when using internal mask
                # BUT: Don't set noData='none' for GTiff driver as it breaks COPY_SRC_OVERVIEWS
                # For GTiff driver, just don't set any noData - the mask handles transparency
                if args.cog:
                    final_options_dict['noData'] = 'none'
            elif args.nodata is not None:  # User specified a NoData value
                final_options_dict['noData'] = args.nodata
            else:  # Keep existing valid NoData from source (may have been modified by preprocessor)
                final_options_dict['noData'] = input_info.nodata
        elif args.nodata is not None:  # New NoData assignment
            final_options_dict['noData'] = args.nodata

        stats = calculate_statistics(temp_ds)
        if args.product_type in [PT.DEM.value, PT.ERROR.value, PT.SCIENTIFIC.value]:
            final_options_dict['resampleAlg'] = gdal.GRA_Bilinear
        else:
            final_options_dict['resampleAlg'] = gdal.GRA_NearestNeighbour

        # Ensure output directory exists before attempting to write the file
        if args.output_path is None:
            raise ProcessingStepFailedError("No output_path provided for the final output file.")
        out_dir = args.output_path.parent
        try:
            if not out_dir.exists():
                logger.info(f"Creating output directory: {out_dir}")
                out_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise ProcessingStepFailedError(f"Failed to create output directory '{out_dir}': {e}")
        
        logger.info(f"Creating {'COG' if args.cog else 'GeoTIFF'} at {args.output_path}")

        # Use the actual dataset description (file path), not the original temp_path
        # If alpha was converted to mask, temp_ds points to "masked.tif", not "intermediate.tif"
        actual_temp_path = temp_ds.GetDescription()       
        if args.cog:
            # For COG driver, use Translate
            final_options = gdal.TranslateOptions(**final_options_dict)
            final_ds = gdal.Translate(str(args.output_path), actual_temp_path, options=final_options)
            if final_ds is None:
                raise ProcessingStepFailedError("gdal.Translate failed to create COG.")
        else:
            # For GTiff driver (cog=False), use CreateCopy to preserve all internal structures
            logger.info("Using CreateCopy() for GTiff format to preserve internal structures.")
            driver = gdal.GetDriverByName('GTiff')
            final_ds = driver.CreateCopy(str(args.output_path), temp_ds, options=final_creation_options)
            if final_ds is None:
                raise ProcessingStepFailedError("CreateCopy failed to create GeoTIFF.")
        
        if tracker:
            tracker.stop("final_translate")
        
        # --- 10. Write external .aux.xml if requested ---
        if args.write_pam_xml:
            logger.info("Writing external .aux.xml file for the final dataset...")
            if stats:
                pam_data = build_pam_data_from_stats(stats, temp_ds)
                write_pam_xml(str(args.output_path), pam_data)
            else:
                logger.warning("No statistics available to write to .aux.xml file.")

        temp_ds = None
        final_ds = None
        if 'original_input_ds' in locals() and original_input_ds:
            original_input_ds = None

    if tracker:
        tracker.stop("gdal_processing")
    
    logger.info(f"\nSuccessfully created {'COG' if args.cog else 'GeoTIFF'}: {args.output_path}")

def optimize_compression(args: OptimizeArguments, tracker: Optional[PerformanceTracker] = None):
    """Main entry point for the CLI script."""
    global arcMode
    arcMode = args.arc_mode or False
    if arcMode:
        init_arcpy()

    if not args.input_path:
        logger.error("A valid input path is required.")
        return 1

    # The input_path can be a single Path or a list of Paths (directory case)
    if isinstance(args.input_path, list):  # directory case
        for file_path in args.input_path:
            current_args = OptimizeArguments(**vars(args))
            current_args.input_path = file_path
            current_args.output_path = file_path
            try:
                _process_single_file(current_args, tracker)
            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}")
                continue
    elif isinstance(args.input_path, Path):
        if args.input_path.is_dir():
            output_dir = Path(args.output_path) if args.output_path else args.input_path
            if not output_dir.exists():
                output_dir.mkdir(parents=True, exist_ok=True)
            
            copy_folder_structure(str(args.input_path), str(output_dir))
            geotiff_files = get_geotiff_files(str(args.input_path))
            
            for file_path_str in geotiff_files:
                file_path = Path(file_path_str)
                out_file = prepare_output_path(str(args.input_path), str(output_dir), str(file_path))
                
                # Create a copy of the arguments for each file
                current_args = OptimizeArguments(**vars(args))
                current_args.input_path = file_path
                current_args.output_path = Path(out_file)
                
                try:
                    _process_single_file(current_args, tracker)
                except Exception as e:
                    logger.error(f"Error processing {file_path.name}: {e}")
                    continue
        else: # single file case
            try:
                return _process_single_file(args, tracker)
            except Exception as e:
                logger.error(f"AN UNEXPECTED ERROR OCCURRED while processing {args.input_path.name}: {e}")
                traceback.print_exc(file=sys.stderr)
                return 1
    return 0
