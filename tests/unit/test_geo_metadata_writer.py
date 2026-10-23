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
The GEO_METADATA writer: a record on disk becomes the text embedded in tag 50909.

It is pretty-printed for the people who read gdalinfo output and QGIS layer properties,
and it is the same document: the writer canonicalizes both and refuses a formatting that
changed anything. The text is UTF-8 whatever the file was. A record that cannot be used
is an error, not a warning that leaves the tag empty.
"""

import logging

import pytest
from osgeo import gdal

import gttk.utils.geo_metadata_writer as writer
from gttk.utils import xml_formatter as xf
from gttk.utils.exceptions import ProcessingStepFailedError
from gttk.utils.geo_metadata_writer import prepare_xml_for_gdal, write_geo_metadata
from gttk.utils.xml_formatter import canonical_xml

pytestmark = pytest.mark.unit

RECORD = ('<?xml version="1.0" encoding="UTF-8"?>\n<?xml-stylesheet type="text/xsl" href="record.xsl"?>\n'
          '<record xmlns:ism="urn:us:gov:ic:ism"><id>SRC_N00E000_01.xml</id>'
          '<ism:Notice ism:noticeType="DS" ism:text="one&#xA;two">text</ism:Notice></record>\n')


class TestPrepareXmlForGdal:

    def test_pretty_printed_and_the_same_document(self, tmp_path):
        record = tmp_path / 'record.xml'
        record.write_text(RECORD, encoding='utf-8')
        text = prepare_xml_for_gdal(record)
        assert canonical_xml(text) == canonical_xml(record.read_bytes())
        assert '\n  <id>SRC_N00E000_01.xml</id>\n  <ism:Notice' in text
        assert '<?xml-stylesheet type="text/xsl" href="record.xsl"?>' in text
        assert 'ism:text="one&#10;two"' in text

    def test_a_latin1_file_becomes_utf8_text(self, tmp_path):
        latin = '<?xml version="1.0" encoding="ISO-8859-1"?>\n<r><t>café ñ</t></r>\n'.encode('latin-1')
        record = tmp_path / 'latin.xml'
        record.write_bytes(latin)
        text = prepare_xml_for_gdal(record)
        assert 'café ñ' in text
        assert text.lower().startswith("<?xml version='1.0' encoding='utf-8'?>")
        assert canonical_xml(text) == canonical_xml(latin)

    def test_a_byte_order_mark_is_dropped(self, tmp_path):
        record = tmp_path / 'bom.xml'
        record.write_bytes(b'\xef\xbb\xbf' + RECORD.encode('utf-8'))
        text = prepare_xml_for_gdal(record)
        assert text.startswith('<?xml') and canonical_xml(text) == canonical_xml(RECORD)

    def test_a_flat_record_comes_out_indented(self, tmp_path):
        record = tmp_path / 'flat.xml'
        record.write_text('<r><a x="1"><b>t</b></a></r>', encoding='utf-8')
        assert prepare_xml_for_gdal(record) == '<r>\n  <a x="1">\n    <b>t</b>\n  </a>\n</r>\n'

    def test_a_missing_record_raises(self, tmp_path):
        with pytest.raises(ProcessingStepFailedError, match='not found'):
            prepare_xml_for_gdal(tmp_path / 'missing.xml')

    def test_a_malformed_record_raises(self, tmp_path):
        bad = tmp_path / 'bad.xml'
        bad.write_text('<unclosed>', encoding='utf-8')
        with pytest.raises(ProcessingStepFailedError, match='well-formed'):
            prepare_xml_for_gdal(bad)

    def test_an_oversize_record_raises(self, tmp_path, monkeypatch):
        record = tmp_path / 'big.xml'
        record.write_text(RECORD, encoding='utf-8')
        monkeypatch.setattr(xf, 'MAX_XML_SIDECAR_BYTES', 10)
        with pytest.raises(ProcessingStepFailedError, match='larger than'):
            prepare_xml_for_gdal(record)

    def test_a_formatter_that_changes_the_record_is_not_trusted(self, tmp_path, monkeypatch):
        record = tmp_path / 'record.xml'
        record.write_text(RECORD, encoding='utf-8')
        monkeypatch.setattr(writer, 'pretty_print_xml', lambda text: text.replace('>text<', '>changed<'))
        records, handler = [], logging.Handler()
        handler.emit = records.append
        logging.getLogger('gttk.utils.geo_metadata_writer').addHandler(handler)
        try:
            text = prepare_xml_for_gdal(record)
        finally:
            logging.getLogger('gttk.utils.geo_metadata_writer').removeHandler(handler)
        assert 'changed' not in text
        assert canonical_xml(text) == canonical_xml(RECORD)
        assert '\n  <id>' in text, "lxml's own indentation is the fallback, not the raw text"
        assert any('changed the record' in r.getMessage() for r in records)

    def test_a_record_c14n_cannot_express_is_embedded_as_lxml_writes_it(self, tmp_path):
        """An unresolved entity reference (the safe parser never expands one) has no canonical
        form, so there is nothing to compare against: lxml's indentation is used as it is."""
        record = tmp_path / 'entity.xml'
        record.write_text('<!DOCTYPE r [<!ENTITY e "x">]><r><a>&e;</a></r>', encoding='utf-8')
        text = prepare_xml_for_gdal(record)
        assert '&e;' in text and '\n  <a>' in text


class TestWriteGeoMetadata:

    def test_writes_the_tag_and_returns_the_text(self, tmp_path):
        record = tmp_path / 'record.xml'
        record.write_text(RECORD, encoding='utf-8')
        path = tmp_path / 'x.tif'
        ds = gdal.GetDriverByName('GTiff').Create(str(path), 8, 8, 1, gdal.GDT_Byte)
        text = write_geo_metadata(ds, record)
        ds = None
        ds = gdal.Open(str(path))
        assert ds.GetMetadataItem('GEO_METADATA') == text
        assert canonical_xml(text) == canonical_xml(RECORD)

    def test_no_dataset_is_an_error(self, tmp_path):
        record = tmp_path / 'record.xml'
        record.write_text(RECORD, encoding='utf-8')
        with pytest.raises(ProcessingStepFailedError, match='No open GDAL dataset'):
            write_geo_metadata(None, record)

    def test_an_unusable_record_is_an_error_not_a_warning(self, tmp_path):
        ds = gdal.GetDriverByName('MEM').Create('', 8, 8, 1, gdal.GDT_Byte)
        with pytest.raises(ProcessingStepFailedError, match='not found'):
            write_geo_metadata(ds, tmp_path / 'missing.xml')
