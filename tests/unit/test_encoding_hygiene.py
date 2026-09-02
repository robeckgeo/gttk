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
Text files are read and written in a named encoding, and the PAM sidecar as bytes.

GTTK ships an ArcGIS Pro toolbox, so it runs on Windows, where an ``open()`` or
``read_text()`` without an encoding means cp1252 and text mode turns every newline into
CRLF. The library named its encoding everywhere but three places; twenty-nine calls in
the tests named none, which held only because every string they wrote was ASCII. The
``.aux.xml`` statistics sidecar went through text mode and would have carried CRLF on
Windows. These keep it that way.
"""

import ast
import inspect
from pathlib import Path

import pytest
from osgeo import gdal

from gttk.utils.statistics import _calculate_statistics_full, build_pam_data_from_stats, write_pam_xml
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
#: GDAL's own script, kept verbatim (DEVELOPER.md, Third-Party Code).
VENDORED = {ROOT / 'gttk' / 'utils' / 'validate_cloud_optimized_geotiff.py'}


def _text_calls_without_encoding(path: Path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {kw.arg for kw in node.keywords}
        if isinstance(node.func, ast.Name) and node.func.id == 'open':
            mode = node.args[1] if len(node.args) > 1 else next((kw.value for kw in node.keywords if kw.arg == 'mode'), None)
            mode_text = mode.value if isinstance(mode, ast.Constant) and isinstance(mode.value, str) else 'r'
            if 'b' not in mode_text and 'encoding' not in keywords:
                yield node.lineno, 'open'
        elif isinstance(node.func, ast.Attribute) and node.func.attr in ('read_text', 'write_text'):
            if 'encoding' not in keywords:
                yield node.lineno, node.func.attr


@pytest.mark.parametrize('tree', ['gttk', 'tests'])
def test_every_text_read_and_write_names_its_encoding(tree):
    offenders = [f'{path.relative_to(ROOT)}:{line} {call}'
                 for path in sorted((ROOT / tree).rglob('*.py')) if path not in VENDORED
                 for line, call in _text_calls_without_encoding(path)]
    assert offenders == [], 'text I/O without an encoding:\n' + '\n'.join(offenders)


class TestPamSidecar:

    def test_is_written_as_bytes(self):
        """Text mode would translate newlines on Windows; the source is checked because on
        this platform the two are indistinguishable."""
        assert 'write_bytes' in inspect.getsource(write_pam_xml)

    def test_holds_well_formed_utf8_with_bare_newlines(self, tmp_path):
        raster = tmp_path / 'dem.tif'
        MockGeoTIFF(width=32, height=32, data_type=gdal.GDT_Float32, crs='EPSG:32610').save_to_file(raster)
        ds = gdal.Open(str(raster))
        write_pam_xml(str(raster), build_pam_data_from_stats(_calculate_statistics_full(ds), ds))
        data = (tmp_path / 'dem.tif.aux.xml').read_bytes()
        assert data.startswith(b'<PAMDataset>') and b'\r' not in data
        data.decode('utf-8')
