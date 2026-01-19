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
Dataclass-based Argument Models for GTTK Tools.

This module defines strongly-typed dataclasses for parsing and validating the
command-line arguments for each tool (`optimize`, `compare`, `test`, `read`).
It uses `__post_init__` for validation and resolving context-aware default
values, ensuring that the core logic receives clean and validated inputs.

Classes:
    BaseArguments: A base dataclass for common script arguments.
    CompareArguments: Arguments for the compare_compression tool.
    OptimizeArguments: Arguments for optimize_compression tool.
    ReadArguments: Arguments for the read_metadata tool.
    TestArguments: Arguments for the test_compression tool.
"""
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
from gttk.utils.optimize_constants import CompressionAlgorithm as CA, ProductType as PT
import gttk.utils.optimize_constants as oc
from osgeo import gdal

logger = logging.getLogger(__name__)

@dataclass
class BaseArguments:
    """A base dataclass for common script arguments."""
    input_path: Optional[Path] = None
    output_path: Optional[Path] = None
    open_report: bool = True
    arc_mode: bool = False
    verbose: bool = False

    def __post_init__(self) -> None:
        """Coerce path-like arguments to Path objects."""
        if self.input_path and isinstance(self.input_path, str):
            self.input_path = Path(self.input_path)
        if self.output_path and isinstance(self.output_path, str):
            self.output_path = Path(self.output_path)

    def handle_error(self, message: str) -> None:
        """Logs an error and raises ValueError."""
        logger.error(message)
        raise ValueError(message)

@dataclass
class CompareArguments(BaseArguments):
    """Arguments for the compare_compression tool."""
    config: str = 'config.toml'
    quality: Optional[int] = oc.DEFAULT_QUALITY
    decimals: Optional[int] = None
    report_format: str = 'html'
    report_suffix: str = '_comp'
    cog: bool = True

    def __post_init__(self) -> None:
        """Validation for compare_compression arguments."""
        try:
            self._validate_compare()
        except ValueError as e:
            self.handle_error(str(e))

    def _validate_compare(self) -> None:
        """Perform validation checks for compare_compression arguments."""
        if self.input_path and isinstance(self.input_path, Path):
            if not self.input_path.exists():
                raise ValueError(f"Baseline file not found: {self.input_path}")
        if self.output_path and isinstance(self.output_path, Path):
            if not self.output_path.exists():
                raise ValueError(f"Comparison file not found: {self.output_path}")

@dataclass
class OptimizeArguments(BaseArguments):
    """Arguments for optimize_compression tools."""
    product_type: Optional[str] = None
    raster_type: Optional[str] = None
    algorithm: Optional[str] = None
    vertical_srs: Optional[str] = None
    nodata: Optional[float] = None
    decimals: Optional[int] = None
    predictor: Optional[int] = None
    max_z_error: Optional[float] = None
    level: Optional[int] = None
    quality: Optional[int] = None
    geo_metadata: bool = False
    write_pam_xml: bool = True
    tile_size: int = 512
    mask_alpha: Optional[bool] = None
    mask_nodata: Optional[bool] = None
    cog: bool = True
    overviews: bool = True
    report_format: str = 'html'
    report_suffix: str = '_comp'

    def __post_init__(self) -> None:
        """Validation and default resolution for optimization arguments."""
        super().__post_init__()
        try:
            self._validate_optimize()
            self._resolve_defaults()
        except ValueError as e:
            self.handle_error(str(e))

    def _validate_optimize(self) -> None:
        """Perform validation checks for optimization arguments."""
        if self.input_path and isinstance(self.input_path, Path):
            if not self.input_path.exists():
                raise ValueError(f"Input file not found: {self.input_path}")
            if self.algorithm in [CA.JPEG.value, CA.JXL.value] and self.product_type != PT.IMAGE.value:
                raise ValueError(f"{self.algorithm} compression is only suitable for imagery products.")
            if self.algorithm == CA.LERC.value and self.product_type not in [PT.DEM.value, PT.ERROR.value, PT.SCIENTIFIC.value]:
                raise ValueError("LERC compression is not optimal for image or thematic products.")
            if self.product_type == PT.DEM.value and self.vertical_srs is None:
                raise ValueError("Vertical SRS must be specified for DEM product type.")
            if self.product_type == PT.THEMATIC.value and self.mask_nodata is True:
                raise ValueError("Thematic products should not have transparency masks.")

            # Lightweight check for single-band restriction on DEM, ERROR, and THEMATIC types
            if self.product_type in [PT.DEM.value, PT.ERROR.value, PT.THEMATIC.value]:
                try:
                    ds = gdal.Open(str(self.input_path), gdal.GA_ReadOnly)
                    if ds:
                        if ds.RasterCount > 1:
                            raise ValueError(f"Multi-band rasters ({ds.RasterCount} bands) are not supported for '{self.product_type}' product type. Use 'image' or 'scientific' instead.")
                        ds = None
                except Exception as e:
                    if "Multi-band rasters" in str(e):
                        raise
                    pass

    def _resolve_defaults(self) -> None:
        """Set context-aware default values."""
        if self.product_type is None:
            raise ValueError("The 'product_type' argument is required.")
        
        if self.algorithm is None:
            self.algorithm = CA.JPEG.value if self.product_type == PT.IMAGE.value else CA.DEFLATE.value

        if self.algorithm in [CA.JPEG.value, CA.JXL.value] and self.quality is None:
            self.quality = oc.DEFAULT_QUALITY
        
        if self.algorithm == CA.DEFLATE.value and self.level is None:
            self.level = oc.DEFAULT_DEFLATE_LEVEL
        elif self.algorithm == CA.ZSTD.value and self.level is None:
            self.level = oc.DEFAULT_ZSTD_LEVEL

        if self.algorithm == CA.LERC.value:
            if self.max_z_error is None:
                self.max_z_error = oc.default_max_z_error_for(self.product_type)
            self.decimals = None
        
        if self.algorithm in [CA.DEFLATE.value, CA.ZSTD.value, CA.LZW.value]:
            if self.decimals is None:
                self.decimals = oc.default_decimals_for(self.product_type, self.algorithm)
            if self.predictor is None:
                self.predictor = oc.default_predictor_for(self.product_type)

        if self.mask_alpha is None:
            self.mask_alpha = True

        if self.mask_nodata is None:
            self.mask_nodata = (self.product_type == PT.IMAGE.value)

        if self.product_type == PT.THEMATIC.value:
            self.mask_nodata = False
            self.mask_alpha = False

@dataclass
class TestArguments(OptimizeArguments):
    """Arguments for the test_compression tool."""
    csv_path: Optional[Path] = None
    product_type: Optional[str] = None
    temp_dir: Optional[Path] = None
    delete_test_files: bool = False
    log_file: Optional[Path] = None
    optimize_script_path: Optional[Path] = None

    def __post_init__(self) -> None:
        """Validation for test_compression arguments."""
        super().__post_init__()
        try:
            self._validate_test()
        except ValueError as e:
            self.handle_error(str(e))

    def _validate_test(self) -> None:
        """Perform validation checks for test-compression arguments."""
        if self.input_path is None:
            raise ValueError("The 'input_path' argument is required for test-compression.")
        if self.csv_path is None and self.product_type is None:
            raise ValueError("Either 'csv_path' or 'product_type' must be provided for test-compression.")
        if self.csv_path and not self.csv_path.is_file():
            raise ValueError(f"Input CSV not found: {self.csv_path}")

    def _validate_optimize(self) -> None:
        """
        Override parent validation. TestArguments acts as a runner config;
        specific compression parameters (like vertical_srs) are supplied
        per-test-case via CSV, not at the runner level.
        """
        pass

@dataclass
class ReadArguments(BaseArguments):
    """Arguments for the read_metadata tool."""
    sections: Optional[List[str]] = None
    reader_type: Optional[str] = None
    page: int = 0
    xml_type: Optional[str] = None
    tag_scope: Optional[str] = None
    banner: Optional[str] = None
    report_format: str = 'html'
    report_suffix: str = '_meta'
    write_pam_xml: bool = True


@dataclass
class ValidateArguments(BaseArguments):
    """
    Arguments for the validate_metadata tool.

    Validates GeoTIFF files against product-specific requirements
    using TOML-based validation rules.

    Attributes:
        product: Validation product name (e.g., 'DGED5', 'GLO-30')
        rules_dir: Directory containing TOML validation rule files
        sections: Optional list of sections to validate
        name_string: Filter files by name substring (directory mode only)
        output_dir: Optional parent directory for output folder
        write_reports: Whether to write individual HTML/MD reports
        report_format: Report format ('html' or 'md')
        output_folder: Computed path to output folder (set in __post_init__)
        json_output_path: Computed path to JSON output file (set in __post_init__)
        gpkg_output_path: Computed path to GeoPackage output file (set in __post_init__)
    """
    product: Optional[str] = None
    rules_dir: Path = field(default_factory=lambda: Path('gttk/resources/rules'))
    sections: Optional[List[str]] = None
    name_string: str = ''
    output_dir: Optional[Path] = None
    write_reports: bool = True
    report_format: str = 'html'

    # Computed paths (set in __post_init__)
    output_folder: Optional[Path] = field(default=None, init=False)
    json_output_path: Optional[Path] = field(default=None, init=False)
    gpkg_output_path: Optional[Path] = field(default=None, init=False)

    def __post_init__(self) -> None:
        """Validation for validate_metadata arguments."""
        super().__post_init__()
        try:
            self._validate_arguments()
            self._setup_output_paths()
        except ValueError as e:
            self.handle_error(str(e))

    def _validate_arguments(self) -> None:
        """Perform validation checks for validate arguments."""
        if self.input_path is None:
            raise ValueError("The 'input_path' argument is required.")

        if not self.input_path.exists():
            raise ValueError(f"Input path not found: {self.input_path}")

        # Accept both files and directories
        if self.input_path.is_file():
            # Single file mode
            if self.input_path.suffix.lower() not in ['.tif', '.tiff']:
                raise ValueError("Input file must be a GeoTIFF (.tif or .tiff)")

            # Warn if name_string provided for single file (ignored)
            if self.name_string:
                logger.warning(
                    f"--name-string '{self.name_string}' is only applicable when "
                    f"--input is a directory. Ignoring for single file validation."
                )

        elif self.input_path.is_dir():
            # Directory/batch mode
            geotiffs = list(self.input_path.glob('*.tif')) + list(self.input_path.glob('*.tiff'))

            if not geotiffs:
                raise ValueError(f"No GeoTIFF files found in directory: {self.input_path}")

            # Apply name filter if provided
            if self.name_string:
                filtered = [f for f in geotiffs if self.name_string in f.name]
                if not filtered:
                    raise ValueError(
                        f"No GeoTIFF files matching name string '{self.name_string}' "
                        f"found in directory: {self.input_path}"
                    )
                logger.info(
                    f"Name filter '{self.name_string}': {len(filtered)} of {len(geotiffs)} files match"
                )
        else:
            raise ValueError(f"Input path must be a file or directory: {self.input_path}")

        # Validate rules directory
        if not self.rules_dir.exists():
            raise ValueError(f"Rules directory not found: {self.rules_dir}")

        if not self.rules_dir.is_dir():
            raise ValueError(f"Rules path is not a directory: {self.rules_dir}")

        # Check for at least one .toml file
        toml_files = list(self.rules_dir.glob('*.toml'))
        if not toml_files:
            raise ValueError(f"No TOML rule files found in: {self.rules_dir}")

        # Validate product is provided
        if self.product is None:
            raise ValueError("The 'product' argument is required.")

    def _setup_output_paths(self) -> None:
        """Setup output folder, JSON file, and GeoPackage paths."""
        # Import here to avoid circular dependency
        from gttk.utils.validation.output import generate_output_paths

        # input_path is guaranteed to be not None by _validate_arguments()
        assert self.input_path is not None, "input_path must be validated before calling _setup_output_paths"

        self.output_folder, self.json_output_path, self.gpkg_output_path = generate_output_paths(
            self.input_path,
            self.output_dir
        )

        # Create output folder
        if not self.output_folder.exists():
            self.output_folder.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created output directory: {self.output_folder}")