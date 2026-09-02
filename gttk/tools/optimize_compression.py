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
from osgeo import gdal
from pathlib import Path
from typing import Any, Optional
from gttk.tools.compare_compression import generate_report_for_datasets
from gttk.utils.exceptions import ProcessingStepFailedError
from gttk.utils.gdal_env import gdal_env
from gttk.utils.geotiff_processor import read_geotiff
from gttk.utils.optimize_constants import CompressionAlgorithm as CA, ProductType as PT
import gttk.utils.optimize_constants as oc
from gttk.utils.cli_help import render_resolved_settings
from gttk.utils.path_helpers import get_geotiff_files, prepare_output_path, copy_folder_structure
from gttk.utils.performance_tracker import PerformanceTracker
from gttk.utils.preprocessor import preprocess_geotiff, round_overviews, VirtualFileManager
from gttk.utils.script_arguments import OptimizeArguments
from gttk.utils.srs_logic import handle_srs_logic, check_vertical_srs_mismatch
from gttk.utils.statistics import calculate_statistics, build_pam_data_from_stats, write_pam_xml

from gttk import __version__

# Global logger variables
log_file_path = None  # Path to the log file so it can be deleted by ArcPy
arcMode = False
arcpy = None
base_path = os.path.dirname(os.path.abspath(__file__))

# GDAL configuration is applied per operation by gdal_env(), not at import: setting it
# here made it process-global for anything that merely imported this module.

logger = logging.getLogger(__name__)

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

            # Report generation costs two full metadata passes, a full COG validation
            # of both files and a histogram render.  That is the right default for a
            # single file and prohibitive for a batch, hence the opt-out.
            if not getattr(args, 'report', True):
                logger.info("GDAL processing complete. Report generation skipped (report=False).")
            else:
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

def _calculate_overview_levels(x_size: int, y_size: int, tile_size: int = 512) -> list:
    """
    Calculate optimal overview levels, stopping when dimensions reach tile_size.
    
    Generates overview levels [2, 4, 8, 16, ...] until EITHER width or height
    is less than or equal to tile_size. This prevents generating unnecessary
    overviews for images where one or both dimensions are already small.
    
    Args:
        x_size: Image width in pixels
        y_size: Image height in pixels
        tile_size: Tile/block size (default: 512)
    
    Returns:
        List of overview levels as integers (e.g., [2, 4, 8])
    
    Example:
        For a 6000x4000 (width x height) image with 512 tile size:
        - Level 2: 3000x2000 (both > 512)
        - Level 4: 1500x1000 (both > 512)
        - Level 8: 750x500 (height <= 512) STOP
        Returns: [2, 4, 8]
    """
    levels = []
    factor = 2
    
    # Keep generating levels until one dimension reaches tile_size
    while True:
        # Calculate dimensions at this overview level
        overview_width = x_size / factor
        overview_height = y_size / factor

        # Add this overview level
        levels.append(factor)
        
        # Stop if either dimension is now <= tile_size
        if overview_width <= tile_size or overview_height <= tile_size:
            break

        factor *= 2
        
        # Safety check to prevent infinite loops
        if factor > 2**18:  # sufficient for 1m global COG at equator with 256x256 tiles
            logger.warning(f"Overview calculation stopped at factor {factor}. This is unexpected.")
            break
    
    # Always include at least one overview level if image is larger than tile_size
    if not levels and (x_size > tile_size and y_size > tile_size):
        levels = [2]
    
    logger.debug(f"Calculated overview levels for {x_size}x{y_size}: {levels}")
    return levels

def _orchestrate_geotiff_optimization(args: OptimizeArguments, vfm: VirtualFileManager, tracker: Optional[PerformanceTracker] = None):
    """Orchestrates the end-to-end GeoTIFF optimization and compression workflow."""
    with gdal_env():
        return _orchestrate_geotiff_optimization_inner(args, vfm, tracker)


def _orchestrate_geotiff_optimization_inner(args: OptimizeArguments, vfm: VirtualFileManager, tracker: Optional[PerformanceTracker] = None):
    if tracker:
        tracker.start("gdal_processing")
    
    logger.info(f"GeoTIFF ToolKit (GTTK) v{__version__} - optimizing "
                f"{Path(args.input_path).name} as '{args.product_type}'")

    original_input_ds = gdal.Open(str(args.input_path), gdal.GA_ReadOnly)
    if original_input_ds is None:
        raise ProcessingStepFailedError(f"Could not open input file '{args.input_path}'.")

    input_info = read_geotiff(original_input_ds)
    target_srs = handle_srs_logic(args, input_info)
    source_metadata = original_input_ds.GetMetadata()

    # PREDICTOR=3 is the TIFF floating-point predictor; libtiff rejects it on integer
    # samples, so clamp it now that the source data type is known.  Overviews follow.
    args.predictor, _pred_warning = oc.resolve_predictor(args.predictor, input_info.data_type)
    if _pred_warning:
        logger.warning(_pred_warning)
    args.overview_predictor, _ovr_warning = oc.resolve_predictor(
        args.overview_predictor, input_info.data_type)
    if _ovr_warning and _ovr_warning != _pred_warning:
        logger.warning(f"Overview {_ovr_warning[0].lower()}{_ovr_warning[1:]}")

    # Logged here rather than on entry: the clamp above is the one decision that cannot
    # be described from the flags alone, so reporting the settings before it would print
    # a predictor the run does not use.
    _clamp_notes = {}
    if _pred_warning:
        _clamp_notes['predictor'] = f'clamped for {input_info.data_type} data'
    if _ovr_warning:
        _clamp_notes['overview_predictor'] = f'clamped for {input_info.data_type} data'
    logger.info(render_resolved_settings(args, notes=_clamp_notes,
                                         data_type=str(input_info.data_type)))

    temp_ds = None
    final_ds = None
    try:
        with vfm as temp_vfm:
            temp_path = temp_vfm.get_temp_path("intermediate.tif")

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

            # --- 2. Detect internal mask and determine overview strategy ---
            has_internal_mask = False
            if temp_ds.RasterCount > 0:
                band = temp_ds.GetRasterBand(1)
                mask_flags = band.GetMaskFlags()
                # GMF_PER_DATASET (0x02) indicates an internal mask
                has_internal_mask = (mask_flags & gdal.GMF_PER_DATASET) != 0
                logger.debug(f"Internal mask detected: {has_internal_mask}")
        
            # Determine if we should round overviews (all conditions must be met)
            should_round_overviews = (
                args.overviews and
                isinstance(args.decimals, int) and
                not getattr(args, 'discard_lsb', False) and  # LSB mode quantizes at write time, not via np.round
                args.algorithm in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value] and
                args.product_type in [PT.DEM.value, PT.ERROR.value, PT.SCIENTIFIC.value] and
                'Float' in str(input_info.data_type) and
                not has_internal_mask  # Don't round if mask present
            )
        
            # Log the decision
            if args.overviews:
                if should_round_overviews:
                    logger.info("Overview strategy: ROUNDING workflow (float data, lossless compression, no mask)")
                elif has_internal_mask:
                    logger.info("Overview strategy: STANDARD workflow (internal mask detected)")
                else:
                    logger.info("Overview strategy: STANDARD workflow (rounding conditions not met)")

            # --- 3. Build creation options based on overview strategy ---
            final_creation_options = [
                'GEOTIFF_VERSION=1.1',
                'BIGTIFF=IF_SAFER',
                f'NUM_THREADS={args.num_threads}',
                f'COMPRESS={args.algorithm}'
            ]
            
            if args.cog:
                final_creation_options += [f'BLOCKSIZE={args.tile_size}']
            
                if args.overviews:
                    if should_round_overviews:
                        # Use existing overviews (built on intermediate and rounded)
                        final_creation_options.append('OVERVIEWS=FORCE_USE_EXISTING')
                    else:
                        # Let COG driver build overviews (standard workflow).  The driver's
                        # own default is an interpolating kernel for any band without a
                        # colour table, which invents class codes in categorical data, so
                        # state the kernel explicitly.  It is only consulted on this branch:
                        # FORCE_USE_EXISTING copies the pyramid built on the intermediate.
                        final_creation_options.append('OVERVIEWS=AUTO')
                        final_creation_options.append(
                            f'OVERVIEW_RESAMPLING={args.overview_resampling}')
                    # The COG driver defaults OVERVIEW_COMPRESS to LZW regardless of
                    # COMPRESS, which silently mixes codecs within one file.
                    final_creation_options.append(f'OVERVIEW_COMPRESS={args.overview_compress}')
                    if (args.overview_compress in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value]
                            and args.overview_predictor and int(args.overview_predictor) != 1):
                        final_creation_options.append(
                            f'OVERVIEW_PREDICTOR={args.overview_predictor}')
                else:
                    final_creation_options.append('OVERVIEWS=NONE')
            else:
                final_creation_options += [
                    'TILED=YES',
                    f'BLOCKXSIZE={args.tile_size}',
                    f'BLOCKYSIZE={args.tile_size}'
                ]
            
                if args.overviews:
                    if should_round_overviews:
                        # Copy existing overviews from intermediate
                        final_creation_options.append('COPY_SRC_OVERVIEWS=YES')
                    else:
                        # Don't copy - will build external overviews after
                        final_creation_options.append('COPY_SRC_OVERVIEWS=NO')
                else:
                    final_creation_options.append('COPY_SRC_OVERVIEWS=NO')

            # Algorithm-specific creation options
            # PREDICTOR=1 is "no predictor" and is the default for both drivers, but they
            # spell it differently: the COG driver warns on '1' (its value list is
            # NO/YES/STANDARD/FLOATING_POINT) and GTiff errors on 'NO'.  Omit it instead.
            if (args.algorithm in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value]
                    and args.predictor and int(args.predictor) != 1):
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
            elif args.algorithm in [CA.LERC.value, CA.LERC_DEFLATE.value, CA.LERC_ZSTD.value]:
                final_creation_options.append(f'MAX_Z_ERROR={args.max_z_error}')

            # Compression level: the COG driver uses LEVEL; the GTiff driver uses ZLEVEL
            # (deflate) / ZSTD_LEVEL (zstd) -- which also covers the LERC_DEFLATE/LERC_ZSTD
            # backends. Passing LEVEL= to the GTiff driver is silently ignored, so branch.
            if args.level:
                if args.algorithm in [CA.DEFLATE.value, CA.LERC_DEFLATE.value]:
                    final_creation_options.append(f'LEVEL={args.level}' if args.cog else f'ZLEVEL={args.level}')
                elif args.algorithm in [CA.ZSTD.value, CA.LERC_ZSTD.value]:
                    final_creation_options.append(f'LEVEL={args.level}' if args.cog else f'ZSTD_LEVEL={args.level}')

            logger.info(f"Final creation options set: {final_creation_options}")

            # --- 4. Build and round overviews on intermediate file (ONLY if rounding workflow) ---
            if should_round_overviews:
                if tracker:
                    tracker.start("overview_creation")
            
                # Type guard: should_round_overviews is True means args.decimals is not None
                assert args.decimals is not None, "args.decimals must be set when should_round_overviews is True"
            
                logger.info("Building internal overviews on intermediate file for rounding (float data, no mask).")
                resample_alg = args.overview_resampling
                overview_list = _calculate_overview_levels(input_info.x_size, input_info.y_size, tile_size=args.tile_size)
                logger.info(f"Using overview levels: {', '.join(map(str, overview_list))}")

                overview_options = [
                    'COMPRESS=NONE',  # Always uncompressed on intermediate file for rounding
                ]

                # Set overview block size using GDAL config option (TILED/BLOCKXSIZE/BLOCKYSIZE not supported for overviews)
                old_ovr_blocksize = gdal.GetConfigOption('GDAL_TIFF_OVR_BLOCKSIZE')
                gdal.SetConfigOption('GDAL_TIFF_OVR_BLOCKSIZE', str(args.tile_size))

                temp_ds.BuildOverviews(resampling=resample_alg, overviewlist=overview_list, options=overview_options)

                # Restore original config option
                gdal.SetConfigOption('GDAL_TIFF_OVR_BLOCKSIZE', old_ovr_blocksize)
            
                logger.info(f"Rounding overviews to {args.decimals} decimal places...")
                temp_ds = round_overviews(temp_ds, args.decimals)
            
                if tracker:
                    tracker.stop("overview_creation")

            # --- 5. Create final COG or GeoTIFF ---
            if tracker:
                tracker.start("final_translate")
            
            final_options_dict = {
                'format': 'COG' if args.cog else 'GTiff',
                'creationOptions': final_creation_options,
                'stats': True,
                'callback': format_gdal_progress if not arcMode else None,
                'callback_data': progress_callback_data if not arcMode else None
            }

            # Re-assert the resolved SRS on the final write rather than letting it flow
            # through the intermediate's GeoTIFF keys.  A compound CRS survives that
            # round-trip only partially: the vertical component comes back identified by
            # its datum (VerticalDatumGeoKey) and loses its own EPSG code, so the output
            # names EGM2008 without ever citing EPSG:3855.  This is -a_srs, an assignment:
            # pixels and the geotransform are untouched.
            if target_srs is not None:
                final_options_dict['outputSRS'] = target_srs.ExportToWkt(['FORMAT=WKT2_2019'])

            # Note: Alpha band stripping is handled entirely by the preprocessor via _create_intermediate_with_mask()
            # which converts alpha to an internal mask. The final translate will preserve this structure automatically.

            # Handle NoData value for final output
            # Note: preprocessor may have unset NoData if it was invalid
            if input_info.nodata is not None:
                if args.mask_nodata:
                    # Unset NoData value when using internal mask
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
        
            # --- 6. Build external overviews for GTiff if using standard workflow ---
            if not args.cog and args.overviews and not should_round_overviews:
                if tracker:
                    tracker.start("external_overviews")
            
                logger.info("Building external overviews on final GTiff file (standard workflow)...")
                resample_alg = args.overview_resampling
                overview_list = _calculate_overview_levels(input_info.x_size, input_info.y_size, tile_size=args.tile_size)
                logger.info(f"Using overview levels: {', '.join(map(str, overview_list))}")
            
                # Reopen as update to build overviews
                final_ds_for_overviews = gdal.Open(str(args.output_path), gdal.GA_Update)
                if final_ds_for_overviews:
                    overview_options_external = [
                        f'COMPRESS={args.algorithm}',
                    ]

                    # Add predictor if applicable
                    if (args.algorithm in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value]
                            and args.predictor and int(args.predictor) != 1):
                        overview_options_external.append(f'PREDICTOR={args.predictor}')

                    # Match the main-band compression level on external GTiff overviews
                    if args.level and args.algorithm == CA.DEFLATE.value:
                        overview_options_external.append(f'ZLEVEL={args.level}')
                    elif args.level and args.algorithm == CA.ZSTD.value:
                        overview_options_external.append(f'ZSTD_LEVEL={args.level}')

                    # Set overview block size using GDAL config option (TILED/BLOCKXSIZE/BLOCKYSIZE not supported for overviews)
                    old_ovr_blocksize = gdal.GetConfigOption('GDAL_TIFF_OVR_BLOCKSIZE')
                    gdal.SetConfigOption('GDAL_TIFF_OVR_BLOCKSIZE', str(args.tile_size))

                    final_ds_for_overviews.BuildOverviews(
                        resampling=resample_alg.upper(),
                        overviewlist=overview_list,
                        options=overview_options_external
                    )

                    # Restore original config option
                    gdal.SetConfigOption('GDAL_TIFF_OVR_BLOCKSIZE', old_ovr_blocksize)

                    final_ds_for_overviews = None
                    logger.info(f"External overviews built successfully with {args.algorithm} compression.")
                else:
                    logger.warning("Failed to open final file for external overview building.")
            
                if tracker:
                    tracker.stop("external_overviews")
        
            # --- 7. Write external .aux.xml if requested ---
            if args.write_pam_xml:
                logger.info("Writing external .aux.xml file for the final dataset...")
                if stats:
                    pam_data = build_pam_data_from_stats(stats, temp_ds)
                    write_pam_xml(str(args.output_path), pam_data)
                else:
                    logger.warning("No statistics available to write to .aux.xml file.")

    finally:
        # GDAL releases a dataset only when the last Python reference goes away.
        temp_ds = None
        final_ds = None
        original_input_ds = None

    if tracker:
        tracker.stop("gdal_processing")
    
    logger.info(f"\nSuccessfully created {'COG' if args.cog else 'GeoTIFF'}: {args.output_path}")

def optimize_compression(args: OptimizeArguments, tracker: Optional[PerformanceTracker] = None):
    """Main entry point for the CLI script."""
    with gdal_env():
        return _optimize_compression_inner(args, tracker)


def _optimize_compression_inner(args: OptimizeArguments, tracker: Optional[PerformanceTracker] = None):
    global arcMode
    arcMode = args.arc_mode or False

    if not args.input_path:
        logger.error("A valid input path is required.")
        return 1

    if isinstance(args.input_path, Path):
        if args.input_path.is_dir():
            output_dir = Path(args.output_path) if args.output_path else args.input_path
            if not output_dir.exists():
                output_dir.mkdir(parents=True, exist_ok=True)
            
            copy_folder_structure(str(args.input_path), str(output_dir))
            geotiff_files = get_geotiff_files(str(args.input_path))

            if args.open_report and args.report:
                logger.info("Directory input: not auto-opening one report per file.")
                args.open_report = False
            
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
