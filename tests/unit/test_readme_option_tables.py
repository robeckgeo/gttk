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
The README's option tables against the parser.

Each tool's section in README.md carries a hand-written table of its options. Nothing
compared it to ``build_parser()``, and it had drifted: ``--arc-mode`` and
``--optimize-script`` were missing, ``--mask-alpha``'s default was written ``True`` where
the truth is "True except for thematic", ``--show-defaults`` was typed as a string, and
``optimize-arc`` had no table at all. Here every table is rebuilt from the parser --
option, short flag, type, whether it is required, and the default as ``--help`` states
it -- and compared row by row. A cell that summarises a per-product-type default as
``Profile`` is accepted, since the profile table below it is pinned separately by
``test_cli_help``; anything else must say what the help says.
"""

import argparse
import re
from pathlib import Path

import pytest

from gttk.main import build_parser
from gttk.utils import cli_help as ch

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
README = ROOT / 'README.md'
SUBCOMMANDS = ('compare', 'optimize', 'optimize-arc', 'test', 'read', 'validate')

#: The heading that opens each tool's section of the README.
SECTION_HEADINGS = {
    'compare': '### Tool: Compare Compression (`gttk compare`)',
    'optimize': '### Tool: Optimize Compression (`gttk optimize`)',
    'test': '### Tool: Test Compression (`gttk test`)',
    'read': '### Tool: Read Metadata (`gttk read`)',
    'validate': '### Tool: Validate Metadata (`gttk validate`)',
    'optimize-arc': '## Advanced Tools: `gttk optimize-arc`',
}
TABLE_HEADING = '#### Command-Line Arguments'

#: argparse ``type`` callables -> the README's spelling of the type.
TYPE_NAMES = {
    'Path': 'Path', 'str': 'str', 'lower': 'str', 'upper': 'str', 'int': 'int',
    'float': 'float', 'float_nodata': 'float', 'str2bool': 'bool',
    'valid_quality': 'int', 'parse_decimals': 'int or none',
}

#: 'Default: <clause>.' in an option's help, up to the first full stop that ends a sentence.
DEFAULT_CLAUSE = re.compile(r'Defaults?: (.+?)\.(?: |$)')
PRODUCT_TYPE_WORD = re.compile(r'\b(' + '|'.join(ch.PRODUCT_TYPES) + r')\b')


# --- What the parser says -----------------------------------------------------

def subparsers():
    root = build_parser()
    choices = next(a for a in root._actions if isinstance(a, argparse._SubParsersAction)).choices
    return {name: choices[name] for name in SUBCOMMANDS}


def options(parser):
    """The parser's options, keyed by long name, with the exclusive-group dests."""
    exclusive = {a.dest for g in parser._mutually_exclusive_groups for a in g._group_actions}
    return ({long_name(a): a for a in parser._actions if not isinstance(a, argparse._HelpAction)},
            exclusive)


def long_name(action):
    return next(s for s in action.option_strings if s.startswith('--'))


def short_name(action):
    return next((s for s in action.option_strings if not s.startswith('--')), '-')


def aliases(action):
    return [s for s in action.option_strings if s.startswith('--') and s != long_name(action)]


def type_cell(action):
    if action.nargs == 0:
        return 'flag'
    if action.nargs == '?':
        return 'str, optional'
    base = TYPE_NAMES[getattr(action.type, '__name__', str(action.type))]
    return 'str[]' if action.nargs == '*' else base


def required_cell(action, exclusive):
    if action.dest in exclusive:
        return 'Excl.¹'
    if action.required:
        return 'Yes'
    if re.search(r'\bRequired for\b', action.help or ''):
        return 'Varies'
    return 'No'


def default_cell(action):
    """The default as the README should state it, without any backticks.

    What ``--help`` says wins: a ``Default:`` clause in the help text is the statement
    of record, and a clause that varies by product type is summarised as ``Profile``.
    With no clause, the literal argparse default, or ``-`` for none.
    """
    match = DEFAULT_CLAUSE.search(action.help or '')
    if match:
        clause = match.group(1)
        return 'Profile' if PRODUCT_TYPE_WORD.search(clause) else clause
    if action.nargs == 0:
        return 'False'
    if action.default is None or action.default is argparse.SUPPRESS:
        return '-'
    return str(action.default)


def expected_rows(name, parsers):
    """{long name: (short, type, required, default, aliases)} the README must show."""
    opts, exclusive = options(parsers[name])
    if name == 'optimize-arc':
        # The README says the interface is optimize's and lists only what is added.
        shared, _ = options(parsers['optimize'])
        opts = {k: v for k, v in opts.items() if k not in shared}
    return {k: (short_name(a), type_cell(a), required_cell(a, exclusive), default_cell(a), aliases(a))
            for k, a in opts.items()}


# --- What the README says -----------------------------------------------------

def plain(cell):
    """A README cell with its formatting removed: backticks, and the footnote-free form."""
    return cell.replace('`', '').strip()


def readme_table(text, name):
    """The rows of the option table in one tool's section, keyed by long name."""
    section = text.split(SECTION_HEADINGS[name], 1)[1]
    body = section.split(TABLE_HEADING, 1)[1]
    table = next(block for block in body.split('\n\n')[1:] if block.lstrip().startswith('|'))
    lines = [line for line in table.splitlines() if line.startswith('|')]
    header = [plain(c) for c in lines[0].strip('|').split('|')]
    rows = {}
    for line in lines[2:]:
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        row = dict(zip(header, cells))
        rows[plain(row['Argument'])] = row
    return rows


@pytest.fixture(scope='module')
def parsers():
    return subparsers()


@pytest.fixture(scope='module')
def readme():
    return README.read_text(encoding='utf-8')


class TestOptionTables:

    @pytest.mark.parametrize('name', SUBCOMMANDS)
    def test_lists_exactly_the_parsers_options(self, name, parsers, readme):
        assert sorted(readme_table(readme, name)) == sorted(expected_rows(name, parsers))

    @pytest.mark.parametrize('name', SUBCOMMANDS)
    def test_every_cell_matches_the_parser(self, name, parsers, readme):
        rows = readme_table(readme, name)
        for option, (short, type_, required, default, alias_names) in expected_rows(name, parsers).items():
            row = rows[option]
            got = (plain(row['Short']), plain(row['Type']), plain(row['Required']), plain(row['Default']))
            assert got == (short, type_, required, default), f'{name} {option}: README {got}'
            assert row['Description'].strip(), f'{name} {option}: no description'
            for alias in alias_names:
                assert alias in row['Description'], f'{name} {option}: alias {alias} not mentioned'

    def test_optimize_arc_takes_every_optimize_option(self, parsers):
        """The README says optimize-arc's interface is optimize's; hold the parser to it."""
        shared, _ = options(parsers['optimize'])
        arc, _ = options(parsers['optimize-arc'])
        assert set(shared) <= set(arc)
        for option, action in shared.items():
            assert (action.option_strings, action.type, action.default, action.help) == \
                   (arc[option].option_strings, arc[option].type, arc[option].default, arc[option].help), option
        assert set(arc) - set(shared) == {'--arc-mode'}


class TestHelpTour:

    def test_names_every_subcommand(self, readme):
        tour = readme.split('### The `gttk` Command', 1)[1].split('### Tool:', 1)[0]
        for name in SUBCOMMANDS:
            assert f'gttk {name} --help' in tour, name
