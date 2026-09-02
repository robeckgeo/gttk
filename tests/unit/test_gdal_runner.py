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
gdal_runner.py is launched by ArcGIS Pro's Python inside OSGeo4W's Python. Its stdout
is a protocol channel -- one JSON line per captured command -- that the parent parses
line by line, and its own log records travel down the same pipe. A ``gdalinfo -json``
payload over 8 KiB (every real DEM) left its closing newline pending in the text layer
while the next record was written beneath it; the parent then saw
``{...}All commands executed successfully.``, not JSON, and Optimize Compression died
with "No output captured from gdalinfo". Nothing in the suite reached that path, so this
drives the runner's main() through a pipe-like stdout with an oversized payload and
parses the result exactly as the parent does.
"""

import io
import json
import sys

import pytest

from gttk.utils import gdal_runner

pytestmark = pytest.mark.unit


def _run_runner(monkeypatch, tmp_path, captured: str) -> str:
    """Drive gdal_runner.main() with one captured command and return raw stdout."""
    raw = io.BytesIO()
    stdout = io.TextIOWrapper(io.BufferedWriter(raw), encoding='utf-8')
    monkeypatch.setattr(sys, 'stdout', stdout)
    osgeo4w = tmp_path / "OSGeo4W"
    osgeo4w.mkdir()
    payload = {"osgeo4w_root": str(osgeo4w),
               "commands": [{"command": ["gdalinfo", "-json", "x.tif"], "capture_output": True}]}
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(gdal_runner, 'create_isolated_env', lambda osgeo4w_dir: {})
    monkeypatch.setattr(gdal_runner, 'run_gdal_command',
                        lambda command, env, capture_output=False: captured)
    monkeypatch.setattr(gdal_runner, 'logger', gdal_runner._configure_script_logging(tmp_path / 'logs'))
    gdal_runner.main()
    stdout.flush()
    return raw.getvalue().decode('utf-8')


def _parse_as_the_parent_does(out: str):
    """optimize_compression_arc.run_gdal_commands: JSON lines with a 'stdout' key."""
    found = []
    for line in out.strip().split('\n'):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and "stdout" in data:
            found.append(data)
    return found


def test_a_large_captured_output_reaches_the_parent_as_one_json_line(monkeypatch, tmp_path):
    gdalinfo_json = json.dumps({"description": "x.tif", "metadata": {"": {"k": "v" * 20000}}})
    out = _run_runner(monkeypatch, tmp_path, gdalinfo_json)
    found = _parse_as_the_parent_does(out)
    assert len(found) == 1, f"parent would capture nothing from: {out[:120]!r} ... {out[-100:]!r}"
    assert found[0] == {"command_index": 0, "stdout": gdalinfo_json}


def test_a_small_captured_output_still_arrives(monkeypatch, tmp_path):
    out = _run_runner(monkeypatch, tmp_path, '{"description": "x.tif"}')
    assert _parse_as_the_parent_does(out) == [{"command_index": 0, "stdout": '{"description": "x.tif"}'}]


class TestProjectionExtractionTimeout:
    """communicate(timeout=30) raises TimeoutExpired but leaves the child running; the
    caller used to swallow it under `except Exception` and return, with an OSGeo4W
    interpreter still alive behind it."""

    def test_a_hung_runner_is_killed(self, tmp_path, monkeypatch):
        import subprocess
        from gttk.utils.config_loader import config
        osgeo4w = tmp_path / 'OSGeo4W'
        (osgeo4w / 'bin').mkdir(parents=True)
        (osgeo4w / 'bin' / 'python.exe').touch()
        monkeypatch.setattr(config, 'get', lambda key, default=None: str(osgeo4w) if key == 'paths.osgeo4w' else default)

        events = []

        class Hung:
            returncode = None

            def communicate(self, input=None, timeout=None):
                if timeout is not None and not events:
                    events.append('timeout')
                    raise subprocess.TimeoutExpired(cmd='python', timeout=timeout)
                events.append('reaped')
                return ('', '')

            def kill(self):
                events.append('killed')

        monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: Hung())
        result = gdal_runner.get_projection_info_from_osgeo4w(str(tmp_path / 'x.tif'))
        assert result == (None, None, None)
        assert events == ['timeout', 'killed', 'reaped']


class TestProjectionScriptWarningsReachTheLog:
    """The generated script used to swallow seven failures with `pass` and still exit 0
    with valid JSON; it now lists them, and the parent logs each one."""

    def test_each_warning_is_logged_with_the_file_name(self, tmp_path, monkeypatch, caplog):
        import json
        import logging
        import subprocess
        from gttk.utils.config_loader import config
        osgeo4w = tmp_path / 'OSGeo4W'
        (osgeo4w / 'bin').mkdir(parents=True)
        (osgeo4w / 'bin' / 'python.exe').touch()
        monkeypatch.setattr(config, 'get', lambda key, default=None: str(osgeo4w) if key == 'paths.osgeo4w' else default)
        answer = {"projection_info": {"is_projected": True}, "wkt_string": "PROJCRS[...]",
                  "projjson_string": "", "warnings": ["WKT export: no PROJ database", "PROJJSON export: boom"]}

        class Answering:
            returncode = 0

            def communicate(self, input=None, timeout=None):
                return (json.dumps({"command_index": 0, "stdout": json.dumps(answer)}) + '\n', '')

            def kill(self):
                pass

        monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: Answering())
        with caplog.at_level(logging.WARNING):
            info, wkt, projjson = gdal_runner.get_projection_info_from_osgeo4w(str(tmp_path / 'tile.tif'))
        assert info == {"is_projected": True} and wkt == "PROJCRS[...]"
        assert 'tile.tif: WKT export: no PROJ database' in caplog.text
        assert 'tile.tif: PROJJSON export: boom' in caplog.text
