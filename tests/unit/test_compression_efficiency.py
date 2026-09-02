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
An error and "uncompressed" are no longer the same number.

``calculate_compression_efficiency`` returned 0.0 for any exception, at debug level, and
0.0 is also the honest answer for an uncompressed file. Four report sites rendered the
figure as authoritative: ``gttk read`` printed 0.00% and a 1.00x ratio, ``gttk validate``
recorded no savings, the comparison report showed the two files as equally efficient, and
``gttk test`` subtracted it from every candidate's improvement column. The figure is now
``None`` when it could not be determined, the reason is logged at warning, and every
renderer says "n/a".
"""

import logging
from pathlib import Path

import pytest
import tifffile
from osgeo import gdal

import gttk.tools.read_metadata as rm
import gttk.tools.validate_metadata as vm
import gttk.utils.geotiff_processor as gp
import gttk.utils.report_builders as rb
from gttk.utils.metadata_extractor import MetadataExtractor
from gttk.utils.tiff_tag_parser import TiffTagParser
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = pytest.mark.unit


@pytest.fixture
def deflate(tmp_path):
    path = tmp_path / 'deflate.tif'
    MockGeoTIFF(width=128, height=128, data_type=gdal.GDT_Float32, crs='EPSG:32610',
                compression='DEFLATE', predictor=3).save_to_file(path)
    return path


@pytest.fixture
def uncompressed(tmp_path):
    path = tmp_path / 'plain.tif'
    MockGeoTIFF(width=128, height=128, data_type=gdal.GDT_Float32, crs='EPSG:32610').save_to_file(path)
    return path


def _expected_efficiency(path: Path) -> float:
    """The figure from first principles: byte counts against width x height x bits."""
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        counts = page.tags['TileByteCounts'].value if 'TileByteCounts' in page.tags else page.tags['StripByteCounts'].value
        compressed = sum(int(c) for c in counts)
        bits = page.tags['BitsPerSample'].value
        bits = sum(bits) if isinstance(bits, tuple) else bits * page.tags['SamplesPerPixel'].value
        uncompressed = page.imagewidth * page.imagelength * bits / 8
    return (1 - compressed / uncompressed) * 100


class TestTheFigure:

    def test_a_compressed_file_gives_the_formula(self, deflate):
        assert gp.calculate_compression_efficiency(str(deflate)) == pytest.approx(_expected_efficiency(deflate))

    def test_an_uncompressed_file_is_zero_not_unknown(self, uncompressed):
        assert gp.calculate_compression_efficiency(str(uncompressed)) == 0.0

    def test_a_missing_file_is_unknown_and_says_why(self, tmp_path, caplog):
        with caplog.at_level(logging.WARNING):
            assert gp.calculate_compression_efficiency(str(tmp_path / 'nope.tif')) is None
        assert 'Compression efficiency unknown' in caplog.text

    def test_an_ifd_that_cannot_be_read_makes_the_figure_unknown(self, deflate, monkeypatch, caplog):
        """A number computed over the IFDs that did read would be a plausible wrong answer."""
        def broken(self, page_index=0):
            raise RuntimeError('truncated strip byte counts')
        monkeypatch.setattr(TiffTagParser, 'get_tags', broken)
        with caplog.at_level(logging.WARNING):
            assert gp.calculate_compression_efficiency(str(deflate)) is None
        assert 'IFD 0' in caplog.text and 'truncated strip byte counts' in caplog.text

    def test_uncompressed_size_of_garbage_is_unknown(self, tmp_path, caplog):
        garbage = tmp_path / 'garbage.tif'
        garbage.write_bytes(b'not a tiff')
        with caplog.at_level(logging.WARNING):
            assert gp.get_uncompressed_size(str(garbage)) is None
        assert 'Uncompressed size unknown' in caplog.text

    def test_header_estimate_is_a_number_for_a_real_ifd_and_unknown_past_the_end(self, deflate, caplog):
        with TiffTagParser(str(deflate)) as parser:
            tags = {tag.code: tag for tag in parser.get_tags()}
            assert gp._estimate_ifd_header_size(0, parser.tif, tags) > 0
            with caplog.at_level(logging.WARNING):
                assert gp._estimate_ifd_header_size(99, parser.tif, tags) is None
        assert 'IFD 99 header size unknown' in caplog.text


class TestTheHelpers:

    def test_ratio(self):
        assert gp.compression_ratio(50.0) == 2.0
        assert gp.compression_ratio(0.0) == 1.0
        assert gp.compression_ratio(100.0) is None
        assert gp.compression_ratio(None) is None

    def test_cells(self):
        assert gp.format_compression_efficiency(45.2) == ('45.20%', '1.82x')
        assert gp.format_compression_efficiency(0.0) == ('0.00%', '1.00x')
        assert gp.format_compression_efficiency(None) == ('n/a', 'n/a')


class TestEveryRendererSaysNotAvailable:

    def test_read_summary(self, deflate, monkeypatch):
        # read_metadata imports the function inside the summary builder, at call time
        monkeypatch.setattr(gp, 'calculate_compression_efficiency', lambda *a, **k: None)
        summary = rm._generate_report_summary(str(deflate))
        assert 'n/a' in summary
        assert '0.00%' not in summary and '1.00x' not in summary

    def test_comparison_report(self, deflate, uncompressed, monkeypatch):
        """The differences table lives on the builder; the CLI renders it by hand."""
        monkeypatch.setattr(rb, 'calculate_compression_efficiency', lambda *a, **k: None)
        with MetadataExtractor(uncompressed) as base, MetadataExtractor(deflate) as comp:
            builder = rb.ComparisonReportBuilder(base, comp, 'Baseline', 'Optimized')
            builder.add_differences_section()
            comparison = builder.file_comparison
        assert comparison.base_file.space_saving == 'n/a' and comparison.base_file.ratio == 'n/a'
        assert comparison.comp_file.space_saving == 'n/a' and comparison.comp_file.ratio == 'n/a'
        assert comparison.efficiency_difference is None
        assert 'could not be compared' in comparison.get_result_text()

    def test_validate_distinguishes_unknown_from_uncompressed(self, deflate, uncompressed, monkeypatch):
        with MetadataExtractor(uncompressed) as extractor:
            info = vm.extract_compression_info(extractor, uncompressed)
        assert info['savings'] == 0.0 and info['ratio'] == 1.0
        with MetadataExtractor(deflate) as extractor:
            info = vm.extract_compression_info(extractor, deflate)
        assert info['savings'] > 0 and info['ratio'] > 1
        monkeypatch.setattr(vm, 'calculate_compression_efficiency', lambda *a, **k: None)
        with MetadataExtractor(deflate) as extractor:
            info = vm.extract_compression_info(extractor, deflate)
        assert info['savings'] is None and info['ratio'] is None


class TestLentTiffFilesStayOpen:

    def test_close_respects_the_caller_s_file(self, deflate):
        """The comparison builder lends each extractor's TiffFile to the calculation."""
        with tifffile.TiffFile(deflate) as lent:
            parser = TiffTagParser(str(deflate), tiff_file=lent)
            parser.close()
            assert not lent.filehandle.closed
            gp.calculate_compression_efficiency(str(deflate), tiff=lent)
            assert not lent.filehandle.closed
