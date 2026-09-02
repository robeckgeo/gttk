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
Scripts generated for the OSGeo4W interpreter carry no path in their source.

Six generated scripts used to embed file paths with only the backslashes escaped, so a
quotation mark in a filename ended the string literal and the rest of the name ran as
Python -- in the OSGeo4W interpreter, on every toolbox Optimize Compression run. The
execution tests below run the real scripts with ``sys.executable`` on a raster whose name
is such a payload; before the fix the payload's marker file appeared and the script did
no work.
"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from osgeo import gdal

import gttk.tools.optimize_compression_arc as oc
import gttk.utils.gdal_runner as gr
from gttk.utils.gdal_scripts import build_script, literal, python_command, write_script
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = pytest.mark.unit

#: A filename that is also a Python statement once a naive string literal ends early.
HOSTILE_NAME = 'x"; open("MARKER", "w").close() #.tif'

HOSTILE_STRINGS = ['x"; import os #', "it's", 'back\\slash', 'new\nline', 'emoji \U0001F600',
                   '{braces}', '"""', 'line sep']

#: Every template, with the values its builder passes.
TEMPLATES = {
    'remap_nodata': (oc._REMAP_NODATA_SCRIPT, dict(source_nodata=-9999.0, target_nodata=-32767.0)),
    'attach_mask': (oc._ATTACH_MASK_SCRIPT, {}),
    'round_overviews': (oc._ROUND_OVERVIEWS_SCRIPT, dict(decimals=2)),
    'run_translate': (oc._RUN_TRANSLATE_SCRIPT, dict(options=['-of', 'COG', '-co', 'COMPRESS=DEFLATE'])),
    'round_dataset': (oc._ROUND_DATASET_SCRIPT, dict(decimals=2)),
    'projection_info': (gr._PROJECTION_INFO_SCRIPT, {}),
}


def _shape(source: str) -> str:
    """The AST with every constant blanked, so only the statement structure remains."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            node.value = None
    return ast.dump(tree)


def _run(script: Path, *argv, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *map(str, argv)],
                          cwd=cwd, capture_output=True, text=True, timeout=120)


# --- literal(): a Python literal by construction --------------------------------

class TestLiteral:

    @pytest.mark.parametrize('text', HOSTILE_STRINGS)
    def test_strings_round_trip_whatever_they_contain(self, text):
        assert ast.literal_eval(literal(text)) == text

    @pytest.mark.parametrize('value', [0, -1, 2.5, -9999.0, True, False, None, ['-co', 'a"b'], (1, 'x')])
    def test_plain_values_round_trip(self, value):
        expected = list(value) if isinstance(value, tuple) else value
        assert ast.literal_eval(literal(value)) == expected

    def test_nan_is_spelled_as_a_call_because_repr_gives_a_bare_name(self):
        assert literal(float('nan')) == "float('nan')"
        assert repr(float('nan')) == 'nan'   # the reason the special case exists

    def test_infinity_is_refused(self):
        with pytest.raises(ValueError):
            literal(float('inf'))

    def test_numpy_scalars_become_plain_numbers(self):
        """repr(np.float64(1.0)) is 'np.float64(1.0)' under NumPy 2, which the script
        cannot evaluate without importing numpy under that name."""
        assert literal(np.float64(-32767.0)) == '-32767.0'
        assert literal(np.int16(3)) == '3'

    def test_paths_are_refused_because_they_travel_on_argv(self):
        with pytest.raises(TypeError):
            literal(Path('in.tif'))

    def test_unsupported_types_are_refused_rather_than_repr_d(self):
        with pytest.raises(TypeError):
            literal({'a': 1})


# --- build_script(): templates and values cannot drift ------------------------------

class TestBuildScript:

    def test_a_missing_value_is_an_error(self):
        with pytest.raises(ValueError):
            build_script('X = {x}\nY = {y}\n', x=1)

    def test_an_unused_value_is_an_error(self):
        with pytest.raises(ValueError):
            build_script('X = {x}\n', x=1, y=2)

    def test_doubled_braces_survive_as_braces(self):
        assert build_script('print(f"{{x}}")\n') == 'print(f"{x}")\n'


# --- The six templates -----------------------------------------------------------------

class TestTemplates:

    @pytest.mark.parametrize('name', sorted(TEMPLATES))
    def test_builds_and_parses(self, name):
        template, values = TEMPLATES[name]
        ast.parse(build_script(template, **values))

    @pytest.mark.parametrize('name', sorted(TEMPLATES))
    def test_reads_its_paths_from_argv(self, name):
        template, values = TEMPLATES[name]
        tree = ast.parse(build_script(template, **values))
        argv_reads = [node for node in ast.walk(tree)
                      if isinstance(node, ast.Subscript)
                      and isinstance(node.value, ast.Attribute) and node.value.attr == 'argv']
        assert argv_reads, f'{name} takes no path from argv'

    @pytest.mark.parametrize('name', sorted(TEMPLATES))
    def test_every_value_lands_as_a_module_level_literal(self, name):
        """The scripts bind their values at the top (DECIMALS = 2, OPTIONS = [...]) and
        refer to those names below, so the literal is easy to find and appears once."""
        template, values = TEMPLATES[name]
        text = build_script(template, **values)
        for placeholder, value in values.items():
            assert f'{placeholder.upper()} = {literal(value)}' in text

    @pytest.mark.parametrize('text', HOSTILE_STRINGS)
    def test_a_hostile_string_value_changes_no_statement(self, text):
        """The translate options are the one place a string reaches a script's source."""
        benign = build_script(oc._RUN_TRANSLATE_SCRIPT, options=['-co', 'COMPRESS=DEFLATE'])
        hostile = build_script(oc._RUN_TRANSLATE_SCRIPT, options=['-co', text])
        assert _shape(hostile) == _shape(benign)
        assert ast.literal_eval(literal(text)) == text


class TestPythonCommand:

    def test_paths_are_separate_argv_elements(self):
        command = python_command(Path('/t/s.py'), Path(HOSTILE_NAME), 'out.tif')
        assert command == {'command': ['python', '/t/s.py', HOSTILE_NAME, 'out.tif']}

    def test_capture_flag_is_only_present_when_asked(self):
        assert 'capture_output' not in python_command('s.py', 'a')
        assert python_command('s.py', 'a', capture_output=True)['capture_output'] is True


# --- The scripts, executed ----------------------------------------------------------------

@pytest.mark.skipif(sys.platform == 'win32', reason='a quotation mark is not a legal filename character on Windows')
class TestGeneratedScriptsRun:

    @pytest.fixture
    def hostile_dem(self, tmp_path):
        """A Float32 raster named like a Python payload, with -9999 in its top-left corner."""
        pixels = np.linspace(100.0, 200.0, 64 * 64, dtype=np.float32).reshape(1, 64, 64)
        pixels[0, :8, :8] = -9999.0
        path = tmp_path / HOSTILE_NAME
        MockGeoTIFF(width=64, height=64, data_type=gdal.GDT_Float32, crs='EPSG:32610',
                    pixel_data=pixels, nodata_value=-9999.0).save_to_file(path)
        return path

    def test_remap_script_does_not_execute_its_input_name(self, hostile_dem, tmp_path):
        script = oc._write_nodata_remap_script(tmp_path / 'remap.py', -9999.0, -32767.0, 'Float32')
        output = tmp_path / 'out.tif'
        result = _run(script, hostile_dem, output, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (tmp_path / 'MARKER').exists(), 'the filename was executed as Python'
        ds = gdal.Open(str(output))
        band = ds.GetRasterBand(1)
        assert band.GetNoDataValue() == -32767.0
        assert band.ReadAsArray()[0, 0] == -32767.0
        assert HOSTILE_NAME not in script.read_text(encoding='utf-8')

    def test_remap_script_handles_a_nan_target(self, hostile_dem, tmp_path):
        script = oc._write_nodata_remap_script(tmp_path / 'remap.py', -9999.0, 'nan', 'Float32')
        output = tmp_path / 'out.tif'
        result = _run(script, hostile_dem, output, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        ds = gdal.Open(str(output))
        band = ds.GetRasterBand(1)
        assert np.isnan(band.GetNoDataValue())
        assert np.isnan(band.ReadAsArray()[0, 0])

    def test_remap_refuses_nan_for_integer_data(self, tmp_path):
        with pytest.raises(ValueError):
            oc._write_nodata_remap_script(tmp_path / 'remap.py', 0, 'nan', 'Int16')

    def test_round_dataset_script_rounds_in_place(self, tmp_path):
        path = tmp_path / HOSTILE_NAME
        pixels = np.full((1, 16, 16), 1.23456, dtype=np.float32)
        MockGeoTIFF(width=16, height=16, data_type=gdal.GDT_Float32, crs='EPSG:32610',
                    pixel_data=pixels).save_to_file(path)
        script = oc._write_round_data_script(tmp_path / 'round.py', 2)
        result = _run(script, path, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (tmp_path / 'MARKER').exists()
        ds = gdal.Open(str(path))
        assert ds.GetRasterBand(1).ReadAsArray()[0, 0] == pytest.approx(1.23)

    def test_translate_script_applies_its_options(self, hostile_dem, tmp_path):
        script = oc._write_translate_script(tmp_path / 'translate.py',
                                            ['-of', 'GTiff', '-co', 'COMPRESS=DEFLATE'])
        output = tmp_path / 'translated.tif'
        result = _run(script, hostile_dem, output, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (tmp_path / 'MARKER').exists()
        assert gdal.Open(str(output)).GetMetadataItem('COMPRESSION', 'IMAGE_STRUCTURE') == 'DEFLATE'

    def test_projection_script_reports_the_crs_of_a_hostile_name(self, hostile_dem, tmp_path):
        script = write_script(tmp_path / 'proj.py', gr._PROJECTION_INFO_SCRIPT)
        result = _run(script, hostile_dem, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not (tmp_path / 'MARKER').exists()
        info = json.loads(result.stdout.strip().splitlines()[-1])
        assert info['projection_info']['projected_cs_code'] == '32610'
        assert 'PROJCRS' in info['wkt_string']
