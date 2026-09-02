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
Tests for gttk.utils.validation.output path construction.

`generate_output_paths` decides an output basename from the input path, and it
has to do so for paths that are not on disk yet -- a library caller may ask where
results *would* go before anything is written. The interesting cases are all
about which of `.stem` and `.name` it picks.
"""

from pathlib import Path

import pytest

from gttk.utils.validation.output import (
    generate_output_paths,
    generate_report_path,
    get_input_files,
)


@pytest.mark.unit
class TestGenerateOutputPaths:
    """Output folder, JSON and GeoPackage path construction."""

    def test_existing_file_uses_stem(self, tmp_path):
        """An existing file drops its extension from the output basename."""
        raster = tmp_path / 'example.tif'
        raster.touch()

        folder, json_file, gpkg_file = generate_output_paths(raster)

        assert folder == tmp_path / 'example_validation'
        assert json_file.name == 'example_validation_results.json'
        assert gpkg_file.name == 'example_validation_map.gpkg'

    def test_existing_directory_uses_name(self, tmp_path):
        """A directory keeps its whole name, dots and all."""
        tiles = tmp_path / 'tiles'
        tiles.mkdir()

        folder, json_file, _ = generate_output_paths(tiles)

        assert folder == tmp_path / 'tiles_validation'
        assert json_file.name == 'tiles_validation_results.json'

    def test_nonexistent_file_path_uses_stem(self, tmp_path):
        """
        A file-shaped path that does not exist is still named as a file.

        Before this was fixed, `is_file()` returned False for a path that had
        not been written yet, the directory branch ran, and every output carried
        the input's extension: `example.tif_validation_results.json`.
        """
        folder, json_file, gpkg_file = generate_output_paths(tmp_path / 'example.tif')

        assert folder.name == 'example_validation'
        assert json_file.name == 'example_validation_results.json'
        assert gpkg_file.name == 'example_validation_map.gpkg'

    def test_nonexistent_directory_path_uses_name(self, tmp_path):
        """A suffix-less path that does not exist reads as a directory."""
        folder, _, _ = generate_output_paths(tmp_path / 'tiles')

        assert folder.name == 'tiles_validation'

    def test_existing_directory_containing_a_dot_uses_name(self, tmp_path):
        """
        `is_dir()` is checked first, so a directory named `v1.2` is not truncated.

        Only the filesystem can settle this one: `Path('v1.2').suffix` is '.2'.
        """
        versioned = tmp_path / 'tiles.v2'
        versioned.mkdir()

        folder, _, _ = generate_output_paths(versioned)

        assert folder.name == 'tiles.v2_validation'

    def test_output_dir_overrides_parent(self, tmp_path):
        """`output_dir` relocates the folder but not its name."""
        raster = tmp_path / 'example.tif'
        raster.touch()
        reports = tmp_path / 'reports'

        folder, json_file, _ = generate_output_paths(raster, reports)

        assert folder == reports / 'example_validation'
        assert json_file.parent == folder

    def test_json_and_gpkg_live_inside_the_folder(self, tmp_path):
        """Both outputs are children of the returned folder."""
        folder, json_file, gpkg_file = generate_output_paths(tmp_path / 'example.tif')

        assert json_file.parent == folder
        assert gpkg_file.parent == folder


@pytest.mark.unit
class TestGenerateReportPath:
    """Per-file report naming."""

    @pytest.mark.parametrize('status,fmt,expected', [
        ('PASS', 'html', 'tile_001_PASS.html'),
        ('FAIL', 'md', 'tile_001_FAIL.md'),
        ('SKIP', 'html', 'tile_001_SKIP.html'),
    ])
    def test_status_and_format_in_filename(self, tmp_path, status, fmt, expected):
        path = generate_report_path(
            tmp_path / 'tile_001.tif', tmp_path / 'out_validation', status, fmt
        )

        assert path.name == expected
        assert path.parent == tmp_path / 'out_validation' / 'reports'


@pytest.mark.unit
class TestGetInputFiles:
    """File selection for a single file or a directory."""

    def test_single_file_returned_as_is(self, tmp_path):
        raster = tmp_path / 'example.tif'
        raster.touch()

        assert get_input_files(raster) == [raster]

    def test_directory_is_sorted_with_tif_before_tiff(self, tmp_path):
        for name in ('b.tif', 'a.tif', 'c.tiff'):
            (tmp_path / name).touch()

        assert [f.name for f in get_input_files(tmp_path)] == ['a.tif', 'b.tif', 'c.tiff']

    def test_name_filter_matches_a_substring(self, tmp_path):
        for name in ('tile_001_DSM.tif', 'tile_002_DSM.tif', 'tile_003_DTM.tif'):
            (tmp_path / name).touch()

        found = get_input_files(tmp_path, name_filter='DSM')

        assert [f.name for f in found] == ['tile_001_DSM.tif', 'tile_002_DSM.tif']

    def test_missing_directory_yields_nothing(self, tmp_path):
        assert get_input_files(tmp_path / 'absent') == []


class TestExtensionsAreMatchedCaseInsensitively:
    """Path.glob('*.tif') is case-sensitive on Linux and not on Windows, so a directory
    of .TIF files validated completely on one platform and found nothing on the other."""

    def test_upper_case_extensions_are_found(self, tmp_path):
        for name in ('a.tif', 'B.TIF', 'c.tiff', 'D.TIFF', 'notes.txt'):
            (tmp_path / name).write_bytes(b'')
        assert [f.name for f in get_input_files(tmp_path)] == ['B.TIF', 'D.TIFF', 'a.tif', 'c.tiff']


class TestGeoPackageReplacement:

    def test_an_output_that_cannot_be_replaced_is_reported_not_raised(self, tmp_path, caplog, monkeypatch):
        """Under ArcGIS Pro the previous GeoPackage may be open in a map and Windows
        refuses the unlink; here a directory in the way stands in for that."""
        import logging
        from types import SimpleNamespace
        import gttk.utils.validation.gpkg_writer as gw
        square = [[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]]
        monkeypatch.setattr(gw.GeoPackageFeature, 'from_json_result',
                            staticmethod(lambda result: SimpleNamespace(name='tile', layer_name='PASSED',
                                                                        wgs84_coordinates=square)))
        blocked = tmp_path / 'validation_map.gpkg'
        blocked.mkdir()
        with caplog.at_level(logging.ERROR):
            assert gw.write_validation_gpkg(blocked, [{'file': 'tile.tif'}], 'DGED5') is None
        assert 'Cannot replace the existing GeoPackage' in caplog.text
