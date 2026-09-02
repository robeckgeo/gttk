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
One version number.

The release number lived in five places that agreed by discipline -- ``pyproject.toml``,
``CITATION.cff``, both README badges and the changelog -- plus a sixth,
``gttk.utils.statistics.__version__ = '1.0.0'``, that agreed with nothing, and five
modules each carried their own ``metadata.version("geotiff-toolkit")`` lookup with a
``0.0.0-dev`` fallback. ``gttk.__version__`` is the one the code reads now; this holds
the six declared copies together and keeps a seventh from appearing.
"""

import ast
import re
import tomllib
from pathlib import Path

import pytest

import gttk

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
RELEASE_HEADING = re.compile(r'^## \[(\d+\.\d+\.\d+)\] - (\d{4}-\d{2}-\d{2})$', re.MULTILINE)


@pytest.fixture(scope='module')
def declared():
    """The version pyproject.toml declares: the one every other copy must equal."""
    with (ROOT / 'pyproject.toml').open('rb') as fh:
        return tomllib.load(fh)['project']['version']


@pytest.fixture(scope='module')
def latest_release():
    """(version, date) of the newest released heading in the changelog."""
    return RELEASE_HEADING.search((ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')).groups()


class TestOneVersion:

    def test_the_package_exposes_it(self, declared):
        assert gttk.__version__ == declared, \
            'gttk.__version__ comes from the installed metadata; after bumping pyproject.toml, reinstall (pip install -e .)'

    def test_the_citation_file(self, declared, latest_release):
        text = (ROOT / 'CITATION.cff').read_text(encoding='utf-8')
        assert f'\nversion: {declared}\n' in text
        assert f'\ndate-released: {latest_release[1]}\n' in text

    @pytest.mark.parametrize('readme', ['README.md', 'README.es.md'])
    def test_the_badge(self, readme, declared):
        assert f'version-{declared}-orange' in (ROOT / readme).read_text(encoding='utf-8')

    def test_the_changelog_names_the_release(self, declared, latest_release):
        assert latest_release[0] == declared

    def test_no_module_carries_its_own(self):
        """Every other module reads gttk.__version__; none looks the metadata up itself
        or declares a number of its own."""
        offenders = []
        for path in (ROOT / 'gttk').rglob('*.py'):
            if path == ROOT / 'gttk' / '__init__.py':
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if isinstance(node, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets):
                    offenders.append(f'{path.relative_to(ROOT)}:{node.lineno} assigns __version__')
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr == 'version' and getattr(node.func.value, 'id', None) == 'metadata'):
                    offenders.append(f'{path.relative_to(ROOT)}:{node.lineno} calls metadata.version')
        assert offenders == []

    def test_the_toolbox_shows_it(self):
        source = (ROOT / 'toolbox' / 'GTTK_Toolbox.pyt').read_text(encoding='utf-8')
        toolbox = source.split('class Toolbox', 1)[1].split('\nclass ', 1)[0]
        assert '__version__' in toolbox, 'the Toolbox label no longer carries the version'
