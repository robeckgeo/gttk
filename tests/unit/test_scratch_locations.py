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
Scratch files never land in whatever directory the command was run from.

``gttk test`` defaulted its scratch directory to ``./temp``, so multi-gigabyte candidate
rasters piled up wherever the user was standing -- 5.7 GB of them in the checkout root,
and 39 files per test-suite run. The ArcGIS optimize path fell back to the working
directory whenever ``TEMP`` was unset, which is every platform but Windows.
"""

import tempfile
from pathlib import Path

import pytest

from gttk.main import build_parser
from gttk.tools import test_compression as tc
from gttk.tools.optimize_compression_arc import TemporaryFileManager

pytestmark = pytest.mark.unit


class TestCompressionTestScratch:

    def test_default_sits_beside_the_workbook_named_after_the_input(self):
        scratch = tc.default_temp_dir(Path('/data/tiles/tile.tif'), Path('/reports/tile_test.xlsx'))
        assert scratch == Path('/reports/tile_gttk_test')

    def test_the_cli_default_is_not_a_relative_path(self):
        """argparse used to default --temp-dir to Path('temp')."""
        parser = build_parser()
        args = parser.parse_args(['test', '-i', 'x.tif', '-t', 'dem'])
        assert args.temp_dir is None

    def test_the_module_no_longer_carries_a_cwd_relative_default(self):
        assert not hasattr(tc, 'DEFAULT_TEMP_DIR')


class TestArcTemporaryWorkspace:

    def test_is_created_under_the_platform_temporary_directory(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv('TEMP', raising=False)
        with TemporaryFileManager() as tfm:
            assert tfm.temp_dir.parent == Path(tempfile.gettempdir())
            assert not tfm.temp_dir.is_relative_to(tmp_path)
            assert tfm.temp_dir.is_dir()
        assert not tfm.temp_dir.exists()
        assert list(tmp_path.iterdir()) == []
