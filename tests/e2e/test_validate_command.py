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

import json
import shutil
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


# ISO 19139 for the GEO_METADATA tag (50909), naming the tile's source record.
TILE_RECORD = '''<?xml version="1.0" encoding="UTF-8"?>
<gmd:MD_Metadata xmlns:gmd="http://www.isotc211.org/2005/gmd"
                 xmlns:gco="http://www.isotc211.org/2005/gco">
  <gmd:fileIdentifier>
    <gco:CharacterString>SRC_N00E000_01.xml</gco:CharacterString>
  </gmd:fileIdentifier>
</gmd:MD_Metadata>
'''


def write_tile(path):
    """A 64x64 DEM whose metadata describes tile N00E000, whatever the file is called."""
    MockGeoTIFF(width=64, height=64, data_type=gdal.GDT_Float32).save_to_file(path)
    ds = gdal.Open(str(path), gdal.GA_Update)
    ds.SetMetadataItem('IDENTIFIER', 'TILE_N00E000_01_DEM')
    ds.SetMetadataItem('TILE_ID', 'N00E000')
    ds.SetMetadataItem('GEO_METADATA', TILE_RECORD)
    ds.FlushCache()
    ds = None


@pytest.mark.e2e
class TestFilenamePlaceholders:

    def test_placeholders_resolve_per_file_in_a_directory_run(self, tmp_path):
        """
        Two tiles with identical metadata, one named for the geocell it describes and
        one for another. The bundled TILE-PLACEHOLDERS-EXAMPLE rules pass the first
        and fail the second on exactly the rules whose expected value names the file.
        """
        tiles = tmp_path / 'tiles'
        tiles.mkdir()
        write_tile(tiles / 'TILE_N00E000_01_DEM.tif')
        shutil.copy(tiles / 'TILE_N00E000_01_DEM.tif', tiles / 'TILE_N00E001_01_DEM.tif')

        code, output = run_validate(tmp_path, '-i', 'tiles', '-p', 'TILE-PLACEHOLDERS-EXAMPLE',
                                    '--open-report', 'false', '--write-reports', 'false')

        assert code == 0, output
        results = list(tmp_path.rglob('*_validation_results.json'))
        assert len(results) == 1, output
        report = json.loads(results[0].read_text(encoding='utf-8'))
        by_name = {f['name']: f for f in report['files']}
        assert set(by_name) == {'TILE_N00E000_01_DEM.tif', 'TILE_N00E001_01_DEM.tif'}

        def statuses(file_result):
            return {(section, r['key']): r['status']
                    for section, section_results in file_result['validation'].items()
                    for r in section_results}

        placeholder_rules = {
            ('gdal', 'IDENTIFIER'),
            ('gdal', 'TILE_ID'),
            ('geo', '/gmd:MD_Metadata/gmd:fileIdentifier/gco:CharacterString'),
        }
        named_for_its_tile = statuses(by_name['TILE_N00E000_01_DEM.tif'])
        assert placeholder_rules <= set(named_for_its_tile)
        assert set(named_for_its_tile.values()) == {'PASS'}, named_for_its_tile

        named_for_another = statuses(by_name['TILE_N00E001_01_DEM.tif'])
        assert {key for key, status in named_for_another.items() if status == 'FAIL'} == placeholder_rules, named_for_another
        assert named_for_another[('tag', '258')] == 'PASS'

        # The JSON carries the value each file was held to
        expected = {r['key']: r['expected']
                    for r in by_name['TILE_N00E001_01_DEM.tif']['validation']['gdal']}
        assert expected == {'IDENTIFIER': 'TILE_N00E001_01_DEM', 'TILE_ID': 'N00E001'}
        assert report['files_passed'] == 1 and report['files_failed'] == 1
