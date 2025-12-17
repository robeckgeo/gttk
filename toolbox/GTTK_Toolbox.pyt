#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2025, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
GeoTIFF ToolKit (GTTK): GeoTIFF Analysis and Optimization Suite.

This toolbox provides a suite of tools for analyzing, optimizing, and compressing
GeoTIFF files. It includes tools to:

1.  Compare Compression: Generate side-by-side comparison reports to evaluate
    the impact of compression settings on file size and quality.
2.  Optimize Compression: Compress and optimize GeoTIFFs into Cloud-Optimized
    GeoTIFFs (COGs) with intelligent, data-aware defaults for various product
    types (DEM, Imagery, Scientific, Thematic, and Error Models).
3.  Read Metadata: Extract and report detailed technical metadata, including
    TIFF tags, GeoKeys, and CRS information.
4.  Test Compression: Benchmark multiple compression algorithms and settings
    to find the optimal configuration for your data.

All tools are designed to handle complex geospatial challenges, such as vertical
datum transformations and compound coordinate systems, while maximizing performance
through in-memory processing.
"""
import arcpy # type: ignore
import numpy as np
import os
import sys
from pathlib import Path

# Add the project root to sys.path to ensure we import the local 'gttk' package.
# We use insert(0, ...) to prioritize this local version over any potentially installed
# version of gttk in the Python environment, ensuring the toolbox uses its own code.
script_path = Path(__file__).resolve()
gttk_path = script_path.parent.parent
if str(gttk_path) not in sys.path:
    sys.path.insert(0, str(gttk_path))

try:
    import gttk.tools.compare_compression as cc
    import gttk.tools.optimize_compression_arc as oc
    import gttk.tools.read_metadata as rm
    import gttk.tools.test_compression as tc
    from gttk.utils.srs_logic import VERTICAL_SRS_NAME_MAP
    from gttk.utils.section_registry import ALL_SECTIONS, PRODUCER_SECTIONS, ANALYST_SECTIONS, get_config
    import gttk.utils.optimize_constants as C
    from gttk.utils.optimize_constants import CompressionAlgorithm as CA, ProductType as PT
    from gttk.utils.script_arguments import OptimizeArguments, CompareArguments, TestArguments, ReadArguments
except ImportError as e:
    arcpy.AddError(f"Failed to import a required module. Ensure the tool scripts are in the correct directory: {gttk_path}")
    arcpy.AddError(f"System Path: {sys.path}")
    raise e

def _get_report_path(input_path: str, suffix: str, format: str) -> str:
    """
    Determine output file path for report.
    
    Args:
        input_path: Path to input GeoTIFF file
        suffix: Suffix to add to filename (e.g., '_meta')
        format: Output format ('html' or 'markdown')
        
    Returns:
        Full path to output report file
    """
    input_file = Path(input_path)
    extension = '.html' if format == 'html' else '.md'
    report_filename = f"{input_file.stem}{suffix}{extension}"
    return str(input_file.parent / report_filename)


class Toolbox:
    def __init__(self):
        """Define the toolbox (the name of the toolbox is the name of the .pyt file)."""
        self.label = "GTTK Toolbox"
        self.alias = "gttk"
        self.icon = "icons/GTTK_Toolbox.pyt.32px.png"
        # List of tool classes associated with this toolbox
        self.tools = [OptimizeCompression, ReadMetadata, CompareCompression, TestCompression]

class CompareCompression:
    def __init__(self):
        """Define the tool class."""
        self.label = "Compare Compression"
        self.description = "Compares two GeoTIFFs and generates a detailed compression report."
        self.icon = "icons/compare.png"
        self.canRunInBackground = True

    def getParameterInfo(self):
        """Define parameter definitions"""
        param_baseline = arcpy.Parameter(
            displayName="Baseline or Input GeoTIFF 1 (e.g., Original)",
            name="baseline_path",
            datatype=["DEFile", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        param_comparison = arcpy.Parameter(
            displayName="Comparison or Output GeoTIFF 2 (e.g., Processed)",
            name="comparison_path",
            datatype=["DEFile", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        param_report_format = arcpy.Parameter(
            displayName="Report File Format",
            name="report_format",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_report_format.filter.type = "ValueList"
        param_report_format.filter.list = ["HTML (.html)", "Markdown (.md)"]
        param_report_format.value = "HTML (.html)"

        param_report_suffix = arcpy.Parameter(
            displayName="Report Filename Suffix",
            name="report_suffix",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_report_suffix.value = "_comp"

        param_report_file = arcpy.Parameter(
            displayName="Report File Path",
            name="report_file",
            datatype="DEFile",
            parameterType="Derived",
            direction="Output")
        # Derived outputs do not support filters. The file extension is handled
        # in the updateParameters method.

        param_open_report = arcpy.Parameter(
            displayName="Open Report on Completion",
            name="open_report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_open_report.value = True

        return [
            param_baseline,
            param_comparison,
            param_report_format,
            param_report_suffix,
            param_report_file,
            param_open_report
        ]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        comp_param = parameters[1].value
        if comp_param and parameters[2].value:
            if hasattr(comp_param, 'dataSource'):
                comp_path_str = comp_param.dataSource
            else:
                comp_path_str = parameters[1].valueAsText

            if not comp_path_str:
                return

            comp_path = Path(comp_path_str)
            report_format_display = parameters[2].valueAsText
            suffix = parameters[3].valueAsText or ""
            
            extension = ".html" if "HTML (.html)" in report_format_display else ".md"
            
            default_report_path = comp_path.with_name(f"{comp_path.stem}{suffix}{extension}")
            parameters[4].value = str(default_report_path)

    def updateMessages(self, parameters):
        return

    def execute(self, parameters, messages):
        baseline_param = parameters[0].value
        if hasattr(baseline_param, 'dataSource'):
            baseline_path = baseline_param.dataSource
        else:
            baseline_path = parameters[0].valueAsText

        comparison_param = parameters[1].value
        if hasattr(comparison_param, 'dataSource'):
            comparison_path = comparison_param.dataSource
        else:
            comparison_path = parameters[1].valueAsText

        report_format_display = parameters[2].valueAsText
        report_format = "html" if "HTML (.html)" in report_format_display else "md"
        report_suffix = parameters[3].valueAsText
        open_report = parameters[5].value

        args = CompareArguments(
            input_path=Path(baseline_path),
            output_path=Path(comparison_path),
            report_suffix=report_suffix,
            report_format=report_format,
            open_report=open_report,
            arc_mode=True
        )

        try:
            report_path = cc.compare_compression(args)
            if not report_path:
                raise Exception("The compare_compression script failed to generate a report. See messages above for details.")

            # Set derived output parameter for ModelBuilder
            parameters[4].value = str(report_path)

            messages.addMessage(f"Report generated successfully: {report_path}")
            if open_report:
                try:
                    os.startfile(report_path)
                    messages.addMessage(f"Opening report: {report_path}")
                except Exception as e:
                    messages.addWarningMessage(f"Could not automatically open the report: {e}")

        except Exception as e:
            messages.addErrorMessage(f"An error occurred: {e}")
            import traceback
            messages.addErrorMessage(traceback.format_exc())

class OptimizeCompression:
    _previous_product_type = None
    _previous_algorithm = None
    _previous_raster_type = None

    def __init__(self):
        """Define the tool class."""
        self.label = "Optimize Compression"
        self.description = "Optimizes and compresses a GeoTIFF into a Cloud Optimized GeoTIFF (COG) with advanced options."
        self.icon = "icons/optimize.png"
        self.canRunInBackground = False
        
        self.PRODUCT_TYPE_MAP = {
            "Digital Elevation Model": PT.DEM.value,
            "Generic Point-cloud Model": PT.ERROR.value,
            "Orthoimage or Basemap": PT.IMAGE.value,
            "Thematic Data (e.g. Landcover)": PT.THEMATIC.value,
            "Scientific Data (e.g. Chemistry)": PT.SCIENTIFIC.value
        }

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        # --- Input and Output ---
        param_input = arcpy.Parameter(
            displayName="Input GeoTIFF, Raster Layer, or Folder",
            name="input_path",
            datatype=["GPRasterLayer", "DEFile", "DEFolder"],
            parameterType="Required",
            direction="Input")

        param_output = arcpy.Parameter(
            displayName="Output GeoTIFF or Folder",
            name="output_path",
            datatype=["DEFile", "DEFolder"],
            parameterType="Required",
            direction="Output")

        # --- Core Settings ---
        param_product_type = arcpy.Parameter(
            displayName="Data Type",
            name="product_type",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_product_type.filter.type = "ValueList"
        param_product_type.filter.list = list(self.PRODUCT_TYPE_MAP.keys())
        param_product_type.value = "Digital Elevation Model"

        param_raster_type = arcpy.Parameter(
            displayName="Raster Type",
            name="raster_type",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_raster_type.filter.type = "ValueList"
        param_raster_type.filter.list = ["PixelIsArea", "PixelIsPoint"]
        param_raster_type.value = "PixelIsPoint" # Default for DEM

        param_vertical_srs = arcpy.Parameter(
            displayName="Vertical SRS Name",
            name="vertical_srs",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_vertical_srs.filter.type = "ValueList"
        param_vertical_srs.filter.list = list(VERTICAL_SRS_NAME_MAP.keys())
        
        param_nodata = arcpy.Parameter(
            displayName="NoData Value",
            name="nodata",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")

        # --- Compression Settings ---
        param_algorithm = arcpy.Parameter(
            displayName="Compression Algorithm",
            name="algorithm",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_algorithm.filter.type = "ValueList"
        param_algorithm.filter.list = [
            CA.JPEG.value,
            CA.JXL.value,
            CA.LZW.value,
            CA.DEFLATE.value,
            CA.ZSTD.value,
            CA.LERC.value,
            CA.NONE.value
        ]
        # Set default algorithm based on default data type (DEM)
        param_algorithm.value = CA.DEFLATE.value

        param_quality = arcpy.Parameter(
            displayName="JPEG Quality",
            name="quality",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param_quality.filter.type = "Range"
        param_quality.filter.list = [75, 100]
        param_quality.value = C.DEFAULT_QUALITY

        param_predictor = arcpy.Parameter(
            displayName="Predictor",
            name="predictor",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_predictor.filter.type = "ValueList"
        param_predictor.filter.list = [
            "1 - None",
            "2 - Horizontal differencing",
            "3 - Floating-point"
        ]
        # Set default predictor for DEM type
        param_predictor.value = "2 - Horizontal differencing"

        param_level = arcpy.Parameter(
            displayName="Compression Level",
            name="level",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param_level.value = 6  # DEFLATE default

        # --- LERC Settings ---
        param_max_z_error = arcpy.Parameter(
            displayName="Max Z Error (LERC)",
            name="max_z_error",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input")
        # Set default for DEM type
        param_max_z_error.value = C.DEFAULT_DEM_MAX_Z_ERROR

        # --- Rounding Settings ---
        param_decimals = arcpy.Parameter(
            displayName="Decimal Places for Rounding",
            name="decimals",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        # Set default for DEM type
        param_decimals.value = C.DEFAULT_DEM_DECIMALS

       # --- Block or Tile Size ---
        param_tile_size = arcpy.Parameter(
            displayName="Tile Size (in pixels)",
            name="tile_size",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param_tile_size.value = C.DEFAULT_TILE_SIZE

        # --- GEO_METADATA Tag ---
        param_geo_metadata = arcpy.Parameter(
            displayName="Write External XML to GEO_METADATA Tag",
            name="geo_metadata",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_geo_metadata.value = False

        # --- Precision Auxiliary Metadata (.aux.xml) ---
        param_write_pam_xml = arcpy.Parameter(
            displayName="Write Statistics XML (.aux.xml)",
            name="write_pam_xml",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_write_pam_xml.value = False

        # --- COG vs. GTiff Driver ---
        param_cog = arcpy.Parameter(
            displayName="Create Cloud Optimized GeoTIFF",
            name="cog",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_cog.value = True

        param_overviews = arcpy.Parameter(
            displayName="Generate Internal Overviews",
            name="overviews",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_overviews.value = True

        param_mask_nodata = arcpy.Parameter(
            displayName="Mask NoData Pixels (if any)",
            name="mask_nodata",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_mask_nodata.value = False

        param_mask_alpha = arcpy.Parameter(
            displayName="Convert Alpha Band (if one exists) to Internal Mask",
            name="mask_alpha",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_mask_alpha.value = True

        param_add_to_map = arcpy.Parameter(
            displayName="Add Output to Map",
            name="add_to_map",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_add_to_map.value = True

        # --- Report Settings ---
        param_report_format = arcpy.Parameter(
            displayName="CompressionReport Format",
            name="report_format",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_report_format.filter.type = "ValueList"
        param_report_format.filter.list = ["HTML (.html)", "Markdown (.md)"]
        param_report_format.value = "HTML (.html)"

        param_report_suffix = arcpy.Parameter(
            displayName="Report Filename Suffix",
            name="report_suffix",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_report_suffix.value = "_comp"

        param_open_report = arcpy.Parameter(
            displayName="Open Report on Completion",
            name="open_report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_open_report.value = True


        params = [
            param_input, param_output, param_product_type, param_raster_type,
            param_vertical_srs, param_nodata, param_algorithm, param_quality,
            param_predictor, param_level, param_max_z_error, param_decimals,
            param_tile_size, param_geo_metadata, param_write_pam_xml, param_cog,
            param_overviews, param_mask_nodata, param_mask_alpha, param_add_to_map,
            param_report_format, param_report_suffix, param_open_report
        ]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to run."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed. This method is called whenever a parameter
        has been changed."""

        if not parameters[2].value:
            return

        product_type = parameters[2].valueAsText
        selected_type_key = self.PRODUCT_TYPE_MAP.get(product_type)
        algorithm = parameters[6].valueAsText

        # --- Set valid algorithms based on data type ---
        if selected_type_key == PT.IMAGE.value:
            valid_algorithms = [
                CA.JPEG.value,
                CA.JXL.value,
                CA.LZW.value,
                CA.DEFLATE.value,
                CA.ZSTD.value,
                CA.NONE.value
            ]
        elif selected_type_key == PT.THEMATIC.value:
            valid_algorithms = [
                CA.LZW.value,
                CA.DEFLATE.value,
                CA.ZSTD.value,
                CA.NONE.value
            ]
        else:
            valid_algorithms = [
                CA.LZW.value,
                CA.DEFLATE.value,
                CA.ZSTD.value,
                CA.LERC.value,
                CA.NONE.value
            ]
        parameters[6].filter.list = valid_algorithms

        # --- State Change Detection using persistent class-level variables ---
        type_changed = (OptimizeCompression._previous_product_type is not None and
                        product_type != OptimizeCompression._previous_product_type)
        
        algo_changed = (OptimizeCompression._previous_algorithm is not None and
                        algorithm != OptimizeCompression._previous_algorithm)

        # --- Handle State Changes ---
        # On first run, or if the data type changed, reset everything for the new type.
        if type_changed or OptimizeCompression._previous_product_type is None:
            # Set default algorithm for the new type
            if selected_type_key == PT.IMAGE.value:
                parameters[6].value = CA.JPEG.value
            else: 
                parameters[6].value = CA.DEFLATE.value
            
            # After setting the new algorithm, get its value for the next step
            new_algorithm = parameters[6].valueAsText
            
            # Reset all dependent parameters
            self._reset_all_dependents(parameters, selected_type_key, new_algorithm)
            
            # Update class-level state
            OptimizeCompression._previous_product_type = product_type
            OptimizeCompression._previous_algorithm = new_algorithm
            OptimizeCompression._previous_raster_type = parameters[3].valueAsText

        # If ONLY the algorithm changed, reset only algorithm-dependent things.
        elif algo_changed:
            self._reset_algorithm_dependents(parameters, algorithm)
            OptimizeCompression._previous_algorithm = algorithm

        # --- Update UI states (enabled/disabled) every time ---
        self._update_parameter_states(parameters, selected_type_key, parameters[6].valueAsText)

        return

    def _reset_all_dependents(self, parameters, selected_type_key, algorithm):
        """Resets all parameters that depend on data type or algorithm."""
        # Reset Raster Type
        if selected_type_key in [PT.DEM.value, PT.ERROR.value, PT.SCIENTIFIC.value]:
            parameters[3].value = "PixelIsPoint"
        else:
            parameters[3].value = "PixelIsArea"

        # Reset JPEG quality
        parameters[7].value = C.DEFAULT_QUALITY
        
        # Reset predictor
        if selected_type_key == PT.SCIENTIFIC.value:
            parameters[8].value = "3 - Floating-point"
        else:
            parameters[8].value = "2 - Horizontal differencing"

        # Reset masking options
        if selected_type_key == PT.IMAGE.value:
            parameters[17].value = True  # Mask NoData defaults to True for imagery
            parameters[18].value = True  # Mask Alpha defaults to True for imagery
        else:
            parameters[17].value = False
            parameters[18].value = True
            
        # Reset LERC and rounding decimal precision by type
        if selected_type_key == PT.DEM.value:
            parameters[10].value = C.DEFAULT_DEM_MAX_Z_ERROR
            parameters[11].value = C.DEFAULT_DEM_DECIMALS
        elif selected_type_key == PT.ERROR.value:
            parameters[10].value = C.DEFAULT_ERROR_MAX_Z_ERROR
            parameters[11].value = C.DEFAULT_ERROR_DECIMALS
        elif selected_type_key == PT.SCIENTIFIC.value:
            parameters[10].value = C.DEFAULT_SCIENTIFIC_MAX_Z_ERROR
            parameters[11].value = C.DEFAULT_SCIENTIFIC_DECIMALS
        else:
            parameters[10].value = None
            parameters[11].value = None

        # Reset algorithm-specific parameters
        self._reset_algorithm_dependents(parameters, algorithm)

    def _reset_algorithm_dependents(self, parameters, algorithm):
        """Resets parameters that depend only on the algorithm."""
        if algorithm == CA.DEFLATE.value:
            parameters[9].value = 6
        elif algorithm == CA.ZSTD.value:
            parameters[9].value = 9
        else:
            parameters[9].value = None
            
    def _update_parameter_states(self, parameters, selected_type_key, algorithm):
        """Update the enabled/disabled state of parameters based on current selections."""
        is_dem = (selected_type_key == PT.DEM.value)
        is_error = (selected_type_key == PT.ERROR.value)
        is_scientific = (selected_type_key == PT.SCIENTIFIC.value)
        has_nodata = (selected_type_key != PT.IMAGE.value)
        is_lerc = (algorithm == CA.LERC.value)

        parameters[3].enabled = True
        parameters[4].parameterType = "Required" if is_dem else "Optional"
        parameters[4].enabled = is_dem
        parameters[5].enabled = has_nodata
        parameters[7].enabled = (algorithm in [CA.JPEG.value, CA.JXL.value])
        parameters[8].enabled = algorithm in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value]
        parameters[9].enabled = algorithm in [CA.DEFLATE.value, CA.ZSTD.value]
        parameters[10].enabled = is_lerc
        parameters[11].enabled = (is_dem or is_error or is_scientific) and not is_lerc

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        # --- Gather Parameters ---
        input_param = parameters[0].value
        if hasattr(input_param, 'dataSource'):
            input_path = input_param.dataSource
        else:
            input_path = parameters[0].valueAsText
        output_path = parameters[1].valueAsText
        product_type_desc = parameters[2].valueAsText
        product_type = self.PRODUCT_TYPE_MAP.get(product_type_desc, PT.DEM.value)
        raster_type_desc = parameters[3].valueAsText
        raster_type = 'point' if raster_type_desc == 'PixelIsPoint' else 'area'
        vertical_srs_name = parameters[4].valueAsText

        # Handle NoData safely
        nodata_str = parameters[5].valueAsText
        if nodata_str and nodata_str.lower() == 'nan':
            nodata = np.nan
        elif nodata_str:
            try:
                nodata = float(nodata_str)
            except ValueError:
                messages.addErrorMessage(f"Invalid NoData value provided: {nodata_str}")
                return
        else:
            nodata = None

        algorithm = parameters[6].valueAsText
        quality = parameters[7].value
        predictor_str = parameters[8].valueAsText
        predictor = int(predictor_str[0:1]) if predictor_str else None
        level = parameters[9].value
        max_z_error = parameters[10].value
        decimals = parameters[11].value
        tile_size = parameters[12].value
        geo_metadata = parameters[13].value
        write_pam_xml = parameters[14].value
        cog = parameters[15].value
        overviews = parameters[16].value
        mask_nodata = parameters[17].value
        mask_alpha = parameters[18].value
        add_to_map = parameters[19].value
        report_format_desc = parameters[20].valueAsText
        report_format = "html" if "HTML" in report_format_desc else "md"
        report_suffix = parameters[21].valueAsText
        open_report = parameters[22].value

        # --- Validate JPEG + RGBA + mask_alpha=False (unsupported) ---
        # If the input has an alpha band and JPEG is selected while the user disabled mask_alpha,
        # fail fast with a clear, actionable message.
        if product_type == PT.DEM.value and not vertical_srs_name:
            messages.addErrorMessage("Vertical SRS is required for Digital Elevation Models.")
            return

        # --- Lightweight check for single-band restriction ---
        if product_type in [PT.DEM.value, PT.ERROR.value, PT.THEMATIC.value]:
            try:
                # Use arcpy to check band count efficiently
                desc = arcpy.Describe(input_path)
                if hasattr(desc, 'bandCount') and desc.bandCount > 1:
                    messages.addErrorMessage(
                        f"Multi-band rasters ({desc.bandCount} bands) are not supported for '{product_type_desc}' product type. "
                        "Use 'Orthoimage or Basemap' or 'Scientific Data' instead."
                    )
                    return
            except Exception as e:
                # If arcpy.Describe fails, we log a warning but proceed, letting the backend validation handle it.
                messages.addWarningMessage(f"Could not validate band count: {e}")

        if algorithm == CA.JPEG.value and (mask_alpha is False):
            # A simplified check. The robust check is in the backend.
            messages.addWarningMessage(
                "If the input has an alpha band, using JPEG compression without converting it "
                "to an internal mask may cause issues. The backend process will validate this."
            )
            messages.addErrorMessage(
                "JPEG compression does not support a preserved alpha band. Re-enable "
                "'Convert Alpha Band (if one exists) to Internal Mask' to convert the alpha "
                "to an internal mask, or choose a different algorithm such as JXL or DEFLATE."
            )
            return

        # --- Conditionally Nullify Parameters invalid for selected algorithm ---
        if not product_type == PT.DEM.value:
            vertical_srs = None

        if product_type in [PT.IMAGE.value, PT.THEMATIC.value]:
            decimals = None
        
        if product_type == PT.IMAGE.value:
            nodata = None
        
        if algorithm == CA.LERC.value:
            decimals = None
        else:
            max_z_error = None
        
        if algorithm not in [CA.JPEG.value, CA.JXL.value]:
            quality = None
            
        if algorithm not in [CA.LZW.value, CA.DEFLATE.value, CA.ZSTD.value]:
            predictor = None
            
        if algorithm not in [CA.DEFLATE.value, CA.ZSTD.value]:
            level = None

        # --- Build Argument Dictionary for optimize_compression_arc.main ---
        # Note: optimize_compression_arc.py handles None for optional args
        args = OptimizeArguments(
            input_path=Path(input_path),
            output_path=Path(output_path),
            product_type=product_type,
            raster_type=raster_type,
            vertical_srs=vertical_srs_name,
            nodata=nodata if nodata != '' else None,
            algorithm=algorithm,
            quality=quality,
            predictor=predictor,
            level=level,
            max_z_error=max_z_error,
            decimals=decimals,
            geo_metadata=geo_metadata,
            write_pam_xml=write_pam_xml,
            tile_size=tile_size,
            mask_alpha=mask_alpha,
            mask_nodata=mask_nodata,
            cog=cog,
            overviews=overviews,
            report_format=report_format,
            report_suffix=report_suffix,
            open_report=open_report,
            arc_mode=True,
        )

        # --- Run the optimize_compression script ---
        try:
            # The script now raises an exception on failure, so we don't need to check status_code
            oc.optimize_compression(args)
            messages.addMessage("Tool completed successfully.")

            # --- Handle Report Opening ---
            report_path = _get_report_path(output_path, report_suffix, report_format)
            
            if open_report:
                try:
                    os.startfile(report_path)
                    messages.addMessage(f"Opening report: {report_path}")
                except Exception as e:
                    messages.addWarningMessage(f"Could not automatically open the report: {e}")

            if add_to_map:
                try:
                    # Add the output raster to the current map
                    aprx = arcpy.mp.ArcGISProject("CURRENT")
                    map_view = aprx.activeMap
                    if map_view:
                        map_view.addDataFromPath(output_path)
                        messages.addMessage(f"Added {os.path.basename(output_path)} to the map.")
                    else:
                        messages.addWarningMessage("No active map found to add the output raster.")
                except Exception as e:
                    messages.addWarningMessage(f"Could not add the output raster to the map: {e}")

        except RuntimeError as e:
            # This will catch the detailed error message propagated from the runner
            messages.addErrorMessage(str(e))
        except Exception as e:
            messages.addErrorMessage(f"An unexpected error occurred in the toolbox script: {e}")
            import traceback
            messages.addErrorMessage("Traceback:")
            messages.addErrorMessage(traceback.format_exc())

class TestCompression:
    _previous_source = None

    def __init__(self):
        """Define the tool class."""
        self.label = "Test Compression"
        self.description = "Tests multiple compression settings from CSV configurations and generates detailed Excel reports comparing performance and efficiency."
        self.icon = "icons/test.png"
        self.canRunInBackground = True
        
        self.PRODUCT_TYPE_MAP = {
            "Digital Elevation Model": PT.DEM.value,
            "Error Model": PT.ERROR.value,
            "Orthoimage or Basemap": PT.IMAGE.value,
            "Thematic Data (e.g. Landcover)": PT.THEMATIC.value,
            "Scientific Data (e.g. Chemistry)": PT.SCIENTIFIC.value
        }

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        # --- Input and Output ---
        param_source = arcpy.Parameter(
            displayName="Source GeoTIFF, Raster Layer, or Folder",
            name="source_geotiff",
            datatype=["GPRasterLayer", "DEFile", "DEFolder"],
            parameterType="Required",
            direction="Input")

        param_output = arcpy.Parameter(
            displayName="Output Excel Report",
            name="output_file",
            datatype="DEFile",
            parameterType="Required",
            direction="Output")
        param_output.filter.list = ["xlsx"]

        # --- Input Method (CSV or Data Type) ---
        param_input_method = arcpy.Parameter(
            displayName="Input Method",
            name="input_method",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_input_method.filter.type = "ValueList"
        param_input_method.filter.list = ["Use Data Type Presets", "Use Custom CSV File"]
        param_input_method.value = "Use Data Type Presets"

        param_product_type = arcpy.Parameter(
            displayName="Product Type (for Preset Selection)",
            name="product_type",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_product_type.filter.type = "ValueList"
        param_product_type.filter.list = list(self.PRODUCT_TYPE_MAP.keys())
        param_product_type.value = "Digital Elevation Model"

        param_csv_path = arcpy.Parameter(
            displayName="Custom CSV Configuration File",
            name="csv_path",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input")
        param_csv_path.filter.list = ["csv"]

        # --- Processing Options ---
        param_temp_dir = arcpy.Parameter(
            displayName="Temporary Files Directory",
            name="temp_dir",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input")
        project_root = Path(__file__).parent.parent
        default_temp_path = project_root / "temp"
        param_temp_dir.value = str(default_temp_path)

        param_delete_test_files = arcpy.Parameter(
            displayName="Delete Temporary Test Files",
            name="delete_test_files",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_delete_test_files.value = False

        # --- Report Options ---
        param_open_report = arcpy.Parameter(
            displayName="Open Excel Report on Completion",
            name="open_report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_open_report.value = True

        params = [
            param_source, param_output, param_input_method, param_product_type,
            param_csv_path, param_temp_dir, param_delete_test_files, param_open_report
        ]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to run."""
        return True

    def updateParameters(self, parameters):
        """Modify parameter states based on input method selection."""
        input_method = parameters[2].valueAsText
        
        if input_method == "Use Data Type Presets":
            parameters[3].enabled = True
            parameters[3].parameterType = "Required"
            parameters[4].enabled = False
            parameters[4].parameterType = "Optional"
            parameters[4].value = None
        elif input_method == "Use Custom CSV File":
            parameters[3].enabled = False
            parameters[3].parameterType = "Optional"
            parameters[4].enabled = True
            parameters[4].parameterType = "Required"
        
        # --- Handle Output Path Updates on Source Change ---
        source_param = parameters[0].value
        if hasattr(source_param, 'dataSource'):
            source = source_param.dataSource
        else:
            source = parameters[0].valueAsText
            
        # Detect if source has changed
        if source != TestCompression._previous_source:
            TestCompression._previous_source = source
            
            # If source is now empty or invalid, clear output
            if not source:
                parameters[1].value = None
            else:
                # If source is valid, generate new output path (always overwrites old value)
                try:
                    input_path = Path(source)
                    # Ensurepath structure is valid before manipulating
                    if input_path.stem:
                        default_output_path = input_path.with_name(f"{input_path.stem}_test.xlsx")
                        parameters[1].value = str(default_output_path)
                except Exception:
                     # If path parsing fails, just clear output
                    parameters[1].value = None

    def updateMessages(self, parameters):
        """Validate parameters and show warnings/errors."""
        input_method = parameters[2].valueAsText
        
        if input_method == "Use Data Type Presets":
            if not parameters[3].value:
                parameters[3].setErrorMessage("Data Type is required when using presets.")
            else:
                parameters[3].clearMessage()
        elif input_method == "Use Custom CSV File":
            if not parameters[4].value:
                parameters[4].setErrorMessage("CSV file is required when using custom configuration.")
            else:
                parameters[4].clearMessage()

    def execute(self, parameters, messages):
        """Execute the test compression tool."""
        try:
            # --- Gather Parameters ---
            input_param = parameters[0].value
            if hasattr(input_param, 'dataSource'):
                source_geotiff = input_param.dataSource
            else:
                source_geotiff = parameters[0].valueAsText

            output = parameters[1].valueAsText
            input_method = parameters[2].valueAsText
            product_type_desc = parameters[3].valueAsText
            csv_path = parameters[4].valueAsText
            temp_dir = parameters[5].valueAsText
            delete_test_files = parameters[6].value
            open_report = parameters[7].value

            # --- Validate Input Method ---
            if input_method == "Use Data Type Presets":
                if not product_type_desc:
                    messages.addErrorMessage("Data Type must be specified when using presets.")
                    return
                product_type = self.PRODUCT_TYPE_MAP.get(product_type_desc, PT.DEM.value)
                csv_path = None
            elif input_method == "Use Custom CSV File":
                if not csv_path:
                    messages.addErrorMessage("CSV file must be specified when using custom configuration.")
                    return
                product_type = None
                csv_path = csv_path
            else:
                messages.addErrorMessage("Invalid input method specified.")
                return

            # --- Build Arguments for test_compression.main ---
            args = TestArguments(
                input_path=Path(source_geotiff),
                output_path=Path(output),
                arc_mode=True,
                product_type=product_type,
                csv_path=Path(csv_path) if csv_path else None,
                temp_dir=Path(temp_dir) if temp_dir else None,
                delete_test_files=delete_test_files,
            )

            messages.addMessage(f"Starting compression testing with arguments: {args}")

            # --- Execute Test Compression Script ---
            try:
                log_file = None
                if temp_dir:
                    log_file = Path(temp_dir) / "test_compression.log"
                else:
                    default_temp = Path(source_geotiff).parent / "temp"
                    default_temp.mkdir(exist_ok=True)
                    log_file = default_temp / "test_compression.log"
                
                args.log_file = log_file

                status_code = tc.test_compression(args)

                if status_code != 0:
                    # If failed, we might want to ensure the user knows where the full log is
                    messages.addErrorMessage(f"The test_compression script failed (Exit Code {status_code}).")
                    if log_file:
                        messages.addErrorMessage(f"Full debug log available at: {log_file}")
                    raise Exception("Compression testing failed. See messages above or log file for details.")
                
                messages.addMessage("\nCompression testing completed successfully.")
                messages.addMessage(f"Results saved to: {output}")

                # --- Open Excel Report ---
                if open_report:
                    try:
                        os.startfile(output)
                        messages.addMessage(f"Opening Excel report: {output}")
                    except Exception as e:
                        messages.addWarningMessage(f"Could not automatically open Excel report: {e}")

            except Exception as e:
                messages.addErrorMessage(f"Test Compression script failed: {e}")
                import traceback
                messages.addErrorMessage("Traceback:")
                messages.addErrorMessage(traceback.format_exc())

        except Exception as e:
            messages.addErrorMessage(f"A critical error occurred: {e}")
            import traceback
            messages.addErrorMessage("Traceback:")
            messages.addErrorMessage(traceback.format_exc())

class ReadMetadata:
    # --- Class-level variables for state management ---
    _previous_reader_type = None
    _previous_sections = None
    _previous_xml_type = None
    _previous_tag_scope = None

    READER_TYPE_PRODUCER = "Producer"
    READER_TYPE_ANALYST = "Analyst"
    READER_TYPE_CUSTOM = "Custom"

    def __init__(self):
        """Define the tool class."""
        self.label = "Read Metadata"
        self.description = "Reads the metadata in a GeoTIFF header and generates a report in Markdown or HTML format."
        self.icon = "icons/read.png"
        self.canRunInBackground = True
        
        # --- Define Reader Type Presets ---
        self.READER_TYPE_PRESETS = {
            self.READER_TYPE_PRODUCER: PRODUCER_SECTIONS,
            self.READER_TYPE_ANALYST: ANALYST_SECTIONS
        }

    def getParameterInfo(self):
        """Define parameter definitions"""
        param_input = arcpy.Parameter(
            displayName="Input GeoTIFF or Raster Layer",
            name="input_geotiff",
            datatype=["DEFile", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        param_format = arcpy.Parameter(
            displayName="Output Format",
            name="output_format",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_format.filter.type = "ValueList"
        param_format.filter.list = ["HTML (.html)", "Markdown (.md)"]
        param_format.value = "HTML (.html)"

        param_suffix = arcpy.Parameter(
            displayName="Output Filename Suffix",
            name="output_suffix",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_suffix.value = "_meta"

        param_output = arcpy.Parameter(
            displayName="Output Report File",
            name="output_file",
            datatype="DEFile",
            parameterType="Derived",
            direction="Output")

        param_open_report = arcpy.Parameter(
            displayName="Open Report on Completion",
            name="open_report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_open_report.value = True

        param_write_pam_xml = arcpy.Parameter(
            displayName="Write Statistics XML (.aux.xml)",
            name="write_pam_xml",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_write_pam_xml.value = True

        param_page = arcpy.Parameter(
            displayName="Image File Directory (IFD)",
            name="page",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param_page.value = 0

        # --- Report Sections ---
        param_banner = arcpy.Parameter(
            displayName="Banner Text",
            name="banner",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")

        param_reader_type = arcpy.Parameter(
            displayName="Reader Type",
            name="reader_type",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_reader_type.filter.type = "ValueList"
        param_reader_type.filter.list = [self.READER_TYPE_PRODUCER, self.READER_TYPE_ANALYST, self.READER_TYPE_CUSTOM]
        param_reader_type.value = self.READER_TYPE_ANALYST

        param_tag_scope = arcpy.Parameter(
            displayName="Tag Scope",
            name="tag_scope",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_tag_scope.filter.type = "ValueList"
        param_tag_scope.filter.list = ["complete", "compact"]
        param_tag_scope.value = "compact"

        param_xml_type = arcpy.Parameter(
            displayName="XML Format",
            name="xml_type",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_xml_type.filter.type = "ValueList"
        param_xml_type.filter.list = ["table", "text"]
        param_xml_type.value = "table"

        params = [
            param_input, param_format, param_suffix, param_output,
            param_open_report, param_write_pam_xml, param_page, param_banner,
            param_reader_type, param_tag_scope, param_xml_type
        ]

        for section_key in ALL_SECTIONS:
            config = get_config(section_key)
            display_name = getattr(config, 'title', section_key)
            param = arcpy.Parameter(
                displayName=display_name,
                name=f"section_{section_key}",
                datatype="GPBoolean",
                parameterType="Optional",
                direction="Input")
            param.value = True if section_key in self.READER_TYPE_PRESETS[self.READER_TYPE_ANALYST] else False
            params.append(param)

        return params

    def isLicensed(self):
        """Set whether tool is licensed to run."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal validation is performed."""
        # arcpy.AddMessage("--- ReadMetadata: updateParameters triggered ---")

        # --- Handle derived output path ---
        input_param = parameters[0].value
        if input_param and parameters[1].value:
            if hasattr(input_param, 'dataSource'):
                input_path_str = input_param.dataSource
            else:
                input_path_str = parameters[0].valueAsText

            if input_path_str:
                input_path = Path(input_path_str)
                output_format_display = parameters[1].valueAsText
                suffix = parameters[2].valueAsText or ""
                extension = ".html" if "HTML (.html)" in output_format_display else ".md"
                default_output_path = input_path.with_name(f"{input_path.stem}{suffix}{extension}")
                parameters[3].value = str(default_output_path)

        # --- Handle Dynamic Reader Type and Sections ---
        reader_type_param_index = 8
        tag_scope_param_index = 9
        xml_type_param_index = 10
        sections_start_index = 11
        
        xml_type = parameters[xml_type_param_index].valueAsText
        tag_scope = parameters[tag_scope_param_index].valueAsText
        reader_type = parameters[reader_type_param_index].valueAsText
        current_sections = tuple(p.value for p in parameters[sections_start_index:])
        
        # Robustness Check: If section count changed (code update), force re-init
        if ReadMetadata._previous_sections is not None and len(ReadMetadata._previous_sections) != len(current_sections):
            ReadMetadata._previous_reader_type = None

        # Robustness Check: If section count changed (code update), force re-init
        if ReadMetadata._previous_sections is not None and len(ReadMetadata._previous_sections) != len(current_sections):
            ReadMetadata._previous_reader_type = None

        # Initialize state on first run or re-init
        if ReadMetadata._previous_reader_type is None:
            ReadMetadata._previous_reader_type = reader_type
            ReadMetadata._previous_sections = current_sections
            ReadMetadata._previous_xml_type = xml_type
            ReadMetadata._previous_tag_scope = tag_scope

        reader_type_changed = reader_type != ReadMetadata._previous_reader_type
        sections_changed = current_sections != ReadMetadata._previous_sections
        tag_scope_changed = tag_scope != ReadMetadata._previous_tag_scope

        if reader_type_changed:
            if reader_type == self.READER_TYPE_PRODUCER:
                parameters[xml_type_param_index].value = "Text"
                parameters[tag_scope_param_index].value = "complete"
            elif reader_type == self.READER_TYPE_ANALYST:
                parameters[xml_type_param_index].value = "Table"
                parameters[tag_scope_param_index].value = "compact"

            if reader_type in self.READER_TYPE_PRESETS:
                preset_sections = self.READER_TYPE_PRESETS[reader_type]
                for i, section_key in enumerate(ALL_SECTIONS):
                    is_in_preset = section_key in preset_sections
                    parameters[sections_start_index + i].value = is_in_preset
            
            # After applying presets, get the new state of sections
            current_sections = tuple(p.value for p in parameters[sections_start_index:])
            ReadMetadata._previous_sections = current_sections

        elif sections_changed or tag_scope_changed:
            parameters[reader_type_param_index].value = self.READER_TYPE_CUSTOM
            ReadMetadata._previous_sections = current_sections
            ReadMetadata._previous_tag_scope = tag_scope

        # Update the previous states for the next change detection
        ReadMetadata._previous_reader_type = parameters[reader_type_param_index].valueAsText
        ReadMetadata._previous_xml_type = parameters[xml_type_param_index].valueAsText
        ReadMetadata._previous_tag_scope = parameters[tag_scope_param_index].valueAsText

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        messages.addMessage("--- ReadMetadata: execute method started ---")
        try:
            input_param = parameters[0].value
            if hasattr(input_param, 'dataSource'):
                input_tiff = input_param.dataSource
            else:
                input_tiff = parameters[0].valueAsText

            output_format_display = parameters[1].valueAsText
            suffix = parameters[2].valueAsText
            open_report = parameters[4].value
            write_pam_xml = parameters[5].value
            page = parameters[6].value
            banner = parameters[7].valueAsText
            reader_type = parameters[8].valueAsText
            tag_scope = parameters[9].valueAsText
            xml_type = parameters[10].valueAsText
            
            sections = []
            # The sections checkboxes start at index 11
            sections_start_index = 11
            for i in range(sections_start_index, len(parameters)):
                if parameters[i].value:
                    # Derive the section key from the parameter name (e.g., "section_tags" -> "tags")
                    section_key = parameters[i].name.replace("section_", "")
                    sections.append(section_key)

            output_format = "html" if "HTML (.html)" in output_format_display else "md"

            # Explicitly add the project root to sys.path to ensure we import the local 'gttk' package.
            # We use insert(0, ...) to prioritize this local version over any potentially installed
            # version of gttk in the Python environment, ensuring the toolbox uses its own code.
            tool_dir = Path(__file__).resolve().parent
            root_dir = tool_dir.parent
            if str(root_dir) not in sys.path:
                sys.path.insert(0, str(root_dir))
            
            # Build base arguments for read_metadata.main()
            args = ReadArguments(
                input_path=Path(input_tiff),
                report_format=output_format,
                report_suffix=suffix,
                page=page,
                banner=banner,
                tag_scope=tag_scope,
                xml_type=xml_type,
                arc_mode=True,
                open_report=open_report,
                write_pam_xml=write_pam_xml,
            )
            
            # Handle mutually exclusive reader_type and sections parameters
            if reader_type in [self.READER_TYPE_PRODUCER, self.READER_TYPE_ANALYST]:
                # Use preset reader type, don't pass custom sections
                args.reader_type = reader_type.lower()  # Convert to lowercase for consistency
                args.sections = None
                messages.addMessage(f"Mode: Preset ({args.reader_type})")
            else:
                # Custom sections selected, don't pass reader_type
                args.reader_type = None
                args.sections = sections
                messages.addMessage(f"Mode: Custom (Selected Sections: {', '.join(sections)})")
            
            messages.addMessage(f"Arguments passed to read_metadata.py: {args}")

            try:
                status_code = rm.read_metadata(args)
                if status_code != 0:
                    raise Exception(f"The read_metadata.py script exited with a non-zero status code: {status_code}. This indicates an error occurred. Please check the script's logs if available.")

                output_filename = _get_report_path(input_tiff, suffix, output_format)
                
                # Set derived output parameter
                parameters[3].value = str(output_filename)

                messages.addMessage(f"Report generated successfully: {output_filename}")
                if open_report:
                    try:
                        os.startfile(output_filename)
                        messages.addMessage(f"Opening report: {output_filename}")
                    except Exception as e:
                        messages.addWarningMessage(f"Could not automatically open the report: {e}")

            except Exception as e:
                messages.addErrorMessage(f"Read Metadata script failed with error: {e}")
                import traceback
                messages.addErrorMessage("Traceback:")
                messages.addErrorMessage(traceback.format_exc())

        except Exception as e:
            messages.addErrorMessage(f"A critical error occurred in the tool's execute method: {e}")
            import traceback
            messages.addErrorMessage(traceback.format_exc())
        messages.addMessage("--- ReadMetadata: execute method finished ---")
