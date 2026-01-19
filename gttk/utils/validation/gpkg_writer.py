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
GeoPackage Writer for Validation Package.

This module provides functions to write validation results to a GeoPackage file
with features organized into PASSED/FAILED/SKIPPED layers based on validation
status.

Functions:
    write_validation_gpkg: Main entry point to write validation GeoPackage
    create_gpkg_layer: Create a polygon layer with validation field schema
    add_feature_to_layer: Add a feature with geometry and attributes
    create_polygon_from_coordinates: Create OGR polygon from GeoJSON coordinates
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from osgeo import gdal, ogr, osr

from gttk.utils.validation.gpkg_models import GeoPackageFeature

logger = logging.getLogger(__name__)

# Suppress GDAL errors during GeoPackage operations
gdal.UseExceptions()


# Field definitions: (field_name, ogr_type, width)
# Width of 0 means use OGR default
FIELD_DEFINITIONS = [
    ('status', ogr.OFTString, 4),
    ('name', ogr.OFTString, 255),
    ('size_mb', ogr.OFTReal, 0),
    ('resolution', ogr.OFTString, 50),
    ('rows', ogr.OFTInteger, 0),
    ('columns', ogr.OFTInteger, 0),
    ('area_sq_km', ogr.OFTReal, 0),
    ('geotiff_version', ogr.OFTString, 20),
    ('is_geotiff', ogr.OFTInteger, 0),
    ('is_bigtiff', ogr.OFTInteger, 0),
    ('is_cog', ogr.OFTInteger, 0),
    ('has_mask', ogr.OFTInteger, 0),
    ('has_alpha', ogr.OFTInteger, 0),
    ('has_external_xml', ogr.OFTInteger, 0),
    ('has_external_ovr', ogr.OFTInteger, 0),
    ('has_internal_ovr', ogr.OFTInteger, 0),
    ('internal_ovr_count', ogr.OFTInteger, 0),
    ('data_type', ogr.OFTString, 20),
    ('decimals', ogr.OFTInteger, 0),
    ('bands', ogr.OFTInteger, 0),
    ('compression_algorithm', ogr.OFTString, 20),
    ('compression_ratio', ogr.OFTReal, 0),
    ('space_savings', ogr.OFTReal, 0),
    ('hsrs_epsg', ogr.OFTInteger, 0),
    ('hsrs_name', ogr.OFTString, 255),
    ('vsrs_epsg', ogr.OFTInteger, 0),
    ('vsrs_name', ogr.OFTString, 255),
    ('horizontal_unit', ogr.OFTString, 50),
    ('vertical_unit', ogr.OFTString, 50),
]

BOOLEAN_FIELDS = {
    'is_geotiff',
    'is_bigtiff',
    'is_cog',
    'has_mask',
    'has_alpha',
    'has_external_xml',
    'has_external_ovr',
    'has_internal_ovr',
}


def write_validation_gpkg(
    output_path: Path,
    file_results: List[Dict[str, Any]],
    product: str
) -> Optional[Path]:
    """
    Write validation results to GeoPackage with PASSED/FAILED/SKIPPED layers.

    Creates a GeoPackage file containing polygon features representing validated
    GeoTIFF files. Features are organized into layers based on their validation
    status. Files without valid geometry are skipped with a warning.

    Args:
        output_path: Path for the output GeoPackage file
        file_results: List of file result dictionaries from validation JSON
        product: Product name for metadata

    Returns:
        Path to created GeoPackage, or None if no features were written
    """
    if not file_results:
        logger.warning("No file results provided for GeoPackage output")
        return None

    # Convert JSON results to GeoPackageFeature objects
    features_by_layer: Dict[str, List[GeoPackageFeature]] = {
        'PASSED': [],
        'FAILED': [],
        'SKIPPED': [],
    }

    skipped_no_geometry = 0
    for result in file_results:
        feature = GeoPackageFeature.from_json_result(result)

        # Check for valid geometry
        if not feature.wgs84_coordinates:
            logger.warning(f"Skipping '{feature.name}' - no valid geometry")
            skipped_no_geometry += 1
            continue

        layer_name = feature.layer_name
        features_by_layer[layer_name].append(feature)

    # Check if we have any features to write
    total_features = sum(len(f) for f in features_by_layer.values())
    if total_features == 0:
        logger.warning("No features with valid geometry to write to GeoPackage")
        return None

    # Create WGS84 spatial reference
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)

    # Create GeoPackage
    driver = ogr.GetDriverByName('GPKG')
    if driver is None:
        logger.error("GPKG driver not available")
        return None

    # Remove existing file if present
    if output_path.exists():
        output_path.unlink()

    data_source = driver.CreateDataSource(str(output_path))
    if data_source is None:
        logger.error(f"Failed to create GeoPackage: {output_path}")
        return None

    try:
        # Create layers and add features
        layers_created = 0
        for layer_name, features in features_by_layer.items():
            if not features:
                continue

            layer = create_gpkg_layer(data_source, layer_name, srs)
            if layer is None:
                logger.error(f"Failed to create layer: {layer_name}")
                continue

            layers_created += 1

            # Use transaction for efficiency
            layer.StartTransaction()
            try:
                for feature in features:
                    add_feature_to_layer(layer, feature)
                layer.CommitTransaction()
            except Exception as e:
                layer.RollbackTransaction()
                logger.error(f"Error writing features to layer {layer_name}: {e}")
                raise

        # Set metadata
        data_source.SetMetadataItem('product', product)
        data_source.SetMetadataItem('tool', 'gttk validate')

    finally:
        # Close data source to flush to disk
        data_source = None

    if layers_created == 0:
        logger.warning("No layers created in GeoPackage")
        return None

    logger.info(
        f"GeoPackage created: {output_path} "
        f"({total_features} features, {layers_created} layers)"
    )

    if skipped_no_geometry > 0:
        logger.warning(f"Skipped {skipped_no_geometry} files without valid geometry")

    return output_path


def create_gpkg_layer(
    data_source: ogr.DataSource, # type: ignore[name-defined]
    layer_name: str,
    srs: osr.SpatialReference
) -> Optional[ogr.Layer]:
    """
    Create a polygon layer with validation field schema.

    Args:
        data_source: OGR DataSource (GeoPackage)
        layer_name: Name for the layer (PASSED/FAILED/SKIPPED)
        srs: Spatial reference system for the layer

    Returns:
        Created OGR Layer, or None on failure
    """
    layer = data_source.CreateLayer(
        layer_name,
        srs,
        ogr.wkbPolygon,
        options=['GEOMETRY_NAME=geom']
    )

    if layer is None:
        return None

    # Add field definitions
    for field_name, field_type, width in FIELD_DEFINITIONS:
        field_defn = ogr.FieldDefn(field_name, field_type)
        if field_name in BOOLEAN_FIELDS:
            field_defn.SetSubType(ogr.OFSTBoolean)
        if width > 0:
            field_defn.SetWidth(width)
        layer.CreateField(field_defn)

    return layer


def add_feature_to_layer(
    layer: ogr.Layer,
    feature: GeoPackageFeature
) -> None:
    """
    Add a GeoPackageFeature with geometry and attributes to a layer.

    Args:
        layer: OGR Layer to add feature to
        feature: GeoPackageFeature containing attributes and geometry
    """
    # Create geometry
    geometry = create_polygon_from_coordinates(feature.wgs84_coordinates)
    if geometry is None:
        logger.warning(f"Failed to create geometry for '{feature.name}'")
        return

    # Create OGR feature
    layer_defn = layer.GetLayerDefn()
    ogr_feature = ogr.Feature(layer_defn)

    # Set geometry
    ogr_feature.SetGeometry(geometry)

    # Set attribute fields
    ogr_feature.SetField('status', feature.status)
    ogr_feature.SetField('name', feature.name)
    ogr_feature.SetField('size_mb', feature.size_mb)

    if feature.resolution is not None:
        ogr_feature.SetField('resolution', feature.resolution)
    if feature.rows is not None:
        ogr_feature.SetField('rows', feature.rows)
    if feature.columns is not None:
        ogr_feature.SetField('columns', feature.columns)
    if feature.area_sq_km is not None:
        ogr_feature.SetField('area_sq_km', feature.area_sq_km)
    if feature.geotiff_version is not None:
        ogr_feature.SetField('geotiff_version', feature.geotiff_version)

    # Boolean fields as integers
    ogr_feature.SetField('is_geotiff', 1 if feature.is_geotiff else 0)
    ogr_feature.SetField('is_bigtiff', 1 if feature.is_bigtiff else 0)
    ogr_feature.SetField('is_cog', 1 if feature.is_cog else 0)
    ogr_feature.SetField('has_mask', 1 if feature.has_mask else 0)
    ogr_feature.SetField('has_alpha', 1 if feature.has_alpha else 0)
    ogr_feature.SetField('has_external_xml', 1 if feature.has_external_xml else 0)
    ogr_feature.SetField('has_external_ovr', 1 if feature.has_external_ovr else 0)
    ogr_feature.SetField('has_internal_ovr', 1 if feature.has_internal_ovr else 0)
    ogr_feature.SetField('internal_ovr_count', feature.internal_ovr_count)

    if feature.data_type is not None:
        ogr_feature.SetField('data_type', feature.data_type)
    if feature.decimals is not None:
        ogr_feature.SetField('decimals', feature.decimals)
    if feature.bands is not None:
        ogr_feature.SetField('bands', feature.bands)

    if feature.compression_algorithm is not None:
        ogr_feature.SetField('compression_algorithm', feature.compression_algorithm)
    if feature.compression_ratio is not None:
        ogr_feature.SetField('compression_ratio', feature.compression_ratio)
    if feature.space_savings is not None:
        ogr_feature.SetField('space_savings', feature.space_savings)

    if feature.hsrs_epsg is not None:
        ogr_feature.SetField('hsrs_epsg', feature.hsrs_epsg)
    if feature.hsrs_name is not None:
        ogr_feature.SetField('hsrs_name', feature.hsrs_name)
    if feature.vsrs_epsg is not None:
        ogr_feature.SetField('vsrs_epsg', feature.vsrs_epsg)
    if feature.vsrs_name is not None:
        ogr_feature.SetField('vsrs_name', feature.vsrs_name)
    if feature.horizontal_unit is not None:
        ogr_feature.SetField('horizontal_unit', feature.horizontal_unit)
    if feature.vertical_unit is not None:
        ogr_feature.SetField('vertical_unit', feature.vertical_unit)

    # Create feature in layer
    layer.CreateFeature(ogr_feature)

    # Cleanup
    ogr_feature = None


def create_polygon_from_coordinates(
    coordinates: Optional[List]
) -> Optional[ogr.Geometry]:
    """
    Create OGR Polygon from GeoJSON-style coordinates.

    Args:
        coordinates: GeoJSON polygon coordinates
                    Format: [[[lon1, lat1], [lon2, lat2], ...]]
                    (outer ring only, as list of coordinate pairs)

    Returns:
        OGR Polygon geometry, or None if coordinates are invalid
    """
    if not coordinates:
        return None

    try:
        # GeoJSON polygon has array of rings, first is outer
        if not isinstance(coordinates, list) or len(coordinates) == 0:
            return None

        outer_ring = coordinates[0]
        if not isinstance(outer_ring, list) or len(outer_ring) < 4:
            # Polygon needs at least 4 points (closed ring)
            return None

        # Create ring
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for point in outer_ring:
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                ring.AddPoint(float(point[0]), float(point[1]))

        # Create polygon
        polygon = ogr.Geometry(ogr.wkbPolygon)
        polygon.AddGeometry(ring)

        return polygon

    except (TypeError, ValueError, IndexError) as e:
        logger.warning(f"Failed to create polygon from coordinates: {e}")
        return None
