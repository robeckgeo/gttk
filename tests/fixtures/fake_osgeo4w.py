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
A directory shaped like an OSGeo4W installation whose tools are this environment's.

The ArcGIS Pro path never runs GDAL in its own process: it launches OSGeo4W's Python on
``gdal_runner.py`` and sends it a JSON payload of commands, and the runner resolves each
command's executable against ``<OSGeo4W>/bin``. None of that could run on Linux, so
``gdal_runner`` and the arc orchestration were tested through stubs that replaced the
very functions under test.

This builds the layout the code looks for -- ``bin/python.exe``, ``bin/gdal_translate``,
``apps/Python312/Scripts/gdal_calc.py``, ``share/gdal``, ``share/proj`` -- out of small
shell shims that ``exec`` the conda environment's interpreter and GDAL tools, and
symlinks to its data directories. Everything up to and including
``_orchestrate_geotiff_optimization`` then runs for real, through the real runner, with
the real GDAL.

POSIX only: the shims are shell scripts and the data directories are symlinks. On Windows
the real OSGeo4W is the fixture.
"""

import os
import shlex
import stat
import sys
from pathlib import Path

#: Command-line tools the arc path invokes by name, provided from the conda environment.
GDAL_TOOLS = ('gdalinfo', 'gdal_translate', 'gdaladdo', 'gdalwarp', 'gdal_edit')

#: The Python directory name the fake mirrors. gdal_runner discovers apps/Python3*, so the
#: exact version is immaterial; this is what OSGeo4W ships at the time of writing.
PYTHON_DIR_NAME = 'Python312'


def _shim(path: Path, target: Path) -> None:
    """A shell script at ``path`` that runs ``target`` with the same arguments.

    ``create_isolated_env`` points PYTHONHOME at the fake tree and blanks PYTHONPATH, which
    is right for OSGeo4W's interpreter and fatal for conda's; the shim drops both.
    """
    path.write_text(
        f"#!/bin/sh\n"
        f"# {path.name}: stands in for OSGeo4W's; runs this environment's instead.\n"
        f"unset PYTHONHOME PYTHONPATH\n"
        f'exec {shlex.quote(str(target))} "$@"\n',
        encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def build_fake_osgeo4w(root: Path) -> Path:
    """Populate ``root`` as a fake OSGeo4W installation and return it."""
    if os.name == 'nt':
        raise RuntimeError('the fake OSGeo4W is POSIX-only; use the real one on Windows')
    conda = Path(sys.prefix)
    bin_dir = root / 'bin'
    python_dir = root / 'apps' / PYTHON_DIR_NAME
    scripts_dir = python_dir / 'Scripts'
    share_dir = root / 'share'
    for directory in (bin_dir, scripts_dir, share_dir):
        directory.mkdir(parents=True, exist_ok=True)

    # The runner looks for bin/python.exe for scripts and for the "python" command by
    # name; on POSIX no .exe is appended, so both names are provided.
    for name in ('python', 'python.exe'):
        _shim(bin_dir / name, Path(sys.executable))
    for tool in GDAL_TOOLS:
        target = conda / 'bin' / tool
        if target.exists():
            _shim(bin_dir / tool, target)

    # gdal_calc.py is run as `python.exe <Scripts>/gdal_calc.py ...`, so it must be a
    # real Python file; the conda environment ships it as a module.
    (scripts_dir / 'gdal_calc.py').write_text(
        "import sys\nfrom osgeo_utils.gdal_calc import main\nsys.exit(main(sys.argv))\n", encoding='utf-8')

    for link, target in (('share/gdal', conda / 'share' / 'gdal'),
                         ('share/proj', conda / 'share' / 'proj'),
                         ('bin/gdalplugins', conda / 'lib' / 'gdalplugins')):
        if target.is_dir():
            (root / link).symlink_to(target, target_is_directory=True)
    return root
