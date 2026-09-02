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
Opening a report never hands its path to a shell unquoted.

Under WSL, ``open_file`` asks PowerShell to open the report with its Windows default
application. It used to do so with ``Start-Process "<path>"`` built by an f-string:
inside PowerShell's double quotes ``$(...)`` is evaluated, a backtick escapes and a ``"``
ends the string, and the path is derived from the input raster's name. No test reached
``open_file`` at all.
"""

import base64
import subprocess
from pathlib import Path

import pytest

import gttk.utils.path_helpers as ph

pytestmark = pytest.mark.unit

HOSTILE = "C:\\reports\\it's $(Remove-Item x) `n `\"y.html"


class TestPowerShellOpenCommand:

    def test_the_path_is_a_single_quoted_literal_with_quotes_doubled(self):
        argv = ph._powershell_open_command(HOSTILE)
        command = base64.b64decode(argv[-1]).decode('utf-16-le')
        assert command == "Start-Process -LiteralPath 'C:\\reports\\it''s $(Remove-Item x) `n `\"y.html'"

    def test_nothing_user_derived_reaches_argv_in_the_clear(self):
        argv = ph._powershell_open_command(HOSTILE)
        assert argv[:4] == ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand']
        assert len(argv) == 5
        assert '$(' not in argv[-1] and '"' not in argv[-1] and '`' not in argv[-1]


class TestOpenFileOnWsl:

    @pytest.fixture
    def popen_calls(self, monkeypatch):
        """Pretend to be WSL with no VS Code, and record what would be launched."""
        calls = []
        monkeypatch.setattr(ph.sys, 'platform', 'linux')
        monkeypatch.setattr(ph, '_is_wsl', lambda: True)
        monkeypatch.setattr(ph, '_convert_wsl_path_to_windows', lambda p: HOSTILE)
        monkeypatch.setattr(subprocess, 'Popen', lambda argv, **kw: calls.append(argv))
        return calls

    def test_an_html_report_goes_to_powershell_encoded(self, popen_calls):
        ph.open_file('/home/user/report.html')
        assert len(popen_calls) == 1
        argv = popen_calls[0]
        assert argv[3] == '-EncodedCommand'
        assert base64.b64decode(argv[4]).decode('utf-16-le').startswith("Start-Process -LiteralPath '")
        assert all('$(' not in element for element in argv)


class TestPrepareOutputPath:
    """The output tree mirrors the input tree and never reaches above it."""

    def test_mirrors_the_relative_path(self, tmp_path):
        out = ph.prepare_output_path(str(tmp_path / 'in'), str(tmp_path / 'out'), str(tmp_path / 'in' / 'a' / 'b.tif'))
        assert out == str(tmp_path / 'out' / 'a' / 'b.tif')

    def test_refuses_a_file_outside_the_input_tree(self, tmp_path):
        with pytest.raises(ValueError, match='not under'):
            ph.prepare_output_path(str(tmp_path / 'in'), str(tmp_path / 'out'), str(tmp_path / 'elsewhere' / 'b.tif'))


class TestSidecarSearchOrder:
    """The documented order: beside the raster, then its parent, then a sibling metadatos/."""

    @pytest.fixture
    def tree(self, tmp_path):
        raster = tmp_path / 'delivery' / 'tiles' / 'tile.tif'
        raster.parent.mkdir(parents=True)
        raster.write_bytes(b'')
        return raster

    def test_beside_the_raster_the_exact_name_wins(self, tree):
        (tree.parent / 'tile_meta.xml').write_text('<a/>', encoding='utf-8')
        (tree.parent / 'tile.xml').write_text('<a/>', encoding='utf-8')
        assert ph.find_xml_metadata_file(tree) == tree.parent / 'tile.xml'

    def test_then_the_meta_suffix(self, tree):
        (tree.parent / 'tile_meta.xml').write_text('<a/>', encoding='utf-8')
        assert ph.find_xml_metadata_file(tree) == tree.parent / 'tile_meta.xml'

    def test_then_the_parent_directory(self, tree):
        (tree.parent.parent / 'tile.xml').write_text('<a/>', encoding='utf-8')
        assert ph.find_xml_metadata_file(tree) == tree.parent.parent / 'tile.xml'

    def test_then_a_metadatos_directory_beside_the_rasters_directory(self, tree):
        metadatos = tree.parent.parent / 'metadatos'
        metadatos.mkdir()
        (metadatos / 'tile.xml').write_text('<a/>', encoding='utf-8')
        assert ph.find_xml_metadata_file(tree) == metadatos / 'tile.xml'

    def test_nothing_further_afield(self, tree):
        (tree.parent.parent.parent / 'tile.xml').write_text('<a/>', encoding='utf-8')
        assert ph.find_xml_metadata_file(tree) is None


class TestBatchCollection:

    def test_a_file_gdal_cannot_open_is_skipped_with_a_warning(self, tmp_path, caplog):
        """A batch used to drop such a file at debug level, so a run over a directory
        could quietly test fewer files than it was given."""
        import logging
        from pathlib import Path
        from tests.fixtures.mock_geotiff_factory import MockGeoTIFF
        MockGeoTIFF(width=16, height=16, crs='EPSG:32610').save_to_file(tmp_path / 'ok.tif')
        (tmp_path / 'bad.tif').write_bytes(b'not a raster')
        with caplog.at_level(logging.WARNING):
            found = ph.get_geotiff_files(str(tmp_path))
        assert [Path(f).name for f in found] == ['ok.tif']
        assert 'bad.tif' in caplog.text and 'skipped' in caplog.text


class TestOpenFileByPlatform:
    """Which launcher each platform gets. None of them runs here."""

    @staticmethod
    def _native(monkeypatch, platform):
        calls = []
        monkeypatch.setattr(ph.sys, 'platform', platform)
        monkeypatch.setattr(ph, '_is_wsl', lambda: False)

        def run(argv, **kwargs):
            assert kwargs.get('check') is True
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0)
        monkeypatch.setattr(subprocess, 'run', run)
        return calls

    def test_windows_hands_the_path_to_startfile(self, monkeypatch):
        opened = []
        monkeypatch.setattr(ph.sys, 'platform', 'win32')
        monkeypatch.setattr(ph.os, 'startfile', opened.append, raising=False)
        ph.open_file(Path('C:/reports/r.html'))
        assert opened == [str(Path('C:/reports/r.html'))]

    def test_macos_uses_open(self, monkeypatch):
        calls = self._native(monkeypatch, 'darwin')
        ph.open_file('/tmp/r.html')
        assert calls == [['open', '/tmp/r.html']]

    def test_linux_uses_xdg_open(self, monkeypatch):
        calls = self._native(monkeypatch, 'linux')
        ph.open_file('/tmp/r.html')
        assert calls == [['xdg-open', '/tmp/r.html']]


class TestOpenFileOnWslByType:

    @pytest.fixture
    def started(self, monkeypatch):
        """WSL, with a record of every process open_file would start."""
        record = {'run': [], 'popen': []}
        monkeypatch.setattr(ph.sys, 'platform', 'linux')
        monkeypatch.setattr(ph, '_is_wsl', lambda: True)
        monkeypatch.setattr(ph, '_convert_wsl_path_to_windows', lambda p: 'C:\\r.html')
        monkeypatch.setattr(subprocess, 'Popen', lambda argv, **kw: record['popen'].append(argv))
        return record

    @staticmethod
    def _vs_code(monkeypatch, record, installed):
        def run(argv, **kwargs):
            record['run'].append(argv)
            return subprocess.CompletedProcess(argv, 0 if installed else 1)
        monkeypatch.setattr(subprocess, 'run', run)

    def test_markdown_opens_in_vs_code_when_it_is_installed(self, monkeypatch, started):
        self._vs_code(monkeypatch, started, installed=True)
        ph.open_file('/home/u/report.md')
        assert started['run'] == [['which', 'code'], ['code', '/home/u/report.md']]
        assert started['popen'] == []

    def test_markdown_falls_back_to_windows_without_vs_code(self, monkeypatch, started):
        self._vs_code(monkeypatch, started, installed=False)
        ph.open_file('/home/u/report.md')
        assert started['run'] == [['which', 'code']]
        assert len(started['popen']) == 1 and started['popen'][0][0] == 'powershell.exe'

    def test_html_goes_straight_to_windows(self, monkeypatch, started):
        self._vs_code(monkeypatch, started, installed=True)
        ph.open_file('/home/u/report.html')
        assert started['run'] == []
        assert len(started['popen']) == 1


class TestWslPathConversion:

    @pytest.fixture
    def no_wslpath(self, monkeypatch):
        def run(argv, **kwargs):
            raise FileNotFoundError('wslpath')
        monkeypatch.setattr(subprocess, 'run', run)

    def test_asks_wslpath_first(self, monkeypatch):
        def run(argv, **kwargs):
            assert argv == ['wslpath', '-w', '/home/u/r.html']
            return subprocess.CompletedProcess(argv, 0, stdout='\\\\wsl.localhost\\Ubuntu\\home\\u\\r.html\n')
        monkeypatch.setattr(subprocess, 'run', run)
        assert ph._convert_wsl_path_to_windows('/home/u/r.html') == '\\\\wsl.localhost\\Ubuntu\\home\\u\\r.html'

    def test_a_mounted_drive_becomes_its_drive_letter(self, no_wslpath):
        """The fallback used to spell /mnt/c/... through the distribution's share, the long
        way round to C:, and always through Ubuntu's."""
        assert ph._convert_wsl_path_to_windows('/mnt/c/Users/eric/r.html') == 'C:\\Users\\eric\\r.html'
        assert ph._convert_wsl_path_to_windows('/mnt/d') == 'D:\\'

    def test_a_distro_path_uses_the_distro_name(self, no_wslpath, monkeypatch):
        monkeypatch.setenv('WSL_DISTRO_NAME', 'Debian')
        assert ph._convert_wsl_path_to_windows('/home/u/r.html') == '\\\\wsl.localhost\\Debian\\home\\u\\r.html'

    def test_ubuntu_when_the_distro_is_unknown(self, no_wslpath, monkeypatch):
        monkeypatch.delenv('WSL_DISTRO_NAME', raising=False)
        assert ph._convert_wsl_path_to_windows('/home/u/r.html') == '\\\\wsl.localhost\\Ubuntu\\home\\u\\r.html'
