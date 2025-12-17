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
Data Models for GeoTIFF ToolKit.

This module defines strongly-typed data classes for representing GeoTIFF metadata
and analysis results. These classes provide type safety, self-documentation, and
clear contracts between modules.

Report framework (architecure) classes:
    MenuItem: Represents a navigation menu item for HTML reports
    ReportSection: Represents a section of a metadata report
    SectionConfig: Configuration for a report section

Domain model classes (no suffix):
    TiffTag: Represents a single TIFF tag with its metadata
    GeoKey: Represents a GeoTIFF key with its value and metadata
    GeoReference: Represents projection and coordinate reference system information
    GeoTransform: Represents the affine transformation matrix
    GeoExtents: Represents geographic corner coordinates
    BoundingBox: Represents geospatial bounding box extents
    StatisticsBand: Represents statistical metrics for a raster band
    HistogramImage: Represents histogram visualization data
    TileInfo: Represents tiling and overview information
    IfdInfo: Represents Image File Directory metadata
    WktString: Represents Well-Known Text coordinate system definition
    JsonString: Represents JSON string data
    CogValidation: Represents Cloud Optimized GeoTIFF validation results
    XmlMetadata: Represents XML metadata (GDAL_METADATA, GEO_METDATA, PAM, XMP, XML file)

Wrapper classes (*Data suffix):
    TiffTagsData: Represents a collection of TIFF tags
    StatisticsData: Full multi-band Statistics table data
    IfdInfoData: Full multi-IFD table data

Comparison container classes (*Comparison suffix):
    DifferencesComparison: Comparison data for compression analysis
    HistogramComparison: Comparison data for histogram analysis
    StatisticsComparison: Comparison data for statistics analysis
    IfdInfoComparison: Comparison data for IFD analysis
    CogValidationComparison: Comparison data for COG validation
"""

import json
from osgeo import osr
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union


# ============================================================================
# GDAL information storage class
# ===========================================================================

@dataclass
class GeoTiffInfo:
    """
    A dataclass to hold key information about a GeoTIFF file.

    Attributes:
        x_size: Width of the raster in pixels.
        y_size: Height of the raster in pixels.
        bands: Number of raster bands.
        wkt_string: The projection definition Well Known Text (WKT) string.
        geo_transform: The affine transformation coefficients.
        res_x: The pixel size in the x-dimension.
        res_y: The pixel size in the y-dimension.
        srs: The spatial reference system (osr.SpatialReference).
        vertical_srs: The vertical spatial reference system, if present.
        vertical_srs_name: The name of the vertical SRS.
        data_type: The data type of the raster bands (e.g., 'Float32').
        nodata: The NoData value for the raster.
        color_interp: The color interpretation of the first band.
        has_alpha: True if an alpha band is present.
        has_mask: True if the dataset has an internal mask.
        projection_info: Raw projection information extracted once (raster_type, CS names/codes, units, etc.)
        native_bbox: Cached native coordinate system bounding box
        geographic_corners: Cached geographic (WGS84) corner coordinates
    """
    filepath: str
    x_size: int
    y_size: int
    bands: int
    wkt_string: str
    geo_transform: Tuple[float, ...]
    res_x: float
    res_y: float
    srs: osr.SpatialReference
    vertical_srs: Optional[osr.SpatialReference] = None
    vertical_srs_name: Optional[str] = None
    data_type: Optional[str] = None
    nodata: Any = None
    color_interp: Optional[str] = None
    has_alpha: bool = False
    transparency_info: Dict[str, Any] = field(default_factory=dict)
    projection_info: Optional[Dict[str, Any]] = None
    native_bbox: Optional[Dict[str, float]] = None
    geographic_corners: Optional[Dict[str, Tuple[float, float]]] = None


# ============================================================================
# Report framework classes
# ============================================================================

@dataclass
class MenuItem:
    """
    Represents a navigation menu item for HTML reports.
    
    Used by HtmlReportFormatter to build navigation menus with consistent
    structure and type safety.
    
    Attributes:
        anchor: HTML anchor ID for linking (e.g., 'tags', 'statistics')
        name: Short display name for the menu (e.g., 'Tags', 'Stats')
        title: Full section title for tooltip
        icon: Icon name for the menu item
    
    Example:
        >>> item = MenuItem(
        ...     anchor='statistics',
        ...     name='Stats',
        ...     title='Statistics',
        ...     icon='chart'
        ... )
    """
    anchor: str
    name: str
    title: str
    icon: str


@dataclass
class ReportSection:
    """
    Represents a section of a metadata report.
    
    Used to organize report content into logical sections that can be
    rendered independently using different renderers.
    
    Attributes:
        id: Unique identifier for the section (e.g., 'tags', 'geokeys')
        title: Display title for the section
        menu: Short title for HTML navigation bar
        data: The actual data for this section (can be any type)
        renderer_hint: Optional hint for which renderer to use
        enabled: Whether this section is enabled in the report
        icon: Optional icon name for HTML menu rendering
    
    Example:
        >>> section = ReportSection(
        ...     id="tags",
        ...     title="TIFF Tags",
        ...     data=[TiffTag(256, "ImageWidth", 1024)],
        ...     renderer_hint="table"
        ... )
        >>> section.is_enabled()
        True
    """
    id: str
    title: str
    menu_name: str
    data: Any
    renderer_hint: Optional[str] = None
    enabled: bool = True
    icon: Optional[str] = None
    
    def is_enabled(self) -> bool:
        """
        Check if this section is enabled.
        
        Returns:
            True if the section is enabled
        """
        return self.enabled
    
    def has_data(self) -> bool:
        """
        Check if this section has data.
        
        Returns:
            True if data is not None and not empty
        """
        if self.data is None:
            return False
        if isinstance(self.data, (list, dict, str)):
            return len(self.data) > 0
        return True


@dataclass(frozen=True)
class SectionConfig:
    """
    Static configuration for a report section.
    
    Defines the metadata needed to render and display a section.
    This is the static template; ReportSection is the runtime instance.
    
    Attributes:
        id: Section identifier (e.g., 'tags', 'geokeys')
        title: Default section heading (may be overridden for dynamic titles)
        menu_name: Short name for HTML navigation menu
        icon: Icon name for HTML rendering (e.g., 'tag', 'key')
        renderer: Renderer method name (e.g., 'render_tags')
    
    Example:
        >>> config = SectionConfig(
        ...     id='geokeys',
        ...     title='GeoKey Directory',
        ...     menu_name='GeoKeys',
        ...     icon='key',
        ...     renderer='render_geokeys'
        ... )
    """
    id: str
    title: str
    menu_name: str
    icon: str
    renderer: str

# ============================================================================
# Domain model classes (no suffix)
# ============================================================================

@dataclass
class TiffTag:
    """
    Represents a single TIFF tag with its metadata.
    
    TIFF tags are the fundamental metadata units in TIFF files, containing
    information about image structure, compression, color space, and more.
    
    Attributes:
        code: The numeric TIFF tag code (e.g., 256 for ImageWidth)
        name: The human-readable tag name (e.g., 'ImageWidth')
        value: The tag's value (can be int, float, str, list, etc.)
        interpretation: Optional human-readable interpretation of the value
    
    Example:
        >>> tag = TiffTag(
        ...     code=256,
        ...     name="ImageWidth",
        ...     value=1024,
        ...     interpretation=None
        ... )
        >>> tag.is_array()
        False
        >>> tag = TiffTag(code=273, name="StripOffsets", value=[100, 200, 300])
        >>> tag.is_array()
        True
    """
    code: int
    name: str
    value: Any
    interpretation: Optional[str] = None
    
    def is_array(self) -> bool:
        """
        Check if the tag value is an array type.
        
        Returns:
            True if the value is a list or tuple, False otherwise
        """
        return isinstance(self.value, (list, tuple))
    
    def is_numeric(self) -> bool:
        """
        Check if the tag value is numeric.
        
        Returns:
            True if the value is int or float, False otherwise
        """
        return isinstance(self.value, (int, float))
    
    def is_string(self) -> bool:
        """
        Check if the tag value is a string.
        
        Returns:
            True if the value is a string, False otherwise
        """
        return isinstance(self.value, str)


@dataclass
class GeoKey:
    """
    Represents a GeoTIFF key with its value and metadata.
    
    GeoKeys are used in GeoTIFF files to store projection, datum, and coordinate
    system information. They are stored in special TIFF tags (34735-34737).
    
    Attributes:
        id: The numeric GeoKey ID (e.g., 1024 for GTModelTypeGeoKey)
        name: The human-readable GeoKey name
        value: The raw GeoKey value (can be int, float, str)
        value_text: The formatted value with interpretation
        location: The TIFF tag where the value is stored (0, 34736, or 34737)
        count: The number of values for this key
        is_citation: Whether this is a citation key (text description)
    
    Example:
        >>> key = GeoKey(
        ...     id=1024,
        ...     name="GTModelTypeGeoKey",
        ...     value=2,
        ...     value_text="2 (ModelTypeGeographic)",
        ...     location=0,
        ...     count=1,
        ...     is_citation=False
        ... )
        >>> key.is_citation_key()
        False
    """
    id: int
    name: str
    value: Any
    value_text: str
    is_citation: bool = False
    location: Optional[int] = None
    count: Optional[int] = None
    
    def is_citation_key(self) -> bool:
        """
        Check if this is a citation key (contains descriptive text).
        
        Citation keys include GTCitation, GeodeticCitation, ProjectedCitation,
        and VerticalCitation.
        
        Returns:
            True if this is a citation key, False otherwise
        """
        return self.is_citation
    
    def is_stored_in_doubles(self) -> bool:
        """
        Check if the value is stored in the GeoDoubleParams tag (34736).
        
        Returns:
            True if stored in tag 34736, False otherwise
        """
        return self.location == 34736
    
    def is_stored_in_ascii(self) -> bool:
        """
        Check if the value is stored in the GeoAsciiParams tag (34737).
        
        Returns:
            True if stored in tag 34737, False otherwise
        """
        return self.location == 34737


@dataclass
class GeoReference:
    """
    Represents projection and coordinate reference system information.
    
    Contains comprehensive information about the geographic and projected
    coordinate systems, including datum, ellipsoid, and units. After refactoring,
    this class stores names and codes separately, with formatting methods to
    combine them for display.
    
    Attributes:
        raster_type: Pixel interpretation ('PixelIsArea' or 'PixelIsPoint')
        geographic_cs: Geographic coordinate system name (without EPSG code)
        geographic_cs_code: EPSG code for geographic CS (e.g., '4326')
        projected_cs: Projected coordinate system name (without EPSG code)
        projected_cs_code: EPSG code for projected CS
        compound_cs: Compound coordinate system name
        datum: Geodetic datum name (without EPSG code)
        datum_code: EPSG code for datum
        ellipsoid: Ellipsoid definition with parameters
        linear_unit: Linear unit name (e.g., 'metre', 'foot')
        angular_unit: Angular unit name (e.g., 'degree', 'radian')
        vertical_cs: Vertical coordinate system name (without EPSG code)
        vertical_cs_code: EPSG code for vertical CS
        vertical_datum: Vertical datum name (without EPSG code)
        vertical_datum_code: EPSG code for vertical datum
        vertical_unit: Vertical unit name
        additional_params: Dictionary for any additional projection parameters
    
    Example:
        >>> georef = GeoReference(
        ...     raster_type="PixelIsArea",
        ...     geographic_cs="WGS 84",
        ...     geographic_cs_code="4326",
        ...     linear_unit="metre"
        ... )
        >>> georef.get_formatted_geographic_cs()
        'WGS 84 (EPSG:4326)'
    """
    raster_type: Optional[str] = None
    geographic_cs: Optional[str] = None
    geographic_cs_code: Optional[str] = None
    projected_cs: Optional[str] = None
    projected_cs_code: Optional[str] = None
    compound_cs: Optional[str] = None
    datum: Optional[str] = None
    datum_code: Optional[str] = None
    ellipsoid: Optional[str] = None
    linear_unit: Optional[str] = None
    angular_unit: Optional[str] = None
    vertical_cs: Optional[str] = None
    vertical_cs_code: Optional[str] = None
    vertical_datum: Optional[str] = None
    vertical_datum_code: Optional[str] = None
    vertical_unit: Optional[str] = None
    additional_params: Dict[str, Any] = field(default_factory=dict)
    
    def get_formatted_geographic_cs(self) -> Optional[str]:
        """
        Get formatted geographic CS with EPSG code.
        
        Returns:
            Formatted string like "WGS 84 (EPSG:4326)" or just "WGS 84" if no code,
            or None if no geographic CS
        """
        if not self.geographic_cs:
            return None
        if self.geographic_cs_code:
            return f"{self.geographic_cs} (EPSG:{self.geographic_cs_code})"
        return self.geographic_cs
    
    def get_formatted_projected_cs(self) -> Optional[str]:
        """
        Get formatted projected CS with EPSG code.
        
        Returns:
            Formatted string like "UTM Zone 10N (EPSG:32610)" or just name if no code,
            or None if no projected CS
        """
        if not self.projected_cs:
            return None
        if self.projected_cs_code:
            return f"{self.projected_cs} (EPSG:{self.projected_cs_code})"
        return self.projected_cs
    
    def get_formatted_datum(self) -> Optional[str]:
        """
        Get formatted datum with EPSG code.
        
        Returns:
            Formatted string like "WGS_1984 (EPSG:6326)" or just name if no code,
            or None if no datum
        """
        if not self.datum:
            return None
        if self.datum_code:
            return f"{self.datum} (EPSG:{self.datum_code})"
        return self.datum
    
    def get_formatted_vertical_cs(self) -> Optional[str]:
        """
        Get formatted vertical CS with EPSG code.
        
        Returns:
            Formatted string like "NAVD88 (EPSG:5703)" or just name if no code,
            or None if no vertical CS
        """
        if not self.vertical_cs:
            return None
        if self.vertical_cs_code:
            return f"{self.vertical_cs} (EPSG:{self.vertical_cs_code})"
        return self.vertical_cs
    
    def get_formatted_vertical_datum(self) -> Optional[str]:
        """
        Get formatted vertical datum with EPSG code.
        
        Returns:
            Formatted string like "North American Vertical Datum 1988 (EPSG:5103)"
            or just name if no code, or None if no vertical datum
        """
        if not self.vertical_datum:
            return None
        if self.vertical_datum_code:
            return f"{self.vertical_datum} (EPSG:{self.vertical_datum_code})"
        return self.vertical_datum
    
    def is_geographic(self) -> bool:
        """
        Check if the horizontal coordinate system is geographic.
        
        Returns:
            True if geographic_cs is set and projected_cs is not
        """
        return self.geographic_cs is not None and self.projected_cs is None
    
    def is_projected(self) -> bool:
        """
        Check if the horizontal coordinate system is projected.
        
        Returns:
            True if projected_cs is set
        """
        return self.projected_cs is not None
    
    def has_vertical(self) -> bool:
        """
        Check if this includes vertical/elevation data.
        
        Returns:
            True if vertical_cs or vertical_datum is set
        """
        return self.vertical_cs is not None or self.vertical_datum is not None


@dataclass
class GeoTransform:
    """
    Represents the affine transformation matrix for geospatial coordinates.
    
    The GeoTransform maps pixel/line coordinates to geographic coordinates
    using six coefficients. The transformation is:
        X = x_origin + pixel * pixel_width + line * x_skew
        Y = y_origin + pixel * y_skew + line * pixel_height
    
    Attributes:
        x_origin: X coordinate of upper-left corner (GT[0])
        pixel_width: Pixel width in georeferenced units (GT[1])
        x_skew: Rotation about x-axis (GT[2])
        y_origin: Y coordinate of upper-left corner (GT[3])
        y_skew: Rotation about y-axis (GT[4])
        pixel_height: Pixel height in georeferenced units (GT[5], typically negative)
        unit: Unit of measurement for the transformation
    
    Example:
        >>> gt = GeoTransform(
        ...     x_origin=0.0,
        ...     pixel_width=30.0,
        ...     x_skew=0.0,
        ...     y_origin=100.0,
        ...     y_skew=0.0,
        ...     pixel_height=-30.0,
        ...     unit="metre"
        ... )
        >>> gt.is_north_up()
        True
    """
    x_origin: float
    pixel_width: float
    x_skew: float
    y_origin: float
    y_skew: float
    pixel_height: float
    unit: Optional[str] = None
    
    def as_tuple(self) -> Tuple[float, float, float, float, float, float]:
        """
        Return the GeoTransform as a 6-element tuple (GDAL format).
        
        Returns:
            Tuple of (x_origin, pixel_width, x_skew, y_origin, y_skew, pixel_height)
        """
        return (
            self.x_origin,
            self.pixel_width,
            self.x_skew,
            self.y_origin,
            self.y_skew,
            self.pixel_height
        )
    
    def is_north_up(self) -> bool:
        """
        Check if the image is oriented north-up (no rotation).
        
        Returns:
            True if both skew parameters are zero
        """
        return self.x_skew == 0.0 and self.y_skew == 0.0
    
    def is_rotated(self) -> bool:
        """
        Check if the image has rotation applied.
        
        Returns:
            True if either skew parameter is non-zero
        """
        return not self.is_north_up()
    
    def resolution(self) -> Tuple[float, float]:
        """
        Get the pixel resolution in x and y directions.
        
        Returns:
            Tuple of (x_resolution, y_resolution) as absolute values
        """
        return (abs(self.pixel_width), abs(self.pixel_height))


@dataclass
class GeoExtents:
    """
    Represents geographic corner coordinates in WGS 84.
    
    Stores the latitude/longitude coordinates of the raster's corners and
    center point, useful for visualization and spatial queries.
    
    Attributes:
        upper_left: (longitude, latitude) of upper-left corner
        lower_left: (longitude, latitude) of lower-left corner
        upper_right: (longitude, latitude) of upper-right corner
        lower_right: (longitude, latitude) of lower-right corner
        center: (longitude, latitude) of center point
    
    Example:
        >>> extents = GeoExtents(
        ...     upper_left=(-180.0, 90.0),
        ...     lower_left=(-180.0, -90.0),
        ...     upper_right=(180.0, 90.0),
        ...     lower_right=(180.0, -90.0),
        ...     center=(0.0, 0.0)
        ... )
        >>> lon, lat = extents.center
        >>> print(f"Center: {lon}°, {lat}°")
        Center: 0.0°, 0.0°
    """
    upper_left: Tuple[float, float]
    lower_left: Tuple[float, float]
    upper_right: Tuple[float, float]
    lower_right: Tuple[float, float]
    center: Tuple[float, float]
    
    def all_corners(self) -> List[Tuple[float, float]]:
        """
        Get all corner coordinates as a list.
        
        Returns:
            List of (longitude, latitude) tuples for all corners
        """
        return [
            self.upper_left,
            self.lower_left,
            self.upper_right,
            self.lower_right
        ]
    
    def longitude_range(self) -> Tuple[float, float]:
        """
        Calculate the longitude range of the extent.
        
        Returns:
            Tuple of (min_longitude, max_longitude)
        """
        lons = [corner[0] for corner in self.all_corners()]
        return (min(lons), max(lons))
    
    def latitude_range(self) -> Tuple[float, float]:
        """
        Calculate the latitude range of the extent.
        
        Returns:
            Tuple of (min_latitude, max_latitude)
        """
        lats = [corner[1] for corner in self.all_corners()]
        return (min(lats), max(lats))


@dataclass
class BoundingBox:
    """
    Represents geospatial bounding box extents.
    
    Defines the geographic or projected extent of a raster in its native
    coordinate system.
    
    Attributes:
        west: Western boundary coordinate
        east: Eastern boundary coordinate
        south: Southern boundary coordinate
        north: Northern boundary coordinate
        horizontal_unit: Horizontal unit of measurement (e.g., 'metre', 'degree')
        bottom: Bottom elevation (for 3D bounding boxes)
        top: Top elevation (for 3D bounding boxes)
        vertical_unit: Vertical unit of measurement (e.g., 'metre', 'foot')
    
    Example:
        >>> bbox = BoundingBox(
        ...     west=-180.0,
        ...     east=180.0,
        ...     south=-90.0,
        ...     north=90.0,
        ...     unit="degree"
        ... )
        >>> bbox.width()
        360.0
    """
    west: float
    east: float
    south: float
    north: float
    horizontal_unit: Optional[str] = None
    bottom: Optional[float] = None
    top: Optional[float] = None
    vertical_unit: Optional[str] = None
    
    def width(self) -> float:
        """
        Calculate the width of the bounding box.
        
        Returns:
            The difference between east and west coordinates
        """
        return self.east - self.west
    
    def height(self) -> float:
        """
        Calculate the height of the bounding box.
        
        Returns:
            The difference between north and south coordinates
        """
        return self.north - self.south
    
    def center(self) -> Tuple[float, float]:
        """
        Calculate the center point of the bounding box.
        
        Returns:
            Tuple of (center_x, center_y) coordinates
        """
        return ((self.west + self.east) / 2, (self.south + self.north) / 2)
    
    def is_3d(self) -> bool:
        """
        Check if this is a 3D bounding box with elevation data.
        
        Returns:
            True if bottom and top are both set
        """
        return self.bottom is not None and self.top is not None


@dataclass
class StatisticsBand:
    """
    Represents statistical metrics for a single raster band.
    
    Contains comprehensive statistics computed from the band's pixel values,
    including basic statistics and histogram data.
    
    Attributes:
        band_name: Name or identifier of the band (e.g., 'Band 1', 'Red')
        valid_percent: Percentage of valid (non-NoData) pixels
        valid_count: Number of valid pixels (non-NoData, unmasked, alpha != 0)
        mask_count: Number of pixels with transparency mask
        alpha_0_count: Number of pixels with alpha value 0
        nodata_count: Number of NoData pixels
        nodata_value: The NoData value for this band
        minimum: Minimum pixel value in the band
        maximum: Maximum pixel value in the band
        mean: Mean (average) pixel value
        std_dev: Standard deviation of pixel values
        median: Median pixel value
        histogram_counts: Pre-computed histogram bin counts for visualization
        histogram_bins: Histogram bin edges corresponding to counts
        histogram: Raw valid pixel data as numpy array (kept for PAM XML export)
    
    Example:
        >>> stats = StatisticsBand(
        ...     band_name="Band 1",
        ...     minimum=0.0,
        ...     maximum=255.0,
        ...     mean=127.5,
        ...     std_dev=73.9
        ... )
        >>> stats.range()
        255.0
    """
    band_name: str
    valid_percent: float
    valid_count: int
    mask_count: int
    alpha_0_count: int
    nodata_count: int
    nodata_value: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    mean: Optional[float] = None
    std_dev: Optional[float] = None
    median: Optional[float] = None
    histogram_counts: Optional[List[int]] = None
    histogram_bins: Optional[List[float]] = None
    histogram: Optional[Any] = None
    
    @classmethod
    def get_display_fields(cls) -> List[Tuple[str, str, bool]]:
        """
        Returns field metadata for table rendering.
        
        Returns:
            List of (display_name, field_name, always_show) tuples
        """
        return [
            ("Valid Percent", "valid_percent", True),
            ("Valid Count", "valid_count", True),
            ("NoData Count", "nodata_count", False),
            ("Mask Count", "mask_count", False),
            ("Alpha=0 Count", "alpha_0_count", False),
            ("Minimum", "minimum", True),
            ("Maximum", "maximum", True),
            ("Mean", "mean", True),
            ("Std Dev", "std_dev", True),
            ("Median", "median", True),
        ]
    
    def range(self) -> Optional[float]:
        """
        Calculate the range (max - min) of pixel values.
        
        Returns:
            The range if min and max are available, None otherwise
        """
        if self.minimum is not None and self.maximum is not None:
            return self.maximum - self.minimum
        return None
    
    def has_nodata(self) -> bool:
        """
        Check if this band has a NoData value defined.
        
        Returns:
            True if nodata_value is set and nodata_count is > 0
        """
        return self.nodata_value is not None and self.nodata_count is not None and self.nodata_count > 0
    
    def has_histogram(self) -> bool:
        """
        Check if histogram data is available.
        
        Returns:
            True if histogram data exists
        """
        return self.histogram_counts is not None and len(self.histogram_counts) > 0


@dataclass
class HistogramImage:
    """
    Represents histogram visualization data.
    
    Contains base64-encoded image data for histogram visualization along
    with band information. Can be used for both metadata and comparison reports.
    
    Attributes:
        base64_image: Base64-encoded PNG image of the histogram
        bands: List of band names/identifiers included in the histogram (optional for comparison reports)
        title: Optional display title for the histogram section
    
    Example:
        >>> histogram = HistogramImage(
        ...     base64_image="iVBORw0KGgoAAAANSUhEUgA...",
        ...     bands=["Band 1", "Band 2", "Band 3"],
        ...     title="Histogram"
        ... )
        >>> histogram.has_data()
        True
    """
    base64_image: str
    bands: Optional[List[str]] = None
    title: Optional[str] = None
    
    def has_data(self) -> bool:
        """
        Check if histogram has valid data.
        
        Returns:
            True if base64_image is not empty
        """
        return bool(self.base64_image)
    
    def band_count(self) -> int:
        """
        Get the number of bands in the histogram.
        
        Returns:
            Number of bands, or 0 if bands is None
        """
        return len(self.bands) if self.bands else 0


@dataclass
class TileInfo:
    """
    Represents tiling and overview information for a raster.
    
    Contains information about tile organization and pyramid levels,
    which is important for understanding raster structure and performance.
    
    Attributes:
        level: Pyramid level (0 for main image, >0 for overviews)
        tile_count: Total number of tiles at this level
        block_size: Tile or strip dimensions in pixels (formatted string)
        tile_dimensions: Tile dimensions in georeferenced units (formatted string)
        total_pixels: Total image dimensions in pixels (formatted string)
        resolution: Pixel resolution at this level (formatted string)
    
    Example:
        >>> tile = TileInfo(
        ...     level=0,
        ...     tile_count=16,
        ...     block_size="256 x 256",
        ...     tile_dimensions="7680.0 x 7680.0 m",
        ...     total_pixels="1024 x 1024",
        ...     resolution="30.0 m"
        ... )
        >>> tile.is_main_image()
        True
    """
    level: int
    tile_count: int
    block_size: str
    tile_dimensions: str
    total_pixels: str
    resolution: str
    
    def is_main_image(self) -> bool:
        """
        Check if this is the main image (not an overview).
        
        Returns:
            True if level is 0
        """
        return self.level == 0
    
    def is_overview(self) -> bool:
        """
        Check if this is an overview (reduced resolution image).
        
        Returns:
            True if level is greater than 0
        """
        return self.level > 0


@dataclass
class IfdInfo:
    """
    Represents Image File Directory (IFD) metadata.
    
    Each IFD represents a separate image or overview within a TIFF file,
    containing complete metadata about dimensions, compression, and format.
    
    Attributes:
        ifd: IFD index/number
        ifd_type: Type of IFD ('Main Image', 'Overview', 'Mask', etc.)
        dimensions: Image dimensions as formatted string
        block_size: Tile or strip size as formatted string
        data_type: GDAL data type ('Byte', 'Int16', etc.)
        bands: Number of bands/channels
        bits_per_sample: Bits per sample (can be int or list for multiple bands)
        decimals: Decimal precision (can be int or list for multiple bands)
        photometric: Photometric interpretation ('RGB', 'BlackIsZero', etc.)
        compression_algorithm: Compression algorithm
        predictor: Predictor type for compression
        lerc_max_z_error: Max Z error for LERC compression
        space_saving: Reduction in size relative to the uncompressed size as a percentage
    
    Example:
        >>> ifd = IfdInfo(
        ...     ifd=0,
        ...     ifd_type="Main Image",
        ...     dimensions="1024 x 768",
        ...     block_size="256 x 256",
        ...     data_type="Float32",
        ...     bands=3,
        ...     bits_per_sample=8,
        ...     decimals=2,
        ...     compression_algorithm="DEFLATE",
        ...     predictor="2-Horizontal",
        ...     space_saving="75.5%",
        ...     ratio="1.32"
        ... )
        >>> ifd.is_compressed()
        True
    """
    ifd: int
    ifd_type: str
    dimensions: str
    block_size: str
    data_type: str
    bands: int
    bits_per_sample: Any  # Can be int or list
    decimals: Optional[Union[int, List[int]]] = None
    photometric: Optional[str] = None
    compression_algorithm: Optional[str] = None
    predictor: Optional[str] = None
    lerc_max_z_error: Optional[str] = None
    space_saving: Optional[str] = None
    ratio: Optional[str] = None
    
    def is_main_image(self) -> bool:
        """
        Check if this is the main image IFD.
        
        Returns:
            True if IFD index is 0
        """
        return self.ifd == 0
    
    def is_compressed(self) -> bool:
        """
        Check if this IFD uses compression.
        
        Returns:
            True if compression is specified and not 'Uncompressed' or 'NONE'
        """
        if self.compression_algorithm is None:
            return False
        return self.compression_algorithm.lower() not in ('uncompressed', 'none', 'n/a')
    
    def is_tiled(self) -> bool:
        """
        Check if this IFD uses tiling (vs. strips).
        
        Note: This is a heuristic based on block_size format.
        More reliable if you have the actual TileWidth tag.
        
        Returns:
            True if block size suggests tiling
        """
        # Simple heuristic: striped images have a block size equal to image width
        if 'x' in self.block_size.lower() and 'x' in self.dimensions.lower():
            block_parts = self.block_size.lower().split('x')
            dims_parts = self.dimensions.lower().split('x')
            if len(block_parts) == len(dims_parts) == 2:
                w = int(block_parts[0].strip())
                full_width = int(dims_parts[0].strip())
                return w < full_width
        return False


@dataclass
class WktString:
    """
    Represents Well-Known Text coordinate system definition.
    
    Contains WKT2 or Esri PE String representation of coordinate reference
    systems, including format version and source information.
    
    Attributes:
        wkt_string: The WKT or PE String content
        format_version: WKT format version (default: "WKT2_2019")
        source_file: Optional source file path
    
    Example:
        >>> wkt = WktString(
        ...     wkt_string='GEOGCS["WGS 84",DATUM["WGS_1984",...]]',
        ...     format_version="WKT2_2019"
        ... )
        >>> wkt.line_count()
        1
    """
    wkt_string: str
    format_version: str = "WKT2_2019"
    source_file: Optional[str] = None
    
    def line_count(self) -> int:
        """
        Count lines in WKT string.
        
        Returns:
            Number of lines in the WKT string
        """
        return len(self.wkt_string.split('\n'))
    
    def has_content(self) -> bool:
        """
        Check if WKT has actual content.
        
        Returns:
            True if wkt_string is not empty
        """
        return bool(self.wkt_string and self.wkt_string.strip())


@dataclass
class JsonString:
    """
    Represents PROJJSON coordinate system definition.
    
    Contains JSON representation of coordinate reference systems in PROJJSON
    format, with validation capabilities.
    
    Attributes:
        json_string: The PROJJSON content as a string
        source_file: Optional source file path
    
    Example:
        >>> json_data = JsonString(
        ...     json_string='{"type": "GeographicCRS", "name": "WGS 84",...}',
        ... )
        >>> json_data.is_valid_json()
        True
    """
    json_string: str
    source_file: Optional[str] = None
    
    def is_valid_json(self) -> bool:
        """
        Validate JSON structure.
        
        Returns:
            True if json_string is valid JSON, False otherwise
        """
        try:
            json.loads(self.json_string)
            return True
        except json.JSONDecodeError:
            return False
    
    def has_content(self) -> bool:
        """
        Check if JSON has actual content.
        
        Returns:
            True if json_string is not empty
        """
        return bool(self.json_string and self.json_string.strip())


@dataclass
class CogValidation:
    """
    Represents Cloud Optimized GeoTIFF (COG) validation results.
    
    Contains the results of COG validation, including any errors or warnings
    that prevent or impact optimal COG usage.
    
    Attributes:
        warnings: List of validation warnings (non-fatal issues)
        errors: List of validation errors (fatal issues preventing COG status)
        details: Dictionary with additional validation details
        headers_size: Size of IFD headers in bytes
    
    Example:
        >>> validation = CogValidation(
        ...     warnings=["IFD offsets not sorted"],
        ...     errors=[],
        ...     details={"data_offsets": {0: 8192}}
        ... )
        >>> validation.is_valid()
        True
        >>> validation.has_warnings()
        True
    """
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    headers_size: Optional[int] = None
    
    def is_valid(self) -> bool:
        """
        Check if the file is a valid Cloud Optimized GeoTIFF.
        
        A file is considered valid if there are no errors. Warnings are
        acceptable but indicate sub-optimal COG organization.
        
        Returns:
            True if there are no errors
        """
        return len(self.errors) == 0
    
    def has_warnings(self) -> bool:
        """
        Check if there are any validation warnings.
        
        Returns:
            True if there are one or more warnings
        """
        return len(self.warnings) > 0
    
    def has_errors(self) -> bool:
        """
        Check if there are any validation errors.
        
        Returns:
            True if there are one or more errors
        """
        return len(self.errors) > 0
    
    def get_status_message(self) -> str:
        """
        Get a human-readable validation status message.
        
        Returns:
            Status message describing COG validity
        """
        if self.is_valid():
            if self.has_warnings():
                return "Valid COG with warnings"
            return "Valid Cloud Optimized GeoTIFF"
        return "Not a valid Cloud Optimized GeoTIFF"


@dataclass
class XmlMetadata:
    """
    Represents XML metadata content.
    
    This class is used for various XML metadata types including GDAL_METADATA,
    XMP, GEO_METADATA, XML, and PAM metadata. It supports both text-based
    and table-based rendering formats.
    
    Attributes:
        title: Display title for the metadata section
        content: The actual XML content as a string
        xml_type: Rendering type ('text' or 'table')
    
    Example:
        >>> xml = XmlMetadata(
        ...     title="GDAL Metadata",
        ...     content="<GDALMetadata/>",
        ...     xml_type="text"
        ... )
        >>> xml.is_table_format()
        False
    """
    title: str
    content: str
    xml_type: str = 'text'  # 'text' or 'table'
    
    def is_table_format(self) -> bool:
        """
        Check if XML should be rendered as table.
        
        Returns:
            True if xml_type is 'table', False otherwise
        """
        return self.xml_type == 'table'
    
    def has_content(self) -> bool:
        """
        Check if metadata has actual content.
        
        Returns:
            True if content is not empty
        """
        return bool(self.content and self.content.strip())


# ============================================================================
# Wrapper classes (Data suffix)
# ============================================================================

@dataclass
class TiffTagsData:
    """
    Represents TIFF tags data with dynamic title and footer.
    
    This wrapper class allows the tags section to have a dynamic title
    based on tag_scope and includes optional footer text for excluded tags.
    
    Attributes:
        tags: List of TiffTag objects
        title: Dynamic title for the section (includes scope indicator)
        footer: Optional footer text explaining excluded tags
    
    Example:
        >>> tags_data = TiffTagsData(
        ...     tags=[TiffTag(256, "ImageWidth", 1024)],
        ...     title="Compact* TIFF Tags (IFD 0 – Main Image)",
        ...     footer="* TIFF tags excluded from the report: StripOffsets, RowsPerStrip"
        ... )
    """
    tags: List[TiffTag]
    title: str
    footer: Optional[str] = None
    
    def has_footer(self) -> bool:
        """
        Check if there is a footer message.
        
        Returns:
            True if footer is set and not empty
        """
        return bool(self.footer)


@dataclass
class StatisticsData:
    """
    Statistics data for reports with table structure.
    
    Wraps statistics information with formatting metadata for consistent
    rendering across different report types.
    
    Attributes:
        title: Display title for the statistics section
        headers: Column headers for the statistics table
        data: List of dictionaries containing statistics values
        footnote: Optional footnote text
    
    Example:
        >>> stats = StatisticsData(
        ...     title="Statistics",
        ...     headers=['Statistic', 'Band 1', 'Band 2'],
        ...     data=[
        ...         {'Statistic': 'Mean', 'Band 1': '127.5', 'Band 2': '130.2'},
        ...         {'Statistic': 'Std Dev', 'Band 1': '45.3', 'Band 2': '42.1'}
        ...     ]
        ... )
    """
    title: str
    headers: List[str]
    data: List[Dict[str, Any]]
    footnote: Optional[str] = None


@dataclass
class IfdInfoData:
    """
    IFD table data for reports.
    
    Contains structured data for rendering Image File Directory (IFD) information
    in reports. Used by both metadata and comparison reports to display IFD details.
    
    Attributes:
        headers: Column headers for the IFD table
        rows: List of dictionaries, each representing one IFD with column values
        title: Display title for the table (default: "Image File Directory (IFD) List")
    
    Example:
        >>> ifd_data = IfdInfoData(
        ...     headers=['IFD', 'Description', 'Dimensions', 'Algorithm'],
        ...     rows=[
        ...         {'IFD': 0, 'Description': 'Main Image', 'Dimensions': '1024x768', 'Algorithm': 'DEFLATE'},
        ...         {'IFD': 1, 'Description': 'Overview', 'Dimensions': '512x384', 'Algorithm': 'DEFLATE'}
        ...     ],
        ...     title="Image File Directory (IFD) List"
        ... )
    """
    headers: List[str]
    rows: List[Dict[str, Any]]
    title: str = "Image File Directory (IFD) List"


# ============================================================================
# Comparison container classes (Comparison suffix)
# ============================================================================

@dataclass
class DifferencesComparison:
    """
    Comparison data for compression analysis reports.
    
    Encapsulates all metrics needed to compare two GeoTIFF files, typically
    used for compression comparison reports. Includes file sizes, compression
    efficiency, COG status, and format details.
    
    Attributes:
        headers: Column headers for the comparison table
        base_row: Data values for the baseline/input file
        comp_row: Data values for the comparison/output file
        base_name: Display name for baseline file (default: 'Baseline')
        comp_name: Display name for comparison file (default: 'Comparison')
        base_size_mb: Baseline file size in megabytes
        comp_size_mb: Comparison file size in megabytes
        size_difference_mb: Size difference (comp - base) in megabytes
        size_difference_pct: Relative size difference as percentage
        efficiency_difference: Compression efficiency difference
        cog_creation_failed: Whether COG creation was requested but failed
        cog_errors: List of COG validation errors
        cog_warnings: List of COG validation warnings
    
    Example:
        >>> diff = DifferencesComparison(
        ...     headers=['File', 'Type', 'Size (MB)'],
        ...     base_row=['Float32', '100.0'],
        ...     comp_row=['Float32', '25.0'],
        ...     base_size_mb=100.0,
        ...     comp_size_mb=25.0,
        ...     size_difference_mb=-75.0,
        ...     size_difference_pct=-75.0
        ... )
        >>> diff.get_result_text()
        'Decreased by 75.00 MB (75.0% smaller).'
    """
    headers: List[str]
    base_row: List[Any]
    comp_row: List[Any]
    base_name: str = 'Baseline'
    comp_name: str = 'Comparison'
    base_size_mb: float = 0.0
    comp_size_mb: float = 0.0
    size_difference_mb: float = 0.0
    size_difference_pct: float = 0.0
    efficiency_difference: float = 0.0
    cog_creation_failed: bool = False
    cog_errors: Optional[List[str]] = None
    cog_warnings: Optional[List[str]] = None
    
    def get_result_text(self) -> str:
        """
        Generate result summary text for the comparison.
        
        Creates a human-readable summary describing the size change and
        compression efficiency difference between the two files.
        
        Returns:
            Formatted result summary string
        """
        size_text = f"{'Decreased' if self.size_difference_mb < 0 else 'Increased'} by {abs(self.size_difference_mb):,.2f} MB"
        rel_text = f"({abs(self.size_difference_pct):.1f}% {'smaller' if self.size_difference_mb < 0 else 'larger'})"
        
        if self.efficiency_difference > 0.05:
            efficiency_text = f", {self.efficiency_difference:.1f}% more efficient compression"
        elif self.efficiency_difference < -0.05:
            efficiency_text = f", {abs(self.efficiency_difference):.1f}% less efficient compression"
        else:
            efficiency_text = ""
        
        return f"{size_text} {rel_text}{efficiency_text}."


@dataclass
class IfdInfoComparison:
    """
    Grouped IFD data for comparison reports.
    
    Contains IFD tables for both baseline and comparison files under a single section.
    Each file's data includes a sub-header and its corresponding table.
    
    Attributes:
        title: Main section title (e.g., "IFDs")
        files: List of tuples (file_label, IfdInfoData)
    
    Example:
        >>> comp_ifd = IfdInfoComparison(
        ...     title="IFDs",
        ...     files=[
        ...         ("Baseline", baseline_ifd_data),
        ...         ("Comparison", comparison_ifd_data)
        ...     ]
        ... )
    """
    title: str
    files: List[Tuple[str, IfdInfoData]]


@dataclass
class StatisticsComparison:
    """
    Grouped statistics data for comparison reports.
    
    Contains statistics for both baseline and comparison files under a single section.
    Each file's data includes a sub-header and its corresponding table.
    
    Attributes:
        title: Main section title (e.g., "Statistics")
        files: List of tuples (file_label, StatisticsData)
    
    Example:
        >>> comp_stats = StatisticsComparison(
        ...     title="Statistics",
        ...     files=[
        ...         ("Baseline", baseline_stats),
        ...         ("Comparison", comparison_stats)
        ...     ]
        ... )
    """
    title: str
    files: List[Tuple[str, StatisticsData]]


@dataclass
class HistogramComparison:
    """
    Grouped histogram data for comparison reports.
    
    Contains histograms for both baseline and comparison files under a single section.
    Each file's data includes a sub-header and its corresponding histogram image.
    
    Attributes:
        title: Main section title (e.g., "Histograms")
        files: List of tuples (file_label, HistogramImage)
    
    Example:
        >>> comp_hist = HistogramComparison(
        ...     title="Histograms",
        ...     files=[
        ...         ("Baseline", baseline_histogram),
        ...         ("Comparison", comparison_histogram)
        ...     ]
        ... )
    """
    title: str
    files: List[Tuple[str, HistogramImage]]


@dataclass
class CogValidationComparison:
    """
    Grouped COG validation data for comparison reports.
    
    Contains COG validation results for both baseline and comparison files under a single section.
    Each file's data includes a sub-header and its corresponding validation results.
    
    Attributes:
        title: Main section title (e.g., "COG Validation")
        files: List of tuples (file_label, CogValidation)
    
    Example:
        >>> comp_cog = CogValidationComparison(
        ...     title="COG Validation",
        ...     files=[
        ...         ("Baseline", baseline_cog),
        ...         ("Comparison", comparison_cog)
        ...     ]
        ... )
    """
    title: str
    files: List[Tuple[str, CogValidation]]
