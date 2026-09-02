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
The three dependency manifests agree with each other and with what the code imports.

`psutil` was listed in environment.yml and requirements.txt but not in pyproject.toml,
so a `pip install geotiff-toolkit` ran without it and the statistics calculator fell
back to a fixed threshold instead of sizing its fast path from the available RAM.
Pillow was declared nowhere at all and present only because matplotlib needs it.
"""

import ast
import pathlib
import re
import sys
import tomllib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Import names that are, on purpose, not pip dependencies.
NOT_PIP = {
    'osgeo': 'GDAL comes from conda-forge or OSGeo4W; pip cannot build it (pyproject.toml)',
    'arcpy': 'provided by ArcGIS Pro',
    'gttk': 'ourselves',
    'tests': 'the suite',
}

#: Import name -> distribution name, where they differ.
IMPORT_TO_DIST = {'PIL': 'pillow', 'jsonpath_ng': 'jsonpath-ng'}


def _normalise(name: str) -> str:
    return name.lower().replace('_', '-')


def _requirement_name(spec: str) -> str:
    return _normalise(re.match(r'[A-Za-z0-9_.\-]+', spec.strip()).group(0))


def third_party_imports() -> set:
    names = set()
    for path in (ROOT / 'gttk').rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split('.')[0])
    names -= set(sys.stdlib_module_names)
    names -= set(NOT_PIP)
    return {_normalise(IMPORT_TO_DIST.get(name, name)) for name in names}


def pyproject():
    with (ROOT / 'pyproject.toml').open('rb') as fh:
        project = tomllib.load(fh)['project']
    return ({_requirement_name(d) for d in project['dependencies']},
            {extra: {_requirement_name(d) for d in specs}
             for extra, specs in project.get('optional-dependencies', {}).items()})


def requirements_txt() -> set:
    lines = (ROOT / 'requirements.txt').read_text(encoding='utf-8').splitlines()
    return {_requirement_name(line) for line in lines if line.strip() and not line.startswith('#')}


def environment_yml() -> set:
    lines = (ROOT / 'environment.yml').read_text(encoding='utf-8').splitlines()
    names = set()
    for line in lines:
        match = re.match(r'\s*-\s*([A-Za-z0-9_.\-]+)', line)
        if match:
            names.add(_normalise(match.group(1)))
    return names - {'python'}


class TestEveryImportIsDeclared:

    def test_pyproject_declares_every_third_party_import(self):
        declared, _ = pyproject()
        missing = third_party_imports() - declared
        assert missing == set(), f'imported by gttk/ but not in [project] dependencies: {sorted(missing)}'

    def test_the_two_that_were_missing(self):
        declared, _ = pyproject()
        assert {'psutil', 'pillow'} <= declared

    def test_the_test_tools_are_a_dev_extra(self):
        _, extras = pyproject()
        assert {'pytest', 'pytest-cov'} <= extras['dev']


class TestTheManifestsAgree:

    def test_requirements_txt_covers_pyproject_and_the_dev_extra(self):
        declared, extras = pyproject()
        assert declared | extras['dev'] <= requirements_txt()

    def test_environment_yml_covers_requirements_txt_and_gdal(self):
        assert requirements_txt() | {'gdal'} <= environment_yml()

    def test_gdal_stays_out_of_pip_requirements(self):
        """`pip install gdal` compiles against a GDAL that pip cannot provide."""
        assert 'gdal' not in requirements_txt()
