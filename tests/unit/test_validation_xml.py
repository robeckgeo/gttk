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
Unit tests for XML validation functionality (Phase 4).

This module tests the namespace-agnostic XPath extraction for:
- GEO_METADATA (ISO 19115/19139)
- XMP metadata (Dublin Core, XMP basic)
- External XML metadata files

Test coverage:
- Namespace-agnostic XPath conversion
- XPath extraction with various namespace patterns
- ISO 19115/19139 metadata patterns
- XMP/Dublin Core metadata patterns
"""

import pytest
from unittest.mock import Mock, MagicMock, PropertyMock

from gttk.utils.validation.extractors import ValueExtractor


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_extractor():
    """Create a mock MetadataExtractor."""
    extractor = Mock()
    extractor.extract_tags.return_value = []
    extractor.extract_geokeys.return_value = []
    extractor.extract_gdal_metadata.return_value = None
    extractor.extract_geo_metadata.return_value = None
    extractor.extract_xmp_metadata.return_value = None
    extractor.extract_xml_metadata.return_value = None
    extractor.extract_projjson_string.return_value = None
    return extractor


@pytest.fixture
def iso19139_xml():
    """Sample ISO 19115/19139 metadata XML with namespaces."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco"
                 xmlns:gmi="http://www.isotc211.org/2005/gmi">
    <gmd:fileIdentifier>
        <gco:CharacterString>abc123-uuid-xyz</gco:CharacterString>
    </gmd:fileIdentifier>
    <gmd:language>
        <gco:CharacterString>eng</gco:CharacterString>
    </gmd:language>
    <gmd:dateStamp>
        <gco:Date>2026-01-15</gco:Date>
    </gmd:dateStamp>
    <gmd:identificationInfo>
        <gmd:MD_DataIdentification>
            <gmd:citation>
                <gmd:CI_Citation>
                    <gmd:title>
                        <gco:CharacterString>Test Dataset Title</gco:CharacterString>
                    </gmd:title>
                </gmd:CI_Citation>
            </gmd:citation>
            <gmd:abstract>
                <gco:CharacterString>This is a test abstract.</gco:CharacterString>
            </gmd:abstract>
        </gmd:MD_DataIdentification>
    </gmd:identificationInfo>
</gmd:MD_Metadata>'''


@pytest.fixture
def xmp_xml():
    """Sample XMP metadata XML with Dublin Core and XMP namespaces."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
    <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
        <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/"
                        xmlns:xmp="http://ns.adobe.com/xap/1.0/"
                        xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
                        xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/">
            <dc:title>
                <rdf:Alt>
                    <rdf:li xml:lang="x-default">Test Image Title</rdf:li>
                </rdf:Alt>
            </dc:title>
            <dc:description>
                <rdf:Alt>
                    <rdf:li xml:lang="x-default">Image description text</rdf:li>
                </rdf:Alt>
            </dc:description>
            <dc:creator>
                <rdf:Seq>
                    <rdf:li>John Doe</rdf:li>
                </rdf:Seq>
            </dc:creator>
            <xmp:CreateDate>2026-01-15T10:30:00</xmp:CreateDate>
            <tiff:ImageWidth>1024</tiff:ImageWidth>
            <tiff:ImageLength>768</tiff:ImageLength>
            <photoshop:Credit>Photo Credit Line</photoshop:Credit>
        </rdf:Description>
    </rdf:RDF>
</x:xmpmeta>'''


@pytest.fixture
def fgdc_xml():
    """Sample FGDC metadata XML (no namespaces)."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<metadata>
    <idinfo>
        <citation>
            <citeinfo>
                <origin>USGS</origin>
                <pubdate>20260115</pubdate>
                <title>Test Dataset</title>
            </citeinfo>
        </citation>
        <descript>
            <abstract>Test abstract text.</abstract>
            <purpose>Testing purposes.</purpose>
        </descript>
        <keywords>
            <theme>
                <themekt>ISO 19115 Topic Category</themekt>
                <themekey>elevation</themekey>
                <themekey>imagery</themekey>
            </theme>
        </keywords>
    </idinfo>
    <dataqual>
        <logic>Logical consistency report.</logic>
        <complete>Completeness report.</complete>
    </dataqual>
</metadata>'''


# =============================================================================
# Namespace-Agnostic XPath Conversion Tests
# =============================================================================

@pytest.mark.unit
class TestNamespaceAgnosticConversion:
    """Test conversion of XPath to namespace-agnostic form."""

    def test_simple_element(self, mock_extractor):
        """Test conversion of simple element name."""
        ve = ValueExtractor(mock_extractor)

        result = ve._convert_to_namespace_agnostic('//title')
        assert result == "//*[local-name()='title']"

    def test_namespaced_element(self, mock_extractor):
        """Test conversion of namespaced element."""
        ve = ValueExtractor(mock_extractor)

        result = ve._convert_to_namespace_agnostic('//gmd:fileIdentifier')
        assert result == "//*[local-name()='fileIdentifier']"

    def test_nested_path(self, mock_extractor):
        """Test conversion of nested path."""
        ve = ValueExtractor(mock_extractor)

        result = ve._convert_to_namespace_agnostic('//gmd:fileIdentifier/gco:CharacterString')
        assert result == "//*[local-name()='fileIdentifier']/*[local-name()='CharacterString']"

    def test_deeply_nested_path(self, mock_extractor):
        """Test conversion of deeply nested path."""
        ve = ValueExtractor(mock_extractor)

        result = ve._convert_to_namespace_agnostic('//idinfo/citation/citeinfo/title')
        assert result == "//*[local-name()='idinfo']/*[local-name()='citation']/*[local-name()='citeinfo']/*[local-name()='title']"

    def test_preserves_predicates(self, mock_extractor):
        """Test that predicates are preserved."""
        ve = ValueExtractor(mock_extractor)

        result = ve._convert_to_namespace_agnostic('//item[@name="test"]')
        assert "[local-name()='item']" in result
        assert '[@name="test"]' in result

    def test_preserves_attributes(self, mock_extractor):
        """Test that attribute selectors are preserved."""
        ve = ValueExtractor(mock_extractor)

        result = ve._convert_to_namespace_agnostic('//@version')
        assert result == '//@version'

    def test_preserves_wildcards(self, mock_extractor):
        """Test that wildcards are preserved."""
        ve = ValueExtractor(mock_extractor)

        result = ve._convert_to_namespace_agnostic('//*')
        assert result == '//*'


# =============================================================================
# ISO 19115/19139 Extraction Tests
# =============================================================================

@pytest.mark.unit
class TestIso19139Extraction:
    """Test XPath extraction from ISO 19115/19139 metadata."""

    def test_extract_file_identifier(self, mock_extractor, iso19139_xml):
        """Test extracting fileIdentifier from ISO 19139."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//gmd:fileIdentifier/gco:CharacterString',
            iso19139_xml
        )

        assert result == 'abc123-uuid-xyz'

    def test_extract_language(self, mock_extractor, iso19139_xml):
        """Test extracting language from ISO 19139."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//gmd:language/gco:CharacterString',
            iso19139_xml
        )

        assert result == 'eng'

    def test_extract_date_stamp(self, mock_extractor, iso19139_xml):
        """Test extracting dateStamp from ISO 19139."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//gmd:dateStamp/gco:Date',
            iso19139_xml
        )

        assert result == '2026-01-15'

    def test_extract_title(self, mock_extractor, iso19139_xml):
        """Test extracting title from nested path."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//gmd:identificationInfo//gmd:title/gco:CharacterString',
            iso19139_xml
        )

        assert result == 'Test Dataset Title'

    def test_extract_abstract(self, mock_extractor, iso19139_xml):
        """Test extracting abstract from ISO 19139."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//gmd:abstract/gco:CharacterString',
            iso19139_xml
        )

        assert result == 'This is a test abstract.'

    def test_namespace_agnostic_extraction(self, mock_extractor, iso19139_xml):
        """Test that namespace-agnostic mode works."""
        ve = ValueExtractor(mock_extractor)

        # Use path without namespace prefixes - should still work
        result = ve.extract_xpath(
            '//fileIdentifier/CharacterString',
            iso19139_xml,
            namespace_agnostic=True
        )

        assert result == 'abc123-uuid-xyz'


# =============================================================================
# XMP/Dublin Core Extraction Tests
# =============================================================================

@pytest.mark.unit
class TestXmpExtraction:
    """Test XPath extraction from XMP metadata."""

    def test_extract_dc_title(self, mock_extractor, xmp_xml):
        """Test extracting Dublin Core title from XMP."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//dc:title/rdf:Alt/rdf:li',
            xmp_xml
        )

        assert result == 'Test Image Title'

    def test_extract_dc_description(self, mock_extractor, xmp_xml):
        """Test extracting Dublin Core description from XMP."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//dc:description/rdf:Alt/rdf:li',
            xmp_xml
        )

        assert result == 'Image description text'

    def test_extract_dc_creator(self, mock_extractor, xmp_xml):
        """Test extracting Dublin Core creator from XMP."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//dc:creator/rdf:Seq/rdf:li',
            xmp_xml
        )

        assert result == 'John Doe'

    def test_extract_xmp_create_date(self, mock_extractor, xmp_xml):
        """Test extracting XMP CreateDate."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//xmp:CreateDate',
            xmp_xml
        )

        assert result == '2026-01-15T10:30:00'

    def test_extract_tiff_width(self, mock_extractor, xmp_xml):
        """Test extracting TIFF namespace element."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//tiff:ImageWidth',
            xmp_xml
        )

        assert result == '1024'

    def test_extract_photoshop_credit(self, mock_extractor, xmp_xml):
        """Test extracting Photoshop namespace element."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//photoshop:Credit',
            xmp_xml
        )

        assert result == 'Photo Credit Line'


# =============================================================================
# FGDC (Non-Namespaced) Extraction Tests
# =============================================================================

@pytest.mark.unit
class TestFgdcExtraction:
    """Test XPath extraction from FGDC metadata (no namespaces)."""

    def test_extract_title(self, mock_extractor, fgdc_xml):
        """Test extracting title from FGDC."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//idinfo/citation/citeinfo/title',
            fgdc_xml
        )

        assert result == 'Test Dataset'

    def test_extract_origin(self, mock_extractor, fgdc_xml):
        """Test extracting origin from FGDC."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//idinfo/citation/citeinfo/origin',
            fgdc_xml
        )

        assert result == 'USGS'

    def test_extract_abstract(self, mock_extractor, fgdc_xml):
        """Test extracting abstract from FGDC."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//idinfo/descript/abstract',
            fgdc_xml
        )

        assert result == 'Test abstract text.'

    def test_extract_pubdate(self, mock_extractor, fgdc_xml):
        """Test extracting publication date from FGDC."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath(
            '//idinfo/citation/citeinfo/pubdate',
            fgdc_xml
        )

        assert result == '20260115'

    def test_extract_first_themekey(self, mock_extractor, fgdc_xml):
        """Test extracting first theme keyword from FGDC."""
        ve = ValueExtractor(mock_extractor)

        # XPath returns first match by default
        result = ve.extract_xpath(
            '//idinfo/keywords/theme/themekey',
            fgdc_xml
        )

        assert result == 'elevation'


# =============================================================================
# Section Extraction Method Tests
# =============================================================================

@pytest.mark.unit
class TestSectionExtractionMethods:
    """Test the high-level section extraction methods."""

    def test_extract_geo_with_content(self, mock_extractor, iso19139_xml):
        """Test extract_geo method with content."""
        geo_md = Mock()
        geo_md.content = iso19139_xml
        mock_extractor.extract_geo_metadata.return_value = geo_md

        ve = ValueExtractor(mock_extractor)
        result = ve.extract_geo('//gmd:fileIdentifier/gco:CharacterString')

        assert result == 'abc123-uuid-xyz'

    def test_extract_geo_no_content(self, mock_extractor):
        """Test extract_geo method without content."""
        mock_extractor.extract_geo_metadata.return_value = None

        ve = ValueExtractor(mock_extractor)
        result = ve.extract_geo('//gmd:fileIdentifier')

        assert result is None

    def test_extract_xmp_with_content(self, mock_extractor, xmp_xml):
        """Test extract_xmp method with content."""
        xmp_md = Mock()
        xmp_md.content = xmp_xml
        mock_extractor.extract_xmp_metadata.return_value = xmp_md

        ve = ValueExtractor(mock_extractor)
        result = ve.extract_xmp('//dc:title/rdf:Alt/rdf:li')

        assert result == 'Test Image Title'

    def test_extract_xmp_no_content(self, mock_extractor):
        """Test extract_xmp method without content."""
        mock_extractor.extract_xmp_metadata.return_value = None

        ve = ValueExtractor(mock_extractor)
        result = ve.extract_xmp('//dc:title')

        assert result is None

    def test_extract_xml_with_content(self, mock_extractor, fgdc_xml):
        """Test extract_xml method with content."""
        xml_md = Mock()
        xml_md.content = fgdc_xml
        mock_extractor.extract_xml_metadata.return_value = xml_md

        ve = ValueExtractor(mock_extractor)
        result = ve.extract_xml('//idinfo/citation/citeinfo/title')

        assert result == 'Test Dataset'

    def test_extract_xml_no_content(self, mock_extractor):
        """Test extract_xml method without content."""
        mock_extractor.extract_xml_metadata.return_value = None

        ve = ValueExtractor(mock_extractor)
        result = ve.extract_xml('//title')

        assert result is None


# =============================================================================
# Caching Tests
# =============================================================================

@pytest.mark.unit
class TestXmlCaching:
    """Test that XML content is cached properly."""

    def test_geo_metadata_caching(self, mock_extractor, iso19139_xml):
        """Test that GEO_METADATA is cached."""
        geo_md = Mock()
        geo_md.content = iso19139_xml
        mock_extractor.extract_geo_metadata.return_value = geo_md

        ve = ValueExtractor(mock_extractor)

        # First extraction
        ve.extract_geo('//gmd:fileIdentifier/gco:CharacterString')
        # Second extraction
        ve.extract_geo('//gmd:language/gco:CharacterString')

        # Should only call extract_geo_metadata once
        assert mock_extractor.extract_geo_metadata.call_count == 1

    def test_xmp_metadata_caching(self, mock_extractor, xmp_xml):
        """Test that XMP metadata is cached."""
        xmp_md = Mock()
        xmp_md.content = xmp_xml
        mock_extractor.extract_xmp_metadata.return_value = xmp_md

        ve = ValueExtractor(mock_extractor)

        # First extraction
        ve.extract_xmp('//dc:title/rdf:Alt/rdf:li')
        # Second extraction
        ve.extract_xmp('//xmp:CreateDate')

        # Should only call extract_xmp_metadata once
        assert mock_extractor.extract_xmp_metadata.call_count == 1

    def test_xml_metadata_caching(self, mock_extractor, fgdc_xml):
        """Test that external XML metadata is cached."""
        xml_md = Mock()
        xml_md.content = fgdc_xml
        mock_extractor.extract_xml_metadata.return_value = xml_md

        ve = ValueExtractor(mock_extractor)

        # First extraction
        ve.extract_xml('//idinfo/citation/citeinfo/title')
        # Second extraction
        ve.extract_xml('//idinfo/descript/abstract')

        # Should only call extract_xml_metadata once
        assert mock_extractor.extract_xml_metadata.call_count == 1


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

@pytest.mark.unit
class TestXmlEdgeCases:
    """Test edge cases and error handling for XML extraction."""

    def test_invalid_xml_returns_none(self, mock_extractor):
        """Test that invalid XML returns None."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath('//title', 'not valid xml <')

        assert result is None

    def test_empty_xml_returns_none(self, mock_extractor):
        """Test that empty XML returns None."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath('//title', '')

        assert result is None

    def test_xpath_not_found_returns_none(self, mock_extractor, fgdc_xml):
        """Test that non-matching XPath returns None."""
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath('//nonexistent/element', fgdc_xml)

        assert result is None

    def test_invalid_xpath_returns_none(self, mock_extractor, fgdc_xml):
        """Test that invalid XPath returns None."""
        ve = ValueExtractor(mock_extractor)

        # Invalid XPath syntax
        result = ve.extract_xpath('//[invalid', fgdc_xml)

        assert result is None

    def test_element_with_no_text_returns_none(self, mock_extractor):
        """Test that element with no text content returns None."""
        xml = '<root><empty></empty></root>'
        ve = ValueExtractor(mock_extractor)

        result = ve.extract_xpath('//empty', xml)

        assert result is None
