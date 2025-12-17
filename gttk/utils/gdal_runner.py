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
bundled GDAL libraries, ensuring consistent and optimal results.
"""
import sys
import os
import json
import subprocess
import logging
import shlex
import tomllib
from pathlib import Path
from typing import List, Dict, Optional, Any

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
        os.system('chcp 65001 > nul')

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