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
Value Extractors for Validation Package.

This module provides the ValueExtractor class that extracts values from
GeoTIFF files for validation against rules. It interfaces with the existing
MetadataExtractor infrastructure.

Classes:
    ValueExtractor: Extracts values from GeoTIFF for validation

Supported Sections:
    - tag: TIFF tag values by tag code
    - geokey: GeoKey values by GeoKey ID
    - gdal: GDAL_METADATA XML item values by name
    - geo: GEO_METADATA XML values by XPath (Phase 4)
    - xmp: XMP metadata values by XPath (Phase 4)
    - xml: External XML file values by XPath (Phase 4)
    - projjson: PROJJSON values by JSONPath (Phase 5)
"""

import logging
from typing import Any, Dict, List, Optional

import lxml.etree as etree

logger = logging.getLogger(__name__)


class ValueExtractor:
    """
    Extracts values from GeoTIFF files for validation.

    This class wraps the MetadataExtractor and provides methods to extract
    specific values by key for each section type (tag, geokey, gdal, etc.).

    Attributes:
        extractor: The underlying MetadataExtractor instance
        _tags_cache: Cached TIFF tags
        _geokeys_cache: Cached GeoKeys
        _gdal_metadata_cache: Cached GDAL metadata XML

    Example:
        >>> with MetadataExtractor(filepath) as extractor:
        ...     value_extractor = ValueExtractor(extractor)
        ...     bits = value_extractor.extract_tag('258')
        ...     print(bits)
        32
    """

    def __init__(self, extractor):
        """
        Initialize the ValueExtractor.

        Args:
            extractor: MetadataExtractor instance with open file handles
        """
        self.extractor = extractor

        # Caches to avoid repeated extraction
        self._tags_cache: Optional[List] = None
        self._geokeys_cache: Optional[List] = None
        self._gdal_metadata_cache: Optional[str] = None
        self._gdal_items_cache: Optional[Dict[str, str]] = None
        self._gdal_items_by_sample_cache: Optional[Dict[str, Dict[int, str]]] = None
        self._geo_metadata_cache: Optional[str] = None
        self._xmp_metadata_cache: Optional[str] = None
        self._xml_metadata_cache: Optional[str] = None
        self._projjson_cache: Optional[str] = None
        self._computed_stats_cache: Optional[List] = None  # On-demand computed statistics

    # =========================================================================
    # Section Content Extraction (for section-level checks)
    # =========================================================================

    def get_section_content(self, section_type: str) -> Optional[Any]:
        """
        Get the content for a section if it exists.

        Used to check if an entire section is available before extracting
        individual values.

        Args:
            section_type: The type of section ('tag', 'geokey', 'gdal', etc.)

        Returns:
            The section content, or None if the section is missing
        """
        if section_type == 'tag':
            return self._get_tags()
        elif section_type == 'geokey':
            return self._get_geokeys()
        elif section_type == 'gdal':
            # GDAL section is always available - statistics can be computed on-demand
            # even if GDAL_METADATA tag is missing
            return True
        elif section_type == 'geo':
            return self._get_geo_metadata_content()
        elif section_type == 'xmp':
            return self._get_xmp_metadata_content()
        elif section_type == 'xml':
            return self._get_xml_metadata_content()
        elif section_type == 'projjson':
            return self._get_projjson_content()
        else:
            logger.warning(f"Unknown section type: {section_type}")
            return None

    # =========================================================================
    # TIFF Tag Extraction
    # =========================================================================

    def _get_tags(self) -> Optional[List]:
        """Get cached tags or extract them."""
        if self._tags_cache is None:
            self._tags_cache = self.extractor.extract_tags(page=0, tag_scope='complete')
        return self._tags_cache if self._tags_cache else None

    def extract_tag(self, key: str) -> Optional[Any]:
        """
        Extract TIFF tag value by tag code.

        Args:
            key: The tag code as a string (e.g., '258' for BitsPerSample)

        Returns:
            The tag value, or None if not found
        """
        tags = self._get_tags()
        if not tags:
            return None

        tag_code = int(key)
        for tag in tags:
            if tag.code == tag_code:
                return tag.value
        return None

    # =========================================================================
    # GeoKey Extraction
    # =========================================================================

    def _get_geokeys(self) -> Optional[List]:
        """Get cached geokeys or extract them."""
        if self._geokeys_cache is None:
            self._geokeys_cache = self.extractor.extract_geokeys()
        return self._geokeys_cache if self._geokeys_cache else None

    def extract_geokey(self, key: str) -> Optional[Any]:
        """
        Extract GeoKey value by GeoKey ID.

        Args:
            key: The GeoKey ID as a string (e.g., '3072' for ProjectedCRSGeoKey)

        Returns:
            The GeoKey value, or None if not found
        """
        geokeys = self._get_geokeys()
        if not geokeys:
            return None

        geokey_id = int(key)
        for geokey in geokeys:
            if geokey.id == geokey_id:
                return geokey.value
        return None

    # =========================================================================
    # GDAL Metadata Extraction
    # =========================================================================

    def _get_gdal_metadata_content(self) -> Optional[str]:
        """Get cached GDAL metadata content or extract it."""
        if self._gdal_metadata_cache is None:
            gdal_md = self.extractor.extract_gdal_metadata()
            if gdal_md and gdal_md.content:
                self._gdal_metadata_cache = gdal_md.content
        return self._gdal_metadata_cache

    def _get_gdal_items(self) -> Dict[str, str]:
        """
        Parse GDAL metadata XML and return items as a dictionary.

        Returns:
            Dict mapping item names to values (for items without sample attribute)
        """
        if self._gdal_items_cache is not None:
            return self._gdal_items_cache

        self._gdal_items_cache = {}
        self._gdal_items_by_sample_cache = {}
        content = self._get_gdal_metadata_content()
        if not content:
            return self._gdal_items_cache

        try:
            root = etree.fromstring(content.encode('utf-8'))
            # GDAL metadata format:
            # <GDALMetadata>
            #   <Item name="NAME">VALUE</Item>
            #   <Item name="NAME" sample="0">VALUE</Item>
            # </GDALMetadata>
            for item in root.findall('.//Item'):
                name = item.get('name')
                if name:
                    sample = item.get('sample')
                    if sample is not None:
                        # Sample-specific item
                        try:
                            sample_idx = int(sample)
                            if name not in self._gdal_items_by_sample_cache:
                                self._gdal_items_by_sample_cache[name] = {}
                            self._gdal_items_by_sample_cache[name][sample_idx] = item.text or ''
                        except ValueError:
                            logger.warning(f"Invalid sample index '{sample}' for GDAL item '{name}'")
                    else:
                        # Global item (no sample attribute)
                        self._gdal_items_cache[name] = item.text or ''
        except etree.XMLSyntaxError as e:
            logger.warning(f"Failed to parse GDAL metadata XML: {e}")

        return self._gdal_items_cache

    def _get_gdal_items_by_sample(self) -> Dict[str, Dict[int, str]]:
        """
        Get GDAL metadata items organized by sample (band) index.

        Returns:
            Dict mapping item names to dicts of {sample_index: value}
        """
        if self._gdal_items_by_sample_cache is None:
            self._get_gdal_items()  # Populates both caches
        return self._gdal_items_by_sample_cache or {}

    # Mapping from GDAL/PAM statistics names to StatisticsBand attributes
    # Used for on-demand statistics calculation
    STATS_ATTRIBUTE_MAP = {
        'STATISTICS_MINIMUM': 'minimum',
        'STATISTICS_MAXIMUM': 'maximum',
        'STATISTICS_MEAN': 'mean',
        'STATISTICS_STDDEV': 'std_dev',
        'STATISTICS_VALID_PERCENT': 'valid_percent',
    }

    def _get_computed_statistics(self) -> Optional[List]:
        """
        Get cached computed statistics or calculate them on-demand.

        Uses the MetadataExtractor's extract_statistics() method which
        calculates statistics via NumPy.

        Returns:
            List of StatisticsBand objects, or None if calculation fails
        """
        if self._computed_stats_cache is None:
            self._computed_stats_cache = self.extractor.extract_statistics()
        return self._computed_stats_cache

    def _get_band_count(self) -> int:
        """Get the number of bands in the raster."""
        stats = self._get_computed_statistics()
        return len(stats) if stats else 0

    def _extract_statistic_value(self, stat_name: str, band_idx: int) -> Optional[float]:
        """
        Extract a computed statistic value for a specific band.

        Args:
            stat_name: The statistic name (e.g., 'STATISTICS_MINIMUM')
            band_idx: The band index (0-based)

        Returns:
            The computed statistic value, or None if not available
        """
        stats_bands = self._get_computed_statistics()
        if not stats_bands:
            return None

        if band_idx < 0 or band_idx >= len(stats_bands):
            logger.warning(
                f"Band index {band_idx} out of range (0-{len(stats_bands)-1}) "
                f"for stats key: {stat_name}"
            )
            return None

        band_stats = stats_bands[band_idx]
        attr_name = self.STATS_ATTRIBUTE_MAP.get(stat_name)
        if attr_name is None:
            return None

        return getattr(band_stats, attr_name, None)

    def _extract_colorinterp_value(self, band_idx: int) -> Optional[str]:
        """
        Extract color interpretation for a specific band via GDAL.

        Args:
            band_idx: The band index (0-based)

        Returns:
            Color interpretation string (e.g., 'Red', 'Green', 'Blue', 'Gray'), or None
        """
        try:
            from osgeo import gdal
            ds = gdal.Open(str(self.extractor.filepath), gdal.GA_ReadOnly)
            if ds is None:
                return None

            band = ds.GetRasterBand(band_idx + 1)  # GDAL uses 1-based indexing
            if band is None:
                ds = None
                return None

            color_interp = band.GetColorInterpretation()
            ds = None

            # Map GDAL color interpretation to string
            color_interp_names = {
                gdal.GCI_Undefined: 'Undefined',
                gdal.GCI_GrayIndex: 'Gray',
                gdal.GCI_PaletteIndex: 'Palette',
                gdal.GCI_RedBand: 'Red',
                gdal.GCI_GreenBand: 'Green',
                gdal.GCI_BlueBand: 'Blue',
                gdal.GCI_AlphaBand: 'Alpha',
                gdal.GCI_HueBand: 'Hue',
                gdal.GCI_SaturationBand: 'Saturation',
                gdal.GCI_LightnessBand: 'Lightness',
                gdal.GCI_CyanBand: 'Cyan',
                gdal.GCI_MagentaBand: 'Magenta',
                gdal.GCI_YellowBand: 'Yellow',
                gdal.GCI_BlackBand: 'Black',
            }
            # Handle NIR which may not be in standard GDAL constants
            if hasattr(gdal, 'GCI_NIRBand'):
                color_interp_names[gdal.GCI_NIRBand] = 'NIR'

            return color_interp_names.get(color_interp, 'Undefined')

        except ImportError:
            logger.warning("GDAL not available for color interpretation lookup")
            return None
        except Exception as e:
            logger.warning(f"Failed to get color interpretation: {e}")
            return None

    def extract_gdal(self, key: str) -> Optional[Any]:
        """
        Extract GDAL metadata item value by name.

        Supports three extraction modes:
        1. On-demand statistics: STATISTICS_* keys are computed from raster data
        2. On-demand color interpretation: COLORINTERP keys are queried via GDAL
        3. Standard GDAL_METADATA: All other keys are looked up in the XML tag

        Band suffix syntax:
        - 'KEY' - For statistics/colorinterp: returns list of values for ALL bands
        - 'KEY:N' - Returns value for band N (0-indexed)

        Supported on-demand statistics keys:
        - STATISTICS_MINIMUM: Minimum pixel value
        - STATISTICS_MAXIMUM: Maximum pixel value
        - STATISTICS_MEAN: Mean pixel value
        - STATISTICS_STDDEV: Standard deviation
        - STATISTICS_VALID_PERCENT: Percentage of valid pixels

        Args:
            key: The metadata item name with optional band suffix
                 (e.g., 'STATISTICS_MINIMUM', 'STATISTICS_MINIMUM:0', 'COLORINTERP:1')

        Returns:
            The item value, or None if not found.
            For keys without band suffix on statistics/colorinterp, returns a list
            of values for all bands (for validation against all bands).

        Example:
            >>> extract_gdal('STATISTICS_MINIMUM')
            [-430.5, -425.2, -410.1]  # All bands
            >>> extract_gdal('STATISTICS_MINIMUM:0')
            -430.5  # Band 0 only
            >>> extract_gdal('COLORINTERP:0')
            'Red'
            >>> extract_gdal('AREA_OR_POINT')
            'Point'  # Standard GDAL_METADATA item
        """
        # Parse band suffix
        band_idx = None
        base_key = key
        if ':' in key:
            parts = key.rsplit(':', 1)
            try:
                band_idx = int(parts[1])
                base_key = parts[0]
            except ValueError:
                # Not a valid band index, treat entire key as the name
                pass

        # Check if this is an on-demand statistics key
        if base_key in self.STATS_ATTRIBUTE_MAP:
            if band_idx is not None:
                # Specific band requested
                return self._extract_statistic_value(base_key, band_idx)
            else:
                # No band suffix - return values for ALL bands
                band_count = self._get_band_count()
                if band_count == 0:
                    return None
                values = []
                for idx in range(band_count):
                    val = self._extract_statistic_value(base_key, idx)
                    if val is None:
                        return None  # Can't compute for all bands
                    values.append(val)
                return values

        # Check if this is a COLORINTERP key
        if base_key == 'COLORINTERP':
            if band_idx is not None:
                # Specific band requested
                # First try GDAL_METADATA XML
                items_by_sample = self._get_gdal_items_by_sample()
                if 'COLORINTERP' in items_by_sample and band_idx in items_by_sample['COLORINTERP']:
                    return items_by_sample['COLORINTERP'][band_idx]
                # Fall back to GDAL query
                return self._extract_colorinterp_value(band_idx)
            else:
                # No band suffix - return values for ALL bands
                band_count = self._get_band_count()
                if band_count == 0:
                    return None
                values = []
                for idx in range(band_count):
                    # First try GDAL_METADATA XML
                    items_by_sample = self._get_gdal_items_by_sample()
                    if 'COLORINTERP' in items_by_sample and idx in items_by_sample['COLORINTERP']:
                        values.append(items_by_sample['COLORINTERP'][idx])
                    else:
                        # Fall back to GDAL query
                        val = self._extract_colorinterp_value(idx)
                        if val is None:
                            return None
                        values.append(val)
                return values

        # Check if this is a sample-specific key in GDAL_METADATA
        if band_idx is not None:
            items_by_sample = self._get_gdal_items_by_sample()
            if base_key in items_by_sample and band_idx in items_by_sample[base_key]:
                return items_by_sample[base_key][band_idx]
            # Key not found for this sample
            return None

        # Standard GDAL_METADATA item lookup
        items = self._get_gdal_items()
        return items.get(key)

    # =========================================================================
    # XML XPath Extraction (for geo, xmp, xml sections)
    # =========================================================================

    def _collect_all_namespaces(self, root: etree._Element) -> Dict[str, str]:
        """
        Collect all namespaces from the entire XML document.

        This walks the entire document tree to discover all namespace
        declarations, not just those at the root level.

        Args:
            root: The root element of the XML document

        Returns:
            Dict mapping namespace prefixes to URIs
        """
        namespaces = {}

        # Collect namespaces from all elements in the document
        for elem in root.iter():
            for prefix, uri in elem.nsmap.items():
                if prefix is None:
                    # Handle default namespace - give it a usable prefix
                    if 'default' not in namespaces:
                        namespaces['default'] = uri
                elif prefix not in namespaces:
                    namespaces[prefix] = uri

        return namespaces

    def _convert_to_namespace_agnostic(self, xpath: str) -> str:
        """
        Convert an XPath expression to namespace-agnostic form.

        This converts element names to use local-name() function,
        allowing XPath to work regardless of namespace prefixes.

        Args:
            xpath: The original XPath expression

        Returns:
            Namespace-agnostic XPath expression

        Example:
            >>> _convert_to_namespace_agnostic('//gmd:fileIdentifier')
            "//*[local-name()='fileIdentifier']"
        """
        import re

        def convert_element(element: str) -> str:
            """Convert a single element name to namespace-agnostic form."""
            # Don't modify attributes (@something)
            if element.startswith('@'):
                return element

            # Don't modify functions (something())
            if '(' in element:
                return element

            # Don't modify wildcards
            if element == '*':
                return element

            # Don't modify empty strings
            if not element:
                return element

            # Remove namespace prefix if present
            if ':' in element:
                local_name = element.split(':')[1]
            else:
                local_name = element

            return f"*[local-name()='{local_name}']"

        # Split xpath into path segments, preserving delimiters
        # This handles //element, /element, element
        parts = re.split(r'(/+)', xpath)

        result_parts = []
        for part in parts:
            if part in ('/', '//'):
                result_parts.append(part)
            elif part:
                # Only convert if it looks like an element name
                # Skip if it's a predicate [...] or attribute
                if part.startswith('[') or part.startswith('@'):
                    result_parts.append(part)
                else:
                    # Handle predicates within the path segment
                    if '[' in part:
                        # Split element and predicate
                        elem_part = part[:part.index('[')]
                        pred_part = part[part.index('['):]
                        converted = convert_element(elem_part) + pred_part
                    else:
                        converted = convert_element(part)
                    result_parts.append(converted)

        return ''.join(result_parts)

    def extract_xpath(
        self,
        xpath: str,
        xml_content: str,
        namespace_agnostic: bool = True
    ) -> Optional[Any]:
        """
        Extract value from XML using XPath with namespace handling.

        Supports two modes:
        1. Namespace-aware: Uses document namespaces with original XPath
        2. Namespace-agnostic: Converts XPath to use local-name() function

        Args:
            xpath: The XPath expression
            xml_content: The XML content string
            namespace_agnostic: If True, convert XPath to namespace-agnostic form

        Returns:
            The extracted value, or None if not found

        Example:
            >>> extract_xpath("//gmd:fileIdentifier/gco:CharacterString", xml)
            "abc123"
        """
        if not xml_content:
            return None

        try:
            root = etree.fromstring(xml_content.encode('utf-8'))

            # Collect all namespaces from the document
            namespaces = self._collect_all_namespaces(root)

            # Try original XPath first with document namespaces
            try:
                results = root.xpath(xpath, namespaces=namespaces)
                if results:
                    return self._extract_xpath_result(results[0])
            except etree.XPathError:
                pass  # Fall through to namespace-agnostic

            # If namespace-agnostic mode is enabled, try converted XPath
            if namespace_agnostic:
                agnostic_xpath = self._convert_to_namespace_agnostic(xpath)
                try:
                    results = root.xpath(agnostic_xpath)
                    if results:
                        return self._extract_xpath_result(results[0])
                except etree.XPathError as e:
                    logger.debug(f"Namespace-agnostic XPath failed: {e}")

            return None

        except etree.XPathError as e:
            logger.warning(f"XPath evaluation error: {e}")
            return None
        except etree.XMLSyntaxError as e:
            logger.warning(f"XML parsing error: {e}")
            return None

    def _extract_xpath_result(self, result: Any) -> Any:
        """
        Extract the value from an XPath result.

        Args:
            result: The XPath result (element, attribute, or text)

        Returns:
            The extracted value as string
        """
        if isinstance(result, etree._Element):
            # Return text content of element
            return result.text
        elif isinstance(result, etree._ElementUnicodeResult):
            # Attribute or text node
            return str(result)
        else:
            return str(result)

    def _get_geo_metadata_content(self) -> Optional[str]:
        """Get cached GEO_METADATA content or extract it."""
        if self._geo_metadata_cache is None:
            geo_md = self.extractor.extract_geo_metadata()
            if geo_md and geo_md.content:
                self._geo_metadata_cache = geo_md.content
        return self._geo_metadata_cache

    def _get_xmp_metadata_content(self) -> Optional[str]:
        """Get cached XMP metadata content or extract it."""
        if self._xmp_metadata_cache is None:
            xmp_md = self.extractor.extract_xmp_metadata()
            if xmp_md and xmp_md.content:
                self._xmp_metadata_cache = xmp_md.content
        return self._xmp_metadata_cache

    def _get_xml_metadata_content(self) -> Optional[str]:
        """Get cached external XML metadata content or extract it."""
        if self._xml_metadata_cache is None:
            xml_md = self.extractor.extract_xml_metadata()
            if xml_md and xml_md.content:
                self._xml_metadata_cache = xml_md.content
        return self._xml_metadata_cache

    def extract_geo(self, key: str) -> Optional[Any]:
        """
        Extract value from GEO_METADATA (Tag 50909) using XPath.

        GEO_METADATA typically contains ISO 19115/19139 metadata with
        namespaces like gmd:, gco:, gmi:. The extraction uses
        namespace-agnostic XPath to work with any namespace version.

        Args:
            key: The XPath expression (e.g., '//fileIdentifier/CharacterString')

        Returns:
            The extracted value, or None if not found

        Example:
            >>> extract_geo('//gmd:fileIdentifier/gco:CharacterString')
            'abc123-uuid'
        """
        content = self._get_geo_metadata_content()
        return self.extract_xpath(key, content, namespace_agnostic=True) if content else None

    def extract_xmp(self, key: str) -> Optional[Any]:
        """
        Extract value from XMP metadata (Tag 700) using XPath.

        XMP (Extensible Metadata Platform) uses namespaces like:
        - dc: Dublin Core (title, creator, description)
        - xmp: XMP basic (CreateDate, ModifyDate)
        - photoshop: Photoshop metadata
        - tiff: TIFF metadata

        Args:
            key: The XPath expression (e.g., '//dc:title/rdf:Alt/rdf:li')

        Returns:
            The extracted value, or None if not found

        Example:
            >>> extract_xmp('//dc:description/rdf:Alt/rdf:li')
            'Image description'
        """
        content = self._get_xmp_metadata_content()
        return self.extract_xpath(key, content, namespace_agnostic=True) if content else None

    def extract_xml(self, key: str) -> Optional[Any]:
        """
        Extract value from external XML metadata file using XPath.

        External XML files (.xml sidecar files) can contain various
        metadata formats including ISO 19115/19139, FGDC, or custom schemas.

        Args:
            key: The XPath expression

        Returns:
            The extracted value, or None if not found

        Example:
            >>> extract_xml('//idinfo/citation/citeinfo/title')
            'Dataset Title'
        """
        content = self._get_xml_metadata_content()
        return self.extract_xpath(key, content, namespace_agnostic=True) if content else None

    # =========================================================================
    # PROJJSON Extraction (Phase 5)
    # =========================================================================

    def _get_projjson_content(self) -> Optional[str]:
        """Get cached PROJJSON content or extract it."""
        if self._projjson_cache is None:
            projjson = self.extractor.extract_projjson_string()
            if projjson and projjson.json_string:
                self._projjson_cache = projjson.json_string
        return self._projjson_cache

    def extract_projjson(self, key: str) -> Optional[Any]:
        """
        Extract value from PROJJSON using full JSONPath expressions.

        Uses the jsonpath-ng library for full JSONPath support including:
        - Dot notation: $.name, $.id.authority
        - Array indexing: $.conversion.method.id[0]
        - Recursive descent: $..name
        - Array slicing: $.coordinateSystem.axis[0:2]
        - Wildcards: $.coordinateSystem.axis[*].name
        - Filters: $..axis[?(@.direction=='north')]

        Args:
            key: The JSONPath expression (e.g., '$.name', '$.type', '$.id.authority')

        Returns:
            The extracted value, or None if not found.
            For single matches, returns the value directly.
            For multiple matches, returns a list of values.

        Example:
            >>> extract_projjson('$.name')
            'NAD83 / UTM zone 10N'
            >>> extract_projjson('$.id.authority')
            'EPSG'
            >>> extract_projjson('$..name')
            ['NAD83 / UTM zone 10N', 'North American Datum 1983', ...]
        """
        content = self._get_projjson_content()
        if not content:
            return None

        import json
        try:
            from jsonpath_ng import parse as jsonpath_parse
            from jsonpath_ng.exceptions import JsonPathParserError

            data = json.loads(content)

            # Ensure path starts with $
            path = key
            if not path.startswith('$'):
                path = '$.' + path

            # Parse and evaluate JSONPath
            try:
                jsonpath_expr = jsonpath_parse(path)
                matches = jsonpath_expr.find(data)

                if not matches:
                    return None

                # Return single value if only one match, otherwise list
                if len(matches) == 1:
                    return matches[0].value
                else:
                    return [match.value for match in matches]

            except JsonPathParserError as e:
                logger.debug(f"JSONPath parse error for '{key}': {e}")
                # Fall back to simple dot notation if jsonpath-ng fails
                return self._extract_projjson_simple(data, key)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse PROJJSON: {e}")
            return None
        except ImportError:
            logger.warning("jsonpath-ng not installed, using simple extraction")
            import json
            try:
                data = json.loads(content)
                return self._extract_projjson_simple(data, key)
            except json.JSONDecodeError:
                return None

    def _extract_projjson_simple(self, data: Dict, key: str) -> Optional[Any]:
        """
        Simple fallback extraction using dot notation only.

        Args:
            data: The parsed PROJJSON data
            key: The path (e.g., '$.name', 'name', 'id.authority')

        Returns:
            The extracted value, or None if not found
        """
        # Handle JSONPath prefix
        path = key
        if path.startswith('$.'):
            path = path[2:]
        elif path.startswith('$'):
            path = path[1:]

        # Handle empty path (root)
        if not path:
            return data

        # Navigate nested structure
        parts = path.split('.')
        current = data
        for part in parts:
            # Handle array indexing [0], [1], etc.
            if '[' in part and ']' in part:
                base = part[:part.index('[')]
                index_str = part[part.index('[') + 1:part.index(']')]
                try:
                    index = int(index_str)
                    if base:
                        current = current.get(base, [])
                    if isinstance(current, list) and 0 <= index < len(current):
                        current = current[index]
                    else:
                        return None
                except (ValueError, TypeError):
                    return None
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    # =========================================================================
    # Generic Value Extraction
    # =========================================================================

    def extract_value(self, section: str, key: str) -> Optional[Any]:
        """
        Extract a value from any section by key.

        This is the main entry point for the validation engine.

        Args:
            section: The section type ('tag', 'geokey', 'gdal', etc.)
            key: The key to extract (tag code, geokey id, item name, xpath, etc.)

        Returns:
            The extracted value, or None if not found
        """
        extractors = {
            'tag': self.extract_tag,
            'geokey': self.extract_geokey,
            'gdal': self.extract_gdal,
            'geo': self.extract_geo,
            'xmp': self.extract_xmp,
            'xml': self.extract_xml,
            'projjson': self.extract_projjson,
        }

        extractor = extractors.get(section)
        if extractor:
            return extractor(key)
        else:
            logger.warning(f"Unknown section type for extraction: {section}")
            return None

    # =========================================================================
    # Type Conversion
    # =========================================================================

    @staticmethod
    def convert_value(value: Any, data_type: str) -> Any:
        """
        Convert a value to the expected data type.

        Used to normalize values before comparison.

        Args:
            value: The value to convert
            data_type: The target type. Basic types: 'string', 'integer',
                       'float', 'boolean'. Extended types (Phase 5): 'date',
                       'datetime', 'url', 'email'.

        Returns:
            The converted value, or the original if conversion fails.
            Extended types are returned as strings (validation happens separately).
        """
        if value is None:
            return None

        try:
            if data_type == 'integer':
                if isinstance(value, (list, tuple)):
                    return [int(v) for v in value]
                return int(value)
            elif data_type == 'float':
                if isinstance(value, (list, tuple)):
                    return [float(v) for v in value]
                return float(value)
            elif data_type == 'string':
                return str(value)
            elif data_type == 'boolean':
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    return value.lower() in ('true', 'yes', '1')
                return bool(value)
            # Extended types (Phase 5) - stored as strings, validation separate
            elif data_type in ('date', 'datetime', 'url', 'email'):
                return str(value)
            else:
                return value
        except (ValueError, TypeError):
            return value
