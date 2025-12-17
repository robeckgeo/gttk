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
Optimize Compression for the ArcGIS Pro Toolbox.

This script is the user-facing front-end for the GeoTIFF optimization tool,
specifically for use in environments like ArcGIS Pro.

Its primary responsibilities are:
- Parsing all user-provided command-line arguments.
- Performing all intelligent pre-processing analysis (determining SRS, NoData, etc.).
- Constructing a series of command-line calls for GDAL executables.
- Calling the back-end gdal_runner.py script as a subprocess,
  passing the commands as a JSON payload via stdin.
- Handling the final report generation after the back-end script finishes.
"""

import logging
import numpy as np
import os
import sys
import traceback
import json
import subprocess
import tomllib
import uuid
from importlib import metadata
from osgeo import gdal, osr
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple, TYPE_CHECKING
from gttk.tools.compare_compression import generate_report_for_datasets
from gttk.utils.exceptions import ProcessingStepFailedError
from gttk.utils.optimize_constants import CompressionAlgorithm as CA, ProductType as PT
from gttk.utils.gdal_runner import create_isolated_env
from gttk.utils.geo_metadata_writer import prepare_xml_for_gdal
from gttk.utils.geotiff_processor import is_nodata_valid, GeoTiffInfo
from gttk.utils.log_helpers import init_arcpy
from gttk.utils.path_helpers import get_geotiff_files, prepare_output_path, copy_folder_structure
from gttk.utils.performance_tracker import PerformanceTracker
from gttk.utils.preprocessor import find_xml_metadata_file
from gttk.utils.script_arguments import OptimizeArguments
from gttk.utils.srs_logic import handle_srs_logic, check_vertical_srs_mismatch
from gttk.utils.statistics_calculator import calculate_statistics, build_pam_data_from_stats, write_pam_xml

try:
    __version__ = metadata.version("geotiff-toolkit")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"

# --- Configuration ---
with open(Path(__file__).resolve().parent.parent.parent / 'config.toml', 'rb') as f:
    config = tomllib.load(f)

SCRIPT_DIR = Path(__file__).resolve().parent
GDAL_RUNNER_SCRIPT = SCRIPT_DIR.parent / 'utils' / 'gdal_runner.py'

# Global logger variables
logger = logging.getLogger('optimize_compression_arc')
# Force WKT2_2019 formatting and preserve WKT2 in GTiff; prefer WKT when reading
gdal.SetConfigOption('OSR_WKT_FORMAT', 'WKT2_2019')
gdal.SetConfigOption('GTIFF_WRITE_SRS_WKT2', 'YES')
gdal.SetConfigOption('GTIFF_SRS_SOURCE', 'WKT')

if TYPE_CHECKING:
    import arcpy # type: ignore

# --- Temporary File Manager ---
class TemporaryFileManager:
    """Manages a temporary workspace on disk."""
    def __init__(self):
        self.temp_dir = Path(os.environ.get("TEMP", Path.cwd())) / f"gttk_{uuid.uuid4().hex}"
        self.temp_dir.mkdir(exist_ok=True)
        self.temp_files: List[Path] = []
        logger.info(f"Created temporary directory: {self.temp_dir}")

    def get_temp_path(self, filename: str) -> Path:
        """Generates and registers a new path within the temporary directory."""
        temp_path = self.temp_dir / filename
        self.temp_files.append(temp_path)
        logger.debug(f"TemporaryFileManager: Registered temp path: {temp_path}")
        return temp_path

    def cleanup(self):
        """Deletes all registered temporary files and the directory."""
        logger.info(f"Cleaning up {len(self.temp_files)} temporary files...")
        import shutil
        try:
            shutil.rmtree(self.temp_dir)
            logger.info("Temporary directory cleaned up successfully.")
        except OSError as e:
            logger.error(f"Error cleaning up temporary directory {self.temp_dir}: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

def run_gdal_commands(commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Executes a list of GDAL commands in an isolated OSGeo4W environment
    by calling the gdal_runner.py script as a subprocess.
    """
    osgeo4w_path_str = config['paths']['osgeo4w']
    if not osgeo4w_path_str:
        raise ValueError("'osgeo4w' not found in config.toml.")
    
    osgeo4w_dir = Path(osgeo4w_path_str)
    python_executable = osgeo4w_dir / "bin" / "python.exe"

    if not python_executable.exists():
        raise FileNotFoundError(f"OSGeo4W Python executable not found at: {python_executable}")
    
    command = [str(python_executable), str(GDAL_RUNNER_SCRIPT)]
    payload = json.dumps({"commands": commands})
    
    logger.info(f"Executing {len(commands)} GDAL command(s) in isolated environment via {python_executable}...")
    
    captured_outputs = []
    
    try:
        isolated_env = create_isolated_env(osgeo4w_dir)

        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=isolated_env,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        
        stdout, stderr = process.communicate(input=payload)

        if stdout:
            # gdalinfo with JSON output is very verbose; log at debug level
            logger.debug("--- GDAL Runner STDOUT ---")
            for line in stdout.strip().split('\n'):
                logger.debug(f"[Runner]: {line}")
                # Try to parse line as JSON for captured output
                try:
                    captured_data = json.loads(line)
                    if isinstance(captured_data, dict) and "stdout" in captured_data:
                        captured_outputs.append(captured_data)
                except json.JSONDecodeError:
                    pass # Ignore lines that are not JSON
            logger.debug("---------------------------------------\n")
        if stderr:
            logger.warning("--- GDAL Runner STDERR ---")
            for line in stderr.strip().split('\n'):
                logger.warning(f"[Runner]: {line}")
            logger.warning("---------------------------------------\n")

        if process.returncode != 0:
            error_message = f"GDAL runner script failed with exit code {process.returncode}."
            if stderr:
                error_message += f"\n--- STDERR ---\n{stderr.strip()}"
            if stdout:
                 error_message += f"\n--- STDOUT ---\n{stdout.strip()}"
            raise RuntimeError(error_message)
            
        return captured_outputs
            
    except Exception as e:
        logger.error(f"An error occurred while launching the GDAL runner: {e}")
        raise

def _get_initial_info(input_path: Path) -> Dict[str, Any]:
    """Gets initial GeoTIFF info using gdalinfo -json."""
    gdalinfo_command = {
        "command": ["gdalinfo", "-json", str(input_path)],
        "capture_output": True
    }
    logger.info(f"Requesting initial metadata for {input_path} using gdalinfo...")
    captured_output = run_gdal_commands([gdalinfo_command])
    
    if not captured_output or "stdout" not in captured_output[0]:
        raise ProcessingStepFailedError("Failed to get initial info: No output captured from gdalinfo.")
        
    try:
        return json.loads(captured_output[0]["stdout"])
    except json.JSONDecodeError as e:
        raise ProcessingStepFailedError(f"Failed to parse gdalinfo JSON output: {e}")

def _get_jxl_overview_options(quality: int, effort: int = 7):
    """
    Maps an integer quality (1-100) to GDAL JXL creation options.
   
    Args:
        quality_int (int): 1-100 (75-100 recommended for JXL).
        effort (int): 1-9 (Speed vs Density). 7 is a strong default for JXL.
       
    Returns:
        list: A list of strings for GDAL creation options.
    """
    # Build CLI-ready --config pairs (all strings). gdaladdo expects
    # '--config', KEY, VALUE tuples; keep values stringified to
    # avoid TypeErrors when joining/printing commands.
    options: List[str] = []

    # effort is numeric; stringify it for the CLI
    options.extend(["--config", "JXL_EFFORT", str(effort)])

    if quality == 100:  # Lossless
        options.extend(["--config", "JXL_LOSSLESS", "YES"])
        # JXL_DISTANCE is ignored when Lossless is YES
    else:  # Lossy
        options.extend(["--config", "JXL_LOSSLESS", "NO"])

        # Calculate Distance using "The Rule of Ten" formula
        # Q90 -> Dist 1.0 (Visually Lossless)
        # Q75 -> Dist 2.5 (Standard Web Quality)
        distance = (100.0 - quality) * 0.1

        # Clamp to safe JXL bounds (minimum quality value is 75 -> max distance 2.5)
        distance = max(0.01, distance)
        options.extend(["--config", "JXL_DISTANCE", f"{distance:.2f}"])

        # Explicitly let Alpha follow the main distance
        options.extend(["--config", "JXL_ALPHA_DISTANCE", "-1"])

    return options

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

def _determine_target_nodata_and_remap_status(
    input_info: GeoTiffInfo,
    args: OptimizeArguments
) -> Tuple[Optional[Union[float, str]], bool]:
    """
    Determine the target NoData value and whether remapping is needed.
    
    This implements the simplified NoData logic: if source NoData is invalid,
    no pixels can have that value, so just use the user-specified value if provided,
    otherwise unset it (return None).
    
    Args:
        input_info: GeoTiffInfo object with source dataset information
        args: OptimizeArguments with user-specified parameters
    
    Returns:
        A tuple containing:
        - The target NoData value (or None if no NoData needed)
        - Boolean indicating whether remapping is needed
    """
    # Convert string "nan" to np.nan if needed
    user_nodata = None
    if args.nodata is not None:
        if isinstance(args.nodata, str) and args.nodata.lower() == 'nan':
            user_nodata = np.nan
        else:
            user_nodata = float(args.nodata)
    
    # Priority 1: User-specified target NoData always takes precedence
    if user_nodata is not None:
        # Override user request if incompatible with LERC CLI
        if args.algorithm == CA.LERC.value and isinstance(user_nodata, float) and np.isnan(user_nodata):
            SAFE_LERC_NODATA = -32767.0
            logger.warning("User requested NoData 'NaN', but gdal_translate CLI cannot handle NaN with LERC.")
            logger.warning(f"Overriding user request: Substituting NaN with {SAFE_LERC_NODATA} for NoData value.")
            user_nodata = SAFE_LERC_NODATA

        # Check if remapping is needed (source differs from user value)
        needs_remap = (input_info.nodata is not None and input_info.nodata != user_nodata)
        return user_nodata, needs_remap
    
    # If no source NoData, no correction needed
    if input_info.nodata is None:
        return None, False
    
    # If no data type provided, can't validate - return as-is
    if input_info.data_type is None:
        return input_info.nodata, False
    
    # Check if the source NoData value is valid for the data type
    if not is_nodata_valid(input_info.nodata, input_info.data_type):
        # Remap invalid or extreme NoData (e.g. -inf) to a safe value if no user value provided
        logger.warning(
            f"Source NoData value {input_info.nodata} is invalid or extreme for {input_info.data_type}. "
            f"Will attempt to remap to a safe value."
        )
        
        if 'Float' in input_info.data_type:
            # Handle LERC + NaN issue for remapping too
            if args.algorithm == CA.LERC.value:
                SAFE_LERC_NODATA = -32767.0
                logger.warning(f"Remapping invalid NoData to {SAFE_LERC_NODATA} instead of NaN for LERC stability.")
                return SAFE_LERC_NODATA, True
            
            # For floats, map invalid NoData to NaN
            return np.nan, True
        else:
            # For integers, if the current one is invalid no pixels can have that value, so unset it
            return None, False
    
    # Valid source NoData, keep it
    return input_info.nodata, False

def _build_nodata_remap_command(
    input_file: str,
    output_file: str,
    source_nodata: Union[float, str],
    target_nodata: Union[float, str],
    data_type: str
) -> List[str]:
    """
    Build gdal_calc.py command to remap NoData values.
    Mirrors the logic in geotiff_processor.remap_nodata_value() but using gdal_calc.py.
    """
    # Normalize string "nan" to numpy.nan for comparisons
    source_is_nan = (isinstance(source_nodata, float) and np.isnan(source_nodata))
    target_is_nan = (isinstance(target_nodata, float) and np.isnan(target_nodata)) or (isinstance(target_nodata, str) and target_nodata.lower() == 'nan')
    
    # Build the numpy.where expression based on source/target types
    if source_is_nan:
        calc_expr = f"numpy.where(numpy.isnan(A), {'numpy.nan' if target_is_nan else target_nodata}, A)"
    else:
        calc_expr = f"numpy.where(A == {source_nodata}, {'numpy.nan' if target_is_nan else target_nodata}, A)"
    
    cmd = [
        "gdal_calc.py",
        "--calc", calc_expr,
        "-A", input_file,
        "--outfile", output_file,
        "--type", data_type
    ]
    
    # Only add --NoDataValue for non-NaN targets (gdal_calc doesn't accept it for NaN)
    if not target_is_nan:
        cmd.extend(["--NoDataValue", str(target_nodata)])
    
    return cmd

def _build_alpha_threshold_command(
    input_file: str,
    thresholded_alpha_file: str,
    threshold: int = 230
) -> List[str]:
    """
    Builds a gdal_calc.py command to threshold the alpha band (band 4).
    Uses a threshold of 230 (90% opaque) to reduce edge effects.
    Creates a single-band GeoTIFF with the thresholded alpha values.
    """
    threshold_alpha_cmd = [
        "gdal_calc.py",
        "--calc", f"numpy.where(A>={threshold}, 255, 0)",
        "-A", input_file,
        "--A_band", "4",
        "--outfile", thresholded_alpha_file,
        "--type", "Byte",
        "--NoDataValue", "0"
    ]
    return threshold_alpha_cmd

def _calculate_overview_levels(x_size: int, y_size: int, tile_size: int = 512) -> List[str]:
    """
    Calculate optimal overview levels where the highest level has only one tile.
    
    Args:
        x_size: Image width in pixels
        y_size: Image height in pixels
        tile_size: Tile/block size (default: 512)
    
    Returns:
        List of overview levels as strings (e.g., ["2", "4", "8", "16"])
    
    Example:
        For a 10240x8192 image with 512 block size:
        - Level 2: 5120x4096 (10x8 tiles)
        - Level 4: 2560x2048 (5x4 tiles)
        - Level 8: 1280x1024 (3x2 tiles)
        - Level 16: 640x512 (2x1 tiles)
        - Level 32: 320x256 (1x1 tile) ✓ STOP
    """
    import math
    
    # Calculate how many levels needed for each dimension to reach <= 1 tile
    levels_x = math.ceil(math.log2(x_size / tile_size)) if x_size > tile_size else 0
    levels_y = math.ceil(math.log2(y_size / tile_size)) if y_size > tile_size else 0
    
    # Use the maximum to ensure both dimensions are <= 1 tile at highest level
    max_levels = max(levels_x, levels_y)
    
    # Generate levels: 2, 4, 8, 16, ..., 2^max_levels
    # Always include at least level 2 if image is larger than tile_size
    if max_levels > 0:
        levels = [str(2 ** i) for i in range(1, max_levels + 1)]
    else:
        levels = ["2"]  # Minimum one level for small images
    
    logger.debug(f"Calculated overview levels for {x_size}x{y_size}: {levels}")
    return levels

def _write_mask_attachment_script(script_path: Path, target_tif: str, mask_tif: str):
    """
    Writes a temporary Python script to attach a mask to a dataset.
    This script is intended to be executed by the gdal_runner in the isolated environment.
    """
    # Escape backslashes for the python string
    target_tif_esc = str(target_tif).replace('\\', '\\\\')
    mask_tif_esc = str(mask_tif).replace('\\', '\\\\')
    
    script_content = f"""
import sys
import os
from osgeo import gdal

gdal.UseExceptions()

def attach_mask():
    target_path = "{target_tif_esc}"
    mask_path = "{mask_tif_esc}"
    
    print(f"Opening target: {{target_path}}")
    ds = gdal.Open(target_path, gdal.GA_Update)
    if not ds:
        print("Failed to open target dataset")
        sys.exit(1)
        
    print(f"Opening mask: {{mask_path}}")
    mask_ds = gdal.Open(mask_path)
    if not mask_ds:
        print("Failed to open mask dataset")
        sys.exit(1)
        
    mask_data = mask_ds.GetRasterBand(1).ReadAsArray()
    
    print("Creating internal mask band...")
    ds.CreateMaskBand(gdal.GMF_PER_DATASET)
    mb = ds.GetRasterBand(1).GetMaskBand()
    mb.WriteArray(mask_data)
    mb.FlushCache()
    
    # Unset NoData
    print("Unsetting NoData values...")
    for i in range(1, ds.RasterCount + 1):
        ds.GetRasterBand(i).DeleteNoDataValue()
        
    ds = None
    mask_ds = None
    print("Mask attachment complete.")

if __name__ == "__main__":
    attach_mask()
"""
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)

def _write_translate_script(script_path: Path, input_path: str, output_path: str, options: List[str], xml_path: Optional[str] = None):
    """
    Writes a temporary Python script to perform gdal_translate.
    This bypasses Windows command line length limits by using the Python API.
    """
    input_esc = str(input_path).replace('\\', '\\\\')
    output_esc = str(output_path).replace('\\', '\\\\')
    xml_path_esc = str(xml_path).replace('\\', '\\\\') if xml_path else None
    
    script_content = f"""
import sys
import json
from osgeo import gdal

gdal.UseExceptions()
gdal.SetConfigOption('OSR_WKT_FORMAT','WKT2_2019')
gdal.SetConfigOption('GTIFF_WRITE_SRS_WKT2','YES')
gdal.SetConfigOption('GTIFF_SRS_SOURCE','WKT')

def run_translate():
    input_path = "{input_esc}"
    output_path = "{output_esc}"
    
    # Load base options
    options = {json.dumps(options)}
    
    # Inject metadata if provided
    xml_file = "{xml_path_esc}"
    if xml_file and xml_file != "None":
        try:
            with open(xml_file, 'r', encoding='utf-8') as f:
                xml_content = f.read()
            options.extend(["-mo", f"GEO_METADATA={{xml_content}}"])
            print(f"Loaded GEO_METADATA from {{xml_file}}")
        except Exception as e:
            print(f"Error reading metadata file: {{e}}")
            sys.exit(1)
            
    print(f"Translating {{input_path}} to {{output_path}}...")
    
    # Use gdal.Translate
    try:
        ds = gdal.Open(input_path)
        if not ds:
            print(f"Failed to open input dataset: {{input_path}}")
            sys.exit(1)
            
        gdal.Translate(output_path, ds, options=options)
        print("Translation complete.")
        ds = None
    except Exception as e:
        print(f"Translation failed: {{e}}")
        sys.exit(1)

if __name__ == "__main__":
    run_translate()
"""
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)

    
def _orchestrate_geotiff_optimization(args: OptimizeArguments, tracker: Optional[PerformanceTracker] = None):
    """Builds and executes a sequence of GDAL commands."""
    
    if tracker:
        tracker.start("gdal_processing")
    
    # 1. Initial State Assessment
    assert args.input_path is not None, "Input path must be provided"
    if not isinstance(args.input_path, Path):
        raise TypeError("optimize_compression requires a single Path object for input_path.")

    info = _get_initial_info(args.input_path)
    
    # Create a GeoTiffInfo object from the gdalinfo output
    wkt = info.get('coordinateSystem', {}).get('wkt', '')
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    geo_transform = tuple(info.get('geoTransform', [0, 1, 0, 0, 0, -1]))
    
    input_info = GeoTiffInfo(
        filepath=str(args.input_path),
        wkt_string=wkt,
        geo_transform=geo_transform,
        srs=srs,
        x_size=info.get('size', [0, 0])[0],
        y_size=info.get('size', [0, 0])[1],
        bands=len(info.get('bands', [])),
        res_x=abs(geo_transform[1]),
        res_y=abs(geo_transform[5]),
        nodata=info.get('bands', [{}])[0].get('noDataValue'),
        data_type=info.get('bands', [{}])[0].get('type'),
        has_alpha=any(b.get('colorInterpretation') == 'Alpha' for b in info.get('bands', []))
    )
    

    # Perform vertical SRS mismatch check
    target_srs = None
    ds = gdal.Open(str(args.input_path))
    if ds:
        try:
            target_srs = handle_srs_logic(args, input_info)
            check_vertical_srs_mismatch(ds, args.vertical_srs, str(args.input_path))
        finally:
            ds = None # Ensure the dataset is closed to release file locks

    commands = []
    current_input = args.input_path
    
    # Determine masking logic (must be defined before use)
    should_mask = False
    if args.mask_nodata is True:
        should_mask = True
    elif args.mask_nodata is None:
        if args.product_type == PT.THEMATIC.value:
            # Thematic data should NOT have transparency masks
            should_mask = False
        elif input_info.has_alpha and args.mask_alpha:
            should_mask = True
        elif args.product_type == PT.IMAGE.value:
            should_mask = True

    with TemporaryFileManager() as tfm:
        # --- Step 1: Remap NoData Values if Necessary ---
        target_nodata, needs_remapping = _determine_target_nodata_and_remap_status(input_info, args)
        
        if needs_remapping:
            if tracker:
                tracker.start("nodata_remap")
            
            assert target_nodata is not None, "target_nodata should not be None when remapping is needed"
            
            remapped_file = tfm.get_temp_path("nodata_remapped.tif")
            remap_cmd = _build_nodata_remap_command(
                input_file=str(current_input),
                output_file=str(remapped_file),
                source_nodata=input_info.nodata,
                target_nodata=target_nodata,
                data_type=input_info.data_type or "Float32"
            )
            commands.append({"command": remap_cmd})
            current_input = remapped_file
            logger.info(f"Step 1: Remapped NoData from {input_info.nodata} to {target_nodata}")
            
            if tracker:
                tracker.stop("nodata_remap")

        # --- Step 2 (Optional): Rounding ---
        needs_rounding = args.decimals is not None and input_info.data_type and 'Float' in input_info.data_type
        if needs_rounding:
            if tracker:
                tracker.start("rounding")
            rounded_file = tfm.get_temp_path("rounded.tif")
            calc_expr = f"round(A, {args.decimals})"
            cmd = [
                "gdal_calc.py",
                "--calc", calc_expr,
                "-A", str(current_input),
                "--outfile", str(rounded_file),
                "--overwrite"
            ]
            
            # Add output data type to match input
            if input_info.data_type:
                cmd.extend(["--type", input_info.data_type])
            
            # Preserve NoData value during rounding
            if target_nodata is not None:
                # Handle NaN specially - gdal_calc doesn't accept --NoDataValue for NaN
                if not (isinstance(target_nodata, float) and np.isnan(target_nodata)):
                    cmd.extend(["--NoDataValue", str(target_nodata)])
            
            commands.append({"command": cmd})
            current_input = rounded_file
            logger.info(f"Step 2: Rounding command created. Output: {current_input}")
            if tracker:
                tracker.stop("rounding")

        # --- Step 3: Packed Preprocessing Translate ---
        if tracker:
            tracker.start("intermediate_processing")
        
        preprocessed_file = tfm.get_temp_path("preprocessed.tif")
        preprocess_cmd = ["gdal_translate",
                          "--config", "OSR_WKT_FORMAT", "WKT2_2019",
                          "--config", "GTIFF_WRITE_SRS_WKT2", "YES",
                          "--config", "GTIFF_SRS_SOURCE", "WKT",
                          "-of", "GTiff", "-co", "TILED=YES"]

        # Add metadata
        source_metadata = info.get('metadata', {}).get('', {})
        software_tag = source_metadata.get('TIFFTAG_SOFTWARE', '')
        new_software_tag = f"{software_tag.strip()} - optimized by GeoTIFF ToolKit v{__version__}" if software_tag else f"GeoTIFF ToolKit v{__version__}"
        # Check for vertical SRS to conditionally remove UNITTYPE
        # This removes potential conflicts if vertical SRS is being stripped
        has_vertical = 'VERT_CS' in wkt or 'VERTCRS' in wkt

        for key, value in source_metadata.items():
            if key == 'TIFFTAG_SOFTWARE':
                continue

            if key == 'UNITTYPE' and has_vertical and not args.vertical_srs:
                continue

            # Quote the value to handle potential special characters
            preprocess_cmd.extend(["-mo", f"{key}={value}"])
        preprocess_cmd.extend(["-mo", f"TIFFTAG_SOFTWARE={new_software_tag}"])

        # Add Area/Point with correct priority
        default_raster_type = 'Point' if args.product_type in [PT.DEM.value, PT.ERROR.value, PT.SCIENTIFIC.value] else 'Area'
        final_raster_type = args.raster_type or default_raster_type
        preprocess_cmd.extend(["-mo", f"AREA_OR_POINT={final_raster_type}"])

        # Determine bands to keep
        source_bands = info.get('bands', [])
        alpha_band_index = None
        
        if input_info.has_alpha and args.mask_alpha:
            # Find alpha band
            for i, band in enumerate(source_bands, start=1):
                if band.get('colorInterpretation') == 'Alpha':
                    alpha_band_index = i
                    break
            
            # Exclude alpha band from the main translation
            if alpha_band_index:
                for i in range(1, len(source_bands) + 1):
                    if i != alpha_band_index:
                        preprocess_cmd.extend(["-b", str(i)])
                # Also preserve color interpretation if needed (though mostly redundant if copying all other bands)

        if target_nodata is not None:
            # If masking is enabled, the NoData value will be unset later.
            # BUT, we need to preserve it during this step so the mask generation works correctly if it depends on it.
            if isinstance(target_nodata, float) and np.isnan(target_nodata):
                preprocess_cmd.extend(["-a_nodata", "nan"])
            else:
                preprocess_cmd.extend(["-a_nodata", str(target_nodata)])
        else:
            # If target_nodata is None, explicitly unset NoData to not inherit default values
            # from previous steps (e.g. gdal_calc defaults) or the source file.
            preprocess_cmd.extend(["-a_nodata", "none"])

        preprocess_cmd.extend([str(current_input), str(preprocessed_file)])
        commands.append({"command": preprocess_cmd})
        current_input = preprocessed_file
        logger.info(f"Step 3: Packed preprocessing command created. Output: {current_input}")
        
        # --- Step 3b: Handle Masking (Alpha to Mask OR NoData Masking) ---
        # The 'preprocessed.tif' has data bands.
        # A mask file may need to be created and attached to it.
        
        mask_source_file = None
        
        if input_info.has_alpha and args.mask_alpha:
            # Case A: Alpha -> Mask
            if tracker:
                tracker.start("alpha_threshold")
            
            logger.info("Step 3b: Extracting and thresholding alpha band for mask...")
            thresholded_alpha_file = tfm.get_temp_path("alpha_thresholded.tif")
            
            # Use the ORIGINAL input (before preprocessing) to get the alpha band.
            # The original input might be 'rounded.tif' or 'remapped.tif' which is fine as they preserved bands.
            # But 'current_input' was just updated to 'preprocessed.tif' which DOES NOT have the alpha band!
            input_for_mask = preprocess_cmd[-2]
            
            alpha_threshold_cmd = _build_alpha_threshold_command(
                input_file=input_for_mask,
                thresholded_alpha_file=str(thresholded_alpha_file)
            )
            commands.append({"command": alpha_threshold_cmd})
            mask_source_file = thresholded_alpha_file
            
            if tracker:
                tracker.stop("alpha_threshold")
                
        elif should_mask and target_nodata is not None:
            # Case B: NoData -> Mask
            if tracker:
                tracker.start("mask_creation")
            
            logger.info(f"Step 3b: Creating mask from NoData ({target_nodata})...")
            mask_from_nodata_file = tfm.get_temp_path("mask_from_nodata.tif")
            
            # Use preprocessed file (current_input) which has the correct NoData set
            # Create mask: 0 where NoData, 255 where valid
            if isinstance(target_nodata, float) and np.isnan(target_nodata):
                mask_calc_expr = "numpy.where(numpy.isnan(A), 0, 255)"
            else:
                mask_calc_expr = f"numpy.where(A == {target_nodata}, 0, 255)"
            
            mask_cmd = [
                "gdal_calc.py",
                "--calc", mask_calc_expr,
                "-A", str(current_input),
                "--outfile", str(mask_from_nodata_file),
                "--type", "Byte",
                "--NoDataValue", "0"
            ]
            commands.append({"command": mask_cmd})
            mask_source_file = mask_from_nodata_file
            
            if tracker:
                tracker.stop("mask_creation")

        # Attach the mask if we created one
        if mask_source_file:
            if tracker:
                tracker.start("mask_attachment")
            
            logger.info(f"Step 3c: Attaching internal mask to {current_input}...")
            
            attach_script_path = tfm.get_temp_path("attach_mask.py")
            _write_mask_attachment_script(attach_script_path, str(current_input), str(mask_source_file))
            
            # Run the python script via gdal_runner
            commands.append({"command": ["python", str(attach_script_path)]})
            
            if tracker:
                tracker.stop("mask_attachment")

        if tracker:
            tracker.stop("intermediate_processing")

        # --- Step 4: Build Internal Overviews on Preprocessed File ---
        if args.overviews and not args.cog:
            if tracker:
                tracker.start("overview_creation")
            
            resample_alg = 'NEAREST' if args.product_type in [PT.IMAGE.value, PT.THEMATIC.value] else 'BILINEAR'
            
            # Build internal overviews using gdaladdo with -ro flag
            overview_cmd = [
                "gdaladdo",
                "-r", resample_alg,
                "-ro",  # Read-only mode - creates INTERNAL overviews
                "--config", "OSR_WKT_FORMAT", "WKT2_2019",
                "--config", "GTIFF_WRITE_SRS_WKT2", "YES",
                "--config", "GTIFF_SRS_SOURCE", "WKT",
                "--config", "COMPRESS_OVERVIEW", args.algorithm,
                "--config", "TILED", "YES",
                "--config", "BLOCKXSIZE", str(args.tile_size),
                "--config", "BLOCKYSIZE", str(args.tile_size),
            ]
            
            # Add algorithm-specific config options
            if args.algorithm in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value] and args.predictor:
                overview_cmd.extend(["--config", "PREDICTOR_OVERVIEW", str(args.predictor)])
            
            if args.algorithm == CA.JPEG.value:
                overview_cmd.extend(["--config", "JPEG_QUALITY_OVERVIEW", str(args.quality)])
                overview_cmd.extend(["--config", "PHOTOMETRIC_OVERVIEW", "YCBCR"])
            
            if args.algorithm == CA.JXL.value and args.quality is not None:
                jxl_options = _get_jxl_overview_options(args.quality)
                overview_cmd.extend(jxl_options)
            
            if args.algorithm == CA.LERC.value:
                overview_cmd.extend(["--config", "MAX_Z_ERROR_OVERVIEW", str(args.max_z_error)])
            
            # Add filename BEFORE overview levels (gdaladdo syntax requires this)
            overview_cmd.append(str(preprocessed_file))
            
            # Add dynamically calculated overview levels AFTER filename
            overview_levels = _calculate_overview_levels(input_info.x_size, input_info.y_size, tile_size=args.tile_size)
            overview_cmd.extend(overview_levels)
            
            logger.info(f"Using overview levels: {', '.join(overview_levels)}")
            
            commands.append({"command": overview_cmd})
            logger.info(f"Step 4: Building internal overviews on preprocessed file {preprocessed_file}")
            
            if tracker:
                tracker.stop("overview_creation")

        # --- Step 5: Final Compression (with COPY_SRC_OVERVIEWS) ---
        if tracker:
            tracker.start("final_translate")
            
        # Collect options separate from the command logic
        translate_options = ["-of", "COG" if args.cog else "GTiff"]

        # Add Area/Point with correct priority
        default_raster_type = 'Point' if args.product_type in [PT.DEM.value, PT.ERROR.value, PT.SCIENTIFIC.value] else 'Area'
        # Use user's value ONLY if it's explicitly provided and not an empty string from the toolbox.
        final_raster_type = args.raster_type if args.raster_type else default_raster_type
        translate_options.extend(["-mo", f"AREA_OR_POINT={final_raster_type}"])
        
        creation_options = [
            "GEOTIFF_VERSION=1.1",
            "BIGTIFF=IF_SAFER",
            "NUM_THREADS=ALL_CPUS",
            f"COMPRESS={args.algorithm}"
        ]
        if args.cog:
            creation_options.extend(
                [
                    f'BLOCKSIZE={args.tile_size}',
                    'OVERVIEWS=IGNORE_EXISTING' if args.overviews else 'OVERVIEWS=NONE'
                ]
            )
            if args.overviews:
                resampling = 'NEAREST' if args.product_type in [PT.IMAGE.value, PT.THEMATIC.value] else 'BILINEAR'
                creation_options.append(f'OVERVIEW_RESAMPLING={resampling}')
        else:
            creation_options.extend(
                [
                    "TILED=YES",
                    f"BLOCKXSIZE={args.tile_size}",
                    f"BLOCKYSIZE={args.tile_size}",
                    "COPY_SRC_OVERVIEWS=YES" if args.overviews else "COPY_SRC_OVERVIEWS=NO"
                ]
            )

        if args.algorithm in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value] and args.predictor:
            creation_options.append(f"PREDICTOR={args.predictor}")
        if args.algorithm == CA.JPEG.value:
            quality_flag = f"QUALITY={args.quality}" if args.cog else f"JPEG_QUALITY={args.quality}"
            creation_options.append(quality_flag)
            if not args.cog:
                creation_options.append("PHOTOMETRIC=YCBCR") # COGs use YCbCr by default, don't have PHOTOMETRIC option
        if args.algorithm == CA.JXL.value and args.quality is not None:
            jxl_options = _get_jxl_options(args.quality)
            creation_options.extend(jxl_options)
        if args.algorithm == CA.LERC.value:
            creation_options.append(f"MAX_Z_ERROR={args.max_z_error}")
        
        for co in creation_options:
            translate_options.extend(["-co", co])

        translate_options.extend(["-stats"])

        # Ensure NoData value is explicitly set on the final output
        if target_nodata is not None and not should_mask:
             if isinstance(target_nodata, float) and np.isnan(target_nodata):
                # Handle the LERC + NaN issue by substituting a safe numeric value
                if args.algorithm == CA.LERC.value and 'Float' in (input_info.data_type or 'Float32'):
                    SAFE_LERC_NODATA = -32767.0
                    logger.warning("WARNING: gdal_translate CLI cannot handle NaN NoData with LERC compression.")
                    logger.warning(f"Substituting NaN with {SAFE_LERC_NODATA} for NoData value.")
                    translate_options.extend(["-a_nodata", str(SAFE_LERC_NODATA)])
                else:
                    translate_options.extend(["-a_nodata", "nan"])
             else:
                translate_options.extend(["-a_nodata", str(target_nodata)])

        if target_srs:
            translate_options.extend(["-a_srs", target_srs.ExportToWkt(['FORMAT=WKT2_2019'])])
            
            # For custom vertical CRSs (without EPSG codes), also store the full WKT in metadata
            # This preserves datum names and axis information that GeoTIFF's GeoKey encoding loses
            if target_srs.IsCompound():
                # Check if the vertical component has an EPSG authority code
                vert_auth_name = target_srs.GetAuthorityName('COMPD_CS|VERT_CS')
                vert_auth_code = target_srs.GetAuthorityCode('COMPD_CS|VERT_CS')
                
                # Only store metadata if we don't have a valid EPSG code
                is_epsg_vertical = (vert_auth_name == 'EPSG' and vert_auth_code is not None)
                
                if not is_epsg_vertical:
                    # No EPSG code for vertical CRS - store full WKT to preserve custom datum info
                    logger.info("Custom vertical CRS detected (non-EPSG). Storing full WKT2 in metadata to preserve datum information.")
                    wkt2_full = target_srs.ExportToWkt(['FORMAT=WKT2_2019'])
                    translate_options.extend(["-mo", f"COMPOUND_CRS_WKT2={wkt2_full}"])

        # --- Add GEO_METADATA if requested ---
        xml_metadata_temp_path = None
        if args.geo_metadata:
            # Search for XML metadata file based on input path
            xml_path = find_xml_metadata_file(Path(args.input_path))
            if xml_path:
                xml_content = prepare_xml_for_gdal(xml_path)
                if xml_content:
                    # Write to temp file to avoid CLI length limits
                    xml_metadata_temp_path = tfm.get_temp_path("geo_metadata.xml")
                    with open(xml_metadata_temp_path, 'w', encoding='utf-8') as f:
                        f.write(xml_content)
                    logger.info(f"Prepared geo metadata from {xml_path.name}.")
                else:
                    logger.warning(f"Failed to prepare XML content from {xml_path}. Skipping metadata embedding.")
            else:
                logger.warning(f"XML metadata file not found for {args.input_path.name}. Skipping metadata embedding.")

        # Construct final command or script
        if xml_metadata_temp_path:
            # Use Python script to bypass CLI limits
            translate_script_path = tfm.get_temp_path("run_translate.py")
            _write_translate_script(
                translate_script_path,
                str(current_input),
                str(args.output_path),
                translate_options,
                str(xml_metadata_temp_path)
            )
            commands.append({"command": ["python", str(translate_script_path)]})
        else:
            # Use standard CLI
            final_translate_cmd = ["gdal_translate",
                                   "--config", "OSR_WKT_FORMAT", "WKT2_2019",
                                   "--config", "GTIFF_WRITE_SRS_WKT2", "YES",
                                   "--config", "GTIFF_SRS_SOURCE", "WKT"] + translate_options + [str(current_input), str(args.output_path)]
            commands.append({"command": final_translate_cmd})
            
        logger.info(f"Step 5: Final compression command created. Output: {args.output_path}")

        if tracker:
            tracker.stop("final_translate")

        # Print all commands staged in order
        logger.info(f"\nGDAL commands staged. Total commands: {len(commands)}")
        logger.info("---------------------------------------\n")
        for line in [" ".join(cmd['command']) for cmd in commands]:
            logger.info(f"> {line}\n")
        logger.info("---------------------------------------\n")

        # --- Execute all commands ---
        run_gdal_commands(commands)
        
        # --- Write external .aux.xml if requested ---
        if args.write_pam_xml:
            if tracker:
                tracker.start("pam_xml_generation")
            
            logger.info("Writing external .aux.xml file for the final dataset...")
            
            output_ds = gdal.Open(str(args.output_path), gdal.GA_ReadOnly)
            if output_ds:
                stats = calculate_statistics(output_ds)
                if stats:
                    pam_data = build_pam_data_from_stats(stats, output_ds)
                    write_pam_xml(str(args.output_path), pam_data)
                    logger.info(f"Successfully wrote .aux.xml file for {args.output_path}")
                else:
                    logger.warning("Failed to calculate statistics for .aux.xml file.")
                output_ds = None
            else:
                logger.error(f"Failed to open output file {args.output_path} for statistics calculation.")
            
            if tracker:
                tracker.stop("pam_xml_generation")
        
        if tracker:
            tracker.stop("gdal_processing")

def optimize_compression(args: OptimizeArguments, tracker: Optional[PerformanceTracker] = None):
    """Main entry point for the ArcPy script."""
    arc_mode = args.arc_mode or False
    if arc_mode:
        init_arcpy()

    input_path = str(args.input_path)
    output_path = str(args.output_path)

    if tracker:
        tracker.start("total_processing")

    if os.path.isdir(input_path):
        if not os.path.exists(output_path):
            os.makedirs(output_path)
        copy_folder_structure(input_path, output_path)
        geotiff_files = get_geotiff_files(input_path)
        for file_path in geotiff_files:
            out_file = prepare_output_path(input_path, output_path, file_path)
            args.input_path = Path(file_path)
            args.output_path = Path(out_file)
            try:
                _orchestrate_geotiff_optimization(args, tracker)
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
                
                if tracker:
                    tracker.stop("report_generation")
            except (ProcessingStepFailedError, Exception) as e:
                logger.error(f"Error processing {file_path}: {e}")
                continue
    else:
        try:
            _orchestrate_geotiff_optimization(args, tracker)
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
            
            if tracker:
                tracker.stop("report_generation")
        except RuntimeError as e:
            # This is the exception from run_gdal_commands with detailed stderr
            logger.error(f"A GDAL execution error occurred:\n{e}")
            if tracker:
                tracker.stop("total_processing")
            raise e # Re-raise the exception to be caught by the .pyt file
        except Exception as e:
            logger.error(f"AN UNEXPECTED ERROR OCCURRED: {e}")
            traceback.print_exc(file=sys.stderr)
            if tracker:
                tracker.stop("total_processing")
            # Wrap the generic exception to be caught by the .pyt file
            raise RuntimeError(f"An unexpected error occurred: {e}")
    
    if tracker:
        tracker.stop("total_processing")
    return 0