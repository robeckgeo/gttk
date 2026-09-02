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
GTTK works from an installed wheel, run from a directory that is not the checkout.

Every test in the suite runs against an editable install of the checkout, where a
config.toml at the repository root, a temp/ directory beside it and the checkout root on
sys.path are all quietly available. From a wheel none of them is. `gttk test` and
`gttk optimize-arc` crashed at dispatch on the missing config.toml, and every other
command printed a warning about it to stdout first. This builds the wheel from what git
would ship, installs it into a throwaway venv, and drives it from a scratch directory.
"""

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from osgeo import gdal

from tests.fixtures.mock_geotiff_factory import MockGeoTIFF

pytestmark = [pytest.mark.integration, pytest.mark.slow]

ROOT = Path(__file__).resolve().parents[2]

#: Resources the reports and tools read at run time; each must be in the wheel.
SHIPPED = [
    'gttk/resources/config.toml',
    'gttk/resources/rules/example_rules.toml',
    'gttk/resources/scripts/navigation.js',
    'gttk/resources/scripts/menu_responsive.js',
    'gttk/resources/styles/base.css',
    'gttk/resources/styles/material_light.toml',
    'gttk/resources/styles/banners.toml',
    'gttk/resources/templates/compression_options_dem.csv',
    'gttk/resources/templates/test_compression_template.xlsx',
    'gttk/resources/i18n/es.toml',
    'gttk/resources/esri/esri_cs_epsg_lookup.json',
    'gttk/resources/tiff/tiff_tag_lookup.json',
]

NETWORK_HINTS = ('Could not fetch', 'Connection', 'connection', 'No matching distribution',
                 'Read timed out', 'Temporary failure in name resolution')


def _run(argv, cwd, **kwargs):
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    return subprocess.run([str(a) for a in argv], cwd=str(cwd), env=env,
                          capture_output=True, text=True, timeout=600, **kwargs)


@pytest.fixture(scope='module')
def installed(tmp_path_factory):
    """The wheel, built from what git would ship, installed into its own venv."""
    work = tmp_path_factory.mktemp('wheel')
    src, dist, venv, cwd = work / 'src', work / 'dist', work / 'venv', work / 'cwd'
    listed = subprocess.run(['git', 'ls-files', '-co', '--exclude-standard', '-z'], cwd=ROOT,
                            capture_output=True, check=True).stdout.split(b'\0')
    for entry in listed:
        if entry:
            relative = Path(os.fsdecode(entry))
            target = src / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)

    build = _run([sys.executable, '-m', 'pip', 'wheel', src, '--no-deps', '-w', dist, '-q'], cwd=work)
    if build.returncode != 0:
        output = build.stdout + build.stderr
        if any(hint in output for hint in NETWORK_HINTS):
            pytest.skip('building the wheel needs the network for pip\'s isolated build backend')
        pytest.fail(output)
    wheel = next(dist.glob('geotiff_toolkit-*.whl'))

    subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(venv)], check=True)
    scripts = venv / ('Scripts' if os.name == 'nt' else 'bin')
    python = scripts / ('python.exe' if os.name == 'nt' else 'python')
    install = _run([python, '-m', 'pip', 'install', '--no-deps', '--no-index', '-q', wheel], cwd=work)
    assert install.returncode == 0, install.stdout + install.stderr

    cwd.mkdir()
    MockGeoTIFF(width=64, height=64, data_type=gdal.GDT_Float32, crs='EPSG:32610').save_to_file(cwd / 'dem.tif')
    return SimpleNamespace(wheel=wheel, python=python, gttk=scripts / ('gttk.exe' if os.name == 'nt' else 'gttk'),
                           venv=venv, cwd=cwd)


class TestTheWheel:

    def test_carries_every_resource_the_code_reads(self, installed):
        names = set(zipfile.ZipFile(installed.wheel).namelist())
        missing = [name for name in SHIPPED if name not in names]
        assert missing == [], f'not in the wheel: {missing}'

    def test_carries_no_bytecode_or_build_cache(self, installed):
        names = zipfile.ZipFile(installed.wheel).namelist()
        assert [n for n in names if n.endswith('.pyc') or '/cache/' in n] == []


class TestFromAScratchDirectory:

    def test_imports_resolve_inside_the_venv(self, installed):
        result = _run([installed.python, '-c',
                       'import gttk, gttk.tools.test_compression, gttk.tools.optimize_compression_arc; print(gttk.__file__)'],
                      cwd=installed.cwd)
        assert result.returncode == 0, result.stderr
        assert Path(result.stdout.strip()).is_relative_to(installed.venv)

    def test_read_writes_a_self_contained_report_and_a_clean_stdout(self, installed):
        result = _run([installed.gttk, 'read', '-i', 'dem.tif', '--open-report', 'false'], cwd=installed.cwd)
        assert result.returncode == 0, result.stdout + result.stderr
        assert not [line for line in result.stdout.splitlines() if line.startswith('Warning:')], result.stdout
        report = (installed.cwd / 'dem_meta.html').read_text(encoding='utf-8')
        assert '<script' in report and '<style' in report

    def test_the_test_tool_dispatches(self, installed):
        """The command that crashed on the missing config.toml."""
        result = _run([installed.gttk, 'test', '-i', 'dem.tif', '-t', 'dem', '-o', 'bench.xlsx',
                       '--open-report', 'false'], cwd=installed.cwd)
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
        assert (installed.cwd / 'bench.xlsx').exists()
        assert (installed.cwd / 'dem_gttk_test').is_dir()

    def test_validate_finds_its_bundled_rules(self, installed):
        result = _run([installed.gttk, 'validate', '-i', 'dem.tif', '-p', 'DGED5', '--open-report', 'false'],
                      cwd=installed.cwd)
        assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
