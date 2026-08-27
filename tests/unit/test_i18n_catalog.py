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
Pin the Spanish catalog to the toolbox it translates.

The toolbox cannot be imported here (it needs arcpy), so its source is parsed with
``ast``: every string handed to ``_()`` or ``N_()`` must have a Spanish entry, every
Spanish entry must still be a string the toolbox uses, and placeholders must survive
translation.  A translation that silently falls back to English -- or a stale entry
nobody notices -- is exactly what this file exists to catch.
"""

import ast
import re
import tomllib
from collections import Counter
from pathlib import Path

import pytest

import gttk.i18n as i18n
from gttk.utils.section_registry import ALL_SECTIONS, get_config

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
PYT = ROOT / 'toolbox' / 'GTTK_Toolbox.pyt'
CATALOG = i18n.CATALOG_DIR / 'es.toml'
PLACEHOLDER = re.compile(r'\{(\w+)\}')


@pytest.fixture(scope='module')
def tree():
    return ast.parse(PYT.read_text(encoding='utf-8'), filename=str(PYT))


@pytest.fixture(scope='module')
def gettext_calls(tree):
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in ('_', 'N_')]


@pytest.fixture(scope='module')
def expected_keys(gettext_calls):
    literals = {call.args[0].value for call in gettext_calls
                if isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)}
    section_titles = {get_config(key).title for key in ALL_SECTIONS}
    return literals | section_titles


@pytest.fixture(scope='module')
def raw_catalog():
    with open(CATALOG, 'rb') as handle:
        return tomllib.load(handle)


@pytest.fixture(scope='module')
def catalog(raw_catalog):
    return i18n._flatten(raw_catalog)


def _leaf_keys(table):
    for key, value in table.items():
        if isinstance(value, dict):
            yield from _leaf_keys(value)
        else:
            yield key


class TestCatalogFile:
    def test_values_are_non_empty_strings(self, catalog):
        assert catalog, 'catalog is empty'
        bad = {k: v for k, v in catalog.items() if not isinstance(v, str) or not v.strip()}
        assert not bad

    def test_no_duplicate_keys_across_tables(self, raw_catalog):
        counts = Counter(_leaf_keys(raw_catalog))
        assert [k for k, n in counts.items() if n > 1] == []

    def test_placeholders_survive_translation(self, catalog):
        problems = []
        for key, value in catalog.items():
            names = set(PLACEHOLDER.findall(key))
            if names != set(PLACEHOLDER.findall(value)):
                problems.append(key)
                continue
            try:
                value.format(**{name: 'x' for name in names})
            except (KeyError, IndexError, ValueError):
                problems.append(key)
        assert problems == []


class TestCatalogCoversTheToolbox:
    def test_every_wrapped_literal_has_a_spanish_entry(self, expected_keys, catalog):
        assert sorted(expected_keys - catalog.keys()) == []

    def test_no_orphan_spanish_keys(self, expected_keys, catalog):
        assert sorted(catalog.keys() - expected_keys) == []

    def test_gettext_never_wraps_an_fstring(self, gettext_calls):
        offenders = [call.lineno for call in gettext_calls
                     if isinstance(call.args[0], ast.JoinedStr)]
        assert offenders == []

    def test_picklist_entries_are_marked_for_translation(self, tree):
        picklists = [node for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id == 'Picklist']
        assert len(picklists) == 6
        for picklist in picklists:
            entries = picklist.args[0]
            assert isinstance(entries, ast.List)
            for entry in entries.elts:
                assert isinstance(entry, ast.Tuple)
                marker = entry.elts[1]
                assert (isinstance(marker, ast.Call) and isinstance(marker.func, ast.Name)
                        and marker.func.id == 'N_'), f'line {entry.lineno}'


class TestActivatedCatalog:
    def test_spanish_labels_differ_from_english_for_the_dialog(self, catalog):
        i18n.activate('es')
        try:
            untranslated = [k for k, v in catalog.items() if k == v]
            # A handful of terms are the same in both languages (e.g. "Predictor").
            assert len(untranslated) <= 3, untranslated
            assert i18n._('Optimize Compression') == 'Optimizar compresión'
        finally:
            i18n.activate('en')
