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
Validate Metadata Tool.

This module provides the main entry point for the `gttk validate` command,
which validates GeoTIFF files against product-specific requirements defined
in TOML rule files.

The tool supports:
- Single file and batch (directory) validation
- Name-based filtering for mixed-product directories
- Product-specific validation rules
- JSON output with optional HTML/MD reports
- PASS/FAIL file naming convention
"""

import json
import logging
import math
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Dict, List, Any, Optional, cast

try:
    __version__ = metadata.version("geotiff-toolkit")
except metadata.PackageNotFoundError:
    __version__ = "0.0.0-dev"

from gttk.utils.gdal_env import gdal_env
from gttk.utils.script_arguments import ValidateArguments
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.path_helpers import open_file, find_xml_metadata_file
from gttk.utils.report_builders import ValidationReportBuilder
from gttk.utils.report_formatters import HtmlReportFormatter, MarkdownReportFormatter
from gttk.utils.validation import (
    load_validation_rules,
    ValidationEngine,
    ValidationResult,
    ValidationSummary,
    get_section_display_name,
)
from gttk.utils.validation.gpkg_writer import write_validation_gpkg
from gttk.utils.validation.output import get_input_files, generate_report_path, generate_output_paths
from gttk.utils.validate_cloud_optimized_geotiff import validate as validate_cog
from gttk.utils.geotiff_processor import calculate_compression_efficiency, compression_ratio

logger = logging.getLogger(__name__)


def validate_metadata(args: ValidateArguments) -> None:
    """Public entry point: applies GTTK's GDAL settings for this call only.

    The settings are restored afterwards, so importing this module does not
    change GDAL's behaviour for the rest of the host process.
    """
    with gdal_env():
        return _validate_metadata_inner(args)


def _validate_metadata_inner(args: ValidateArguments) -> None:
    """
    Main entry point for the validate_metadata tool.

    Validates GeoTIFF files against product-specific requirements
    defined in TOML rule files.

    Args:
        args: ValidateArguments instance with validated arguments
    """
    # These fields are validated in ValidateArguments.__post_init__()
    # and are guaranteed to be non-None after construction
    assert args.input_path is not None, "input_path validated in __post_init__"
    assert args.product is not None, "product validated in __post_init__"
    assert args.output_folder is not None, "output_folder set in __post_init__"
    assert args.json_output_path is not None, "json_output_path set in __post_init__"
    assert args.gpkg_output_path is not None, "gpkg_output_path set in __post_init__"

    logger.info(f"Validate Metadata Tool")
    logger.info(f"Input: {args.input_path}")
    logger.info(f"Product: {args.product}")

    # Get list of files to process
    input_files = get_input_files(args.input_path, args.name_filter)

    # Log processing mode
    if args.input_path.is_file():
        logger.info(f"Single file validation: {args.input_path.name}")
    else:
        total_in_dir = len(get_input_files(args.input_path))
        if args.name_filter:
            logger.info(
                f"Batch validation with name filter '{args.name_filter}': "
                f"{len(input_files)} of {total_in_dir} files"
            )
        else:
            logger.info(f"Batch validation: {len(input_files)} files")

    # Load validation rules (reuse for all files)
    try:
        rules_by_section, rules_file = load_validation_rules(
            args.rules_dir,
            args.product,
            args.sections
        )

        total_rules = sum(len(rules) for rules in rules_by_section.values())
        logger.info(f"Loaded {total_rules} rules from {rules_file}")

        for section, rules in rules_by_section.items():
            logger.debug(f"  - {section}: {len(rules)} rules")

    except ValueError as e:
        logger.error(f"Failed to load validation rules: {e}")
        raise

    # Process each file
    all_file_results = []
    files_passed = 0
    files_failed = 0
    files_skipped = 0

    for input_file in input_files:
        logger.info(f"Validating: {input_file.name}")

        try:
            file_result = validate_single_file(
                input_file,
                rules_by_section,
                args.product,
                rules_file,
                output_folder=args.output_folder,
                write_reports=args.write_reports,
                report_format=args.report_format
            )
            all_file_results.append(file_result)

            # Track file-level status
            if file_result['failed'] > 0:
                files_failed += 1
                logger.info(f"  Result: FAIL ({file_result['failed']} failures)")
            elif file_result['passed'] > 0:
                files_passed += 1
                logger.info(f"  Result: PASS ({file_result['passed']} passed)")
            else:
                files_skipped += 1
                logger.info(f"  Result: SKIP ({file_result['skipped']} skipped)")

        except Exception as e:
            logger.error(f"  Error validating {input_file.name}: {e}")
            # Create error result
            all_file_results.append({
                'name': input_file.name,
                'path': str(input_file),
                'error': str(e),
                'total_rules': 0,
                'passed': 0,
                'failed': 0,
                'skipped': 0,
                'validation': {}
            })
            files_failed += 1

    # Build and save JSON output
    report_data = build_json_report(
        args.product,
        rules_file,
        all_file_results,
        files_passed,
        files_failed,
        files_skipped
    )

    # Write JSON output
    with open(args.json_output_path, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2)

    logger.info(f"Validation results saved to: {args.json_output_path}")

    # Write GeoPackage output
    gpkg_result = write_validation_gpkg(
        args.gpkg_output_path,
        all_file_results,
        args.product
    )
    if gpkg_result:
        logger.info(f"GeoPackage output saved to: {args.gpkg_output_path}")

    # Summary
    logger.info(f"Summary: {files_passed} passed, {files_failed} failed, {files_skipped} skipped")

    # Open report if requested
    if args.open_report:
        try:
            open_file(str(args.json_output_path))
            logger.info(f"Opened report: {args.json_output_path}")
        except Exception as e:
            logger.warning(f"Could not open report: {e}")


def validate_single_file(
    filepath: Path,
    rules_by_section: Dict[str, List],
    product: str,
    rules_file: str,
    output_folder: Optional[Path] = None,
    write_reports: bool = False,
    report_format: str = 'html'
) -> Dict[str, Any]:
    """
    Validate a single GeoTIFF file.

    Args:
        filepath: Path to the GeoTIFF file
        rules_by_section: Dict mapping section names to rule lists
        product: Product name for logging
        rules_file: Name of the rules file
        output_folder: Optional output folder for reports
        write_reports: Whether to write HTML/MD reports
        report_format: Report format ('html' or 'md')

    Returns:
        Dict containing validation results for this file
    """
    with MetadataExtractor(str(filepath)) as extractor:
        # Run validation
        engine = ValidationEngine(extractor)
        results_by_section = engine.validate_all_sections(rules_by_section)

        # Extract file metadata while extractor is still open
        properties = extract_file_properties(filepath)
        structure = extract_file_structure(extractor)
        compression = extract_compression_info(extractor, filepath)
        geometry = extract_geometry_info(extractor)
        statistics = extract_statistics_for_json(extractor)
        tiling = extract_tiling_for_json(extractor)
        ifd = extract_ifd_for_json(extractor)

    # Count results
    total = 0
    passed = 0
    failed = 0
    skipped = 0

    for section_results in results_by_section.values():
        for result in section_results:
            total += 1
            if result.passed:
                passed += 1
            elif result.failed:
                failed += 1
            else:
                skipped += 1

    # Build result dictionary
    validation_dict: Dict[str, List[Dict[str, Any]]] = {}
    for section, section_results in results_by_section.items():
        validation_dict[section] = [
            format_result_for_json(result)
            for result in section_results
        ]

    # Generate HTML/MD report if requested
    report_path = None
    if write_reports and output_folder:
        summary = build_validation_summary(
            filepath, product, rules_file, results_by_section
        )
        report_path = generate_validation_report(
            summary, output_folder, report_format
        )

    # Build complete file result with all metadata sections
    result_dict: Dict[str, Any] = {
        'name': filepath.name,
        'path': str(filepath),
        'properties': properties,
        'structure': structure,
        'compression': compression,
        'geometry': geometry,
        'statistics': statistics,
        'tiling': tiling,
        'ifd': ifd,
        'validation': validation_dict,
        'total_rules': total,
        'passed': passed,
        'failed': failed,
        'skipped': skipped,
    }

    if report_path:
        result_dict['report_path'] = str(report_path)

    return result_dict


def format_result_for_json(result: ValidationResult) -> Dict[str, Any]:
    """
    Format a ValidationResult for JSON output.

    Args:
        result: ValidationResult to format

    Returns:
        Dict suitable for JSON serialization
    """
    return {
        'key': result.rule.key,
        'description': result.rule.description,
        'constraint': result.rule.constraint,
        'expected': result.rule.expected,
        'actual': result.value,
        'status': result.status,
        'message': result.message,
        'optional': result.rule.optional
    }


def extract_file_properties(filepath: Path) -> Dict[str, Any]:
    """
    Extract file system properties.

    Args:
        filepath: Path to the GeoTIFF file

    Returns:
        Dict containing file properties
    """
    file_stat = filepath.stat()
    size_mb = file_stat.st_size / (1024 * 1024)

    # Get creation time
    try:
        creation_time = getattr(file_stat, 'st_birthtime', file_stat.st_ctime)
        created = datetime.fromtimestamp(creation_time, timezone.utc).isoformat()
    except Exception:
        created = None

    # Get modification time
    try:
        modified = datetime.fromtimestamp(file_stat.st_mtime, timezone.utc).isoformat()
    except Exception:
        modified = None

    return {
        'size_mb': round(size_mb, 2),
        'created': created,
        'modified': modified
    }


def extract_file_structure(extractor: MetadataExtractor) -> Dict[str, Any]:
    """
    Extract GeoTIFF structural information.

    Args:
        extractor: MetadataExtractor instance

    Returns:
        Dict containing file structure info
    """
    # COG validation
    is_cog = False
    if extractor.gdal_ds:
        _, cog_errors, _ = validate_cog(extractor.gdal_ds, full_check=True)
        is_cog = len(cog_errors) == 0

    # Overview check
    has_overviews = False
    if extractor.gdal_ds and extractor.gdal_ds.RasterCount > 0:
        band = extractor.gdal_ds.GetRasterBand(1)
        if band:
            has_overviews = band.GetOverviewCount() > 0

    # Mask check
    has_mask = False
    if extractor.geotiff_info:
        has_mask = extractor.geotiff_info.transparency_info.get('has_mask', False)

    # Alpha check
    has_alpha = extractor.geotiff_info.has_alpha if extractor.geotiff_info else False

    # External files check
    xml_file = find_xml_metadata_file(extractor.filepath)
    has_external_xml = xml_file is not None

    ovr_path = extractor.filepath.with_suffix(extractor.filepath.suffix + '.ovr')
    has_external_ovr = ovr_path.exists()

    # GeoTIFF version
    version = extractor.extract_geotiff_version() if extractor.is_geotiff else None

    return {
        'is_geotiff': extractor.is_geotiff,
        'is_bigtiff': extractor.geotiff_info.is_bigtiff if extractor.geotiff_info else False,
        'is_cog': is_cog,
        'has_overviews': has_overviews,
        'has_mask': has_mask,
        'has_alpha': has_alpha,
        'has_external_xml': has_external_xml,
        'has_external_ovr': has_external_ovr,
        'version': version
    }


def extract_compression_info(extractor: MetadataExtractor, filepath: Path) -> Dict[str, Any]:
    """
    Extract compression characteristics.

    Args:
        extractor: MetadataExtractor instance
        filepath: Path to the file

    Returns:
        Dict containing compression info
    """
    algorithm = 'NONE'
    if extractor.gdal_ds:
        algorithm = extractor.gdal_ds.GetMetadataItem('COMPRESSION', 'IMAGE_STRUCTURE') or 'NONE'

    # Calculate efficiency
    # None means the efficiency could not be determined; 0.0 is a real answer (an
    # uncompressed file) and reports as 0.0 savings and a 1.0 ratio, not as nothing.
    efficiency = calculate_compression_efficiency(str(filepath))
    savings = round(efficiency / 100, 4) if efficiency is not None else None
    ratio_value = compression_ratio(efficiency)
    ratio = round(ratio_value, 2) if ratio_value is not None else None

    return {
        'algorithm': algorithm,
        'savings': savings,
        'ratio': ratio
    }


def extract_geometry_info(extractor: MetadataExtractor) -> Dict[str, Any]:
    """
    Extract spatial geometry and CRS information.

    Args:
        extractor: MetadataExtractor instance

    Returns:
        Dict containing geometry info
    """
    result: Dict[str, Any] = {
        'area_sq_km': None,
        'hsrs_epsg': None,
        'hsrs_name': None,
        'vsrs_epsg': None,
        'vsrs_name': None,
        'horizontal_unit': None,
        'vertical_unit': None,
        'wgs84_coordinates': None,
        'native_bbox': None
    }

    if not extractor.geotiff_info:
        return result

    info = extractor.geotiff_info
    proj_info = info.projection_info or {}

    # CRS info from projection_info
    if proj_info.get('is_projected'):
        result['hsrs_epsg'] = _safe_int(proj_info.get('projected_cs_code'))
        result['hsrs_name'] = proj_info.get('projected_cs_name')
    elif proj_info.get('is_geographic'):
        result['hsrs_epsg'] = _safe_int(proj_info.get('geographic_cs_code'))
        result['hsrs_name'] = proj_info.get('geographic_cs_name')

    # Vertical CRS
    if proj_info.get('is_compound'):
        result['vsrs_epsg'] = _safe_int(proj_info.get('vertical_cs_code'))
        result['vsrs_name'] = proj_info.get('vertical_cs_name')

    # Units
    result['horizontal_unit'] = proj_info.get('linear_unit_name') or proj_info.get('angular_unit_name')
    result['vertical_unit'] = proj_info.get('vertical_unit_name')

    # Native bounding box
    if info.native_bbox:
        result['native_bbox'] = info.native_bbox

    # Geographic corners as GeoJSON polygon
    if info.geographic_corners:
        corners = info.geographic_corners
        try:
            # Build GeoJSON polygon from corners
            ul = corners.get('Upper Left', (0, 0))
            ur = corners.get('Upper Right', (0, 0))
            lr = corners.get('Lower Right', (0, 0))
            ll = corners.get('Lower Left', (0, 0))

            # GeoJSON polygon coordinates (closed ring)
            result['wgs84_coordinates'] = [[[ul[0], ul[1]], [ur[0], ur[1]], [lr[0], lr[1]], [ll[0], ll[1]], [ul[0], ul[1]]]]

            # Calculate area from bbox
            if info.native_bbox:
                width = abs(info.native_bbox.get('east', 0) - info.native_bbox.get('west', 0))
                height = abs(info.native_bbox.get('north', 0) - info.native_bbox.get('south', 0))

                # If geographic CRS, approximate with meters
                if proj_info.get('is_geographic'):
                    # Rough conversion at mid-latitude
                    mid_lat = (ul[1] + ll[1]) / 2
                    meters_per_degree = 111320 * math.cos(math.radians(mid_lat))
                    area_sq_m = width * meters_per_degree * height * 111320
                else:
                    area_sq_m = width * height

                result['area_sq_km'] = round(area_sq_m / 1_000_000, 2)
        except Exception:
            pass

    return result


def _safe_int(value: Any) -> Optional[int]:
    """Safely convert value to int, returning None on failure."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def extract_statistics_for_json(extractor: MetadataExtractor) -> List[Dict[str, Any]]:
    """
    Extract band statistics for JSON output.

    Args:
        extractor: MetadataExtractor instance

    Returns:
        List of dicts containing per-band statistics
    """
    stats = extractor.extract_statistics()
    if not stats:
        return []

    result: List[Dict[str, Any]] = []
    for idx, stat in enumerate(stats):
        stat_dict: Dict[str, Any] = {
            'band': idx + 1,
            'band_name': stat.band_name,
            'nodata_value': stat.nodata_value,
            'valid_percent': stat.valid_percent,
            'valid_count': stat.valid_count,
            'nodata_count': stat.nodata_count,
            'minimum': stat.minimum,
            'maximum': stat.maximum,
            'mean': stat.mean,
            'std_dev': stat.std_dev,
        }
        result.append(stat_dict)

    return result


def extract_tiling_for_json(extractor: MetadataExtractor) -> List[Dict[str, Any]]:
    """
    Extract tiling/overview information for JSON output.

    Args:
        extractor: MetadataExtractor instance

    Returns:
        List of dicts containing tiling info per level
    """
    tiles = extractor.extract_tile_info()
    if not tiles:
        return []

    result: List[Dict[str, Any]] = []
    for tile in tiles:
        result.append({
            'level': tile.level,
            'tile_count': tile.tile_count,
            'block_size': tile.block_size,
            'tile_dimensions': tile.tile_dimensions,
            'total_pixels': tile.total_pixels,
            'resolution': tile.resolution
        })

    return result


def extract_ifd_for_json(extractor: MetadataExtractor) -> List[Dict[str, Any]]:
    """
    Extract IFD information for JSON output.

    Args:
        extractor: MetadataExtractor instance

    Returns:
        List of dicts containing IFD info
    """
    ifds = extractor.extract_ifd_info()
    if not ifds:
        return []

    result: List[Dict[str, Any]] = []
    for ifd in ifds:
        result.append({
            'ifd': ifd.ifd,
            'ifd_type': ifd.ifd_type,
            'dimensions': ifd.dimensions,
            'block_size': ifd.block_size,
            'data_type': ifd.data_type,
            'decimals': ifd.decimals,
            'bands': ifd.bands,
            'bits_per_sample': ifd.bits_per_sample,
            'photometric': ifd.photometric,
            'compression_algorithm': ifd.compression_algorithm,
            'predictor': ifd.predictor,
            'lerc_max_z_error': ifd.lerc_max_z_error,
            'space_saving': ifd.space_saving,
        })

    return result


def build_json_report(
    product: str,
    rules_file: str,
    file_results: List[Dict],
    files_passed: int,
    files_failed: int,
    files_skipped: int
) -> Dict[str, Any]:
    """
    Build the complete JSON report structure.

    Args:
        product: Product name
        rules_file: Name of the rules file used
        file_results: List of per-file result dictionaries
        files_passed: Count of files that passed
        files_failed: Count of files that failed
        files_skipped: Count of files that were skipped

    Returns:
        Dict containing the complete report structure
    """
    return {
        'product': product,
        'rules_file': rules_file,
        'report_date': datetime.now().isoformat(),
        'gttk_version': __version__,
        'total_files': len(file_results),
        'files_passed': files_passed,
        'files_failed': files_failed,
        'files_skipped': files_skipped,
        'files': file_results
    }


def build_validation_summary(
    filepath: Path,
    product: str,
    rules_file: str,
    results_by_section: Dict[str, List[ValidationResult]]
) -> ValidationSummary:
    """
    Build a ValidationSummary from results.

    Args:
        filepath: Path to the validated file
        product: Product name
        rules_file: Name of the rules file
        results_by_section: Dict of section results

    Returns:
        ValidationSummary instance
    """
    total = 0
    passed = 0
    failed = 0
    skipped = 0

    for section_results in results_by_section.values():
        for result in section_results:
            total += 1
            if result.passed:
                passed += 1
            elif result.failed:
                failed += 1
            else:
                skipped += 1

    return ValidationSummary(
        product=product,
        input_file=filepath.name,
        rules_file=rules_file,
        report_date=datetime.now().strftime('%Y-%m-%d'),
        total_rules=total,
        passed=passed,
        failed=failed,
        skipped=skipped,
        results_by_section=results_by_section
    )


def generate_validation_report(
    summary: ValidationSummary,
    output_folder: Path,
    report_format: str
) -> Path:
    """
    Generate HTML or Markdown validation report.

    Args:
        summary: ValidationSummary containing validation results
        output_folder: Output folder for the report
        report_format: Report format ('html' or 'md')

    Returns:
        Path to the generated report file
    """
    # Build sections using ValidationReportBuilder
    builder = ValidationReportBuilder(summary)
    builder.build()

    # Generate report path with PASS/FAIL suffix
    # Use Path to reconstruct from string if needed
    input_file = Path(summary.input_file)
    report_path = generate_report_path(
        input_file,
        output_folder,
        summary.overall_status,
        report_format
    )

    # Create formatter based on format
    if report_format == 'html':
        formatter = HtmlReportFormatter(
            filename=summary.input_file,
            report_type='validation'
        )
        formatter.report_title = f"Validation Report: {summary.product}"
        formatter.include_title = True
    else:
        formatter = MarkdownReportFormatter(filename=summary.input_file)
        formatter.report_title = f"Validation Report: {summary.product}"
        formatter.include_title = True

    # Set sections from builder
    formatter.sections = builder.sections

    # Generate report content
    report_content = formatter.format()

    # Write to file
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)

    logger.debug(f"Generated validation report: {report_path}")
    return report_path
