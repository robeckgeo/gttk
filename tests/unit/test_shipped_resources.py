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
Every icon the reports can ask for ships, and every icon that ships can be asked for.

Icons are found by construction: a section's ``icon`` name under ``svg/menu``, a report
type's name (and its ``_white`` twin) under ``svg/favicon``. Nothing checked either
direction. The PAM section asked for ``aux`` while the file that draws it is ``pam.svg``,
so every metadata report logged a missing icon and showed none; and twenty files -- a set
of GUI glyphs for an application this repository does not contain, PNG favicon tiles, an
``.ico`` and an unreferenced menu icon -- shipped in the wheel for nothing.
"""

from pathlib import Path

import pytest

from gttk.utils import section_registry
from gttk.utils.validation import models as validation_models

pytestmark = pytest.mark.unit

ICONS = Path(__file__).resolve().parents[2] / 'gttk' / 'resources' / 'icons'
#: HtmlReportFormatter(report_type=...) as the three tools construct it.
REPORT_TYPES = ('metadata', 'comparison', 'validation')
#: The project mark. Nothing in the package renders it; the documentation does.
PROJECT_MARK = 'svg/favicon/gttk.svg'


def menu_icons_requested():
    names = {config.icon for config in section_registry.SECTION_CONFIGS.values()}
    # The validation report's sections, and get_section_icon's fallback.
    return names | set(validation_models.SECTION_ICONS.values()) | {'checkbox'}


def shipped():
    return {path.relative_to(ICONS).as_posix() for path in ICONS.rglob('*') if path.is_file()}


def test_every_menu_icon_a_section_names_ships():
    missing = sorted(name for name in menu_icons_requested()
                     if not (ICONS / 'svg' / 'menu' / f'{name}.svg').is_file())
    assert missing == []


def test_every_favicon_ships_in_both_themes():
    missing = sorted(f'{kind}{suffix}' for kind in REPORT_TYPES for suffix in ('', '_white')
                     if not (ICONS / 'svg' / 'favicon' / f'{kind}{suffix}.svg').is_file())
    assert missing == []


def test_nothing_ships_that_nothing_asks_for():
    expected = ({f'svg/menu/{name}.svg' for name in menu_icons_requested()}
                | {f'svg/favicon/{kind}{suffix}.svg' for kind in REPORT_TYPES for suffix in ('', '_white')}
                | {PROJECT_MARK})
    assert shipped() == expected
