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
One default per option.

Every option has two homes: its ``add_argument`` in ``gttk/main.py`` and its field in
the argument dataclass a library caller builds directly. Where the two disagreed, a
script got one behaviour and ``gttk`` another: ``delete_test_files`` was ``True`` on the
command line and ``False`` in ``TestArguments``, and ``ReadArguments`` left ``reader_type``,
``xml_type`` and ``tag_scope`` as ``None`` for the tool to fill in -- with ``text`` for
``xml_type``, where the command line and README say ``table``. Here every argparse
default is held equal to the dataclass default, and the two divergences that are meant
are named, along with the three places DEVELOPER.md documents the ArcGIS dialog
diverging from the command line.
"""

import argparse
import dataclasses
import re
from pathlib import Path

import pytest

from gttk.main import build_parser
import gttk.utils.script_arguments as sa

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]

# Through the module: a name starting with Test at module level would be collected.
DATACLASSES = {
    'compare': sa.CompareArguments,
    'optimize': sa.OptimizeArguments,
    'optimize-arc': sa.OptimizeArguments,
    'test': sa.TestArguments,
    'read': sa.ReadArguments,
    'validate': sa.ValidateArguments,
}

#: (subcommand, field) -> (command-line default, dataclass default), each on purpose.
DIVERGENCES = {
    # The subcommand exists for ArcGIS Pro, so its runs are arc-mode runs; the dataclass
    # is shared with `optimize`, which has no such flag.
    ('optimize-arc', 'arc_mode'): (True, False),
    # DEVELOPER.md, "Known ArcGIS toolbox divergences": the dataclass carries the
    # dialog's value and the command line opts out.
    ('read', 'write_pam_xml'): (False, True),
}


def cli_defaults(name):
    root = build_parser()
    sub = next(a for a in root._actions if isinstance(a, argparse._SubParsersAction)).choices[name]
    return {a.dest: (False if a.nargs == 0 else a.default)
            for a in sub._actions
            if not isinstance(a, argparse._HelpAction) and not a.required
            and a.default is not argparse.SUPPRESS}


def dataclass_defaults(cls):
    out = {}
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING:
            out[f.name] = f.default
        elif f.default_factory is not dataclasses.MISSING:
            out[f.name] = f.default_factory()
    return out


class TestCommandLineAgainstDataclass:

    @pytest.mark.parametrize('name', sorted(DATACLASSES))
    def test_every_default_agrees(self, name):
        cli, declared = cli_defaults(name), dataclass_defaults(DATACLASSES[name])
        for dest, value in cli.items():
            if dest not in declared:
                continue  # --show-defaults exits; it is not a field
            if (name, dest) in DIVERGENCES:
                assert (value, declared[dest]) == DIVERGENCES[(name, dest)], f'{name} {dest}'
            else:
                assert value == declared[dest], f'{name} {dest}: command line {value!r}, dataclass {declared[dest]!r}'

    def test_every_named_divergence_still_exists(self):
        for (name, dest), (cli_value, declared_value) in DIVERGENCES.items():
            assert cli_defaults(name)[dest] == cli_value, f'{name} {dest}'
            assert dataclass_defaults(DATACLASSES[name])[dest] == declared_value, f'{name} {dest}'


class TestToolboxDivergences:
    """DEVELOPER.md documents three places where the Read Metadata dialog differs from
    the command line, on purpose. The dialog and the document are held to that list."""

    TOOLBOX = ROOT / 'toolbox' / 'GTTK_Toolbox.pyt'
    #: parameter -> (what the dialog pre-fills, the command-line default)
    DOCUMENTED = {
        'reader_type': ('analyst', 'producer'),
        'tag_scope': ('compact', 'complete'),
        'write_pam_xml': (True, False),
    }

    def test_the_dialog_pre_fills_exactly_the_documented_values(self):
        read_tool = self.TOOLBOX.read_text(encoding='utf-8').split('class ReadMetadata', 1)[1].split('\nclass ', 1)[0]
        cli = cli_defaults('read')
        for param, (dialog_value, cli_value) in self.DOCUMENTED.items():
            assert cli[param] == cli_value, param
            if isinstance(dialog_value, str):
                pattern = rf"param_{param}\.value = \w+\.label\('{dialog_value}'\)"
            else:
                pattern = rf"param_{param}\.value = {dialog_value}\b"
            assert re.search(pattern, read_tool), f'{param}: the dialog no longer pre-fills {dialog_value!r}'

    def test_developer_md_lists_them_and_nothing_else(self):
        text = (ROOT / 'DEVELOPER.md').read_text(encoding='utf-8')
        section = text.split('### Known ArcGIS toolbox divergences', 1)[1].split('\n## ', 1)[0]
        rows = {re.match(r'\| `(\w+)` \| `(\w+)` \| `(\w+)` \|', line).groups()
                for line in section.splitlines() if line.startswith('| `')}
        assert rows == {(param, str(dialog), str(cli)) for param, (dialog, cli) in self.DOCUMENTED.items()}
