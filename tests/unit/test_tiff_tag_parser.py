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
A tag that cannot be parsed stays in the table, and a missing tag lookup says so.

The tag parser used to drop a tag it could not parse -- one warning in the log, nothing in
the report -- and, when its lookup file was missing, to name every tag but four
"UnknownTag", which reads as a strange file rather than a broken installation.
"""

import logging

import pytest
from osgeo import gdal

import gttk.utils.tiff_tag_parser as ttp
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = pytest.mark.unit


@pytest.fixture
def raster(tmp_path):
    path = tmp_path / 'x.tif'
    MockGeoTIFF(width=16, height=16, crs='EPSG:32610', compression='DEFLATE').save_to_file(path)
    return path


def test_an_unparsable_tag_stays_in_the_table_marked(raster, monkeypatch, caplog):
    real = ttp.TiffTagParser._get_tag_interpretation

    def broken(self, code, value):
        if code == 259:
            raise RuntimeError('compression code table missing')
        return real(self, code, value)

    monkeypatch.setattr(ttp.TiffTagParser, '_get_tag_interpretation', broken)
    with ttp.TiffTagParser(str(raster)) as parser, caplog.at_level(logging.WARNING):
        tags = {tag.code: tag for tag in parser.get_tags()}
    assert 259 in tags
    assert tags[259].value == '(unparsed)'
    assert tags[259].interpretation == 'unparsed: compression code table missing'
    assert 'shown as unparsed' in caplog.text


class TestTagNames:

    def test_a_missing_lookup_is_named_in_every_unknown_tag(self, monkeypatch):
        monkeypatch.setattr(ttp, 'TIFF_TAGS', {})
        monkeypatch.setattr(ttp, 'TAG_LOOKUP_ERROR', 'tag lookup file not found: x')
        assert ttp.tag_name_for(256) == 'UnknownTag (256; tag lookup unavailable)'

    def test_a_genuinely_unknown_tag_is_just_unknown(self, monkeypatch):
        monkeypatch.setattr(ttp, 'TAG_LOOKUP_ERROR', None)
        assert ttp.tag_name_for(65000) == 'UnknownTag (65000)'
        assert ttp.tag_name_for(256) == 'ImageWidth'

    def test_a_missing_lookup_file_sets_the_flag_and_logs_an_error(self, monkeypatch, caplog, tmp_path):
        # Point the package lookup at an empty directory: the JSON is then not there.
        monkeypatch.setattr(ttp.resources, 'files', lambda package: tmp_path)
        saved = ttp.TAG_LOOKUP_ERROR
        try:
            with caplog.at_level(logging.ERROR):
                tags, exif = ttp._load_tiff_tag_lookup()
            assert set(tags) == {256, 257, 258, 259} and exif == {}
            assert ttp.TAG_LOOKUP_ERROR and 'not found' in ttp.TAG_LOOKUP_ERROR
            assert 'only four tags can be named' in caplog.text
        finally:
            ttp.TAG_LOOKUP_ERROR = saved
