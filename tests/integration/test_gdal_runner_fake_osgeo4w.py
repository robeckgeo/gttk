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
gdal_runner, run for real against a fake OSGeo4W tree.

Until now the runner's environment builder, its command resolution and its projection
extraction were 24% covered, and only because ``test_gdal_runner`` stubbed every function
``main()`` calls. These tests build the directory layout the code looks for (see
``tests/fixtures/fake_osgeo4w``) and drive it the way ArcGIS Pro does: the runner script
launched by path, a JSON payload on stdin, and real GDAL doing the work.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from osgeo import gdal

from gttk.utils import gdal_runner
from gttk.utils.config_loader import config
from tests.fixtures.fake_osgeo4w import build_fake_osgeo4w
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.name == 'nt', reason='the fake OSGeo4W is POSIX-only; Windows has the real one')]

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / 'gttk' / 'utils' / 'gdal_runner.py'
HOSTILE_NAME = 'x"; open("MARKER", "w").close() #.tif'


@pytest.fixture(scope='module')
def osgeo4w(tmp_path_factory):
    return build_fake_osgeo4w(tmp_path_factory.mktemp('OSGeo4W'))


@pytest.fixture
def dem(tmp_path):
    path = tmp_path / 'dem.tif'
    MockGeoTIFF(width=64, height=64, data_type=gdal.GDT_Float32, crs='EPSG:32610').save_to_file(path)
    return path


@pytest.fixture
def configured(osgeo4w, monkeypatch):
    """config.toml's paths.osgeo4w, pointed at the fake tree."""
    monkeypatch.setattr(config, 'get', lambda key, default=None: str(osgeo4w) if key == 'paths.osgeo4w' else default)
    return osgeo4w


class TestIsolatedEnvironment:

    def test_points_at_the_tree_and_scrubs_the_host(self, osgeo4w, monkeypatch):
        monkeypatch.setenv('CONDA_PREFIX', '/somewhere')
        monkeypatch.setenv('PROJ_DATA', '/elsewhere')
        env = gdal_runner.create_isolated_env(osgeo4w)
        assert env['PATH'].split(os.pathsep)[0] == str(osgeo4w / 'bin')
        assert env['PYTHONHOME'] == str(osgeo4w / 'apps' / 'Python312')
        assert env['GDAL_DATA'] == str(osgeo4w / 'share' / 'gdal')
        assert env['PROJ_LIB'] == str(osgeo4w / 'share' / 'proj')
        assert 'CONDA_PREFIX' not in env and 'PROJ_DATA' not in env

    def test_discovers_whichever_python_osgeo4w_ships(self, tmp_path):
        root = tmp_path / 'OSGeo4W'
        (root / 'apps' / 'Python313').mkdir(parents=True)
        assert gdal_runner.osgeo4w_python_dir(root) == root / 'apps' / 'Python313'
        assert gdal_runner.osgeo4w_python_dir(tmp_path / 'empty') == tmp_path / 'empty' / 'apps' / 'Python312'


class TestRunGdalCommand:

    def test_runs_gdalinfo_through_the_tree(self, osgeo4w, dem):
        env = gdal_runner.create_isolated_env(osgeo4w)
        out = gdal_runner.run_gdal_command(['gdalinfo', '-json', str(dem)], env, capture_output=True)
        info = json.loads(out)
        assert info['size'] == [64, 64]

    def test_runs_a_python_script_from_the_scripts_directory(self, osgeo4w, dem, tmp_path):
        env = gdal_runner.create_isolated_env(osgeo4w)
        out = tmp_path / 'thresholded.tif'
        gdal_runner.run_gdal_command(['gdal_calc.py', '-A', str(dem), '--outfile', str(out),
                                      '--calc', 'A*0+1', '--type', 'Byte', '--quiet'], env)
        ds = gdal.Open(str(out))
        assert ds.GetRasterBand(1).ReadAsArray()[0, 0] == 1

    def test_a_missing_tool_is_named(self, osgeo4w):
        env = gdal_runner.create_isolated_env(osgeo4w)
        with pytest.raises(FileNotFoundError, match='no_such_tool'):
            gdal_runner.run_gdal_command(['no_such_tool', '--version'], env)


class TestRunnerScriptEndToEnd:

    def test_a_payload_runs_and_captures(self, osgeo4w, dem, tmp_path):
        """Launched by path with a JSON payload, exactly as the parent does it."""
        out = tmp_path / 'deflate.tif'
        payload = {'osgeo4w_root': str(osgeo4w), 'commands': [
            {'command': ['gdalinfo', '-json', str(dem)], 'capture_output': True},
            {'command': ['gdal_translate', str(dem), str(out), '-co', 'COMPRESS=DEFLATE']},
        ]}
        # The parent launches <OSGeo4W>/bin/python.exe on the runner with this environment;
        # PYTHONHOME in it points at the tree, which the shim drops before running python.
        env = gdal_runner.create_isolated_env(osgeo4w)
        result = subprocess.run([str(osgeo4w / 'bin' / 'python.exe'), str(RUNNER)], input=json.dumps(payload),
                                env=env, capture_output=True, text=True, timeout=300)
        assert result.returncode == 0, result.stderr
        captured = [json.loads(line) for line in result.stdout.splitlines()
                    if line.startswith('{') and '"stdout"' in line]
        assert len(captured) == 1 and json.loads(captured[0]['stdout'])['size'] == [64, 64]
        assert gdal.Open(str(out)).GetMetadataItem('COMPRESSION', 'IMAGE_STRUCTURE') == 'DEFLATE'


class TestProjectionInfo:

    def test_reads_the_crs_through_the_tree(self, configured, dem):
        info, wkt, projjson = gdal_runner.get_projection_info_from_osgeo4w(str(dem))
        assert info['projected_cs_code'] == '32610'
        assert 'PROJCRS' in wkt and '"type"' in projjson

    def test_a_hostile_filename_is_data_not_code(self, configured, tmp_path):
        hostile = tmp_path / HOSTILE_NAME
        MockGeoTIFF(width=16, height=16, data_type=gdal.GDT_Float32, crs='EPSG:32610').save_to_file(hostile)
        info, wkt, _ = gdal_runner.get_projection_info_from_osgeo4w(str(hostile))
        assert info['projected_cs_code'] == '32610'
        assert not (tmp_path / 'MARKER').exists()
        assert not (ROOT / 'MARKER').exists()
