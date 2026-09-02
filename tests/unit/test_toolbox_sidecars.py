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
Pin the ArcGIS help sidecars (``.pyt.xml``) to the toolbox they document.

ArcGIS Pro shows a tool's side-panel help from a static XML file that nothing
checks: the Optimize sidecar had drifted five parameters behind the dialog before
these tests existed.  Each language's sidecars must document exactly the parameters
the ``.pyt`` defines, under the labels that language displays.
"""

import ast
# The sidecars are files this repository ships, not untrusted input, so the stdlib
# parser is adequate here (no external entities are resolved from our own XML).
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import gttk.i18n as i18n
from gttk.utils.section_registry import ALL_SECTIONS, get_config

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
TOOLBOX_DIR = ROOT / 'toolbox'
PYT = TOOLBOX_DIR / 'GTTK_Toolbox.pyt'
SIDECAR_ROOT = TOOLBOX_DIR / 'i18n'
LANGUAGES = ('en', 'es')
TOOLS = ('CompareCompression', 'OptimizeCompression', 'TestCompression',
         'ReadMetadata', 'ValidateMetadata')
XML_LANG = '{http://www.w3.org/XML/1998/namespace}lang'


@pytest.fixture(scope='module')
def tree():
    return ast.parse(PYT.read_text(encoding='utf-8'), filename=str(PYT))


@pytest.fixture(scope='module')
def named_msgids(tree):
    """Module-level ``NAME = N_("...")`` constants the dialog reuses."""
    constants = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == 'N_'):
            constants[node.targets[0].id] = node.value.args[0].value
    return constants


def _msgid(expr, named_msgids):
    """The English source string behind a ``_(...)`` expression, or None if dynamic."""
    if not (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == '_'):
        return None
    arg = expr.args[0]
    if isinstance(arg, ast.Constant):
        return arg.value
    if isinstance(arg, ast.Name):
        return named_msgids[arg.id]
    return None


def _class(tree, name):
    return next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)


def tool_label(tree, class_name, named_msgids):
    for node in ast.walk(_class(tree, class_name)):
        if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Attribute)
                and node.targets[0].attr == 'label'):
            return _msgid(node.value, named_msgids)
    raise AssertionError(f'{class_name} has no label')


def tool_parameters(tree, class_name, named_msgids):
    """``{parameter name: English displayName}`` as the dialog defines them."""
    params = {}
    for node in ast.walk(_class(tree, class_name)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'Parameter'):
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords}
        name = keywords['name']
        if isinstance(name, ast.Constant):
            params[name.value] = _msgid(keywords['displayName'], named_msgids)
    if class_name == 'ReadMetadata':
        for key in ALL_SECTIONS:
            params[f'section_{key}'] = get_config(key).title
    assert all(params.values()), f'{class_name}: a displayName is not a plain _() literal'
    return params


def sidecar(lang, tool=None):
    name = f'GTTK_Toolbox.{tool}.pyt.xml' if tool else 'GTTK_Toolbox.pyt.xml'
    path = SIDECAR_ROOT / lang / name
    assert path.exists(), path
    return ET.parse(path).getroot()


@pytest.fixture(autouse=True)
def english_afterwards():
    yield
    i18n.activate('en')


class TestLayout:
    def test_both_languages_ship_the_same_files(self):
        listings = {lang: sorted(p.name for p in (SIDECAR_ROOT / lang).glob('*.pyt.xml'))
                    for lang in LANGUAGES}
        assert listings['en'] == listings['es']
        assert listings['en'] == sorted(['GTTK_Toolbox.pyt.xml']
                                        + [f'GTTK_Toolbox.{t}.pyt.xml' for t in TOOLS])

    def test_generated_copies_beside_the_toolbox_are_ignored(self):
        assert '/toolbox/GTTK_Toolbox*.pyt.xml' in (ROOT / '.gitignore').read_text(encoding='utf-8').splitlines()

    def test_toolbox_copies_the_active_language_on_load(self):
        source = PYT.read_text(encoding='utf-8')
        assert 'i18n.sync_sidecars(script_path, LANG)' in source

    def test_stale_arcmap_sidecar_is_gone(self):
        assert not (TOOLBOX_DIR / 'GTTK_Toolbox.xml').exists()

    @pytest.mark.parametrize('lang', LANGUAGES)
    def test_toolbox_level_sidecar(self, lang):
        root = sidecar(lang)
        assert root.get(XML_LANG) == lang
        toolbox = root.find('toolbox')
        assert toolbox.get('name') == 'GTTK_Toolbox' and toolbox.get('alias') == 'gttk'
        assert root.find('dataIdInfo/idAbs').text.strip()
        assert 'v0.' not in root.find('dataIdInfo/idCredit').text
        assert root.find('Binary/Thumbnail/Data').text.strip()


class TestToolSidecars:
    @pytest.mark.parametrize('lang', LANGUAGES)
    @pytest.mark.parametrize('tool', TOOLS)
    def test_documents_exactly_the_dialog_parameters(self, tree, named_msgids, lang, tool):
        root = sidecar(lang, tool)
        assert root.get(XML_LANG) == lang
        element = root.find('tool')
        assert element.get('name') == tool and element.get('toolboxalias') == 'gttk'
        documented = [param.get('name') for param in element.find('parameters')]
        expected = tool_parameters(tree, tool, named_msgids)
        assert sorted(documented) == sorted(expected)
        assert len(documented) == len(set(documented))

    @pytest.mark.parametrize('lang', LANGUAGES)
    @pytest.mark.parametrize('tool', TOOLS)
    def test_labels_match_the_dialog_in_that_language(self, tree, named_msgids, lang, tool):
        i18n.activate(lang)
        element = sidecar(lang, tool).find('tool')
        assert element.get('displayname') == i18n._(tool_label(tree, tool, named_msgids))
        expected = tool_parameters(tree, tool, named_msgids)
        mismatched = {param.get('name'): (param.get('displayname'), i18n._(expected[param.get('name')]))
                      for param in element.find('parameters')
                      if param.get('displayname') != i18n._(expected[param.get('name')])}
        assert mismatched == {}

    @pytest.mark.parametrize('lang', LANGUAGES)
    @pytest.mark.parametrize('tool', TOOLS)
    def test_every_help_text_is_present(self, lang, tool):
        element = sidecar(lang, tool).find('tool')
        assert element.find('summary').text.strip()
        assert all(item.text.strip() for item in element.find('usage'))
        empty = [param.get('name') for param in element.find('parameters')
                 if not (param.find('dialogReference') is not None
                         and ''.join(param.find('dialogReference').itertext()).strip())]
        assert empty == []

    @pytest.mark.parametrize('lang', LANGUAGES)
    @pytest.mark.parametrize('tool', TOOLS)
    def test_explanations_are_rich_text(self, lang, tool):
        """Pro's item-description stylesheet (geoprocessingPro.xslt) shows a dialogReference
        only when it holds child elements or escaped HTML; plain text falls through to
        the "no reference" placeholder.  Esri's editor writes DIV/P/SPAN, so we do too."""
        element = sidecar(lang, tool).find('tool')
        plain = [param.get('name') for param in element.find('parameters')
                 if param.find('dialogReference/DIV') is None]
        assert plain == []

    @pytest.mark.parametrize('tool', TOOLS)
    def test_languages_agree_on_structure(self, tool):
        attributes = {}
        for lang in LANGUAGES:
            element = sidecar(lang, tool).find('tool')
            attributes[lang] = [(p.get('name'), p.get('type'), p.get('direction'), p.get('datatype'))
                                for p in element.find('parameters')]
        assert attributes['en'] == attributes['es']
