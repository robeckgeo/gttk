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
Tests for the rendered command-line help.

Most `optimize` options have no fixed default -- the value is chosen later from
--product-type and from the codec that ends up selected -- so argparse's stock
formatter used to print `(default: None)` for options that very much do have one,
while hand-written 'Default: ...' sentences said something else on the same line.

The fix generates those sentences from the resolver, so the tests that matter here
are the ones that would catch it drifting back apart: no `(default: None)` anywhere,
no default stated twice, and every cell of the epilog table equal to what
OptimizeArguments actually resolves.
"""

import argparse
import re
from pathlib import Path

import pytest

import gttk.utils.optimize_constants as oc
from gttk.main import build_parser
from gttk.utils import cli_help as ch
from gttk.utils.script_arguments import OptimizeArguments

SUBCOMMANDS = ('compare', 'optimize', 'optimize-arc', 'test', 'read', 'validate')

#: 'Default: X ... (default: Y)' -- the two halves of one line disagreeing.
DOUBLED_DEFAULT = re.compile(r'Defaults?:.*\(default:', re.IGNORECASE)


@pytest.fixture(scope='module')
def parsers():
    """Every parser in the CLI, keyed by subcommand, plus '' for the root."""
    root = build_parser()
    subparsers = next(a for a in root._actions
                      if isinstance(a, argparse._SubParsersAction))
    return {'': root, **subparsers.choices}


def _help_of(parsers, name):
    """Help text rendered at a fixed width, so wrapping cannot hide a match."""
    parser = parsers[name]
    parser.formatter_class = lambda prog: ch.GttkHelpFormatter(prog, width=200)
    return parser.format_help()


# --- The formatter tells the truth -----------------------------------------

class TestNoMisleadingDefaults:
    """argparse's stock formatter appends a default to every optional, with no
    exception for required= or for None-as-sentinel.  Neither is acceptable here."""

    @pytest.mark.parametrize('name', SUBCOMMANDS)
    def test_no_default_none_anywhere(self, parsers, name):
        assert 'default: None' not in _help_of(parsers, name)

    @pytest.mark.parametrize('name', SUBCOMMANDS)
    def test_no_default_stated_twice(self, parsers, name):
        """Checked per option: a hand-written 'Default: ...' plus argparse's own
        '(default: ...)' is how --mask-nodata ended up contradicting itself."""
        formatter = ch.GttkHelpFormatter(prog='gttk')
        for action in parsers[name]._actions:
            rendered = formatter._get_help_string(action)
            assert not DOUBLED_DEFAULT.search(rendered), \
                f'{name}: {action.option_strings} states its default twice: {rendered}'

    @pytest.mark.parametrize('name', SUBCOMMANDS)
    def test_required_arguments_carry_no_default(self, parsers, name):
        formatter = ch.GttkHelpFormatter(prog='gttk')
        for action in parsers[name]._actions:
            if action.required:
                assert '(default:' not in formatter._get_help_string(action), \
                    f'{name}: required {action.option_strings} shows a default'

    def test_help_action_is_not_given_a_default(self, parsers):
        """-h defaults to SUPPRESS; printing it would leak '==SUPPRESS=='."""
        assert 'SUPPRESS' not in _help_of(parsers, 'optimize')

    def test_a_real_static_default_is_still_shown(self, parsers):
        """The formatter suppresses noise, not information."""
        assert '(default: _comp)' in _help_of(parsers, 'optimize')


# --- Help text cannot drift from behaviour ---------------------------------

class TestGeneratedHelpMatchesResolver:

    @pytest.mark.parametrize('product_type', ch.PRODUCT_TYPES)
    @pytest.mark.parametrize('column,field,overrides', [
        ('-a', 'algorithm', {}),
        ('-p', 'predictor', {}),
        ('-d', 'decimals', {}),
        ('mask-nodata', 'mask_nodata', {}),
        ('ovr-resampling', 'overview_resampling', {}),
    ])
    def test_table_cell_equals_resolved_value(self, product_type, column, field, overrides):
        """Every cell of the epilog table is read back from the resolver, so the
        table cannot describe behaviour the tool does not have."""
        row = next(line.split() for line in ch.profile_table().splitlines()
                   if line.strip().startswith(product_type))
        header = next(line.split() for line in ch.profile_table().splitlines()
                      if line.strip().startswith('-t'))
        args = OptimizeArguments(product_type=product_type, vertical_srs='EPSG:5703',
                                 **overrides)
        assert row[header.index(column)] == ch.fmt_value(getattr(args, field))

    def test_lerc_column_marks_imagery_unavailable(self):
        """LERC is refused for imagery, which is a different thing from unset."""
        image_row = next(line for line in ch.profile_table().splitlines()
                         if line.strip().startswith('image'))
        assert 'n/a' in image_row

    def test_clause_collapses_when_every_type_agrees(self):
        assert ch.default_clause('num_threads') == 'ALL_CPUS'

    def test_clause_groups_types_by_value(self):
        clause = ch.default_clause('algorithm')
        assert 'JPEG (image)' in clause
        assert 'DEFLATE (dem, error, scientific, thematic)' in clause

    def test_algorithm_help_states_the_resolved_default(self, parsers):
        text = ' '.join(_help_of(parsers, 'optimize').split())
        assert ch.default_clause('algorithm') in text

    def test_table_fits_a_standard_terminal(self):
        assert max(len(line) for line in ch.profile_table().splitlines()) <= 80


# --- --show-defaults --------------------------------------------------------

class TestShowDefaults:

    def _run(self, argv):
        with pytest.raises(SystemExit) as exit_info:
            build_parser().parse_args(argv)
        return exit_info.value.code

    def test_exits_cleanly_without_input_or_output(self, capsys):
        """It exits from inside the action, so required= never fires -- the same
        mechanism --help uses."""
        assert self._run(['optimize', '--show-defaults', 'dem']) == 0
        assert 'DEFLATE' in capsys.readouterr().out

    def test_reports_the_resolved_values(self, capsys):
        self._run(['optimize', '--show-defaults', 'dem'])
        out = capsys.readouterr().out
        for expected in ('--algorithm', 'DEFLATE', '--predictor', '--decimals'):
            assert expected in out

    def test_marks_options_the_codec_does_not_use(self, capsys):
        self._run(['optimize', '--show-defaults', 'dem'])
        assert 'not used by DEFLATE' in capsys.readouterr().out

    def test_bare_flag_covers_every_product_type(self, capsys):
        self._run(['optimize', '--show-defaults'])
        out = capsys.readouterr().out
        for product_type in ch.PRODUCT_TYPES:
            assert f'-t {product_type}' in out

    def test_does_not_leak_into_the_namespace(self):
        """main() splats vars(args) into OptimizeArguments, so a dest that is not a
        dataclass field would be a TypeError on every ordinary run."""
        args = build_parser().parse_args(
            ['optimize', '-i', 'in.tif', '-o', 'out.tif', '-t', 'thematic'])
        assert 'show_defaults' not in vars(args)

    def test_namespace_still_constructs_the_dataclass(self, tmp_path):
        source = tmp_path / 'in.tif'
        source.touch()
        args = build_parser().parse_args(
            ['optimize', '-i', str(source), '-o', 'out.tif', '-t', 'thematic'])
        namespace = vars(args)
        namespace.pop('tool', None)
        assert OptimizeArguments(**namespace).algorithm == 'DEFLATE'


# --- The flags themselves ---------------------------------------------------

class TestOptionSurface:

    def test_boolean_options_render_as_bool(self, parsers):
        assert '--cog BOOL' in _help_of(parsers, 'optimize')

    def test_compare_accepts_the_documented_report_format_flag(self, parsers):
        """Every other subcommand and the README use the hyphen; compare only
        declared the underscore, so the documented flag did not exist."""
        args = parsers['compare'].parse_args(
            ['-i', 'a.tif', '-o', 'b.tif', '--report-format', 'md'])
        assert args.report_format == 'md'

    def test_compare_still_accepts_the_historic_spelling(self, parsers):
        args = parsers['compare'].parse_args(
            ['-i', 'a.tif', '-o', 'b.tif', '--report_format', 'md'])
        assert args.report_format == 'md'

    @pytest.mark.parametrize('name', SUBCOMMANDS)
    def test_no_missing_spaces_in_help(self, parsers, name):
        """Catches the 'syntax-highlightedtext' and 'mask(e.g.' class of typo."""
        text = _help_of(parsers, name)
        assert not re.search(r'[a-z]\(e\.g\.', text)
        assert 'highlightedtext' not in text

    def test_optimize_options_are_grouped(self, parsers):
        text = _help_of(parsers, 'optimize')
        for title in ('required:', 'compression:', 'overviews:',
                      'masking and nodata:', 'report:'):
            assert title in text


# --- What a run reports about itself ----------------------------------------

class TestResolvedSettingsBlock:
    """`--show-defaults` says what would happen; the run log says what did.  The
    difference worth reporting is who chose each value, which _resolve_defaults
    overwrites in place -- hence explicit_fields, captured before it runs."""

    def _block(self, **kwargs):
        kwargs.setdefault('vertical_srs', 'EPSG:5703')
        return ch.render_resolved_settings(OptimizeArguments(product_type='dem', **kwargs))

    def _row(self, block, flag):
        return next(line for line in block.splitlines() if line.strip().startswith(flag + ' '))

    def test_a_deferred_option_the_caller_set_is_credited_to_them(self):
        assert 'set by you' in self._row(self._block(algorithm='ZSTD'), '--algorithm')

    def test_a_deferred_option_left_alone_is_credited_to_the_profile(self):
        assert 'profile: dem' in self._row(self._block(), '--algorithm')

    def test_a_static_default_the_caller_changed_is_credited_to_them(self):
        """explicit_fields cannot see these -- they are never None -- so the value
        differing from the declared default is the only evidence."""
        assert 'set by you' in self._row(self._block(tile_size=256), '--tile-size')

    def test_a_static_default_left_alone_is_not(self):
        assert 'built-in default' in self._row(self._block(), '--tile-size')

    def test_notes_override_a_derived_answer(self):
        """The integer-data predictor clamp happens after resolution and depends on the
        raster, so nothing derivable from the flags could describe it."""
        args = OptimizeArguments(product_type='dem', vertical_srs='EPSG:5703')
        block = ch.render_resolved_settings(args, notes={'predictor': 'clamped for Int16 data'})
        assert 'clamped for Int16 data' in self._row(block, '--predictor')

    def test_data_type_reaches_the_heading(self):
        args = OptimizeArguments(product_type='dem', vertical_srs='EPSG:5703')
        assert 'Float32' in ch.render_resolved_settings(args, data_type='Float32')

    def test_same_shape_as_show_defaults(self):
        """One renderer, so the two blocks stay comparable."""
        runtime = self._block()
        static = ch.render_show_defaults('dem')
        for title, _ in ch._SHOW_SECTIONS:
            assert f'  {title}' in runtime and f'  {title}' in static


class TestExplicitFieldTracking:

    def test_records_only_what_the_caller_passed(self):
        args = OptimizeArguments(product_type='dem', vertical_srs='EPSG:5703',
                                 algorithm='ZSTD', predictor=3)
        assert {'algorithm', 'predictor'} <= args.explicit_fields
        assert 'level' not in args.explicit_fields      # resolved to 9, not asked for
        assert 'overview_compress' not in args.explicit_fields

    def test_survives_being_rebuilt_from_vars(self):
        """The directory walk rebuilds these once per file.  Recomputing would see
        resolved values everywhere and credit the caller with all of them."""
        first = OptimizeArguments(product_type='dem', vertical_srs='EPSG:5703',
                                  algorithm='ZSTD')
        again = OptimizeArguments(**vars(first))
        assert again.explicit_fields == first.explicit_fields
        assert 'level' not in again.explicit_fields

    def test_mask_alpha_is_not_pre_empted_by_argparse(self):
        """argparse used to default --mask-alpha to True while the dataclass declared
        None, so every run looked as though the caller had asked for it."""
        args = build_parser().parse_args(
            ['optimize', '-i', 'in.tif', '-o', 'out.tif', '-t', 'thematic'])
        assert args.mask_alpha is None


# --- The README says the same thing as the code -----------------------------

class TestReadmeMatchesResolver:
    """README's profile table is written by hand, so pin it to the resolver.  It is
    one of the four copies of this knowledge that drifted apart in the first place."""

    README = Path(__file__).resolve().parents[2] / 'README.md'
    #: Column header -> (OptimizeArguments field, extra flags to pin)
    COLUMNS = {
        '`-a`': ('algorithm', {}),
        '`-p`': ('predictor', {}),
        '`-d`': ('decimals', {}),
        '`-z` *': ('max_z_error', {'algorithm': 'LERC'}),
        '`--mask-nodata`': ('mask_nodata', {}),
        '`--mask-alpha`': ('mask_alpha', {}),
        '`--overview-resampling`': ('overview_resampling', {}),
        '`--raster-type`': ('raster_type', {}),
    }

    @pytest.fixture(scope='class')
    def table(self):
        text = self.README.read_text(encoding='utf-8')
        body = text.split('#### Product-Type Profiles', 1)[1].split('\n#### ', 1)[0]
        rows = [[c.strip() for c in line.strip().strip('|').split('|')]
                for line in body.splitlines()
                if line.startswith('|') and '---' not in line]
        header, *data = rows
        return header, {row[0].strip('`'): row for row in data}

    def test_every_product_type_has_a_row(self, table):
        _, rows = table
        assert set(rows) == set(ch.PRODUCT_TYPES)

    @pytest.mark.parametrize('product_type', ch.PRODUCT_TYPES)
    def test_row_matches_the_resolver(self, table, product_type):
        header, rows = table
        row = rows[product_type]
        for column, (field, overrides) in self.COLUMNS.items():
            args = ch.probe_defaults(product_type, **overrides)
            expected = 'n/a' if args is None else ch.fmt_value(getattr(args, field))
            assert row[header.index(column)] == expected, \
                f'README {product_type}/{column} says {row[header.index(column)]!r}, ' \
                f'resolver says {expected!r}'


# --- The ArcGIS toolbox reads the same resolver -----------------------------

class TestToolboxParity:
    """GTTK_Toolbox.pyt used to keep a hand-maintained second copy of the
    per-product-type defaults, and it had drifted."""

    TOOLBOX = Path(__file__).resolve().parents[2] / 'toolbox' / 'GTTK_Toolbox.pyt'

    def test_toolbox_has_no_second_defaults_table(self):
        """The per-product-type branching the toolbox used to duplicate is gone;
        _reset_all_dependents now asks the resolver instead."""
        source = self.TOOLBOX.read_text(encoding='utf-8')
        for leaked in ('DEFAULT_SCIENTIFIC_MAX_Z_ERROR', 'DEFAULT_DEM_MAX_Z_ERROR',
                       'DEFAULT_ERROR_MAX_Z_ERROR', 'DEFAULT_DEM_DECIMALS',
                       'DEFAULT_ERROR_DECIMALS'):
            assert leaked not in source, \
                f'toolbox reaches past the resolver for {leaked}'

    def test_toolbox_exposes_every_optimize_option(self):
        """The toolbox param list had fallen five options behind the CLI."""
        source = self.TOOLBOX.read_text(encoding='utf-8')
        for name in ('overview_resampling', 'overview_compress', 'overview_predictor',
                     'num_threads', 'report'):
            assert f'"{name}"' in source or f"'{name}'" in source, \
                f'toolbox does not expose {name}'

    @pytest.mark.parametrize('product_type', ch.PRODUCT_TYPES)
    def test_resolver_answers_every_question_the_toolbox_asks(self, product_type):
        """Whatever the toolbox pre-fills has to be something the resolver produces,
        or the dialog would show values the run then ignores."""
        args = OptimizeArguments(product_type=product_type, vertical_srs='EPSG:5703')
        assert args.raster_type in ('Point', 'Area')
        assert args.overview_resampling in oc.OVERVIEW_RESAMPLING_CHOICES
        assert isinstance(args.mask_alpha, bool) and isinstance(args.mask_nodata, bool)
