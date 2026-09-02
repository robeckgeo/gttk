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
XML from a GeoTIFF or a sidecar can name a file; GTTK must never read it.

Nine parse sites used lxml's default parser, so whether an external entity was fetched
depended on the installed libxml2. The one here refuses, which made the risk invisible to
a test that only checked the external case; the internal-entity case is the same switch
(``resolve_entities``) and is observable on every libxml2, so both are asserted, through
the real entry points: a tag written into a raster, a sidecar next to it, and the
formatters that render them.
"""

import logging

import pytest
from lxml import etree
from osgeo import gdal

from gttk.utils import xml_formatter
from gttk.utils.geo_metadata_writer import prepare_xml_for_gdal, write_geo_metadata
from gttk.utils.markdown_formatter import xml_to_markdown
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.report_builders import MetadataReportBuilder
from gttk.utils.validation.extractors import ValueExtractor
from gttk.utils.xml_formatter import decode_xml_bytes, pretty_print_xml, read_xml_with_encoding_detection
from gttk.utils.xml_safety import SAFE_OPTIONS, parse_untrusted, untrusted_parser
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = pytest.mark.unit

INTERNAL = 'SECRET-INTERNAL-ENTITY'
EXTERNAL = 'SECRET-FILE-CONTENT'


@pytest.fixture
def secret_file(tmp_path):
    path = tmp_path / 'secret.txt'
    path.write_text(EXTERNAL, encoding='utf-8')
    return path


@pytest.fixture
def payloads(secret_file):
    """One document with an internal entity, one whose entity names a local file."""
    return {
        'internal': f'<!DOCTYPE a [<!ENTITY x "{INTERNAL}">]><a><b>&x;</b></a>',
        'external': f'<!DOCTYPE a [<!ENTITY x SYSTEM "{secret_file.as_uri()}">]><a><b>&x;</b></a>',
    }


def _leaks(text) -> bool:
    """True if an entity was expanded into content.

    The internal entity's text sits in the DOCTYPE of every document that carries it, so
    its bare presence proves nothing; its presence as the value of ``<b>`` -- as element
    text, a table cell or an extracted value -- does. The external one's text lives only
    in the secret file, so any appearance is a read.
    """
    if text is None:
        return False
    text = str(text)
    if EXTERNAL in text:
        return True
    return text.strip() == INTERNAL or f'<b>{INTERNAL}</b>' in text or f'| {INTERNAL}' in text


# --- The parser itself ---------------------------------------------------------------

class TestUntrustedParser:

    @pytest.mark.parametrize('kind', ['internal', 'external'])
    def test_entities_are_never_substituted(self, payloads, kind):
        root = parse_untrusted(payloads[kind])
        assert not _leaks(etree.tostring(root, encoding='unicode'))
        assert root.find('b').text is None

    def test_the_default_parser_would_have_expanded_the_internal_one(self, payloads):
        """The property the seed could not observe: on this libxml2 the external entity
        is refused either way, but the internal one shows the switch."""
        root = etree.fromstring(payloads['internal'].encode('utf-8'))
        assert root.find('b').text == INTERNAL

    def test_safety_options_cannot_be_overridden(self):
        for key in SAFE_OPTIONS:
            with pytest.raises(ValueError):
                untrusted_parser(**{key: not SAFE_OPTIONS[key]})
            with pytest.raises(ValueError):
                untrusted_parser(**{key: SAFE_OPTIONS[key]})

    def test_other_options_pass_through(self):
        root = parse_untrusted('<a> <b/> </a>', remove_blank_text=True)
        assert root.text is None
        root = parse_untrusted('<a><b></a>', recover=True)
        assert root.tag == 'a'

    def test_str_input_with_an_encoding_declaration_is_accepted(self):
        root = parse_untrusted('<?xml version="1.0" encoding="UTF-8"?><a>é</a>')
        assert root.text == 'é'


# --- Every site, through its real entry point -----------------------------------------

class TestEverySiteIsHardened:

    @pytest.fixture
    def raster(self, tmp_path):
        path = tmp_path / 'metadata.tif'
        MockGeoTIFF(width=16, height=16, crs='EPSG:32610').save_to_file(path)
        return path

    @pytest.mark.parametrize('kind', ['internal', 'external'])
    def test_validation_xpath(self, payloads, kind):
        """validation/extractors.py: the XPath extractor used for XMP, GEO and sidecars."""
        assert not _leaks(ValueExtractor(None).extract_xpath('//b', payloads[kind]))

    @pytest.mark.parametrize('kind', ['internal', 'external'])
    def test_validation_gdal_metadata_items(self, payloads, kind, monkeypatch, raster):
        """validation/extractors.py: tag 42112, whose XML GDAL itself usually writes."""
        with MetadataExtractor(raster) as extractor:
            values = ValueExtractor(extractor)
            monkeypatch.setattr(values, '_get_gdal_metadata_content', lambda: payloads[kind])
            assert not any(_leaks(v) for v in values._get_gdal_items().values())

    @pytest.mark.parametrize('kind', ['internal', 'external'])
    def test_xmp_tag_in_a_raster(self, payloads, kind, raster):
        """Tag 700 through GDAL, then the validation extractor and the tag parser."""
        ds = gdal.Open(str(raster), gdal.GA_Update)
        ds.SetMetadata([payloads[kind]], 'xml:XMP')
        ds.FlushCache()
        ds = None
        with MetadataExtractor(raster) as extractor:
            assert not _leaks(ValueExtractor(extractor).extract_xmp('//b'))
            xmp = next(tag for tag in extractor.extract_tags() if tag.code == 700)
            assert not _leaks(xmp.value) and not _leaks(xmp.interpretation)

    @pytest.mark.parametrize('kind', ['internal', 'external'])
    def test_geo_metadata_tag_written_from_a_sidecar(self, payloads, kind, raster, tmp_path):
        """geo_metadata_writer.py parses the sidecar, writes tag 50909; extract_geo reads it."""
        iso = tmp_path / 'iso.xml'
        iso.write_text(payloads[kind], encoding='utf-8')
        assert not _leaks(prepare_xml_for_gdal(iso))
        ds = gdal.Open(str(raster), gdal.GA_Update)
        write_geo_metadata(ds, iso)
        ds.FlushCache()
        ds = None
        with MetadataExtractor(raster) as extractor:
            assert not _leaks(ValueExtractor(extractor).extract_geo('//b'))

    @pytest.mark.parametrize('kind', ['internal', 'external'])
    def test_xml_sidecar_next_to_the_raster(self, payloads, kind, raster):
        raster.with_suffix('.xml').write_text(payloads[kind], encoding='utf-8')
        with MetadataExtractor(raster) as extractor:
            assert not _leaks(ValueExtractor(extractor).extract_xml('//b'))

    @pytest.mark.parametrize('kind', ['internal', 'external'])
    def test_report_statistics_filter(self, payloads, kind, raster):
        """report_builders.py: the GDAL_METADATA filter that drops STATISTICS_* items."""
        with MetadataExtractor(raster) as extractor:
            builder = MetadataReportBuilder(extractor)
            filtered, _ = builder._filter_statistics_from_gdal_metadata(payloads[kind])
            assert not _leaks(filtered)

    @pytest.mark.parametrize('kind', ['internal', 'external'])
    def test_pretty_printer(self, payloads, kind):
        assert not _leaks(pretty_print_xml(payloads[kind]))

    @pytest.mark.parametrize('kind', ['internal', 'external'])
    def test_markdown_renderer(self, payloads, kind):
        assert not _leaks(xml_to_markdown(payloads[kind]))
        assert not _leaks(xml_to_markdown(payloads[kind].encode('utf-8')))


# --- Sidecar reading -----------------------------------------------------------------

class TestSidecarReading:

    def test_an_oversized_sidecar_is_refused(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(xml_formatter, 'MAX_XML_SIDECAR_BYTES', 1024)
        big = tmp_path / 'big.xml'
        big.write_bytes(b'<a>' + b'x' * 2048 + b'</a>')
        with caplog.at_level(logging.ERROR):
            assert read_xml_with_encoding_detection(big) is None
        assert 'exceeds' in caplog.text

    def test_a_sidecar_under_the_limit_is_read(self, tmp_path):
        small = tmp_path / 'small.xml'
        small.write_bytes(b'<a/>')
        assert read_xml_with_encoding_detection(small) == b'<a/>'

    def test_undecodable_bytes_still_come_back_as_text(self):
        """latin-1 maps every byte, so the fallback chain cannot end in None."""
        assert decode_xml_bytes(b'\xff\xfe<a/>') is not None
        assert decode_xml_bytes('<a>é</a>'.encode('utf-8')) == '<a>é</a>'
        assert decode_xml_bytes(b'') is None
