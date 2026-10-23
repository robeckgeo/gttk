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
A product pipeline's header survives `gttk optimize`.

A producer that writes its own TIFFTAG_SOFTWARE and its own GEO_METADATA record before
calling GTTK gets them back as written: the tag untouched with --software-stamp False, and
the record byte for byte. A record GTTK embeds itself (--geo-metadata PATH, or the sidecar
-g True finds) is pretty-printed for the people who read gdalinfo and QGIS, and is the same
document. The NoData posts of a rounded DEM keep their bits.
"""

import numpy as np
import pytest
import tifffile
from osgeo import gdal

import gttk.tools.optimize_compression as ocmp
from gttk.utils.script_arguments import OptimizeArguments
from gttk.utils.xml_formatter import canonical_xml
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = pytest.mark.integration

RECORD = ('<?xml version="1.0" encoding="UTF-8"?>\n<?xml-stylesheet type="text/xsl" href="record.xsl"?>\n'
          '<record xmlns:ism="urn:us:gov:ic:ism"><id>SRC_N00E000_01.xml</id>'
          '<ism:Notice ism:noticeType="DS" ism:text="one&#xA;two">text</ism:Notice></record>\n')
FLAT_RECORD = '<record><id>SRC_N00E000_01.xml</id><a x="1"><b>t</b></a></record>'


def _tag_bytes(path, code):
    """A TIFF tag's raw value, the way a consumer that verifies the header reads it."""
    with tifffile.TiffFile(str(path)) as tif:
        tag = tif.pages[0].tags.get(code)
        if tag is None:
            return None
        value = tag.value
        if isinstance(value, str):
            return value.encode('utf-8')
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        return np.asarray(value, dtype=np.uint8).tobytes()


@pytest.fixture
def dem(tmp_path):
    """A Float32 DEM whose producer already wrote its header: TIFFTAG_SOFTWARE and GEO_METADATA."""
    path = tmp_path / 'dem_tile.tif'
    data = np.full((1, 64, 64), 123.456, np.float32)
    data[0, 0, :4] = np.nan
    MockGeoTIFF(width=64, height=64, data_type=gdal.GDT_Float32, crs='EPSG:4326',
                nodata_value=np.nan, pixel_data=data).save_to_file(path)
    ds = gdal.Open(str(path), gdal.GA_Update)
    ds.SetMetadataItem('TIFFTAG_SOFTWARE', 'PRODUCER')
    ds.SetMetadataItem('GEO_METADATA', RECORD)
    ds.FlushCache()
    ds = None
    return path


def _optimize(source, output, **overrides):
    kwargs = dict(input_path=source, output_path=output, product_type='dem', vertical_srs='EPSG:3855',
                  algorithm='DEFLATE', predictor=2, decimals=2, report=False, write_pam_xml=False,
                  open_report=False, arc_mode=True)
    kwargs.update(overrides)
    return ocmp.optimize_compression(OptimizeArguments(**kwargs))


class TestTheProducersHeaderSurvives:

    def test_software_stamp_false_keeps_the_tag(self, dem, tmp_path):
        out = tmp_path / 'product.tif'
        assert _optimize(dem, out, software_stamp=False) == 0
        assert gdal.Open(str(out)).GetMetadataItem('TIFFTAG_SOFTWARE') == 'PRODUCER'
        assert _tag_bytes(out, 305) == b'PRODUCER'

    def test_software_stamp_true_appends_the_toolkit(self, dem, tmp_path):
        from gttk import __version__
        out = tmp_path / 'product.tif'
        assert _optimize(dem, out) == 0
        assert gdal.Open(str(out)).GetMetadataItem('TIFFTAG_SOFTWARE') == \
            f'PRODUCER - optimized by GeoTIFF ToolKit v{__version__}'

    def test_the_record_arrives_byte_for_byte(self, dem, tmp_path):
        assert _tag_bytes(dem, 50909) == RECORD.encode('utf-8')
        out = tmp_path / 'product.tif'
        assert _optimize(dem, out, software_stamp=False) == 0
        assert _tag_bytes(out, 50909) == RECORD.encode('utf-8')

    def test_nodata_posts_keep_their_bits_and_the_rest_sits_on_the_lattice(self, dem, tmp_path):
        out = tmp_path / 'product.tif'
        assert _optimize(dem, out, software_stamp=False) == 0
        ds = gdal.Open(str(out))
        band = ds.GetRasterBand(1)
        result = band.ReadAsArray()
        assert np.isnan(band.GetNoDataValue())
        assert np.all(np.isnan(result[0, :4]))
        finite = result[np.isfinite(result)]
        assert finite.size == 64 * 64 - 4
        assert np.all(finite == np.float32(123.46))


class TestARecordGttkEmbeds:

    def test_an_explicit_record_is_readable_and_the_same_document(self, dem, tmp_path):
        record = tmp_path / 'flat.xml'
        record.write_text(FLAT_RECORD, encoding='utf-8')
        out = tmp_path / 'product.tif'
        assert _optimize(dem, out, geo_metadata=record) == 0
        embedded = _tag_bytes(out, 50909)
        assert canonical_xml(embedded) == canonical_xml(FLAT_RECORD)
        assert b'\n  <a x="1">\n    <b>t</b>\n  </a>' in embedded
        assert b'ism:Notice' not in embedded, "the explicit record replaces the input's"

    def test_the_sidecar_is_embedded_the_same_way(self, dem, tmp_path):
        (tmp_path / 'dem_tile.xml').write_text(FLAT_RECORD, encoding='utf-8')
        out = tmp_path / 'product.tif'
        assert _optimize(dem, out, geo_metadata=True) == 0
        embedded = _tag_bytes(out, 50909)
        assert canonical_xml(embedded) == canonical_xml(FLAT_RECORD)
        assert b'\n  <a x="1">' in embedded

    def test_a_latin1_record_comes_out_utf8(self, dem, tmp_path):
        latin = '<?xml version="1.0" encoding="ISO-8859-1"?>\n<record><t>café ñ</t></record>\n'.encode('latin-1')
        record = tmp_path / 'latin.xml'
        record.write_bytes(latin)
        out = tmp_path / 'product.tif'
        assert _optimize(dem, out, geo_metadata=record) == 0
        embedded = _tag_bytes(out, 50909)
        assert b"encoding='utf-8'" in embedded.lower()
        assert 'café ñ' in embedded.decode('utf-8')
        assert canonical_xml(embedded) == canonical_xml(latin)

    def test_no_sidecar_is_still_a_success_and_the_inputs_record_stays(self, dem, tmp_path):
        out = tmp_path / 'product.tif'
        assert _optimize(dem, out, geo_metadata=True) == 0
        assert _tag_bytes(out, 50909) == RECORD.encode('utf-8')

    def test_unusable_records_fail_the_run(self, dem, tmp_path):
        with pytest.raises(ValueError, match='not found'):
            OptimizeArguments(input_path=dem, output_path=tmp_path / 'p.tif', product_type='dem',
                              vertical_srs='EPSG:3855', geo_metadata=tmp_path / 'missing.xml')
        bad = tmp_path / 'bad.xml'
        bad.write_text('not xml', encoding='utf-8')
        out = tmp_path / 'product.tif'
        assert _optimize(dem, out, geo_metadata=bad) == 1
        assert not out.exists()
