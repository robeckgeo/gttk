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
The histogram generator draws to PNG bytes for a report; it never shows a window.
Left to itself, matplotlib picks a GUI backend wherever a display is advertised --
WSLg sets DISPLAY for every shell -- and QtAgg then blocks on the compositor socket,
which stalled ``gttk optimize`` and ``gttk read`` for the whole 900-second timeout in
a headless run.  The module must therefore select the Agg backend itself, before
pyplot is imported, whatever the environment says.
"""

import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def test_importing_the_histogram_generator_selects_the_agg_backend():
    """Run the import in a fresh interpreter with a display advertised and no
    MPLBACKEND override, the situation that provoked the stall, and read back the
    backend matplotlib ended up with."""
    env = {k: v for k, v in os.environ.items() if k != "MPLBACKEND"}
    env["DISPLAY"] = ":99"
    result = subprocess.run(
        [sys.executable, "-c",
         "import matplotlib\n"
         "import gttk.utils.statistics.histogram_generator\n"
         "print(matplotlib.get_backend())"],
        env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().lower() == "agg", result.stdout
