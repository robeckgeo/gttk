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
