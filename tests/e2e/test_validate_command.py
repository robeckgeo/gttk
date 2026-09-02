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
End-to-end tests for the `gttk validate` command.

The one property these pin that no unit test can is *where the command is run
from*. The default rules directory used to be the repo-relative
`gttk/resources/rules`, so `gttk validate` worked from a checkout's root and
nowhere else -- an installed copy run from a data directory failed with
"Rules directory not found" unless `--rules-dir` was passed. Every test here
therefore runs the CLI with `cwd` set to a temporary directory.
"""

import subprocess
import sys

import pytest
from osgeo import gdal

from gttk.utils.validation.loader import bundled_rules_dir
from tests.fixtures.mock_geotiff_factory import MockGeoTIFF


def run_validate(cwd, *args, timeout=120):
    """
    Run `gttk validate` as a subprocess from `cwd`, never from the repo root.

    Returns (returncode, output) with stdout and stderr joined: the CLI reports
    errors through its logger, whose handler writes to stdout.
    """
    result = subprocess.run(
        [sys.executable, '-m', 'gttk', 'validate', *args],
        capture_output=True, text=True, cwd=cwd, timeout=timeout,
    )
    return result.returncode, result.stdout + result.stderr


@pytest.mark.e2e
class TestValidateCommand:

    def test_runs_from_a_directory_that_is_not_the_repo_root(self, tmp_path):
        """
        No --rules-dir, and a working directory with no `gttk/` under it.

        The rules are found inside the package, the run completes, and the
        results land beside the input. The validation itself reports failures --
        a 64x64 mock raster is not a DGED5 tile -- but that is a result, not an
        error, and the exit code says so.
        """
        raster = tmp_path / 'probe.tif'
        MockGeoTIFF(width=64, height=64, data_type=gdal.GDT_Float32).save_to_file(raster)

        code, output = run_validate(tmp_path, '-i', 'probe.tif', '-p', 'DGED5', '-w', 'false')

        assert code == 0, output
        assert 'Rules directory not found' not in output
        assert (tmp_path / 'probe_validation' / 'probe_validation_results.json').is_file()

    def test_help_names_the_bundled_default_without_leaking_a_path(self, tmp_path):
        """
        The formatter appends '(default: ...)' unless the help states the default
        itself. For --rules-dir the true default is an absolute path into
        site-packages, which is noise to a reader; the help says what it is instead.
        """
        code, output = run_validate(tmp_path, '--help')

        assert code == 0
        assert 'Default: the rules bundled with GTTK' in output
        assert str(bundled_rules_dir()) not in output

    def test_explicit_rules_dir_is_still_honoured(self, tmp_path):
        """--rules-dir overrides the bundled default, and a bad one is reported."""
        raster = tmp_path / 'probe.tif'
        MockGeoTIFF(width=64, height=64).save_to_file(raster)
        empty = tmp_path / 'no_rules_here'
        empty.mkdir()

        code, output = run_validate(tmp_path, '-i', 'probe.tif', '-p', 'DGED5',
                                    '-r', str(empty), '-w', 'false')

        assert code != 0
        assert 'No TOML rule files found' in output


    def test_a_directory_of_upper_case_extensions_is_validated(self, tmp_path):
        """glob('*.tif') found nothing here for A.TIF while Windows found everything."""
        tiles = tmp_path / 'tiles'
        tiles.mkdir()
        MockGeoTIFF(width=16, height=16, crs='EPSG:32610').save_to_file(tiles / 'A.TIF')
        code, output = run_validate(tmp_path, '-i', 'tiles', '-p', 'DGED5', '-w', 'false')
        assert code == 0, output
        results = list(tmp_path.rglob('*_validation_results.json'))
        assert results, output
        assert any('A.TIF' in r.read_text(encoding='utf-8') for r in results)
