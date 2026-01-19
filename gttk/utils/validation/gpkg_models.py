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
GeoPackage Data Models for Validation Package.

This module defines the data model for GeoPackage features created from
validation results. Each GeoPackageFeature represents a validated GeoTIFF
file with its metadata attributes and WGS84 geometry.

Classes:
    GeoPackageFeature: Dataclass representing a feature in the validation GeoPackage
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class GeoPackageFeature:
    """
    Data model for a GeoPackage feature representing a validated GeoTIFF file.

    Features are assigned to PASSED/FAILED/SKIPPED layers based on validation
    results. Each feature contains file metadata, structural properties, and
    WGS84 geometry for spatial visualization.

    Attributes:
        status: Validation status string (e.g., "PASS", "FAIL", "SKIP")
        name: TIF filename (no path, just the filename)
        size_mb: File size in megabytes
        resolution: Resolution string from tiling info (e.g., "1.0 m")
        rows: Raster height in pixels
        columns: Raster width in pixels
        area_sq_km: Coverage area in square kilometers
        geotiff_version: GeoTIFF specification version
        is_geotiff: Whether file is a valid GeoTIFF
        is_bigtiff: Whether file uses BigTIFF format
        is_cog: Whether file is Cloud-Optimized GeoTIFF
        has_mask: Whether file has a transparency mask
        has_alpha: Whether file has an alpha channel
        has_external_xml: Whether external XML metadata file exists
        has_external_ovr: Whether external overview file exists
        has_internal_ovr: Whether file has internal overviews
        internal_ovr_count: Number of internal overview levels
        data_type: GDAL data type (e.g., "Float32", "Byte")
        decimals: Decimal precision for floating-point data
        bands: Number of raster bands
        compression_algorithm: Compression algorithm (e.g., "DEFLATE", "LERC")
        compression_ratio: Compression ratio (uncompressed/compressed)
        space_savings: Space savings as decimal (0-1)
        hsrs_epsg: Horizontal CRS EPSG code
        hsrs_name: Horizontal CRS name
        vsrs_epsg: Vertical CRS EPSG code
        vsrs_name: Vertical CRS name
        horizontal_unit: Horizontal unit name
        vertical_unit: Vertical unit name
        passed: Number of validation rules passed
        failed: Number of validation rules failed
        skipped: Number of validation rules skipped
        wgs84_coordinates: GeoJSON polygon coordinates in WGS84
    """

    # Core identification
    status: str
    name: str

    # File properties
    size_mb: float

    # Dimensions and resolution
    resolution: Optional[str]
    rows: Optional[int]
    columns: Optional[int]

    # Geometry
    area_sq_km: Optional[float]

    # Structure flags
    geotiff_version: Optional[str]
    is_geotiff: bool
    is_bigtiff: bool
    is_cog: bool
    has_mask: bool
    has_alpha: bool
    has_external_xml: bool
    has_external_ovr: bool
    has_internal_ovr: bool
    internal_ovr_count: int

    # IFD 0 properties
    data_type: Optional[str]
    decimals: Optional[int]
    bands: Optional[int]

    # Compression
    compression_algorithm: Optional[str]
    compression_ratio: Optional[float]
    space_savings: Optional[float]

    # CRS
    hsrs_epsg: Optional[int]
    hsrs_name: Optional[str]
    vsrs_epsg: Optional[int]
    vsrs_name: Optional[str]
    horizontal_unit: Optional[str]
    vertical_unit: Optional[str]

    # Validation counts
    passed: int
    failed: int
    skipped: int

    # Geometry (GeoJSON coordinates)
    wgs84_coordinates: Optional[List]

    @property
    def layer_name(self) -> str:
        """
        Determine the GeoPackage layer name based on validation status.

        Returns:
            'FAILED' if any rules failed
            'PASSED' if any rules passed and none failed
            'SKIPPED' if all rules were skipped or none provided
        """
        if self.failed > 0:
            return 'FAILED'
        elif self.passed > 0:
            return 'PASSED'
        return 'SKIPPED'

    @classmethod
    def from_json_result(cls, file_result: Dict[str, Any]) -> GeoPackageFeature:
        """
        Factory method to create a GeoPackageFeature from validation JSON result.

        Args:
            file_result: Dict containing validation results for a single file
                         (as stored in the 'files' array of JSON output)

        Returns:
            GeoPackageFeature instance populated from the JSON result
        """
        # compute 4-char status from file_result
        status = ('FAIL' if file_result.get('failed', 0) > 0
                  else 'PASS' if file_result.get('passed', 0) > 0
                  else 'SKIP')

        properties = file_result.get('properties', {})
        structure = file_result.get('structure', {})
        compression = file_result.get('compression', {})
        geometry = file_result.get('geometry', {})
        tiling = file_result.get('tiling', [])
        ifd = file_result.get('ifd', [])

        # Extract resolution from first tiling entry
        resolution = None
        if tiling and len(tiling) > 0:
            resolution = tiling[0].get('resolution')

        # Parse dimensions from IFD 0 or tiling info
        rows = None
        columns = None
        if ifd and len(ifd) > 0:
            dims_str = ifd[0].get('dimensions', '')
            columns, rows = _parse_dimensions(dims_str)
        elif tiling and len(tiling) > 0:
            pixels_str = tiling[0].get('total_pixels', '')
            columns, rows = _parse_dimensions(pixels_str)

        # Get IFD 0 properties
        data_type = None
        decimals = None
        bands = None
        if ifd and len(ifd) > 0:
            ifd0 = ifd[0]
            data_type = ifd0.get('data_type')
            decimals = ifd0.get('decimals')
            bands = ifd0.get('bands')

        # Count internal overviews
        internal_ovr_count = 0
        if structure.get('has_overviews') and ifd:
            internal_ovr_count = len([i for i in ifd if i.get('ifd_type').lower() == 'overview'])

        return cls(
            # status determined by layer name
            status=status,
            name=file_result.get('name', ''),
            size_mb=properties.get('size_mb', 0.0),
            resolution=resolution,
            rows=rows,
            columns=columns,
            area_sq_km=geometry.get('area_sq_km'),
            geotiff_version=structure.get('version'),
            is_geotiff=structure.get('is_geotiff', False),
            is_bigtiff=structure.get('is_bigtiff', False),
            is_cog=structure.get('is_cog', False),
            has_mask=structure.get('has_mask', False),
            has_alpha=structure.get('has_alpha', False),
            has_external_xml=structure.get('has_external_xml', False),
            has_external_ovr=structure.get('has_external_ovr', False),
            has_internal_ovr=structure.get('has_overviews', False),
            internal_ovr_count=internal_ovr_count,
            data_type=data_type,
            decimals=decimals,
            bands=bands,
            compression_algorithm=compression.get('algorithm'),
            compression_ratio=compression.get('ratio'),
            space_savings=compression.get('savings'),
            hsrs_epsg=geometry.get('hsrs_epsg'),
            hsrs_name=geometry.get('hsrs_name'),
            vsrs_epsg=geometry.get('vsrs_epsg'),
            vsrs_name=geometry.get('vsrs_name'),
            horizontal_unit=geometry.get('horizontal_unit'),
            vertical_unit=geometry.get('vertical_unit'),
            passed=file_result.get('passed', 0),
            failed=file_result.get('failed', 0),
            skipped=file_result.get('skipped', 0),
            wgs84_coordinates=geometry.get('wgs84_coordinates'),
        )


def _parse_dimensions(dims_str: str) -> tuple:
    """
    Parse dimensions string into (width, height) tuple.

    Handles formats like "1024 x 768", "10012 x 10012", etc.

    Args:
        dims_str: Dimensions string (e.g., "1024 x 768")

    Returns:
        Tuple of (width, height) as integers, or (None, None) if parsing fails
    """
    if not dims_str:
        return None, None

    try:
        parts = dims_str.lower().split('x')
        if len(parts) == 2:
            width = int(parts[0].strip())
            height = int(parts[1].strip())
            return width, height
    except (ValueError, IndexError):
        pass

    return None, None
