#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2026, Eric Robeck
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
5.  Validate Metadata: Check GeoTIFF metadata against product-specific rules.

The dialog is shown in the language ArcGIS Pro is displaying (see gttk.i18n).

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


def _prefer_this_checkout():
    """Make the `gttk` beside this toolbox -- as it is on disk now -- the one that runs.

    ArcGIS Pro keeps imported modules for the life of the session and re-runs only
    this file on Refresh.  Left alone, a Refresh after a `git pull` runs the new
    toolbox against the old package still in memory (this toolbox once died that way,
    calling a function its stale `gttk.i18n` did not have yet), and a `gttk` imported
    earlier from a second checkout, or installed into the Pro conda environment with
    `pip install -e` (which registers an import finder that outranks sys.path), would
    keep answering.  So: forget every loaded `gttk` module, unhook such a finder, and
    say so when the copy that was loaded came from somewhere else.
    """
    def root_of(file):
        return Path(file).resolve().parent.parent if file else None

    notes = []
    loaded = sys.modules.get('gttk')
    if loaded is not None:
        loaded_root = root_of(getattr(loaded, '__file__', None))
        if loaded_root != gttk_path:
            notes.append(f"released a gttk loaded earlier from {loaded_root or 'an unknown location'}")
        for name in [m for m in sys.modules if m == 'gttk' or m.startswith('gttk.')]:
            del sys.modules[name]
    for finder in list(sys.meta_path):
        try:
            spec = finder.find_spec('gttk', None)
        except Exception:
            continue
        origin = getattr(spec, 'origin', None) if spec is not None else None
        if origin and origin != 'namespace' and root_of(origin) != gttk_path:
            sys.meta_path.remove(finder)
            notes.append(f"ignored a gttk installed at {root_of(origin)}")
    if notes:
        arcpy.AddMessage(f"Using gttk from {gttk_path} ({'; '.join(notes)}).")


_prefer_this_checkout()

# Configure PROJ_LIB for ArcGIS BEFORE importing any modules that use GDAL
# This must happen before GDAL is imported, as GDAL only reads PROJ_LIB during initialization
if 'PROJ_LIB' not in os.environ:
    arcpy.AddMessage("PROJ_LIB not set, attempting configuration...")
    try:
        # Load config to get OSGeo4W path
        config_path = gttk_path / "config.toml"
        arcpy.AddMessage(f"Looking for config at: {config_path}")
        
        if config_path.exists():
            arcpy.AddMessage("Config file found, attempting to load...")
            try:
                import sys
                if sys.version_info >= (3, 11):
                    import tomllib
                else:
                    try:
                        import tomli as tomllib
                    except ImportError:
                        tomllib = None
                
                if tomllib:
                    with open(config_path, "rb") as f:
                        config = tomllib.load(f)
                    arcpy.AddMessage("Config loaded successfully")
                    
                    osgeo4w_root = config.get('paths', {}).get('osgeo4w')
                    arcpy.AddMessage(f"OSGeo4W root from config: {osgeo4w_root}")
                    
                    if osgeo4w_root:
                        osgeo4w_path = Path(osgeo4w_root)
                        proj_share_path = osgeo4w_path / "share" / "proj"
                        proj_db_path = proj_share_path / "proj.db"
                        
                        arcpy.AddMessage(f"Checking for proj.db at: {proj_db_path}")
                        if proj_db_path.exists():
                            os.environ['PROJ_LIB'] = str(proj_share_path)
                            arcpy.AddMessage(f"✓ PROJ_LIB configured: {proj_share_path}")
                        else:
                            arcpy.AddWarning(f"proj.db not found at: {proj_db_path}")
                    else:
                        arcpy.AddWarning("OSGeo4W path not found in config.toml")
                else:
                    arcpy.AddWarning("tomllib/tomli not available for reading config")
            except Exception as e:
                arcpy.AddWarning(f"Error during PROJ_LIB configuration: {e}")
                import traceback
                arcpy.AddWarning(traceback.format_exc())
        else:
            arcpy.AddWarning(f"Config file not found at: {config_path}")
    except Exception as e:
        arcpy.AddWarning(f"Failed to configure PROJ_LIB: {e}")
else:
    arcpy.AddMessage(f"PROJ_LIB already set to: {os.environ['PROJ_LIB']}")

try:
    from osgeo import gdal
    # GTTK applies GDAL's exception mode per operation, not at import, so this
    # toolbox makes the choice for the ArcGIS process it runs in.
    gdal.UseExceptions()
    import gttk.i18n as i18n
    from gttk.i18n import _, N_, Picklist
    import gttk.tools.compare_compression as cc
    import gttk.tools.optimize_compression_arc as oc
    import gttk.tools.read_metadata as rm
    import gttk.tools.test_compression as tc
    import gttk.tools.validate_metadata as vm
    from gttk.utils.srs_logic import VERTICAL_SRS_NAME_MAP
    from gttk.utils.section_registry import ALL_SECTIONS, PRODUCER_SECTIONS, ANALYST_SECTIONS, get_config
    import gttk.utils.optimize_constants as C
    from gttk.utils.optimize_constants import CompressionAlgorithm as CA, ProductType as PT
    from gttk.utils.cli_help import probe_defaults
    from gttk.utils.script_arguments import OptimizeArguments, CompareArguments, TestArguments, ReadArguments, ValidateArguments
    from gttk.utils.validation import get_available_products
    from gttk.utils.validation.loader import VALID_SECTIONS as VALIDATION_SECTIONS
except ImportError as e:
    missing = getattr(e, 'name', None)
    if isinstance(e, ModuleNotFoundError) and missing and not missing.startswith('gttk'):
        # The usual cause: ArcGIS Pro is running its default conda environment, which
        # lacks the packages GTTK needs (tifffile, jsonpath-ng).  Naming the interpreter
        # shows which environment Pro is actually using.
        arcpy.AddError(f"The Python environment ArcGIS Pro is using has no '{missing}' package: {sys.executable}")
        arcpy.AddError("Clone the default environment in the Package Manager, add 'tifffile' and 'jsonpath-ng' to "
                       "the clone, make it the active environment and restart ArcGIS Pro (see toolbox/README.md).")
    else:
        arcpy.AddError(f"Failed to import a required module. Ensure the tool scripts are in the correct directory: {gttk_path}")
        arcpy.AddError(f"gttk was imported from: {getattr(sys.modules.get('gttk'), '__file__', None)}")
    arcpy.AddError(f"Python: {sys.executable}")
    arcpy.AddError(f"System Path: {sys.path}")
    raise e

# The dialog's language: an explicit override, else what ArcGIS Pro is displaying, else
# the Windows display language, else English.  Chosen every time Pro (re)loads the
# toolbox, so "Refresh" in the Catalog pane is enough after editing config.toml.
LANG = i18n.activate(i18n.detect_language(reload_config=True))


def _language_line():
    """The language in use and what chose it, worded in that language."""
    lang, source = i18n.detection()
    return _("Language: {lang} (source: {source})").format(lang=lang, source=source)


arcpy.AddMessage(_language_line())
# Pro reads the help side panel from static .pyt.xml files beside this toolbox and has
# no per-language lookup, so the active language's copies are put in place here.
for _warning in i18n.sync_sidecars(script_path, LANG).warnings:
    arcpy.AddWarning(_warning)

#: Dialog group for the options that are not part of the core compression choice.
OVERVIEW_CATEGORY = _("Overview and Performance")

# Every dialog choice below is a Picklist: the dialog shows the active language's
# labels, the code is what the rest of the toolbox compares and passes on, and
# Picklist.code() accepts the label in any language, so a run saved to History or
# copied as a Python command under one language still resolves under another.

#: GDAL predictor codes as the dialog spells them.  Labels keep their leading digit.
PREDICTOR = Picklist([
    (1, N_("1 - None")),
    (2, N_("2 - Horizontal differencing")),
    (3, N_("3 - Floating-point")),
])

#: Product types, shared by Optimize and Test Compression.  Optimize used to spell the
#: error model "Generic Point-cloud Model"; the alias keeps that history runnable.
PRODUCT_TYPE = Picklist([
    (PT.DEM.value, N_("Digital Elevation Model")),
    (PT.ERROR.value, N_("Error Model")),
    (PT.IMAGE.value, N_("Orthoimage or Basemap")),
    (PT.THEMATIC.value, N_("Thematic Data (e.g. Landcover)")),
    (PT.SCIENTIFIC.value, N_("Scientific Data (e.g. Chemistry)")),
], aliases={"Generic Point-cloud Model": PT.ERROR.value})

INPUT_METHOD = Picklist([
    ('presets', N_("Use Product Type Presets")),
    ('csv', N_("Use Custom CSV File")),
])

READER_TYPE = Picklist([
    ('producer', N_("Producer")),
    ('analyst', N_("Analyst")),
    ('custom', N_("Custom")),
])

TAG_SCOPE = Picklist([
    ('complete', N_("complete")),
    ('compact', N_("compact")),
])

XML_TYPE = Picklist([
    ('table', N_("table")),
    ('text', N_("text")),
])

#: Named because an error message quotes this checkbox; both come from one string.
LABEL_MASK_ALPHA = N_("Convert Alpha Band (if one exists) to Internal Mask")


def _settle(param, picklist):
    """Respell a picklist value in the active language.

    ArcGIS validates a choice against the dialog's ValueList before ``execute`` runs
    (ERROR 000800), so a value saved under another language -- from History, a model
    or a copied Python command -- would be refused.  ``updateParameters`` runs first,
    which is where this rewrites anything the picklist recognises.
    """
    text = param.valueAsText
    if text:
        label = picklist.normalize(text)
        if label and label != text:
            param.value = label


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
        self.label = _("GTTK Toolbox")
        self.alias = "gttk"
        self.icon = "icons/GTTK_Toolbox.pyt.32px.png"
        # List of tool classes associated with this toolbox
        self.tools = [OptimizeCompression, ReadMetadata, CompareCompression, TestCompression, ValidateMetadata]

class CompareCompression:
    def __init__(self):
        """Define the tool class."""
        self.label = _("Compare Compression")
        self.description = _("Compares two GeoTIFFs and generates a detailed compression report.")
        self.icon = "icons/compare.png"
        self.canRunInBackground = True
        self.category = _("Compression Tools")

    def getParameterInfo(self):
        """Define parameter definitions"""
        param_baseline = arcpy.Parameter(
            displayName=_("Baseline or Input GeoTIFF 1 (e.g., Original)"),
            name="baseline_path",
            datatype=["DEFile", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        param_comparison = arcpy.Parameter(
            displayName=_("Comparison or Output GeoTIFF 2 (e.g., Processed)"),
            name="comparison_path",
            datatype=["DEFile", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        param_report_format = arcpy.Parameter(
            displayName=_("Report File Format"),
            name="report_format",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_report_format.filter.type = "ValueList"
        param_report_format.filter.list = ["HTML (.html)", "Markdown (.md)"]
        param_report_format.value = "HTML (.html)"

        param_report_suffix = arcpy.Parameter(
            displayName=_("Report Filename Suffix"),
            name="report_suffix",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_report_suffix.value = "_comp"

        param_report_file = arcpy.Parameter(
            displayName=_("Report File Path"),
            name="report_file",
            datatype="DEFile",
            parameterType="Derived",
            direction="Output")
        # Derived outputs do not support filters. The file extension is handled
        # in the updateParameters method.

        param_open_report = arcpy.Parameter(
            displayName=_("Open Report on Completion"),
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
        messages.addMessage(_language_line())
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
                raise Exception(_("The compare_compression script failed to generate a report. See messages above for details."))

            # Set derived output parameter for ModelBuilder
            parameters[4].value = str(report_path)

            messages.addMessage(_("Report generated successfully: {path}").format(path=report_path))

        except Exception as e:
            messages.addErrorMessage(_("An error occurred: {error}").format(error=e))
            import traceback
            messages.addErrorMessage(traceback.format_exc())

class OptimizeCompression:
    _previous_product_type = None
    _previous_algorithm = None
    _previous_raster_type = None

    def __init__(self):
        """Define the tool class."""
        self.label = _("Optimize Compression")
        self.description = _("Optimizes and compresses a GeoTIFF into a Cloud Optimized GeoTIFF (COG) with advanced options.")
        self.icon = "icons/optimize.png"
        self.canRunInBackground = False
        self.category = _("Compression Tools")

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        # --- Input and Output ---
        param_input = arcpy.Parameter(
            displayName=_("Input GeoTIFF, Raster Layer, or Folder"),
            name="input_path",
            datatype=["GPRasterLayer", "DEFile", "DEFolder"],
            parameterType="Required",
            direction="Input")

        param_output = arcpy.Parameter(
            displayName=_("Output GeoTIFF or Folder"),
            name="output_path",
            datatype=["DEFile", "DEFolder"],
            parameterType="Required",
            direction="Output")

        # --- Core Settings ---
        param_product_type = arcpy.Parameter(
            displayName=_("Product Type"),
            name="product_type",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_product_type.filter.type = "ValueList"
        param_product_type.filter.list = PRODUCT_TYPE.labels()
        param_product_type.value = PRODUCT_TYPE.label(PT.DEM.value)
        # The dialog opens on DEM/DEFLATE, so every static value below is that pair's
        # resolved answer.  Read it back rather than restating it; updateParameters
        # replaces the lot as soon as either selection changes.
        opening = probe_defaults(PT.DEM.value, algorithm=CA.DEFLATE.value)

        param_raster_type = arcpy.Parameter(
            displayName=_("Raster Type"),
            name="raster_type",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_raster_type.filter.type = "ValueList"
        param_raster_type.filter.list = ["PixelIsArea", "PixelIsPoint"]
        param_raster_type.value = ("PixelIsPoint" if opening.raster_type == 'Point'
                                   else "PixelIsArea")

        param_vertical_srs = arcpy.Parameter(
            displayName=_("Vertical SRS Name"),
            name="vertical_srs",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_vertical_srs.filter.type = "ValueList"
        param_vertical_srs.filter.list = list(VERTICAL_SRS_NAME_MAP.keys())
        
        param_nodata = arcpy.Parameter(
            displayName=_("NoData Value"),
            name="nodata",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")

        # --- Compression Settings ---
        param_algorithm = arcpy.Parameter(
            displayName=_("Compression Algorithm"),
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
        # Set default algorithm based on default product type (DEM)
        param_algorithm.value = CA.DEFLATE.value

        param_quality = arcpy.Parameter(
            displayName=_("JPEG/JXL Quality"),
            name="quality",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param_quality.filter.type = "Range"
        param_quality.filter.list = [75, 100]
        param_quality.value = C.DEFAULT_QUALITY

        param_predictor = arcpy.Parameter(
            displayName=_("Predictor"),
            name="predictor",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_predictor.filter.type = "ValueList"
        param_predictor.filter.list = PREDICTOR.labels()
        param_predictor.value = PREDICTOR.label(opening.predictor)

        param_level = arcpy.Parameter(
            displayName=_("Compression Level"),
            name="level",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param_level.value = opening.level

        # --- LERC Settings ---
        param_max_z_error = arcpy.Parameter(
            displayName=_("Max Z Error (LERC)"),
            name="max_z_error",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input")
        param_max_z_error.value = C.default_max_z_error_for(PT.DEM.value)

        # --- Rounding Settings ---
        param_decimals = arcpy.Parameter(
            displayName=_("Decimal Places for Rounding"),
            name="decimals",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param_decimals.value = opening.decimals

       # --- Block or Tile Size ---
        param_tile_size = arcpy.Parameter(
            displayName=_("Tile Size (in pixels)"),
            name="tile_size",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param_tile_size.value = C.DEFAULT_TILE_SIZE

        # --- GEO_METADATA Tag ---
        param_geo_metadata = arcpy.Parameter(
            displayName=_("Write External XML to GEO_METADATA Tag"),
            name="geo_metadata",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_geo_metadata.value = False

        # --- Precision Auxiliary Metadata (.aux.xml) ---
        param_write_pam_xml = arcpy.Parameter(
            displayName=_("Write Statistics XML (.aux.xml)"),
            name="write_pam_xml",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_write_pam_xml.value = True  # matches `gttk optimize -w`

        # --- COG vs. GTiff Driver ---
        param_cog = arcpy.Parameter(
            displayName=_("Create Cloud Optimized GeoTIFF"),
            name="cog",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_cog.value = True

        param_overviews = arcpy.Parameter(
            displayName=_("Generate Internal Overviews"),
            name="overviews",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_overviews.value = True

        param_mask_nodata = arcpy.Parameter(
            displayName=_("Mask NoData Pixels (if any)"),
            name="mask_nodata",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_mask_nodata.value = opening.mask_nodata

        param_mask_alpha = arcpy.Parameter(
            displayName=_(LABEL_MASK_ALPHA),
            name="mask_alpha",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_mask_alpha.value = opening.mask_alpha

        param_add_to_map = arcpy.Parameter(
            displayName=_("Add Output to Map"),
            name="add_to_map",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_add_to_map.value = True

        # --- Report Settings ---
        param_report_format = arcpy.Parameter(
            displayName=_("Compression Report Format"),
            name="report_format",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_report_format.filter.type = "ValueList"
        param_report_format.filter.list = ["HTML (.html)", "Markdown (.md)"]
        param_report_format.value = "HTML (.html)"

        param_report_suffix = arcpy.Parameter(
            displayName=_("Report Filename Suffix"),
            name="report_suffix",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_report_suffix.value = "_comp"

        param_open_report = arcpy.Parameter(
            displayName=_("Open Report on Completion"),
            name="open_report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_open_report.value = True


        # --- Overview and performance settings ---
        # Appended rather than slotted in beside "Create Overviews": every method below
        # addresses parameters by position, so a new index in the middle would silently
        # shift them all.  `category` is what groups them in the dialog instead.
        param_overview_resampling = arcpy.Parameter(
            displayName=_("Overview Resampling"),
            name="overview_resampling",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            category=OVERVIEW_CATEGORY)
        param_overview_resampling.filter.type = "ValueList"
        param_overview_resampling.filter.list = list(C.OVERVIEW_RESAMPLING_CHOICES)

        param_overview_compress = arcpy.Parameter(
            displayName=_("Overview Compression"),
            name="overview_compress",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            category=OVERVIEW_CATEGORY)
        param_overview_compress.filter.type = "ValueList"
        param_overview_compress.filter.list = list(C.OVERVIEW_COMPRESS_CHOICES)

        param_overview_predictor = arcpy.Parameter(
            displayName=_("Overview Predictor"),
            name="overview_predictor",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            category=OVERVIEW_CATEGORY)
        param_overview_predictor.filter.type = "ValueList"
        param_overview_predictor.filter.list = PREDICTOR.labels()

        param_num_threads = arcpy.Parameter(
            displayName=_("Worker Threads"),
            name="num_threads",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            category=OVERVIEW_CATEGORY)
        param_num_threads.value = "ALL_CPUS"

        param_report = arcpy.Parameter(
            displayName=_("Generate Comparison Report"),
            name="report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
            category=OVERVIEW_CATEGORY)
        param_report.value = True

        params = [
            param_input, param_output, param_product_type, param_raster_type,
            param_vertical_srs, param_nodata, param_algorithm, param_quality,
            param_predictor, param_level, param_max_z_error, param_decimals,
            param_tile_size, param_geo_metadata, param_write_pam_xml, param_cog,
            param_overviews, param_mask_nodata, param_mask_alpha, param_add_to_map,
            param_report_format, param_report_suffix, param_open_report,
            param_overview_resampling, param_overview_compress,
            param_overview_predictor, param_num_threads, param_report
        ]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to run."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed. This method is called whenever a parameter
        has been changed."""

        _settle(parameters[2], PRODUCT_TYPE)
        _settle(parameters[8], PREDICTOR)
        _settle(parameters[25], PREDICTOR)

        if not parameters[2].value:
            return

        selected_type_key = PRODUCT_TYPE.code(parameters[2].valueAsText)
        algorithm = parameters[6].valueAsText

        # --- Set valid algorithms based on product type ---
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
                        selected_type_key != OptimizeCompression._previous_product_type)
        
        algo_changed = (OptimizeCompression._previous_algorithm is not None and
                        algorithm != OptimizeCompression._previous_algorithm)

        # --- Handle State Changes ---
        # On first run, or if the product type changed, reset everything for the new type.
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
            OptimizeCompression._previous_product_type = selected_type_key
            OptimizeCompression._previous_algorithm = new_algorithm
            OptimizeCompression._previous_raster_type = parameters[3].valueAsText

        # If ONLY the algorithm changed, reset only algorithm-dependent things.
        elif algo_changed:
            self._reset_algorithm_dependents(parameters, algorithm)
            OptimizeCompression._previous_algorithm = algorithm

        # --- Update UI states (enabled/disabled) every time ---
        self._update_parameter_states(parameters, selected_type_key, parameters[6].valueAsText)

        return

    def _resolved(self, selected_type_key, algorithm):
        """What the CLI would choose for this product type and codec.

        The toolbox used to keep its own copy of this branching, which is how its
        masking and predictor pre-fills drifted away from `gttk optimize`.  Asking
        OptimizeArguments instead means there is only one answer to maintain; it
        needs no raster, and returns None for a combination it would reject (LERC on
        imagery, say), in which case the product type alone still gives an answer.
        """
        return (probe_defaults(selected_type_key, algorithm=algorithm)
                or probe_defaults(selected_type_key))

    def _reset_all_dependents(self, parameters, selected_type_key, algorithm):
        """Re-prefill every parameter that depends on product type or algorithm."""
        defaults = self._resolved(selected_type_key, algorithm)
        if defaults is None:
            return

        parameters[3].value = ("PixelIsPoint" if defaults.raster_type == 'Point'
                               else "PixelIsArea")
        parameters[7].value = defaults.quality or C.DEFAULT_QUALITY
        # The predictor box stays populated even for a codec that ignores it, so fall
        # back to the product type's own value rather than blanking the dialog.
        parameters[8].value = PREDICTOR.label(
            defaults.predictor or C.default_predictor_for(selected_type_key))
        parameters[17].value = defaults.mask_nodata
        parameters[18].value = defaults.mask_alpha

        max_z_error = C.default_max_z_error_for(selected_type_key)
        parameters[10].value = (max_z_error if selected_type_key in C.LERC_PRODUCT_TYPES
                                else None)
        decimals = C.default_decimals_for(selected_type_key, algorithm)
        # The box is a GPLong; NO_ROUNDING ('none') is not a number it can hold.
        parameters[11].value = decimals if isinstance(decimals, int) else None

        parameters[23].value = defaults.overview_resampling
        parameters[24].value = defaults.overview_compress
        parameters[25].value = PREDICTOR.label(defaults.overview_predictor)
        parameters[26].value = defaults.num_threads

        # Reset algorithm-specific parameters
        self._reset_algorithm_dependents(parameters, algorithm)

    def _reset_algorithm_dependents(self, parameters, algorithm):
        """Resets parameters that depend only on the algorithm."""
        parameters[9].value = C.default_level_for(algorithm)

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

        # Overview settings only mean anything while overviews are being built.
        building_overviews = bool(parameters[16].value)
        for index in (23, 24, 25):
            parameters[index].enabled = building_overviews
        parameters[25].enabled = building_overviews and parameters[8].enabled

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        messages.addMessage(_language_line())
        # --- Gather Parameters ---
        input_param = parameters[0].value
        if hasattr(input_param, 'dataSource'):
            input_path = input_param.dataSource
        else:
            input_path = parameters[0].valueAsText
        output_path = parameters[1].valueAsText
        product_type = PRODUCT_TYPE.code(parameters[2].valueAsText) or PT.DEM.value
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
                messages.addErrorMessage(_("Invalid NoData value provided: {value}").format(value=nodata_str))
                return
        else:
            nodata = None

        algorithm = parameters[6].valueAsText
        quality = parameters[7].value
        predictor = PREDICTOR.code(parameters[8].valueAsText)
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
        overview_resampling = parameters[23].valueAsText
        overview_compress = parameters[24].valueAsText
        overview_predictor = PREDICTOR.code(parameters[25].valueAsText)
        num_threads = parameters[26].valueAsText
        report = parameters[27].value

        # --- Validate JPEG + RGBA + mask_alpha=False (unsupported) ---
        # If the input has an alpha band and JPEG is selected while the user disabled mask_alpha,
        # fail fast with a clear, actionable message.
        if product_type == PT.DEM.value and not vertical_srs_name:
            messages.addErrorMessage(_("Vertical SRS is required for Digital Elevation Models."))
            return

        # --- Lightweight check for single-band restriction ---
        if product_type in [PT.DEM.value, PT.ERROR.value, PT.THEMATIC.value]:
            try:
                # Use arcpy to check band count efficiently
                desc = arcpy.Describe(input_path)
                if hasattr(desc, 'bandCount') and desc.bandCount > 1:
                    messages.addErrorMessage(_(
                        "Multi-band rasters ({bands} bands) are not supported for the "
                        "'{product}' product type. Use '{image}' or '{scientific}' instead."
                    ).format(bands=desc.bandCount, product=PRODUCT_TYPE.label(product_type),
                             image=PRODUCT_TYPE.label(PT.IMAGE.value),
                             scientific=PRODUCT_TYPE.label(PT.SCIENTIFIC.value)))
                    return
            except Exception as e:
                # If arcpy.Describe fails, we log a warning but proceed, letting the backend validation handle it.
                messages.addWarningMessage(_("Could not validate band count: {error}").format(error=e))

        if algorithm == CA.JPEG.value and (mask_alpha is False):
            # A simplified check. The robust check is in the backend.
            messages.addWarningMessage(_(
                "If the input has an alpha band, using JPEG compression without converting it "
                "to an internal mask may cause issues. The backend process will validate this."
            ))
            messages.addErrorMessage(_(
                "JPEG compression does not support a preserved alpha band. Re-enable "
                "'{mask_alpha}' to convert the alpha to an internal mask, or choose a "
                "different algorithm such as JXL or DEFLATE."
            ).format(mask_alpha=_(LABEL_MASK_ALPHA)))
            return

        # --- Conditionally Nullify Parameters invalid for selected algorithm ---
        if not product_type == PT.DEM.value:
            vertical_srs_name = None

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
            overview_resampling=overview_resampling,
            overview_compress=overview_compress,
            overview_predictor=overview_predictor,
            num_threads=num_threads,
            report=report,
            report_format=report_format,
            report_suffix=report_suffix,
            open_report=open_report,
            arc_mode=True,
        )

        # --- Run the optimize_compression script ---
        try:
            oc.optimize_compression(args)
            messages.addMessage(_("Tool completed successfully."))

            if add_to_map:
                try:
                    # Add the output raster to the current map
                    aprx = arcpy.mp.ArcGISProject("CURRENT")
                    map_view = aprx.activeMap
                    if map_view:
                        map_view.addDataFromPath(output_path)
                        messages.addMessage(_("Added {name} to the map.").format(name=os.path.basename(output_path)))
                    else:
                        messages.addWarningMessage(_("No active map found to add the output raster."))
                except Exception as e:
                    messages.addWarningMessage(_("Could not add the output raster to the map: {error}").format(error=e))

        except RuntimeError as e:
            # This will catch the detailed error message propagated from the runner
            messages.addErrorMessage(str(e))
        except Exception as e:
            messages.addErrorMessage(_("An unexpected error occurred in the toolbox script: {error}").format(error=e))
            import traceback
            messages.addErrorMessage(_("Traceback:"))
            messages.addErrorMessage(traceback.format_exc())

class TestCompression:
    _previous_source = None

    def __init__(self):
        """Define the tool class."""
        self.label = _("Test Compression")
        self.description = _("Tests multiple compression settings from CSV configurations and generates detailed Excel reports comparing performance and efficiency.")
        self.icon = "icons/test.png"
        self.canRunInBackground = True
        self.category = _("Compression Tools")

    def getParameterInfo(self):
        """Define parameter definitions"""
        
        # --- Input and Output ---
        param_source = arcpy.Parameter(
            displayName=_("Source GeoTIFF, Raster Layer, or Folder"),
            name="source_geotiff",
            datatype=["GPRasterLayer", "DEFile", "DEFolder"],
            parameterType="Required",
            direction="Input")

        param_output = arcpy.Parameter(
            displayName=_("Output Excel Report"),
            name="output_file",
            datatype="DEFile",
            parameterType="Required",
            direction="Output")
        param_output.filter.list = ["xlsx"]

        # --- Input Method (Product Type or custom CSV) ---
        param_input_method = arcpy.Parameter(
            displayName=_("Input Method"),
            name="input_method",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_input_method.filter.type = "ValueList"
        param_input_method.filter.list = INPUT_METHOD.labels()
        param_input_method.value = INPUT_METHOD.label('presets')

        param_product_type = arcpy.Parameter(
            displayName=_("Product Type (for Preset Selection)"),
            name="product_type",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_product_type.filter.type = "ValueList"
        param_product_type.filter.list = PRODUCT_TYPE.labels()
        param_product_type.value = PRODUCT_TYPE.label(PT.DEM.value)

        param_csv_path = arcpy.Parameter(
            displayName=_("Custom CSV Configuration File"),
            name="csv_path",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input")
        param_csv_path.filter.list = ["csv"]

        # --- Processing Options ---
        param_temp_dir = arcpy.Parameter(
            displayName=_("Temporary Files Directory"),
            name="temp_dir",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input")
        project_root = Path(__file__).parent.parent
        default_temp_path = project_root / "temp"
        param_temp_dir.value = str(default_temp_path)

        param_delete_test_files = arcpy.Parameter(
            displayName=_("Delete Temporary Test Files"),
            name="delete_test_files",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_delete_test_files.value = True

        # --- Report Options ---
        param_open_report = arcpy.Parameter(
            displayName=_("Open Excel Report on Completion"),
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
        _settle(parameters[2], INPUT_METHOD)
        _settle(parameters[3], PRODUCT_TYPE)
        input_method = INPUT_METHOD.code(parameters[2].valueAsText)
        
        if input_method == 'presets':
            parameters[3].enabled = True
            parameters[3].parameterType = "Required"
            parameters[4].enabled = False
            parameters[4].parameterType = "Optional"
            parameters[4].value = None
        elif input_method == 'csv':
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
        input_method = INPUT_METHOD.code(parameters[2].valueAsText)
        
        if input_method == 'presets':
            if not parameters[3].value:
                parameters[3].setErrorMessage(_("Product Type is required when using presets."))
            else:
                parameters[3].clearMessage()
        elif input_method == 'csv':
            if not parameters[4].value:
                parameters[4].setErrorMessage(_("CSV file is required when using custom configuration."))
            else:
                parameters[4].clearMessage()

    def execute(self, parameters, messages):
        """Execute the test compression tool."""
        messages.addMessage(_language_line())
        try:
            # --- Gather Parameters ---
            input_param = parameters[0].value
            if hasattr(input_param, 'dataSource'):
                source_geotiff = input_param.dataSource
            else:
                source_geotiff = parameters[0].valueAsText

            output = parameters[1].valueAsText
            input_method = INPUT_METHOD.code(parameters[2].valueAsText)
            product_type_desc = parameters[3].valueAsText
            csv_path = parameters[4].valueAsText
            temp_dir = parameters[5].valueAsText
            delete_test_files = parameters[6].value
            open_report = parameters[7].value

            # --- Validate Input Method ---
            if input_method == 'presets':
                if not product_type_desc:
                    messages.addErrorMessage(_("Product Type must be specified when using presets."))
                    return
                product_type = PRODUCT_TYPE.code(product_type_desc) or PT.DEM.value
                csv_path = None
            elif input_method == 'csv':
                if not csv_path:
                    messages.addErrorMessage(_("CSV file must be specified when using custom configuration."))
                    return
                product_type = None
                csv_path = csv_path
            else:
                messages.addErrorMessage(_("Invalid input method specified."))
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
                open_report=open_report,
            )

            messages.addMessage(_("Starting compression testing with arguments: {args}").format(args=args))

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
                    messages.addErrorMessage(_("The test_compression script failed (Exit Code {code}).").format(code=status_code))
                    if log_file:
                        messages.addErrorMessage(_("Full debug log available at: {path}").format(path=log_file))
                    raise Exception(_("Compression testing failed. See messages above or log file for details."))
                
                messages.addMessage("\n" + _("Compression testing completed successfully."))
                messages.addMessage(_("Results saved to: {path}").format(path=output))

            except Exception as e:
                messages.addErrorMessage(_("Test Compression script failed: {error}").format(error=e))
                import traceback
                messages.addErrorMessage(_("Traceback:"))
                messages.addErrorMessage(traceback.format_exc())

        except Exception as e:
            messages.addErrorMessage(_("A critical error occurred: {error}").format(error=e))
            import traceback
            messages.addErrorMessage(_("Traceback:"))
            messages.addErrorMessage(traceback.format_exc())

class ReadMetadata:
    # --- Class-level variables for state management ---
    _previous_reader_type = None
    _previous_sections = None
    _previous_xml_type = None
    _previous_tag_scope = None

    def __init__(self):
        """Define the tool class."""
        self.label = _("Read Metadata")
        self.description = _("Reads the metadata in a GeoTIFF header and generates a report in Markdown or HTML format.")
        self.icon = "icons/read.png"
        self.canRunInBackground = True
        self.category = _("Metadata Tools")
        
        # --- Define Reader Type Presets ---
        self.READER_TYPE_PRESETS = {
            'producer': PRODUCER_SECTIONS,
            'analyst': ANALYST_SECTIONS
        }

    def getParameterInfo(self):
        """Define parameter definitions"""
        param_input = arcpy.Parameter(
            displayName=_("Input GeoTIFF or Raster Layer"),
            name="input_geotiff",
            datatype=["DEFile", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        param_format = arcpy.Parameter(
            displayName=_("Output Format"),
            name="output_format",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_format.filter.type = "ValueList"
        param_format.filter.list = ["HTML (.html)", "Markdown (.md)"]
        param_format.value = "HTML (.html)"

        param_suffix = arcpy.Parameter(
            displayName=_("Output Filename Suffix"),
            name="output_suffix",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_suffix.value = "_meta"

        param_output = arcpy.Parameter(
            displayName=_("Output Report File"),
            name="output_file",
            datatype="DEFile",
            parameterType="Derived",
            direction="Output")

        param_open_report = arcpy.Parameter(
            displayName=_("Open Report on Completion"),
            name="open_report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_open_report.value = True

        param_write_pam_xml = arcpy.Parameter(
            displayName=_("Write Statistics XML (.aux.xml)"),
            name="write_pam_xml",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_write_pam_xml.value = True

        param_page = arcpy.Parameter(
            displayName=_("Image File Directory (IFD)"),
            name="page",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input")
        param_page.value = 0

        # --- Report Sections ---
        param_banner = arcpy.Parameter(
            displayName=_("Banner Text"),
            name="banner",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")

        param_reader_type = arcpy.Parameter(
            displayName=_("Reader Type"),
            name="reader_type",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_reader_type.filter.type = "ValueList"
        param_reader_type.filter.list = READER_TYPE.labels()
        param_reader_type.value = READER_TYPE.label('analyst')

        param_tag_scope = arcpy.Parameter(
            displayName=_("Tag Scope"),
            name="tag_scope",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_tag_scope.filter.type = "ValueList"
        param_tag_scope.filter.list = TAG_SCOPE.labels()
        param_tag_scope.value = TAG_SCOPE.label('compact')

        param_xml_type = arcpy.Parameter(
            displayName=_("XML Format"),
            name="xml_type",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_xml_type.filter.type = "ValueList"
        param_xml_type.filter.list = XML_TYPE.labels()
        param_xml_type.value = XML_TYPE.label('table')

        params = [
            param_input, param_format, param_suffix, param_output,
            param_open_report, param_write_pam_xml, param_page, param_banner,
            param_reader_type, param_tag_scope, param_xml_type
        ]

        for section_key in ALL_SECTIONS:
            config = get_config(section_key)
            display_name = _(getattr(config, 'title', section_key))
            param = arcpy.Parameter(
                displayName=display_name,
                name=f"section_{section_key}",
                datatype="GPBoolean",
                parameterType="Optional",
                direction="Input")
            param.value = True if section_key in self.READER_TYPE_PRESETS['analyst'] else False
            params.append(param)

        return params

    def isLicensed(self):
        """Set whether tool is licensed to run."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal validation is performed."""
        _settle(parameters[8], READER_TYPE)
        _settle(parameters[9], TAG_SCOPE)
        _settle(parameters[10], XML_TYPE)

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
        
        xml_type = XML_TYPE.code(parameters[xml_type_param_index].valueAsText)
        tag_scope = TAG_SCOPE.code(parameters[tag_scope_param_index].valueAsText)
        reader_type = READER_TYPE.code(parameters[reader_type_param_index].valueAsText)
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
            if reader_type == 'producer':
                parameters[xml_type_param_index].value = XML_TYPE.label('text')
                parameters[tag_scope_param_index].value = TAG_SCOPE.label('complete')
            elif reader_type == 'analyst':
                parameters[xml_type_param_index].value = XML_TYPE.label('table')
                parameters[tag_scope_param_index].value = TAG_SCOPE.label('compact')

            if reader_type in self.READER_TYPE_PRESETS:
                preset_sections = self.READER_TYPE_PRESETS[reader_type]
                for i, section_key in enumerate(ALL_SECTIONS):
                    is_in_preset = section_key in preset_sections
                    parameters[sections_start_index + i].value = is_in_preset
            
            # After applying presets, get the new state of sections
            current_sections = tuple(p.value for p in parameters[sections_start_index:])
            ReadMetadata._previous_sections = current_sections

        elif sections_changed or tag_scope_changed:
            parameters[reader_type_param_index].value = READER_TYPE.label('custom')
            ReadMetadata._previous_sections = current_sections
            ReadMetadata._previous_tag_scope = tag_scope

        # Update the previous states for the next change detection
        ReadMetadata._previous_reader_type = READER_TYPE.code(parameters[reader_type_param_index].valueAsText)
        ReadMetadata._previous_xml_type = XML_TYPE.code(parameters[xml_type_param_index].valueAsText)
        ReadMetadata._previous_tag_scope = TAG_SCOPE.code(parameters[tag_scope_param_index].valueAsText)

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter. This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        """The source code of the tool."""
        messages.addMessage(_("--- ReadMetadata: execute method started ---"))
        messages.addMessage(_language_line())
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
            reader_type = READER_TYPE.code(parameters[8].valueAsText)
            tag_scope = TAG_SCOPE.code(parameters[9].valueAsText)
            xml_type = XML_TYPE.code(parameters[10].valueAsText)
            
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
            if reader_type in ('producer', 'analyst'):
                # Use preset reader type, don't pass custom sections
                args.reader_type = reader_type
                args.sections = None
                messages.addMessage(_("Mode: Preset ({mode})").format(mode=READER_TYPE.label(reader_type)))
            else:
                # Custom sections selected, don't pass reader_type
                args.reader_type = None
                args.sections = sections
                messages.addMessage(_("Mode: Custom (Selected Sections: {sections})").format(sections=', '.join(sections)))
            
            messages.addMessage(_("Arguments passed to read_metadata.py: {args}").format(args=args))

            try:
                status_code = rm.read_metadata(args)
                if status_code != 0:
                    raise Exception(_("The read_metadata.py script exited with a non-zero status code: {code}. This indicates an error occurred. Please check the script's logs if available.").format(code=status_code))

                output_filename = _get_report_path(input_tiff, suffix, output_format)
                
                # Set derived output parameter
                parameters[3].value = str(output_filename)

                messages.addMessage(_("Report generated successfully: {path}").format(path=output_filename))

            except Exception as e:
                messages.addErrorMessage(_("Read Metadata script failed with error: {error}").format(error=e))
                import traceback
                messages.addErrorMessage(_("Traceback:"))
                messages.addErrorMessage(traceback.format_exc())

        except Exception as e:
            messages.addErrorMessage(_("A critical error occurred in the tool's execute method: {error}").format(error=e))
            import traceback
            messages.addErrorMessage(traceback.format_exc())
        messages.addMessage(_("--- ReadMetadata: execute method finished ---"))


class ValidateMetadata:
    """
    ArcGIS Python Toolbox tool for validating GeoTIFF files against
    product-specific requirements defined in TOML rule files.
    """
    # --- Class-level state for dynamic updates ---
    _previous_rules_dir = None
    _available_products = []

    def __init__(self):
        """Define the tool class."""
        self.label = _("Validate Metadata")
        self.description = _("Validates GeoTIFF files against product-specific requirements defined in TOML rule files.")
        self.icon = "icons/validate.png"
        self.canRunInBackground = False
        self.category = _("Metadata Tools")

    def getParameterInfo(self):
        """Define parameter definitions."""
        # --- Parameter 0: Input GeoTIFF(s) ---
        param_input = arcpy.Parameter(
            displayName=_("Input GeoTIFF(s)"),
            name="input_path",
            datatype=["DEFile", "DEFolder", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        # --- Parameter 1: Rules Directory ---
        param_rules_dir = arcpy.Parameter(
            displayName=_("Rules Directory"),
            name="rules_dir",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input")
        # Set default to gttk/resources/rules relative to toolbox
        project_root = Path(__file__).parent.parent
        default_rules_path = project_root / "gttk" / "resources" / "rules"
        if default_rules_path.exists():
            param_rules_dir.value = str(default_rules_path)

        # --- Parameter 2: Product ---
        param_product = arcpy.Parameter(
            displayName=_("Product"),
            name="product",
            datatype="GPString",
            parameterType="Required",
            direction="Input")
        param_product.filter.type = "ValueList"
        # Will be populated dynamically in updateParameters
        param_product.filter.list = []

        # --- Parameter 3: Sections (multivalue) ---
        param_sections = arcpy.Parameter(
            displayName=_("Sections to Validate"),
            name="sections",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
            multiValue=True)
        param_sections.filter.type = "ValueList"
        param_sections.filter.list = VALIDATION_SECTIONS
        # Default to all sections
        param_sections.value = VALIDATION_SECTIONS

        # --- Parameter 4: Name Filter ---
        param_name_filter = arcpy.Parameter(
            displayName=_("Name Filter"),
            name="name_filter",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_name_filter.value = ""

        # --- Parameter 5: Output Directory ---
        param_output_dir = arcpy.Parameter(
            displayName=_("Output Directory"),
            name="output_dir",
            datatype="DEFolder",
            parameterType="Optional",
            direction="Input")

        # --- Parameter 6: Write Individual Reports ---
        param_write_reports = arcpy.Parameter(
            displayName=_("Write Individual Reports"),
            name="write_reports",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_write_reports.value = True

        # --- Parameter 7: Report Format ---
        param_report_format = arcpy.Parameter(
            displayName=_("Report Format"),
            name="report_format",
            datatype="GPString",
            parameterType="Optional",
            direction="Input")
        param_report_format.filter.type = "ValueList"
        param_report_format.filter.list = ["HTML", "Markdown"]
        param_report_format.value = "HTML"

        # --- Parameter 8: Open Report on Completion ---
        param_open_report = arcpy.Parameter(
            displayName=_("Open Report on Completion"),
            name="open_report",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input")
        param_open_report.value = True

        # --- Parameter 9: Output Folder (Derived) ---
        param_output_folder = arcpy.Parameter(
            displayName=_("Output Folder"),
            name="output_folder",
            datatype="DEFolder",
            parameterType="Derived",
            direction="Output")

        # --- Parameter 10: JSON Summary Path (Derived) ---
        param_json_path = arcpy.Parameter(
            displayName=_("JSON Summary Path"),
            name="json_output_path",
            datatype="DEFile",
            parameterType="Derived",
            direction="Output")

        return [
            param_input,        # 0
            param_rules_dir,    # 1
            param_product,      # 2
            param_sections,     # 3
            param_name_filter,  # 4
            param_output_dir,   # 5
            param_write_reports,  # 6
            param_report_format,  # 7
            param_open_report,    # 8
            param_output_folder,  # 9
            param_json_path       # 10
        ]

    def isLicensed(self):
        """Set whether tool is licensed to run."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal validation."""
        rules_dir_param = parameters[1].valueAsText

        # Only refresh products if rules directory has changed
        if rules_dir_param != ValidateMetadata._previous_rules_dir:
            ValidateMetadata._previous_rules_dir = rules_dir_param

            if rules_dir_param and Path(rules_dir_param).exists():
                try:
                    products = get_available_products(Path(rules_dir_param))
                    ValidateMetadata._available_products = sorted(products.keys())
                    parameters[2].filter.list = ValidateMetadata._available_products
                except Exception as e:
                    arcpy.AddWarning(_("Could not load products: {error}").format(error=e))
                    parameters[2].filter.list = []
                    ValidateMetadata._available_products = []
            else:
                parameters[2].filter.list = []
                ValidateMetadata._available_products = []

        # Enable/disable name filter based on input type
        input_param = parameters[0].value
        if input_param:
            if hasattr(input_param, 'dataSource'):
                input_path_str = input_param.dataSource
            else:
                input_path_str = parameters[0].valueAsText

            if input_path_str:
                input_path = Path(input_path_str)
                # Only enable name filter for directories
                parameters[4].enabled = input_path.is_dir() if input_path.exists() else True

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool parameter."""
        # Validate input path
        input_param = parameters[0].value
        if input_param:
            if hasattr(input_param, 'dataSource'):
                input_path_str = input_param.dataSource
            else:
                input_path_str = parameters[0].valueAsText

            if input_path_str:
                input_path = Path(input_path_str)
                if not input_path.exists():
                    parameters[0].setErrorMessage(_("Input path does not exist: {path}").format(path=input_path))
                elif input_path.is_file() and input_path.suffix.lower() not in ['.tif', '.tiff']:
                    parameters[0].setErrorMessage(_("Input file must be a GeoTIFF (.tif or .tiff)"))
                else:
                    parameters[0].clearMessage()

        # Validate product selection
        if parameters[1].value and not parameters[2].value:
            parameters[1].setWarningMessage(_("Select a product from the dropdown after loading the rules directory"))

        # Validate rules directory
        rules_dir = parameters[1].valueAsText
        if rules_dir:
            rules_path = Path(rules_dir)
            if not rules_path.exists():
                parameters[1].setErrorMessage(_("Rules directory does not exist: {path}").format(path=rules_dir))
            elif not rules_path.is_dir():
                parameters[1].setErrorMessage(_("Path must be a directory"))
            elif not list(rules_path.glob('*.toml')):
                parameters[1].setErrorMessage(_("No TOML rule files found in directory"))
            else:
                parameters[1].clearMessage()

    def execute(self, parameters, messages):
        """Execute the validation tool."""
        messages.addMessage(_("--- ValidateMetadata: execute method started ---"))
        messages.addMessage(_language_line())

        try:
            # --- Extract Parameters ---
            input_param = parameters[0].value
            if hasattr(input_param, 'dataSource'):
                input_path = input_param.dataSource
            else:
                input_path = parameters[0].valueAsText

            rules_dir = parameters[1].valueAsText
            product = parameters[2].valueAsText
            sections = parameters[3].valueAsText
            name_filter = parameters[4].valueAsText or ""
            output_dir = parameters[5].valueAsText
            write_reports = parameters[6].value
            report_format_display = parameters[7].valueAsText
            open_report = parameters[8].value

            # Convert sections string to list
            if sections:
                sections_list = [s.strip() for s in sections.split(';') if s.strip()]
            else:
                sections_list = None

            # Map report format
            report_format = "html" if report_format_display == "HTML" else "md"

            # Build arguments
            args = ValidateArguments(
                input_path=Path(input_path),
                rules_dir=Path(rules_dir) if rules_dir else Path('gttk/resources/rules'),
                product=product,
                sections=sections_list,
                name_filter=name_filter,
                output_dir=Path(output_dir) if output_dir else None,
                write_reports=write_reports,
                report_format=report_format,
                open_report=open_report,
                arc_mode=True
            )

            messages.addMessage(_("Input: {path}").format(path=args.input_path))
            messages.addMessage(_("Rules Directory: {path}").format(path=args.rules_dir))
            messages.addMessage(_("Product: {product}").format(product=args.product))
            messages.addMessage(_("Sections: {sections}").format(sections=args.sections or _("All")))
            messages.addMessage(_("Output Folder: {path}").format(path=args.output_folder))

            # --- Run Validation ---
            try:
                vm.validate_metadata(args)

                # Set derived output parameters
                parameters[9].value = str(args.output_folder)
                parameters[10].value = str(args.json_output_path)

                messages.addMessage(_("Validation complete. Results saved to: {path}").format(path=args.json_output_path))

            except Exception as e:
                messages.addErrorMessage(_("Validation failed: {error}").format(error=e))
                import traceback
                messages.addErrorMessage(_("Traceback:"))
                messages.addErrorMessage(traceback.format_exc())

        except Exception as e:
            messages.addErrorMessage(_("A critical error occurred: {error}").format(error=e))
            import traceback
            messages.addErrorMessage(_("Traceback:"))
            messages.addErrorMessage(traceback.format_exc())

        messages.addMessage(_("--- ValidateMetadata: execute method finished ---"))
