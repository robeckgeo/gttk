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
Metadata Extractor for GeoTIFF Files.

This module provides a MetadataExtractor class to orchestrate the extraction of
metadata from GeoTIFF files, populating the data models directly.
"""
import logging
import math
import re
import tifffile
from osgeo import gdal
from pathlib import Path
from typing import Any, Dict, List, Optional
from gttk.utils.data_models import (
    TiffTag, GeoKey, GeoReference, GeoExtents, GeoTransform,
    BoundingBox, StatisticsBand, TileInfo, IfdInfo,
    WktString, JsonString, XmlMetadata, CogValidation, GeoTiffInfo
)
from gttk.utils.geokey_parser import GeoKeyParser, is_geotiff
from gttk.utils.geotiff_processor import (
    get_lerc_max_z_error,
    determine_decimal_precision,
    calculate_precision_from_tifffile_page
)
from gttk.utils.path_helpers import find_xml_metadata_file
from gttk.utils.statistics import calculate_statistics
from gttk.utils.tiff_tag_parser import TiffTagParser
from gttk.utils.validate_cloud_optimized_geotiff import validate as validate_cog
from gttk.utils.xml_formatter import read_xml_with_encoding_detection, decode_xml_bytes

logger = logging.getLogger(__name__)

PREDICTOR_ABBREV_MAP = {
    1: "1-None",
    2: "2-Horizontal",
    3: "3-Float",
    34892: "34892-Horizontal/Float",
    34893: "34893-Horizontal/Float/Swap"
}

# TIFF tag codes for XML and Esri PE metadata
GEO_ASCII_PARAMS_TAG = 34737
GDAL_METADATA_TAG = 42112
GEO_METADATA_TAG = 50909
XMP_TAG = 700

def _raw_tag_value(tif: tifffile.TiffFile, page_index: int, code: int) -> Any:
    """The raw tifffile value of tag ``code`` on page ``page_index``, or None if absent."""
    page_tags = getattr(tif.pages[page_index], 'tags', None)
    raw_tag = page_tags.get(code) if page_tags is not None else None
    return raw_tag.value if raw_tag is not None else None


class MetadataExtractor:
    """Orchestrates the extraction of metadata from a GeoTIFF file."""

    def __init__(self, filepath: str, geotiff_info: Optional[GeoTiffInfo] = None):
        """
        Initializes the MetadataExtractor.

        Args:
            filepath: Path to the GeoTIFF file.
            geotiff_info: Optional pre-populated GeoTiffInfo with cached metadata.
                         If provided, extraction methods will read from this cache
                         instead of re-opening GDAL and re-extracting data.
        """
        self.filepath = Path(filepath)
        if not self.filepath.exists():
            raise FileNotFoundError(f"File not found: {self.filepath}")
        
        self.gdal_ds: Optional[gdal.Dataset] = None
        self.tiff: Optional[tifffile.TiffFile] = None
        self.geotiff_info = geotiff_info
        self.is_geotiff = is_geotiff(self.filepath)
        
        # Cache for statistics to avoid recalculating for bbox and statistics sections
        self._statistics_cache: Optional[List[StatisticsBand]] = None

    def __enter__(self):
        """Opens file handles and populates GeoTiffInfo if not provided."""
        self.gdal_ds = gdal.Open(str(self.filepath), gdal.GA_ReadOnly)
        try:
            self.tiff = tifffile.TiffFile(self.filepath)
        except Exception:
            # __exit__ never runs when __enter__ raises, so the dataset -- and on
            # Windows the lock it holds on the file -- would outlive this failure.
            self.gdal_ds = None
            raise
        
        # If GeoTiffInfo wasn't provided, populate it now from the open dataset
        if not self.geotiff_info and self.gdal_ds:
            from gttk.utils.geotiff_processor import read_geotiff
            self.geotiff_info = read_geotiff(self.gdal_ds)
        
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Closes file handles."""
        self.gdal_ds = None
        if self.tiff:
            self.tiff.close()

    def extract_tags(self, page: int = 0, tag_scope: str = 'complete') -> List[TiffTag]:
        """
        Extracts TIFF tags from the file.

        Args:
            page: The IFD page to extract tags from.
            tag_scope: The scope of tags to extract ('complete' or 'compact').

        Returns:
            A list of TiffTag objects.
        """
        if not self.tiff:
            return []
        parser = TiffTagParser(self.filepath, tiff_file=self.tiff)
        return parser.get_tags(page_index=page, tag_scope=tag_scope)

    def extract_geokeys(self) -> Optional[List[GeoKey]]:
        """
        Extracts GeoKeys from the file.

        Returns:
            A list of GeoKey objects, or None if the file is not a GeoTIFF.
        """
        if not self.is_geotiff or not self.tiff:
            return None
        parser = GeoKeyParser(self.filepath, tiff_file=self.tiff)
        _, geokeys = parser.parse_geokey_directory()
        return geokeys
    
    def extract_geotiff_version(self) -> Optional[str]:
        """
        Extracts the GeoTIFF version from the file.

        Returns:
            The GeoTIFF version as a string, or None if not found.
        """
        if not self.is_geotiff or not self.tiff:
            return None
        parser = GeoKeyParser(self.filepath, tiff_file=self.tiff)
        version, _ = parser.parse_geokey_directory()
        return version

    def extract_georeference(self) -> Optional[GeoReference]:
        """
        Extracts georeferencing information from cached GeoTiffInfo.
        
        This now reads from the pre-populated projection_info instead of
        re-opening GDAL and calling geokey_parser.get_projection_info().
        """
        if not self.is_geotiff or not self.geotiff_info:
            return None
        
        proj_info = self.geotiff_info.projection_info
        if not proj_info:
            return None
        
        # Build ellipsoid string if we have the parameters
        ellipsoid_str = None
        if proj_info.get('ellipsoid_name'):
            semi_major = proj_info.get('semi_major')
            inv_flat = proj_info.get('inv_flattening')
            if semi_major and inv_flat:
                ellipsoid_str = f"{proj_info['ellipsoid_name']} (a={semi_major}, rf={inv_flat})"
            else:
                ellipsoid_str = proj_info['ellipsoid_name']
        
        return GeoReference(
            raster_type=proj_info.get('raster_type'),
            geographic_cs=proj_info.get('geographic_cs_name'),
            geographic_cs_code=proj_info.get('geographic_cs_code'),
            projected_cs=proj_info.get('projected_cs_name'),
            projected_cs_code=proj_info.get('projected_cs_code'),
            compound_cs=proj_info.get('compound_cs_name'),
            datum=proj_info.get('datum_name'),
            datum_code=proj_info.get('datum_code'),
            ellipsoid=ellipsoid_str,
            linear_unit=proj_info.get('linear_unit_name'),
            angular_unit=proj_info.get('angular_unit_name'),
            vertical_cs=proj_info.get('vertical_cs_name'),
            vertical_cs_code=proj_info.get('vertical_cs_code'),
            vertical_datum=proj_info.get('vertical_datum_name'),
            vertical_datum_code=proj_info.get('vertical_datum_code'),
            vertical_unit=proj_info.get('vertical_unit_name')
        )

    def extract_geotransform(self) -> Optional[GeoTransform]:
        """
        Extracts the GeoTransform from cached GeoTiffInfo.
        
        This now reads from the pre-populated geo_transform tuple instead of
        calling geokey_parser.get_geotransform_info() and parsing formatted strings.
        """
        if not self.is_geotiff or not self.geotiff_info:
            return None
        
        gt = self.geotiff_info.geo_transform
        if not gt or len(gt) < 6:
            return None
        
        # Get unit from projection info
        proj_info = self.geotiff_info.projection_info or {}
        unit = proj_info.get('linear_unit_name') or proj_info.get('angular_unit_name')

        return GeoTransform(
            x_origin=gt[0],
            pixel_width=gt[1],
            x_skew=gt[2],
            y_origin=gt[3],
            y_skew=gt[4],
            pixel_height=gt[5],
            unit=unit
        )

    def extract_bounding_box(self) -> Optional[BoundingBox]:
        """
        Extracts the bounding box from cached GeoTiffInfo.
        
        This now reads from the pre-calculated native_bbox instead of
        calling geokey_parser.get_geospatial_extents().
        """
        if not self.is_geotiff or not self.geotiff_info:
            return None
        
        bbox = self.geotiff_info.native_bbox
        if not bbox:
            return None

        georef = self.extract_georeference()
        hor_unit = georef.linear_unit if georef and georef.is_projected() else (georef.angular_unit if georef else None)
        
        # Check for 3D SRS (Compound or 3D Geographic)
        vert_unit, bottom, top = None, None, None
        is_3d = False
        if georef:
            if georef.has_vertical():
                is_3d = True
                vert_unit = georef.vertical_unit
            elif georef.vertical_unit:
                # 3D Geographic CRS (e.g., EPSG:4979) has vertical_unit set via PROJJSON parsing
                is_3d = True
                vert_unit = georef.vertical_unit
        logger.debug(f"extract_bounding_box: is_3d={is_3d}, vert_unit={vert_unit}")
        if is_3d:
            stats = self.extract_statistics()
            if stats and len(stats) == 1:  # single band only (i.e. DEM)
                bottom = stats[0].minimum
                top = stats[0].maximum

        return BoundingBox(
            west=bbox['west'],
            east=bbox['east'],
            south=bbox['south'],
            north=bbox['north'],
            horizontal_unit=hor_unit,
            bottom=bottom,
            top=top,
            vertical_unit=vert_unit
        )

    def extract_geo_extents(self) -> Optional[GeoExtents]:
        """
        Extracts the geographic extents from cached GeoTiffInfo.
        
        This now reads from the pre-calculated geographic_corners instead of
        calling geokey_parser.get_geographic_extents() and re-transforming coordinates.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            if not self.is_geotiff or not self.geotiff_info:
                logger.info("extract_geo_extents: Not a GeoTIFF or no geotiff_info")
                return None
            
            corners = self.geotiff_info.geographic_corners
            if not corners:
                logger.warning("extract_geo_extents: No geographic_corners in geotiff_info - geoextent section will be skipped")
                return None
            
            return GeoExtents(
                upper_left=corners.get('Upper Left', (0.0, 0.0)),
                lower_left=corners.get('Lower Left', (0.0, 0.0)),
                upper_right=corners.get('Upper Right', (0.0, 0.0)),
                lower_right=corners.get('Lower Right', (0.0, 0.0)),
                center=corners.get('Center', (0.0, 0.0))
            )
        except Exception as e:
            logger.warning(f"Failed to extract geo extents: {e}")
            return None

    def extract_statistics(self, page: int = 0) -> Optional[List[StatisticsBand]]:
        """
        Extract statistics for each band with caching.
        
        Returns StatisticsBand objects directly from calculate_statistics()
        with all fields populated including histogram data. Results are cached
        to avoid duplicate calculation when both bbox and statistics sections
        are requested.
        
        Args:
            page: IFD page index (0 for main image, >0 for overviews)
            
        Returns:
            List of StatisticsBand objects or None if extraction fails
        """
        if not self.gdal_ds:
            return None
        
        if page == 0:
            # Check cache for main image statistics
            if self._statistics_cache is not None:
                logger.debug("Using cached statistics (avoids duplicate calculation)")
                return self._statistics_cache
            
            # Calculate and cache statistics for main image
            logger.debug("Calculating statistics (will be cached)")
            stats = calculate_statistics(self.gdal_ds)
            self._statistics_cache = stats
            return stats
        else:
            # Overviews are not cached (typically only requested once)
            main_band = self.gdal_ds.GetRasterBand(1)
            if main_band and page <= main_band.GetOverviewCount():
                overview_band = main_band.GetOverview(page - 1)
                if overview_band:
                    return calculate_statistics(overview_band)
        
        return None

    def extract_ifd_info(self) -> Optional[List[IfdInfo]]:
        """Extracts IFD information."""
        if not self.gdal_ds:
            return None
        return self._build_ifd_table_data(self.gdal_ds, str(self.filepath))

    def extract_tile_info(self) -> Optional[List[TileInfo]]:
        """Extracts tiling and overview information."""
        if not self.gdal_ds:
            return None
        
        tile_info_raw = self._get_tile_info_for_markdown(self.gdal_ds)
        if not tile_info_raw:
            return None

        return [TileInfo(**info) for info in tile_info_raw]

    def validate_cog(self) -> Optional[CogValidation]:
        """Validates COG compliance."""
        if not self.is_geotiff:
            return None
        
        try:
            warnings, errors, details = validate_cog(str(self.filepath), full_check=True)
            headers_size = None
            if details and details.get('data_offsets') and not errors:
                headers_size = min(details['data_offsets'][k] for k in details['data_offsets'])
                if headers_size == 0:
                    stat_res = gdal.VSIStatL(str(self.filepath))
                    if stat_res:
                        headers_size = stat_res.size
            
            return CogValidation(
                warnings=warnings,
                errors=errors,
                details=details,
                headers_size=headers_size
            )
        except Exception as e:
            # A crash in the validator is not "no issues": report it as one.
            logger.warning(f"COG validation could not run for {self.filepath.name}: {e}")
            return CogValidation(errors=[f"Validation could not run: {e}"])

    def extract_esri_pe_string(self) -> Optional[WktString]:
        """Extracts the ESRI_PE_STRING as a multiline WKT string."""
        def split_arguments(content):
            args = []
            balance = 0
            in_quote = False
            last_split = 0
            for i, char in enumerate(content):
                if char == '"':
                    in_quote = not in_quote
                elif not in_quote:
                    if char == '[':
                        balance += 1
                    elif char == ']':
                        balance -= 1
                    elif char == ',' and balance == 0:
                        args.append(content[last_split:i].strip())
                        last_split = i + 1
            args.append(content[last_split:].strip())
            return args

        def format_element(element_str, indent_level):
            element_str = element_str.strip()
            bracket_start = element_str.find('[')
            if bracket_start == -1:
                return element_str

            element_name = element_str[:bracket_start]
            
            balance = 1
            j = bracket_start + 1
            in_quote = False
            content_end = -1
            while j < len(element_str):
                if element_str[j] == '"':
                    in_quote = not in_quote
                elif not in_quote and element_str[j] == '[':
                    balance += 1
                elif not in_quote and element_str[j] == ']':
                    balance -= 1
                if balance == 0:
                    content_end = j
                    break
                j += 1
            
            content = element_str[bracket_start + 1 : content_end]
            
            args = split_arguments(content)
            
            has_nested_elements = any('[' in arg for arg in args)
            is_cs_element = element_name.upper().endswith('CS')

            if is_cs_element or has_nested_elements:
                output = element_name + '[' + format_element(args[0], indent_level)
                inner_indent = indent_level + 1
                for arg in args[1:]:
                    output += ',\n' + '    ' * inner_indent + format_element(arg, inner_indent)
                output += ']'
                return output
            else:
                return element_str

        tags = self.extract_tags()
        ascii_tag = next((t for t in tags if t.code == GEO_ASCII_PARAMS_TAG), None)
        if not ascii_tag:
            return None
        value_str = ascii_tag.value
        if 'esri pe string' not in value_str.lower():
            return None
        
        match = re.search(r'Esri PE String\s*=', value_str, re.IGNORECASE)
        if not match:
            return None
            
        pe_str = value_str[match.end():].split('|')[0].strip()
        top_level_elements = split_arguments(pe_str)
        if len(top_level_elements) > 1:
            pe_str = ',\n'.join(format_element(elem, 0) for elem in top_level_elements)
        else:
            pe_str = format_element(pe_str, 0)

        return WktString(wkt_string=pe_str, format_version="WKT_ESRI", source_file=str(self.filepath))

    def extract_wkt_string(self) -> Optional[WktString]:
        """Extracts WKT2 string, preferring custom metadata for non-EPSG vertical CRSs."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            if not self.is_geotiff or not self.gdal_ds:
                logger.info("extract_wkt_string: Not a GeoTIFF or no GDAL dataset")
                return None
            
            # Check for custom WKT2 metadata (for custom vertical datums)
            custom_wkt = self.gdal_ds.GetMetadataItem('COMPOUND_CRS_WKT2')
            if custom_wkt:
                logger.info("extract_wkt_string: Found COMPOUND_CRS_WKT2 metadata, using custom WKT")
                # Parse the custom WKT to get a proper SRS object for multiline formatting
                from osgeo import osr
                custom_srs = osr.SpatialReference()
                if custom_srs.ImportFromWkt(custom_wkt) == 0:
                    version = "WKT2_2019 (from metadata)"
                    wkt = custom_srs.ExportToWkt(['FORMAT=WKT2_2019', 'MULTILINE=YES'])
                    return WktString(wkt_string=wkt, format_version=version, source_file=str(self.filepath))
            
            # Use cached SRS from geotiff_info (which may have been populated by OSGeo4W fallback)
            srs = self.geotiff_info.srs if self.geotiff_info else None
            
            # Fallback to GetSpatialRef() if cached SRS not available
            if not srs:
                srs = self.gdal_ds.GetSpatialRef()
            
            if not srs:
                logger.warning("extract_wkt_string: No SRS available (GetSpatialRef() and cached SRS both None) - wkt section will be skipped")
                return None
            
            version = "WKT2_2019"
            wkt = srs.ExportToWkt([f'FORMAT={version}', 'MULTILINE=YES'])
            return WktString(wkt_string=wkt, format_version=version, source_file=str(self.filepath))
        except Exception as e:
            logger.warning(f"Failed to extract WKT string: {e}")
            return None

    def extract_projjson_string(self) -> Optional[JsonString]:
        """Extracts PROJJSON string."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            if not self.is_geotiff or not self.gdal_ds:
                logger.info("extract_projjson_string: Not a GeoTIFF or no GDAL dataset")
                return None
            
            # First try using cached PROJJSON from OSGeo4W (if available)
            # This ensures consistent format with full member IDs when PROJ database was accessible
            if self.geotiff_info and self.geotiff_info.cached_projjson:
                logger.info("Using cached PROJJSON from OSGeo4W")
                return JsonString(json_string=self.geotiff_info.cached_projjson, source_file=str(self.filepath))
            
            # Use cached SRS from geotiff_info (which may have been populated by OSGeo4W fallback)
            srs = self.geotiff_info.srs if self.geotiff_info else None
            
            # Fallback to GetSpatialRef() if cached SRS not available
            if not srs:
                srs = self.gdal_ds.GetSpatialRef()
            
            if not srs:
                logger.warning("extract_projjson_string: No SRS available (GetSpatialRef() and cached SRS both None) - json section will be skipped")
                return None
            
            projjson = srs.ExportToPROJJSON()
            return JsonString(json_string=projjson, source_file=str(self.filepath))
        except Exception as e:
            logger.warning(f"Failed to extract PROJJSON string: {e}")
            return None

    def extract_gdal_metadata(self) -> Optional[XmlMetadata]:
        """Extracts GDAL_METADATA TIFF Tag."""
        tags = self.extract_tags()
        gdal_tag = next((t for t in tags if t.code == GDAL_METADATA_TAG), None)
        if not gdal_tag:
            return None
        gdal_tag.value = gdal_tag.value.strip()
        return XmlMetadata(title=f'GDAL_METADATA (Tag {GDAL_METADATA_TAG})', content=str(gdal_tag.value))

    def extract_geo_metadata(self) -> Optional[XmlMetadata]:
        """Extracts GDAL_METADATA TIFF Tag."""
        tags = self.extract_tags()
        geo_tag = next((t for t in tags if t.code == GEO_METADATA_TAG), None)
        if not geo_tag:
            return None
        geo_tag.value = geo_tag.value.strip()
        return XmlMetadata(title=f'GEO_METADATA (Tag {GEO_METADATA_TAG})', content=str(geo_tag.value))

    def extract_xmp_metadata(self) -> Optional[XmlMetadata]:
        """Extracts Extensible Metadata Platform (XMP) TIFF Tag."""
        tags = self.extract_tags()
        xmp_tag = next((t for t in tags if t.code == XMP_TAG), None)
        if not xmp_tag:
            return None
        xmp_tag.value = xmp_tag.value.strip()
        return XmlMetadata(title='XMP: Extensible Metadata Platform (Tag 700 - XMLPacket)', content=str(xmp_tag.value))

    def extract_xml_metadata(self) -> Optional[XmlMetadata]:
        """Extracts metadata from external XML file with the same base name."""
        # From external files
        external_xml_path = find_xml_metadata_file(self.filepath)
        if not external_xml_path:
            return None
        content_bytes = read_xml_with_encoding_detection(external_xml_path)
        content = decode_xml_bytes(content_bytes) if content_bytes else ""
        return XmlMetadata(title=f'XML Metadata File: {external_xml_path.name}', content=content or "")

    def extract_pam_metadata(self) -> Optional[XmlMetadata]:
        """Extracts metadata from the Precision Auxiliary Metadata (PAM) external files (.aux.xml)."""
        pam_xml_path = self.filepath.with_suffix('.aux.xml')
        if not pam_xml_path.exists():
            return None
        content_bytes = read_xml_with_encoding_detection(pam_xml_path)
        content = decode_xml_bytes(content_bytes) if content_bytes else ""

        return XmlMetadata(title='PAM: Persistent Auxiliary Metadata (.aux.xml)', content=content or "")

    def _get_tile_info_for_markdown(self, ds: gdal.Dataset) -> List[Dict[str, Any]]:
        """Get list of dictionaries containing tiling information for each pyramid level."""
        if not ds:
            return []
            
        output = []
        band = ds.GetRasterBand(1)
        if not band:
            return []
        block_size = band.GetBlockSize()
        
        if block_size[0] != ds.RasterXSize:
            gt = ds.GetGeoTransform()
            pixel_size_x = abs(gt[1])
            pixel_size_y = abs(gt[5])
            
            # Use projection_info from geotiff_info instead of calling SRS methods
            # This handles broken PROJ environments in ArcGIS Pro
            proj_info = self.geotiff_info.projection_info if self.geotiff_info else {}
            is_geographic = proj_info.get('is_geographic', False) if proj_info else False
            
            units = "arc seconds"
            if not is_geographic:
                # Try to get linear unit name from projection_info
                linear_units = proj_info.get('linear_unit_name') if proj_info else None
                if linear_units:
                    units = linear_units.lower()
                    units = re.sub(r'metre|meter', 'm', units)
                    units = re.sub(r'foot', 'ft', units)
                    units = re.sub(r'us survey ft', 'ft', units)
                    units = re.sub(r'degree', 'deg', units)
                else:
                    units = "units"  # Fallback if unit name not available
            elif is_geographic:
                pixel_size_x *= 3600
                pixel_size_y *= 3600
                
            rows = ds.RasterYSize
            cols = ds.RasterXSize
            tiles_x = math.ceil(cols / block_size[0])
            tiles_y = math.ceil(rows / block_size[1])
            tile_width = block_size[0] * pixel_size_x
            tile_height = block_size[1] * pixel_size_y
            total_tiles = tiles_x * tiles_y
            output.append({
                "level": 0,
                "tile_count": total_tiles,
                "block_size": f"{block_size[0]} x {block_size[1]}",
                "tile_dimensions": f"{tile_width:.2f} x {tile_height:.2f} {units}",
                "total_pixels": f"{rows} x {cols}",
                "resolution": f"{pixel_size_x:.4f} {units}"
            })
            
            overview_count = band.GetOverviewCount()
            for i in range(overview_count):
                ovr = band.GetOverview(i)
                if not ovr:
                    continue
                ovr_x = math.ceil(ovr.XSize / block_size[0])
                ovr_y = math.ceil(ovr.YSize / block_size[1])
                level_factor = ds.RasterXSize / ovr.XSize
                resolution = pixel_size_x * level_factor
                tile_width = block_size[0] * resolution
                tile_height = block_size[1] * resolution
                ovr_tiles = ovr_x * ovr_y
                output.append({
                    "level": i + 1,
                    "tile_count": ovr_tiles,
                    "block_size": f"{block_size[0]} x {block_size[1]}",
                    "tile_dimensions": f"{tile_width:.2f} x {tile_height:.2f} {units}",
                    "total_pixels": f"{ovr.YSize} x {ovr.XSize}",
                    "resolution": f"{resolution:.4f} {units}"
                })
                
        return output

    def _build_ifd_table_data(self, ds: gdal.Dataset, input_filename: str) -> Optional[List[IfdInfo]]:
        """
        Build IFD data from GDAL dataset.
        """
        ifds: List[IfdInfo] = []

        if not ds or not input_filename:
            return None

        main_band = ds.GetRasterBand(1)
        # is_tiled is now determined per-IFD based on tags

        tiff = None
        try:
            tiff = TiffTagParser(input_filename)
            num_pages = len(tiff.tif.pages)

            for i in range(num_pages):
                problems: List[str] = []   # fields that could not be read for this IFD
                tags_list = tiff.get_tags(page_index=i)
                tags = {tag.code: tag for tag in tags_list}

                width_tag = tags.get(256)
                height_tag = tags.get(257)
                width = width_tag.value if width_tag else None
                height = height_tag.value if height_tag else None

                compression_tag = tags.get(259)
                algo_text = compression_tag.interpretation if compression_tag else ""
                
                bands_tag = tags.get(277)
                band_count = int(bands_tag.value) if bands_tag else 0

                bits_tag = tags.get(258)
                bit_count = bits_tag.value if bits_tag else 0

                # Try to get SampleFormat (339) directly from page tags for reliability
                sample_format_key = 0
                try:
                    page_obj = tiff.tif.pages[i]
                    page_tags = getattr(page_obj, 'tags', None)
                    if page_tags and 339 in page_tags:
                        sample_format_raw = page_tags[339].value
                        sample_format_key = sample_format_raw[0] if isinstance(sample_format_raw, (list, tuple)) else sample_format_raw
                except Exception:
                    pass

                # Translate SampleFormat TIFF tag to GDAL data type codes
                bit_depth = bit_count[0] if isinstance(bit_count, (list, tuple)) else bit_count
                data_type = 'Invalid'
                if bit_depth == 1:
                    data_type = 'Bit'
                elif sample_format_key == 1:
                    if bit_depth == 8:
                        data_type = 'Byte'
                    elif bit_depth in (16, 32, 64):
                        data_type = f'UInt{bit_depth}'
                elif sample_format_key == 2:
                    if bit_depth in (8, 16, 32, 64):
                        data_type = f'Int{bit_depth}'
                elif sample_format_key == 3:
                    if bit_depth in (32, 64):
                        data_type = f'Float{bit_depth}'
                elif sample_format_key == 4:
                    data_type = 'Undefined'  # Not associated with a GDAL data type
                elif sample_format_key == 5:
                    if bit_depth in (16, 32):
                        data_type = f'CInt{bit_depth}'
                elif sample_format_key == 6:
                    if bit_depth in (32, 64):
                        data_type = f'CFloat{bit_depth}'

                # Determine decimal precision
                # Only attempt for Float types to avoid nonsense results for masks/integers
                decimals = None
                is_float = 'Float' in data_type
                
                if is_float:
                    if i == 0:
                        # Main Image (IFD 0): Use GDAL dataset logic (strided reading)
                        decimals = determine_decimal_precision(ds)
                    else:
                        # Overviews/Other IFDs: Use tifffile to access specific IFD data safely
                        # This avoids ambiguity mapping IFD index to GDAL Overviews
                        try:
                            page = tiff.tif.pages[i]
                            decimals = calculate_precision_from_tifffile_page(page)
                        except Exception:
                            decimals = None

                photo_tag = tags.get(262)
                photo_interp = photo_tag.interpretation if photo_tag else None

                predictor_tag = tags.get(317)
                pred_value = predictor_tag.value if predictor_tag else 0
                pred_abbrev = PREDICTOR_ABBREV_MAP.get(pred_value, None)

                # Check for TileWidth (322) to determine if tiled
                is_ifd_tiled = 322 in tags
                
                # Helper to safely extract integer from scalar or list
                def _safe_int(val, default):
                    if val is None:
                        return default
                    if isinstance(val, (list, tuple)):
                        val = val[0] if val else default
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        return default

                w = _safe_int(width, ds.RasterXSize if ds else 0)
                h = _safe_int(height, ds.RasterYSize if ds else 0)

                block_size_str = ''
                
                # Strategy 1: Prefer GDAL's structural reporting if available (Main & Overviews)
                # This avoids parsing issues with raw tags and correctly handles strip/tile abstraction.
                if ds and main_band:
                    try:
                        if i == 0:
                            bx, by = main_band.GetBlockSize()
                            block_size_str = f'{bx} x {by}'
                        else:
                            # Map IFD index to GDAL Overview index
                            ovr_idx = i - 1
                            if ovr_idx < main_band.GetOverviewCount():
                                ovr = main_band.GetOverview(ovr_idx)
                                if ovr:
                                    bx, by = ovr.GetBlockSize()
                                    block_size_str = f'{bx} x {by}'
                    except Exception:
                        pass

                # Strategy 2: Use TIFF Tags if GDAL didn't provide a value
                if not block_size_str:
                    if is_ifd_tiled:
                        # Tiled
                        tw_tag = tags.get(322)
                        tl_tag = tags.get(323)
                        tw = tw_tag.value if tw_tag else None
                        tl = tl_tag.value if tl_tag else None
                        
                        tw_val = _safe_int(tw, None)
                        tl_val = _safe_int(tl, None)

                        if tw_val and tl_val:
                            block_size_str = f'{tw_val} x {tl_val}'
                    else:
                        # Striped
                        rps_tag = tags.get(278)
                        rps = rps_tag.value if rps_tag else None
                        
                        try:
                            rps_val = _safe_int(rps, h)
                            # Ensure reasonable bounds
                            if h > 0:
                                rps_val = min(max(rps_val, 1), h)
                            block_size_str = f'{w} x {rps_val}'
                        except Exception as e:
                            problems.append(f'block size ({e})')
                            block_size_str = ''
                
                # Final fallback for block size if still empty
                if not block_size_str and ds:
                    try:
                        if i == 0:
                            bx, by = main_band.GetBlockSize()
                            block_size_str = f'{bx} x {by}'
                        else:
                            ovr = ds.GetRasterBand(1).GetOverview(i - 1) if i > 0 else None
                            if ovr:
                                bx, by = ovr.GetBlockSize()
                                block_size_str = f'{bx} x {by}'
                    except Exception as e:
                        problems.append(f'block size from GDAL ({e})')

                compression_str = 'N/A'
                ratio_str = 'N/A'
                try:
                    # If algorithm explicitly reports uncompressed, show 0%
                    if algo_text and 'uncompressed' in algo_text.lower():
                        compression_str = '0.00%'
                        ratio_str = '1.00x'
                    else:
                        # Prefer the raw tile/strip byte counts from tifffile pages
                        byte_counts_tag_code = 325 if is_ifd_tiled else 279
                        raw_byte_counts = None
                        try:
                            # The raw tifffile value, not the summarized text TiffTagParser shows
                            raw_byte_counts = _raw_tag_value(tiff.tif, i, byte_counts_tag_code)
                        except Exception as e:
                            problems.append(f'byte counts ({e})')

                        # Fall back to the parsed/display value only if raw access failed
                        byte_counts_tag = tags.get(byte_counts_tag_code)
                        byte_counts = raw_byte_counts if raw_byte_counts is not None else (byte_counts_tag.value if byte_counts_tag else None)

                        # Coerce numeric inputs to int where appropriate
                        try:
                            w_val = int(width) if width is not None else int(ds.RasterXSize)
                            h_val = int(height) if height is not None else int(ds.RasterYSize)
                        except Exception as e:
                            problems.append(f'dimensions ({e})')
                            w_val = None
                            h_val = None

                        try:
                            bands_val = int(band_count) if band_count is not None else None
                        except Exception as e:
                            problems.append(f'band count ({e})')
                            bands_val = None

                        if byte_counts and w_val and h_val and bands_val and bit_count:
                            # Determine bits per sample (sum for multi-sample pixels)
                            if isinstance(bit_count, (list, tuple)):
                                bits_per_sample = sum(int(b) for b in bit_count)
                            else:
                                try:
                                    bits_per_sample = int(bit_count)
                                except Exception as e:
                                    problems.append(f'bits per sample ({e})')
                                    bits_per_sample = None

                            # Compute compressed size
                            if isinstance(byte_counts, (list, tuple)):
                                compressed_size = sum(int(b) for b in byte_counts)
                            else:
                                # If it's a single int/float
                                try:
                                    compressed_size = int(byte_counts)
                                except Exception as e:
                                    problems.append(f'compressed size ({e})')
                                    compressed_size = None

                            if bits_per_sample and compressed_size is not None:
                                uncompressed_size = w_val * h_val * bits_per_sample / 8
                                if uncompressed_size > 0:
                                    efficiency = (1 - (compressed_size / uncompressed_size)) * 100
                                    ratio_str = f"{(100 / (100 - efficiency)):.2f}x"
                                    compression_str = f"{efficiency:.2f}%"
                except Exception as e:
                    # compression_str and ratio_str stay 'N/A', and the reader is told why
                    problems.append(f'compression ({e})')

                lerc_mze_str = ""
                has_lerc_mze = False
                if algo_text and 'lerc' in algo_text.lower():
                    has_lerc_mze = True
                    lerc_mze_str = get_lerc_max_z_error(ds)
                
                predictor_display = None
                if pred_abbrev:
                    predictor_display = pred_abbrev
                else:
                    algo_low = (algo_text or "").lower()
                    predictor_unsupported = any(k in algo_low for k in ["jxl", "lerc", "jpeg", "webp", "jp2openjpeg"])
                    if not predictor_unsupported and any(k in algo_low for k in ["lzw", "deflate", "zstd"]):
                        predictor_display = "None"
                
                if problems:
                    logger.warning(f"{self.filepath.name}: IFD {i} fields could not be read and show as N/A: "
                                   + '; '.join(problems))
                ifds.append(IfdInfo(
                    ifd=i,
                    ifd_type=self._get_ifd_type_from_tags(tags_list, i),
                    dimensions=f"{width} x {height}" if (width is not None and height is not None) else "",
                    block_size=block_size_str,
                    bands=band_count,
                    bits_per_sample=bit_count,
                    data_type=data_type,
                    decimals=decimals,
                    photometric=photo_interp if photo_interp else None,
                    compression_algorithm=algo_text if algo_text else None,
                    predictor=predictor_display,
                    lerc_max_z_error=lerc_mze_str if has_lerc_mze else None,
                    space_saving=compression_str,
                    ratio=ratio_str
                ))

        except Exception as e:
            logger.warning(f"IFD table unavailable for {self.filepath.name}: {e}")
            return None
        finally:
            if tiff:
                tiff.close()

        return ifds if ifds else None

    def _get_ifd_type_from_tags(self, tags: List[TiffTag], page: int) -> str:
        """
        Determine IFD type from tags present.
        """
        if page == 0:
            return "Main Image"
        
        for tag in tags:
            if tag.code == 254:  # NewSubfileType
                subfile_type = tag.value
                if isinstance(subfile_type, int):
                    if subfile_type & 1:
                        return "Overview"
                    if subfile_type & 2:
                        return "Page"
                    if subfile_type & 4:
                        return "Mask"
        
        return "Overview"
