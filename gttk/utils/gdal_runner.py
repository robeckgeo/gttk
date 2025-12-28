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
Isolated GDAL Command Runner for ArcGIS Pro Compatibility.

This script acts as a bridge to execute GDAL commands in a clean, standalone
OSGeo4W environment. It is designed to be called as a subprocess from within
the ArcGIS Pro Python environment to bypass potential conflicts with Esri's
bundled GDAL libraries, ensuring consistent and optimal results. It is used by 
the `optimize-arc` command to create GeoTIFFs with the most up-to-date GDAL
capabilities and by the `gttk read` command to call gdalinfo when ArcGIS Pro's 
bundled GDAL cannot handle modern EPSG codes that require a PROJ database).
"""
import sys
import os
import json
import subprocess
import logging
import shlex
import tempfile
import tomllib
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple

# --- Configuration ---
# Add the project's root directory to the Python path to allow imports of the 'gttk' package
# THIS MUST HAPPEN BEFORE ANY gttk IMPORTS
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR.parent.parent))  # Go up to project root where gttk package is

from gttk.utils.exceptions import GdalExecutionError
from gttk.utils.log_helpers import setup_logger, shutdown_logger

# Load config to find the OSGeo4W path
CONFIG_PATH = SCRIPT_DIR.parent.parent / 'config.toml'  # Project root

# --- Global Logger Setup ---
# Initialize the logger at the module level for consistent access.
log_dir = SCRIPT_DIR.parent / 'logs'
log_dir.mkdir(exist_ok=True)
debug_log_file = log_dir / 'gdal_runner_debug.log'
logger = setup_logger(log_file=str(debug_log_file))

def get_config() -> Dict[str, Any]:
    """Loads the main configuration file (TOML format)."""
    try:
        with open(CONFIG_PATH, "rb") as f:  # tomllib needs binary mode
            return tomllib.load(f)
    except FileNotFoundError:
        logging.error(f"Configuration file not found at: {CONFIG_PATH}")
        raise
    except tomllib.TOMLDecodeError:
        logging.error(f"Error decoding TOML syntax from: {CONFIG_PATH}")
        raise

def create_isolated_env(osgeo4w_dir: Path) -> Dict[str, str]:
    """
    Creates a clean environment dictionary configured for a specific OSGeo4W installation.

    This function starts with the current environment, removes a comprehensive list of
    potentially conflicting variables (especially from ArcGIS Pro's conda env), and then sets
    the essential paths for the target OSGeo4W environment to function correctly.
    """
    # Start with a copy of the current environment
    env = os.environ.copy()
    logging.debug("--- Initial Environment (before cleaning) ---")
    for k, v in sorted(env.items()):
        logging.debug(f"{k}={v}")
    logging.debug("--------------------------------------------")

    # List of variables to remove to prevent contamination
    vars_to_remove = [
        # GDAL/PROJ conflicts
        'GDAL_CONFIG_FILE', 'GDAL_DATA', 'GDAL_DRIVER_PATH', 'PROJ_LIB', 'PROJ_DATA',
        # Python conflicts
        'PYTHONHOME', 'PYTHONPATH',
        # Conda conflicts
        'CONDA_DEFAULT_ENV', 'CONDA_EXE', 'CONDA_PREFIX', 'CONDA_PREFIX_1',
        'CONDA_PROMPT_MODIFIER', 'CONDA_PYTHON_EXE', 'CONDA_SHLVL',
        # ArcGIS/ESRI conflicts (comprehensive list)
        'ARCHOME', 'ARCHOME_USER', 'ESRIActiveAGOLBingHive', 'ESRIActiveAGOLKey',
        'ESRIActiveAGOLOAuthAppID', 'ESRIActiveAGOLOAuthAppIDLicensing',
        'ESRIActiveAGOLPortalSettingsKey', 'ESRIActiveAGOLSignInKey',
        'ESRIActiveAGOLUserAgent', 'ESRIActiveExecutable', 'ESRIActiveInstallation',
        'ESRIActiveInstallationPath', 'ESRIActiveOAuthKey', 'ESRIActiveProduct',
        'ESRIApplicationLangIdKey', 'ESRIDictionaryLangIdKey', 'ESRIOfflineHelpKey',
        'ESRIOfflineHelpLangIdKey', 'ESRIOnlineHelpLangIdKey', 'ESRIWebHelpStartPage',
        'ESRIWebHelpUrl', 'ESRI_OS_DATADIR_COMMON_DONOTUSE', 'ESRI_OS_DATADIR_LOCAL_DONOTUSE',
        'ESRI_OS_DATADIR_ROAMING_DONOTUSE', 'ESRI_OS_DIR_DONOTUSE',
        # Other potential conflicts
        'IIQ_SENSOR_PROFILES_LOCATION', 'OPENSSL_MODULES', 'SSL_CERT_DIR',
        'SSL_CERT_FILE', 'XML_CATALOG_FILES'
    ]

    for var in vars_to_remove:
        env.pop(var, None)

    # --- Configure the clean OSGeo4W environment ---
    bin_dir = osgeo4w_dir / "bin"
    python_dir = osgeo4w_dir / "apps" / "Python312" # Assuming Python 3.12, adjust if needed
    scripts_dir = python_dir / "Scripts"
    share_dir = osgeo4w_dir / "share"

    # Prepend the OSGeo4W paths to the existing PATH to ensure they are found first
    # while preserving other necessary system paths.
    existing_path = env.get('PATH', '')
    new_path_entries = [
        str(bin_dir),
        str(python_dir),
        str(scripts_dir)
    ]
    env['PATH'] = ';'.join(new_path_entries) + ';' + existing_path

    # Set GDAL-specific variables
    env['GDAL_DATA'] = str(share_dir / "gdal")
    env['PROJ_LIB'] = str(share_dir / "proj")
    env['GDAL_DRIVER_PATH'] = str(bin_dir / "gdalplugins")

    # Set Python variables for the OSGeo4W interpreter
    env['PYTHONHOME'] = str(python_dir)
    # Ensure PYTHONPATH is empty to prevent loading modules from other environments
    env['PYTHONPATH'] = ""

    # Suppress known noisy warnings from GDAL/Numpy that don't affect functionality
    # 1. RuntimeWarning: overflow/invalid value in multiply (common in gdal_calc with extreme NoData)
    # 2. FutureWarning: gdal.UseExceptions() not called (safe to ignore for CLI tools)
    env['PYTHONWARNINGS'] = (
        "ignore:overflow encountered in multiply:RuntimeWarning,"
        "ignore:invalid value encountered in multiply:RuntimeWarning,"
        "ignore:Neither gdal.UseExceptions:FutureWarning"
    )

    return env

def run_gdal_command(command: List[str], env: Dict[str, str], capture_output: bool = False) -> Optional[str]:
    """
    Executes a single GDAL command in the provided environment.
    """
    if sys.platform == 'win32':
        # Avoid launching a visible cmd window via os.system('chcp...') by setting the console code
        # page via Win32 API when possible, falling back to a hidden subprocess if needed.
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            try:
                subprocess.run(
                    ['cmd', '/c', 'chcp', '65001'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=(subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                )
            except Exception:
                # If even this fails, continue without changing code page.
                logging.debug('Unable to set console code page to 65001.')

    command_str = [str(item) for item in command]
    
    try:
        path_dirs = env.get('PATH', '').split(';')
        if not path_dirs:
            raise GdalExecutionError("PATH environment variable is not set.")
        osgeo4w_bin_dir = Path(path_dirs[0])
        executable_name = command_str[0]

        # Handle Python scripts vs. compiled executables
        if executable_name.lower().endswith('.py'):
            # For python scripts, we must provide the full path to both the interpreter and the script.
            python_executable = osgeo4w_bin_dir / "python.exe"
            
            # Search for the script in the standard OSGeo4W locations
            script_path = osgeo4w_bin_dir / executable_name
            if not script_path.is_file():
                # Fallback to the Scripts folder for tools like gdal_calc.py
                script_path = osgeo4w_bin_dir.parent / "apps" / "Python312" / "Scripts" / executable_name
                if not script_path.is_file():
                    raise FileNotFoundError(f"GDAL Python script '{executable_name}' not found in expected OSGeo4W directories.")
            
            # Rebuild the command list with full paths
            command_str = [str(python_executable), str(script_path)] + command_str[1:]
        else:
            # For .exe files, we must provide the full path to avoid ambiguity and quoting errors.
            if sys.platform == 'win32' and not executable_name.lower().endswith('.exe'):
                executable_name += '.exe'
            
            exe_full_path = osgeo4w_bin_dir / executable_name
            if not exe_full_path.is_file():
                raise FileNotFoundError(f"GDAL executable not found at: {exe_full_path}")
            
            command_str[0] = str(exe_full_path)

    except IndexError:
        raise GdalExecutionError("Could not determine OSGeo4W bin directory from PATH.")
    
    log_command = ' '.join(shlex.quote(s) for s in command_str)
    logging.info(f"Executing: {log_command}")

    logging.debug("--- Final Environment for Subprocess ---")
    for k, v in sorted(env.items()):
        logging.debug(f"{k}={v}")
    logging.debug("----------------------------------------")

    try:
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        
        result = subprocess.run(
            command_str,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8',
            env=env,
            creationflags=creation_flags
        )
        
        if capture_output:
            if result.stderr:
                logging.info(f"[Captured STDERR]:\n{result.stderr}")
            return result.stdout
        else:
            if result.stdout:
                print(result.stdout, file=sys.stdout)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return None

    except subprocess.CalledProcessError as e:
        error_message = f"Command failed with exit code {e.returncode}"
        logging.error(error_message)
        if e.stdout:
            logging.error(f"--- STDOUT ---\n{e.stdout}")
            error_message += f"\nSTDOUT: {e.stdout}"
        if e.stderr:
            logging.error(f"--- STDERR ---\n{e.stderr}")
            error_message += f"\nSTDERR: {e.stderr}"
        
        # Also print the detailed error to the runner's stderr so the parent process can capture it.
        print(f"GDAL Execution Error:\n{e.stderr}", file=sys.stderr)
        
        raise GdalExecutionError(error_message)
    except FileNotFoundError:
        logging.error(f"Command not found: {command_str[0]}. Is the OSGeo4W path in config.toml correct?")
        raise
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
        raise

def get_projection_info_from_osgeo4w(filepath: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    Get complete projection info, WKT, and PROJJSON from OSGeo4W using GDAL Python bindings.
    
    Executes _retrieve_projection_info logic directly in the clean OSGeo4W environment,
    avoiding the crippled ArcGIS Pro Python env, which lacks the `PROJ_LIB` variable.
    
    Args:
        filepath: Path to GeoTIFF file
        
    Returns:
        Tuple of (projection_info dict, wkt_string, projjson_string) or (None, None, None) if execution fails
    """
    try:
        from gttk.utils.config_loader import config
        osgeo4w_root = config.get('paths.osgeo4w')
        
        logger.info(f"OSGeo4W root from config: {osgeo4w_root}")
        
        if not osgeo4w_root:
            logger.warning("OSGeo4W path not configured in config.toml")
            return (None, None, None)
        
        osgeo4w_dir = Path(osgeo4w_root)
        if not osgeo4w_dir.is_dir():
            logger.warning(f"OSGeo4W directory does not exist: {osgeo4w_dir}")
            return (None, None, None)
        
        python_executable = osgeo4w_dir / "bin" / "python.exe"
        if not python_executable.exists():
            logger.warning(f"OSGeo4W Python executable not found at: {python_executable}")
            return (None, None, None)
        
        # Get path to gdal_runner.py (this file's sibling)
        gdal_runner_script = Path(__file__).resolve().parent / "gdal_runner.py"
        if not gdal_runner_script.exists():
            logger.warning(f"gdal_runner.py not found at: {gdal_runner_script}")
            return (None, None, None)
        
        logger.info(f"Extracting projection info for: {filepath}")
        logger.info("Using gdal_runner subprocess with Python bindings")
        
        # Create a Python script that uses GDAL bindings to extract projection info, WKT, and PROJJSON
        # Escape backslashes for the python string
        filepath_esc = str(filepath).replace('\\', '\\\\')
        
        extract_script_content = f'''
import sys
import json
from osgeo import gdal, osr

def extract_projection_info():
    """Extract projection info, WKT, and PROJJSON using same logic as _retrieve_projection_info."""
    filepath = "{filepath_esc}"
    
    ds = gdal.Open(filepath)
    if not ds:
        print(json.dumps({{"error": "Failed to open dataset"}}), file=sys.stderr)
        sys.exit(1)
    
    srs = ds.GetSpatialRef()
    if not srs:
        print(json.dumps({{"error": "No spatial reference found"}}), file=sys.stderr)
        sys.exit(1)
    
    info = {{}}
    
    # Raster type
    metadata = ds.GetMetadata()
    raster_type = metadata.get('AREA_OR_POINT', 'Area').lower()
    info['raster_type'] = 'PixelIsArea' if raster_type == 'area' else 'PixelIsPoint'
    
    # CS types
    info['is_geographic'] = bool(srs.IsGeographic())
    info['is_projected'] = bool(srs.IsProjected())
    info['is_compound'] = bool(srs.IsCompound())
    
    # Geographic CS
    if srs.IsGeographic() or srs.IsProjected():
        try:
            info['geographic_cs_name'] = srs.GetAttrValue('GEOGCS')
            info['geographic_cs_code'] = srs.GetAuthorityCode('GEOGCS')
            info['datum_name'] = srs.GetAttrValue('DATUM')
            info['datum_code'] = srs.GetAuthorityCode('DATUM')
            info['ellipsoid_name'] = srs.GetAttrValue('SPHEROID')
            info['semi_major'] = srs.GetSemiMajor()
            info['inv_flattening'] = srs.GetInvFlattening()
            info['angular_unit_name'] = srs.GetAngularUnitsName()
        except Exception:
            pass
    
    # Projected CS
    if srs.IsProjected():
        try:
            info['projected_cs_name'] = srs.GetAttrValue('PROJCS')
            info['projected_cs_code'] = srs.GetAuthorityCode('PROJCS')
            info['linear_unit_name'] = srs.GetLinearUnitsName()
        except Exception:
            pass
    
    # Compound CS
    if srs.IsCompound():
        try:
            info['compound_cs_name'] = srs.GetAttrValue('COMPD_CS')
        except Exception:
            pass
    
    # Vertical CS - extract from WKT (compound CRS)
    try:
        wkt = srs.ExportToWkt()
        if 'VERT_CS' in wkt or 'VERTCRS' in wkt:
            vert_srs = osr.SpatialReference()
            vert_srs.ImportFromWkt(wkt)
            
            vert_name = vert_srs.GetAttrValue('VERT_CS')
            if vert_name:
                info['vertical_cs_name'] = vert_name
                info['vertical_cs_code'] = vert_srs.GetAuthorityCode('VERT_CS')
            
            vert_datum = vert_srs.GetAttrValue('VERT_DATUM')
            if vert_datum:
                info['vertical_datum_name'] = vert_datum
                info['vertical_datum_code'] = vert_srs.GetAuthorityCode('VERT_DATUM')
            
            vert_unit = vert_srs.GetLinearUnitsName()
            if vert_unit:
                info['vertical_unit_name'] = vert_unit
    except Exception:
        pass
    
    # Check for 3D Geographic CRS (e.g., EPSG:4979)
    # These have ellipsoidal height as 3rd axis but no separate VERT_CS
    if info['is_geographic'] and not info.get('vertical_unit_name'):
        try:
            axis_count = srs.GetAxesCount()
            if axis_count == 3:
                # Check if 3rd axis is vertical/height
                axis_name = srs.GetAxisName(None, 2)
                if axis_name and ('height' in axis_name.lower() or 'ellipsoid' in axis_name.lower()):
                    # Get unit from 3rd axis
                    axis_unit_name = srs.GetAxisName(None, 2)
                    axis_unit_val = srs.GetAxisOrientation(None, 2)
                    # Get the linear unit for the 3rd axis
                    linear_unit = srs.GetLinearUnitsName()
                    if linear_unit:
                        info['vertical_unit_name'] = linear_unit
        except Exception:
            pass
    
    # Export WKT for use in ArcGIS environment
    wkt_string = ""
    try:
        wkt_string = srs.ExportToWkt(['FORMAT=WKT2_2019', 'MULTILINE=YES'])
    except Exception:
        pass
    
    # Export PROJJSON for use in ArcGIS environment
    # This ensures consistent format with full member IDs when PROJ database is available
    projjson_string = ""
    try:
        projjson_string = srs.ExportToPROJJSON()
    except Exception:
        pass
    
    # Output projection_info, WKT, and PROJJSON as JSON
    result = {{
        "projection_info": info,
        "wkt_string": wkt_string,
        "projjson_string": projjson_string
    }}
    print(json.dumps(result))
    ds = None

if __name__ == "__main__":
    extract_projection_info()
'''
        
        # Write extraction script to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as tmp_script:
            temp_script_path = tmp_script.name
            tmp_script.write(extract_script_content)
        
        try:
            # Build command to run the Python script via gdal_runner
            python_command = {
                "command": ["python", temp_script_path],
                "capture_output": True
            }
            
            payload = json.dumps({"commands": [python_command]})
            
            # Create isolated environment
            logger.info("Creating isolated OSGeo4W environment...")
            isolated_env = create_isolated_env(osgeo4w_dir)
            
            # Log critical environment variables for debugging
            logger.info(f"PROJ_LIB: {isolated_env.get('PROJ_LIB', 'NOT SET')}")
            logger.info(f"GDAL_DATA: {isolated_env.get('GDAL_DATA', 'NOT SET')}")
            
            # Launch gdal_runner.py as subprocess
            command = [str(python_executable), str(gdal_runner_script)]
            
            logger.info(f"Executing: {' '.join(command)}")
            
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
            
            stdout, stderr = process.communicate(input=payload, timeout=30)
            
            logger.info(f"gdal_runner return code: {process.returncode}")
            
            if stderr:
                logger.info(f"gdal_runner stderr: {stderr[:500]}")
            
            if process.returncode != 0:
                logger.warning(f"gdal_runner failed with exit code {process.returncode}")
                return (None, None, None)
            
            # Parse captured output
            if not stdout:
                logger.warning("WARNING: gdal_runner returned empty stdout")
                return (None, None, None)
            
            logger.info("Parsing gdal_runner output...")
            
            # The runner returns JSON lines, one per captured command
            for line in stdout.strip().split('\n'):
                try:
                    captured_data = json.loads(line)
                    if isinstance(captured_data, dict) and "stdout" in captured_data:
                        if captured_data['stdout']:
                            # Parse the result JSON from the captured stdout
                            result = json.loads(captured_data["stdout"])
                            projection_info = result.get("projection_info")
                            wkt_string = result.get("wkt_string", "")
                            projjson_string = result.get("projjson_string", "")
                            logger.info(f"Successfully extracted projection_info: {projection_info}")
                            logger.info(f"WKT string length: {len(wkt_string)} chars")
                            logger.info(f"PROJJSON string length: {len(projjson_string)} chars")
                            return (projection_info, wkt_string, projjson_string)
                except json.JSONDecodeError:
                    continue
            
            logger.warning("No captured projection_info found in gdal_runner stdout")
            return (None, None, None)
        
        finally:
            # Clean up temp script
            try:
                Path(temp_script_path).unlink(missing_ok=True)
            except Exception:
                pass
                
    except Exception as e:
        logger.warning(f"Error extracting projection info via OSGeo4W: {e}")
        import traceback
        logger.warning(traceback.format_exc())
        return (None, None, None)

def main():
    """Main entry point for the gdal_runner script."""
    try:
        config = get_config()
        osgeo4w_path_str = config.get('paths', {}).get('osgeo4w')
        if not osgeo4w_path_str:
            raise ValueError("'osgeo4w' not found or is empty in config.toml under [paths] section.")

        osgeo4w_dir = Path(osgeo4w_path_str)
        if not osgeo4w_dir.is_dir():
            raise FileNotFoundError(f"The specified OSGeo4W path does not exist: {osgeo4w_dir}")

        # Create the isolated environment
        isolated_env = create_isolated_env(osgeo4w_dir)

        # Read commands from stdin
        payload_json = sys.stdin.read()
        if not payload_json:
            raise ValueError("No JSON payload received from stdin.")

        payload = json.loads(payload_json)
        commands = payload.get("commands", [])

        if not isinstance(commands, list):
            raise ValueError("JSON payload must contain a 'commands' list.")

        logger.info(f"Received {len(commands)} command(s) to execute.")

        for i, cmd_info in enumerate(commands):
            if not isinstance(cmd_info, dict) or "command" not in cmd_info:
                logger.warning(f"Skipping invalid command entry at index {i}: {cmd_info}")
                continue

            cmd_args = cmd_info["command"]
            capture = cmd_info.get("capture_output", False)

            if not cmd_args or not isinstance(cmd_args, list):
                logger.warning(f"Skipping invalid command args at index {i}: {cmd_args}")
                continue
            
            captured_stdout = run_gdal_command(cmd_args, env=isolated_env, capture_output=capture)

            if captured_stdout:
                # Wrap the captured output in a structured way for the parent process
                output_payload = {
                    "command_index": i,
                    "stdout": captured_stdout
                }
                # Print the JSON payload to the actual stdout for the parent to read
                print(json.dumps(output_payload), file=sys.stdout)


        logger.info("All commands executed successfully.")

    except (json.JSONDecodeError, ValueError, GdalExecutionError, FileNotFoundError) as e:
        msg = f"Fatal error: {e}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        msg = f"An unexpected critical error occurred: {e}"
        logger.error(msg)
        print(msg, file=sys.stderr)
        sys.exit(1)
    finally:
        # --- CRITICAL ---
        # Ensure the logger is shut down to release the lock on the log file.
        shutdown_logger(logger)

if __name__ == "__main__":
    main()