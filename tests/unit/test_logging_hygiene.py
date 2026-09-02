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
GTTK logs to the ``gttk`` logger, never to root -- at operation time as well as at import.

``logging.debug(...)`` and its siblings are the root logger's convenience functions, and
they call ``logging.basicConfig()`` when root has no handlers. Three modules used them:
``gdal_runner.create_isolated_env()`` runs inside the ArcGIS Pro process, and the two tag
parsers reach theirs on any malformed tag during an ordinary ``gttk read``. One call was
enough to install a stderr handler on the host's root logger for the rest of the process.
DEVELOPER.md promised otherwise; ``test_import_side_effects`` could not see it because it
checks module-level loggers, not call sites.
"""

import ast
import pathlib
import subprocess
import sys
import textwrap

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROOT_LOGGER_FUNCTIONS = {'debug', 'info', 'warning', 'warn', 'error', 'critical', 'exception', 'log'}

#: Stand-alone scripts run by hand; their main() may configure root logging for itself.
SCRIPTS = {
    ROOT / 'gttk' / 'resources' / 'esri' / 'build_esri_cs_epsg_lookup.py',
    ROOT / 'gttk' / 'resources' / 'tiff' / 'build_tiff_tag_lookup.py',
}

#: stdout is these modules' output by design: --show-defaults prints its table, and the
#: OSGeo4W-side runner uses stdout as its protocol channel to the parent.
PRINTS_BY_DESIGN = {
    ROOT / 'gttk' / 'utils' / 'cli_help.py',
    ROOT / 'gttk' / 'utils' / 'gdal_runner.py',
    # GDAL's own validate_cloud_optimized_geotiff.py, kept verbatim (DEVELOPER.md, Third-Party
    # Code); its prints are in its usage() and main(), which GTTK never calls.
    ROOT / 'gttk' / 'utils' / 'validate_cloud_optimized_geotiff.py',
}


def _print_calls_outside_main(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    in_main = {id(inner) for node in tree.body
               if isinstance(node, ast.If) and '__main__' in ast.unparse(node.test)
               for inner in ast.walk(node)}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == 'print' and id(node) not in in_main):
            yield node.lineno


def _root_logger_calls(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == 'logging'
                and node.func.attr in ROOT_LOGGER_FUNCTIONS):
            yield node.lineno


def test_no_module_calls_the_root_logger():
    offenders = [f'{path.relative_to(ROOT)}:{line}'
                 for path in sorted((ROOT / 'gttk').rglob('*.py')) if path not in SCRIPTS
                 for line in _root_logger_calls(path)]
    assert offenders == [], 'these log through the root logger, which installs a handler on it:\n' + '\n'.join(offenders)


def test_no_module_prints():
    """A library's stdout belongs to the application. The resource manager reported a theme
    or banner file it could not read with print(), into whatever the host was writing."""
    offenders = [f'{path.relative_to(ROOT)}:{line}'
                 for path in sorted((ROOT / 'gttk').rglob('*.py')) if path not in SCRIPTS | PRINTS_BY_DESIGN
                 for line in _print_calls_outside_main(path)]
    assert offenders == [], 'these print instead of logging:\n' + '\n'.join(offenders)


def test_create_isolated_env_leaves_the_root_logger_alone():
    """The in-process half of the ArcGIS bridge, run in a clean interpreter."""
    result = subprocess.run([sys.executable, '-c', textwrap.dedent("""
        import logging, pathlib
        from gttk.utils.gdal_runner import create_isolated_env
        create_isolated_env(pathlib.Path('/nonexistent/OSGeo4W'))
        print(logging.getLogger().handlers)
    """)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '[]', result.stdout
