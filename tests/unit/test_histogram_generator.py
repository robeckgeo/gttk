#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2026, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
The histogram generator draws to PNG bytes for a report; it never shows a window and it
never decides matplotlib's backend for anyone else.

Left to itself, matplotlib picks a GUI backend wherever a display is advertised -- WSLg
sets DISPLAY for every shell -- and QtAgg then blocked on the compositor socket, which
stalled ``gttk optimize`` and ``gttk read`` for the whole 900-second timeout in a headless
run. The first cure was ``matplotlib.use("Agg")`` at import, which traded one leak for
another: an application that had chosen its own backend lost it the moment it imported
GTTK. The module now draws on a Figure with its own Agg canvas and never imports pyplot,
so the backend is never selected at all.
"""

import base64
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit

STATS = {'band_histogram_counts': [[1, 2, 3]], 'band_histogram_bins': [[0, 1, 2, 3]],
         'band_names': ['Band 1']}

RENDER = (
    "import sys, matplotlib\n"
    "from gttk.utils.statistics.histogram_generator import generate_histogram_base64\n"
    f"png = generate_histogram_base64({STATS!r}, 'x.tif')\n"
    "print(png[:8]); print('matplotlib.pyplot' in sys.modules); print(matplotlib.rcParams._get('backend'))\n"
)


def _render(env):
    result = subprocess.run([sys.executable, '-c', RENDER], env=env, capture_output=True,
                            text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_renders_headless_with_a_display_advertised_and_no_backend_chosen():
    """The situation that provoked the stall: DISPLAY set, MPLBACKEND not, nothing
    resolved -- and the rendering must neither hang nor import pyplot."""
    env = {k: v for k, v in os.environ.items() if k != 'MPLBACKEND'}
    env['DISPLAY'] = ':99'
    png_head, pyplot_loaded, backend = _render(env)
    assert base64.b64decode(png_head + '====')[:4] == b'\x89PNG'
    assert pyplot_loaded == 'False'


def test_leaves_the_host_applications_backend_alone():
    """An application that chose the PDF backend must still have it after rendering."""
    env = dict(os.environ, MPLBACKEND='pdf')
    _, _, backend = _render(env)
    assert backend == 'pdf'
