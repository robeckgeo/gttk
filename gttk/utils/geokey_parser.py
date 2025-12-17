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
GeoKey Parser.

A comprehensive tool for extracting and interpreting GeoKey metadata including:
- GeoKey numbers, names and their values
- GeoTIFF specification (1.0 or 1.1)
- Projection information
- Coordinate system details
- Unit information and conversions

The parser supports both GeoTIFF 1.0 and 1.1 specifications and provides
detailed error handling and logging.
"""

import logging
import os
import sqlite3
import tifffile
from osgeo import gdal, osr
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union
from gttk.utils.data_models import GeoKey

# Configure environment and logging
os.environ['PROJ_NETWORK'] = 'OFF'  # Disable PROJ network access

# --- Lookup Tables ---
# Lookup tables for GeoTIFF keys and their values
# GeoTIFF Standard v1.1: https://docs.ogc.org/is/19-008r4/19-008r4.html#_summary_of_geokey_ids_and_names

GEOKEY_NAMES = {
    # GeoTIFF Configuration Keys
    1024: 'GTModelTypeGeoKey',
    1025: 'GTRasterTypeGeoKey',
    1026: 'GTCitationGeoKey',
    # Geographic CRS Parameter Keys
    2048: 'GeodeticCRSGeoKey',
    2049: 'GeodeticCitationGeoKey ',
    2050: 'GeodeticDatumGeoKey',
    2051: 'PrimeMeridianGeoKey',
    2052: 'GeogLinearUnitsGeoKey',
    2053: 'GeogLinearUnitSizeGeoKey',
    2054: 'GeogAngularUnitsGeoKey',
    2055: 'GeogAngularUnitSizeGeoKey',
    2056: 'EllipsoidGeoKey',
    2057: 'EllipsoidSemiMajorAxisGeoKey',
    2058: 'EllipsoidSemiMinorAxisGeoKey',
    2059: 'EllipsoidInvFlatteningGeoKey',
    2061: 'PrimeMeridianLongGeoKey',
    # Projected CRS Parameter Keys
    2060: 'GeogAzimuthUnitsGeoKey',
    3072: 'ProjectedCRSGeoKey',
    3073: 'ProjectedCitationGeoKey',
    3074: 'ProjectionGeoKey',
    3075: 'ProjMethodGeoKey',
    3076: 'ProjLinearUnitsGeoKey',
    3077: 'ProjLinearUnitSizeGeoKey',
    3078: 'ProjStdParallel1GeoKey',
    3079: 'ProjStdParallel2GeoKey',
    3080: 'ProjNatOriginLongGeoKey',
    3081: 'ProjNatOriginLatGeoKey',
    3082: 'ProjFalseEastingGeoKey',
    3083: 'ProjFalseNorthingGeoKey',
    3084: 'ProjFalseOriginLongGeoKey',
    3085: 'ProjFalseOriginLatGeoKey',
    3086: 'ProjFalseOriginEastingGeoKey',
    3087: 'ProjFalseOriginNorthingGeoKey',
    3088: 'ProjCenterLongGeoKey',
    3089: 'ProjCenterLatGeoKey',
    3090: 'ProjCenterEastingGeoKey',
    3091: 'ProjCenterNorthingGeoKey',
    3092: 'ProjScaleAtNatOriginGeoKey',
    3093: 'ProjScaleAtCenterGeoKey',
    3094: 'ProjAzimuthAngleGeoKey',
    3095: 'ProjStraightVertPoleLongGeoKey',
    # Vertical CRS Parameter Keys
    4096: 'VerticalGeoKey',
    4097: 'VerticalCitationGeoKey',
    4098: 'VerticalDatumGeoKey',
    4099: 'VerticalUnitsGeoKey',
    5120: 'CoordinateEpochGeoKey',  # https://gdal.org/en/stable/user/coordinate_epoch.html#geotiff
    # Non-standardized GeoKeys (not part of the official GeoTIFF standard, but pop up in older files)
    2062: 'TOWGS84GeoKey',  # https://github.com/opengeospatial/geotiff/issues/6
    3059: 'ProjLinearUnitsInterpCorrectGeoKey'  # https://github.com/opengeospatial/geotiff/issues/104
}

# Mapping for component lookups in PROJ database
# Key ID -> Table Name
PROJ_DB_TABLE_MAP = {
    2050: 'geodetic_datum',  # GeodeticDatumGeoKey
    2051: 'prime_meridian',  # PrimeMeridianGeoKey
    2052: 'unit_of_measure', # GeogLinearUnitsGeoKey
    2054: 'unit_of_measure', # GeogAngularUnitsGeoKey
    2056: 'ellipsoid',       # EllipsoidGeoKey
    2060: 'unit_of_measure', # GeogAzimuthUnitsGeoKey
    3076: 'unit_of_measure', # ProjLinearUnitsGeoKey
    4098: 'vertical_datum',  # VerticalDatumGeoKey
    4099: 'unit_of_measure'  # VerticalUnitsGeoKey
}

GEOKEY_LOOKUP = {
    1024: {  # GTModelTypeGeoKey
        1: 'ModelTypeProjected',
        2: 'ModelTypeGeographic',
        3: 'ModelTypeGeocentric'
    },
    1025: {  # GTRasterTypeGeoKey
        1: 'RasterPixelIsArea',
        2: 'RasterPixelIsPoint'
    }
}

# ProjMethodGeoKey (ProjCoordTransGeoKey in v1.0)
PROJECTION_METHOD_MAP = {
    1: 'CT_TransverseMercator',
    2: 'CT_TransvMercator_Modified_Alaska',
    3: 'CT_ObliqueMercator',
    4: 'CT_ObliqueMercator_Laborde',
    5: 'CT_ObliqueMercator_Rosenmund',
    6: 'CT_ObliqueMercator_Spherical',
    7: 'CT_Mercator',
    8: 'CT_LambertConfConic_2SP',
    9: 'CT_LambertConfConic_Helmert',
    10: 'CT_LambertAzimEqualArea',
    11: 'CT_AlbersEqualArea',
    12: 'CT_AzimuthalEquidistant',
    13: 'CT_EquidistantConic',
    14: 'CT_Stereographic',
    15: 'CT_PolarStereographic',
    16: 'CT_ObliqueStereographic',
    17: 'CT_Equirectangular',
    18: 'CT_CassiniSoldner',
    19: 'CT_Gnomonic',
    20: 'CT_MillerCylindrical',
    21: 'CT_Orthographic',
    22: 'CT_Polyconic',
    23: 'CT_Robinson',
    24: 'CT_Sinusoidal',
    25: 'CT_VanDerGrinten',
    26: 'CT_NewZealandMapGrid',
    27: 'CT_TransvMercator_SouthOriented'
}

# Mapping of GeoTIFF key names to their v1.0 equivalents
# All other key names are the same in both versions
GEOKEY_v1_0_MAP = {
    'GeodeticCRSGeoKey': 'GeographicTypeGeoKey',
    'GeodeticCitationGeoKey': 'GeogCitationGeoKey',
    'GeodeticDatumGeoKey': 'GeogGeodeticDatumGeoKey',
    'PrimeMeridianGeoKey': 'GeogPrimeMeridianGeoKey',
    'EllipsoidGeoKey': 'GeogEllipsoidGeoKey',
    'EllipsoidSemiMajorAxisGeoKey': 'GeogSemiMajorAxisGeoKey',
    'EllipsoidSemiMinorAxisGeoKey': 'GeogSemiMinorAxisGeoKey',
    'EllipsoidInvFlatteningGeoKey': 'GeogInvFlatteningGeoKey',
    'PrimeMeridianLongGeoKey': 'GeogPrimeMeridianLongGeoKey',
    'ProjectedCRSGeoKey': 'ProjectedCSTypeGeoKey',
    'ProjectedCitationGeoKey': 'PCSCitationGeoKey',
    'ProjMethodGeoKey': 'ProjCoordTransGeoKey',
    'VerticalGeoKey': 'VerticalCSTypeGeoKey'
}

# Keys that should be displayed as plain text without value in parentheses
CITATION_KEYS = {
    1026,  # GTCitationGeoKey
    2049,  # GeodeticCitationGeoKey
    3073,  # ProjectedCitationGeoKey
    4097   # VerticalCitationGeoKey
}

# Keys defining the Coordinate Reference Systems (CRS)
CRS_KEYS = {
    2048,  # GeodeticCRSGeoKey
    3072,  # ProjectedCRSGeoKey
    4096   # VerticalGeoKey
}

# Mapping of GeoKey IDs to OSR attribute names for lookup (Legacy/Fallback)
AUTHORITY_KEYS = {
    2048: 'GEOGCS',    # GeodeticCRSGeoKey
    2050: 'DATUM',     # GeodeticDatumGeoKey
    2056: 'SPHEROID',  # EllipsoidGeoKey
    3072: 'PROJCS',    # ProjectedCRSGeoKey
    4096: 'VERT_CS',   # VerticalGeoKey
    4098: 'VERT_DATUM' # VerticalDatumGeoKey
}

GEO_DOUBLE_TAG = 34736
GEO_ASCII_TAG = 34737

# GeoTIFF "User-Defined" value
KvUserDefined = 32767

class GeoKeyParser:
    """A parser for extracting and interpreting GeoTIFF metadata."""

    def __init__(self, filename: Union[str, Path], tiff_file: Optional[tifffile.TiffFile] = None):
        """
        Initializes the GeoTIFF parser.

        Args:
            filename: Path to the GeoTIFF file.
            tiff_file: An optional, already opened tifffile.TiffFile object.
        """
        self.filename = Path(filename)
        self._tiff_file_external = tiff_file is not None
        self.tif: tifffile.TiffFile
        self.gdal_ds: Optional[gdal.Dataset] = None

        if self._tiff_file_external:
            assert tiff_file is not None
            self.tif = tiff_file
        else:
            if not self.filename.exists():
                raise FileNotFoundError(f"GeoTIFF file not found: {self.filename}")
            try:
                self.tif = tifffile.TiffFile(str(self.filename))
            except Exception as e:
                raise RuntimeError(
                    f"Cannot read TIFF structure from '{self.filename}': {e}\n"
                    f"The file may be corrupted or not a valid TIFF file."
                )

        if not self.tif or not self.tif.pages or not hasattr(self.tif.pages[0], 'tags'):
            if not self._tiff_file_external:
                self.tif.close()
            raise RuntimeError(
                f"No valid TIFF pages or tags found in '{self.filename}'.\n"
                f"The file may be corrupted or not a properly formatted TIFF."
            )

        try:
            self.gdal_ds = gdal.Open(str(self.filename))
            if not self.gdal_ds or not self.gdal_ds.GetSpatialRef():
                raise ValueError(
                    f"No spatial reference found in '{self.filename}'.\n"
                    f"This file does not appear to contain GeoTIFF georeferencing information."
                )
        except Exception as e:
            if not self._tiff_file_external:
                self.tif.close()
            self.gdal_ds = None
            raise RuntimeError(
                f"Failed to open '{self.filename}' with GDAL or extract spatial reference.\n"
                f"Ensure the file is a valid GeoTIFF with georeferencing information.\n"
                f"Details: {e}"
            )

    def parse_geokey_directory(self) -> Tuple[Optional[str], List[GeoKey]]:
        """
        Parse GeoKeyDirectoryTag (34735) and related tags to extract GeoKeys.
        
        Reads TIFF tags:
            - 34735: GeoKeyDirectoryTag (key IDs and storage locations)
            - 34736: GeoDoubleParamsTag (floating-point values)
            - 34737: GeoAsciiParamsTag (string values)
        
        Returns:
            Tuple[version, geokeys] where:
                - version: GeoTIFF spec version ("1.0", "1.1") or None
                - geokeys: List of GeoKey dataclass instances with interpretations
                
        Example:
            >>> with GeoKeyParser('example.tif') as parser:
            ...     version, keys = parser.parse_geokey_directory()
            ...     print(f"GeoTIFF v{version}: {len(keys)} keys")
            ...     for key in keys:
            ...         print(f"  {key.name}: {key.value_text}")
            GeoTIFF v1.1: 8 keys
              GTModelTypeGeoKey: 2 (ModelTypeGeographic)
              GTRasterTypeGeoKey: 1 (RasterPixelIsArea)
              GeodeticCRSGeoKey: 4326 (WGS 84)
              ...
        """
        if not self.tif.series:
            return None, []
        first_page = self.tif.series[0].keyframe
        
        geokey_dir_tag = first_page.tags.get(34735)
        if not geokey_dir_tag or len(geokey_dir_tag.value) < 4:
            return None, []

        geokey_dir = geokey_dir_tag.value
        geo_double_params = first_page.tags.get(34736)
        geo_ascii_params = first_page.tags.get(34737)
        
        _, key_revision, minor_revision, num_keys = geokey_dir[:4]
        version_info = f"{key_revision}.{minor_revision}"
        use_v1_0_names = version_info == "1.0"

        keys: List[GeoKey] = []
        for i in range(num_keys):
            offset = 4 + (i * 4)
            key_data = geokey_dir[offset:offset + 4]
            if len(key_data) < 4:
                logging.debug(f"Skipping malformed GeoKey at index {i}")
                continue

            key_id, tag_loc, count, value_offset = key_data
            
            try:
                key = self._process_geokey(key_id, tag_loc, count, value_offset,
                                           geo_double_params, geo_ascii_params, use_v1_0_names)
                if key:
                    keys.append(key)
            except Exception as e:
                logging.debug(f"Error parsing GeoKey {i} (ID: {key_id}): {e}")
                
        return version_info, keys

    def _process_geokey(self, key_id: int, tag_loc: int, count: int, value_offset: int,
                        geo_double_params: Optional[Any], geo_ascii_params: Optional[Any],
                        use_v1_0_names: bool) -> Optional[GeoKey]:
        """Processes a single GeoKey and returns a GeoKey object."""
        key_name = GEOKEY_NAMES.get(key_id, f"UnknownGeoKey ({key_id})")
        if use_v1_0_names:
            key_name = GEOKEY_v1_0_MAP.get(key_name, key_name)
        
        value = self._get_geokey_value(tag_loc, value_offset, count, geo_double_params, geo_ascii_params)
        if value is None:
            return None

        if isinstance(value, (bytes, str)):
            value = value.decode('ascii', 'replace') if isinstance(value, bytes) else value
            value = value.rstrip('\x00|')

        value_text = str(value)
        
        if key_id not in CITATION_KEYS and isinstance(value, int):
            value_desc = GEOKEY_LOOKUP.get(key_id, {}).get(value) or self._get_osr_lookup(key_id, value)
            if value_desc:
                value_text = f"{value} ({value_desc})"
        
        return GeoKey(
            name=key_name,
            id=key_id,
            value=value,
            value_text=value_text,
            is_citation=key_id in CITATION_KEYS,
            location=tag_loc,
            count=count
        )

    def _get_geokey_value(self, tag_loc: int, value_offset: int, count: int,
                         double_params: Optional[Any], ascii_params: Optional[Any]) -> Optional[Any]:
        """Extracts a GeoKey value from the appropriate tag."""
        if tag_loc == 0:
            return value_offset
        
        if tag_loc == GEO_DOUBLE_TAG and double_params:
            value = double_params.value[value_offset : value_offset + count]
            return value[0] if len(value) == 1 else value
        
        if tag_loc == GEO_ASCII_TAG and ascii_params:
            try:
                # The value is often a tuple of bytes, join them into a single string
                if isinstance(ascii_params.value, tuple):
                    ascii_val = b"".join(ascii_params.value)
                else:
                    ascii_val = ascii_params.value

                ascii_str = ascii_val.decode('ascii', 'replace') if isinstance(ascii_val, bytes) else str(ascii_val)
                return ascii_str[value_offset : value_offset + count].rstrip('\x00')
            except Exception as e:
                logging.debug(f"Error decoding ASCII params: {e}")
        
        return None

    def _get_osr_lookup(self, key_id: int, value: int) -> Optional[str]:
        """
        Uses OSR and PROJ database to look up GeoKey values.
        """
        # Handle "User-Defined" value (32767) common in Esri files
        if value == KvUserDefined:
            return "User-Defined"

        # Handle Projection Method (Mapped internally)
        if key_id == 3075:
            return PROJECTION_METHOD_MAP.get(value)

        # 1. Try component lookup via PROJ database (Units, Datums, Ellipsoids)
        if key_id in PROJ_DB_TABLE_MAP:
            return self._lookup_proj_db(key_id, value)

        # 2. Try CRS lookup via GDAL/OSR (Projected/Geographic/Vertical CRS)
        # This handles ProjectedCRSGeoKey (3072), GeodeticCRSGeoKey (2048), VerticalGeoKey (4096)
        if key_id in CRS_KEYS:
            srs = osr.SpatialReference()
            try:
                # ImportFromEPSG handles complex lookups including UTM zones
                if srs.ImportFromEPSG(value) == 0:
                    name = srs.GetName()
                    # Clean up the name if it's just the code (sometimes happens with bad lookups)
                    if name and name != str(value):
                        return name
            except (RuntimeError, TypeError):
                pass
                
        return None

    def _lookup_proj_db(self, key_id: int, code: int) -> Optional[str]:
        """
        Queries the PROJ SQLite database for component names (units, datums, etc.).
        """
        table_name = PROJ_DB_TABLE_MAP.get(key_id)
        if not table_name:
            return None

        # Attempt to find proj.db
        proj_lib = os.environ.get('PROJ_LIB')
        if not proj_lib:
             # Try to infer from potential locations (Windows/Conda specific fallback)
            import sys
            if sys.platform == 'win32':
                # Common Conda path
                candidate = os.path.join(sys.prefix, 'Library', 'share', 'proj')
                if os.path.exists(os.path.join(candidate, 'proj.db')):
                    proj_lib = candidate
            
            if not proj_lib:
                # Try locating via osr module location as a fallback
                try:
                    import osgeo
                    package_path = os.path.dirname(osgeo.__file__)
                    # Often in .../site-packages/osgeo/data/proj or similar
                    candidate = os.path.join(package_path, 'data', 'proj')
                    if os.path.exists(os.path.join(candidate, 'proj.db')):
                        proj_lib = candidate
                except ImportError:
                    pass

        if not proj_lib or not os.path.exists(os.path.join(proj_lib, 'proj.db')):
            return None

        db_path = os.path.join(proj_lib, 'proj.db')
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Most tables use 'code' and 'name', but let's be safe
            query = f"SELECT name FROM {table_name} WHERE code = ?"
            cursor.execute(query, (code,))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]
                
        except Exception as e:
            logging.debug(f"PROJ DB lookup failed for {table_name}:{code} - {e}")
            return None
            
        return None



    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._tiff_file_external:
            self.tif.close()
        self.gdal_ds = None

def is_geotiff(filepath: Path) -> bool:
    """
    Check if a file is a valid GeoTIFF with georeferencing information.
    
    A file is considered a GeoTIFF if:
        1. It can be opened by GDAL's GTiff or COG driver
        2. It contains a valid spatial reference system (SRS)
    
    Args:
        filepath: Path to the file to check
        
    Returns:
        True if the file is a valid GeoTIFF with SRS, False otherwise
        
    Example:
        >>> is_geotiff(Path('data.tif'))
        True
        >>> is_geotiff(Path('regular.tif'))  # No georeferencing
        False
        >>> is_geotiff(Path('image.jpg'))
        False
    """
    if not os.path.exists(filepath):
        return False

    try:
        # Suppress GDAL errors for invalid files
        gdal.PushErrorHandler('CPLQuietErrorHandler')
        ds = gdal.Open(filepath)
        gdal.PopErrorHandler()

        if ds is None:
            return False

        # 1. Check if the driver is for the TIFF format
        driver_name = ds.GetDriver().ShortName
        if driver_name not in ['GTiff', 'COG']:
            ds = None
            return False

        # 2. Check for a SRS (the definitive test)
        srs = ds.GetSpatialRef()
        if srs is not None and srs.ExportToWkt() != '':
            ds = None
            return True

        ds = None
        return False

    except Exception:
        # Ensure the dataset is closed if an error occurs after opening
        ds = None
        return False

