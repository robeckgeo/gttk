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
The repository's test configuration says what a `pytest` run does. These tests keep it
saying the truth.

Coverage used to be switched on in pytest.ini's addopts, so every invocation -- one test
file, `--collect-only`, a 17-second subprocess run -- rewrote .coverage, coverage.xml and
htmlcov/. The table on disk then described whatever had run last, and a wrong claim that an
omit pattern hid a 1,400-line module survived two reports because nobody asked which run
had produced the numbers. Coverage is opt-in now (`pytest --cov`, and the CI job), and its
settings live in pyproject.toml, the file coverage.py actually reads.
"""

import pathlib
import tomllib

import pytest

pytestmark = pytest.mark.unit

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TestCoverageIsOptIn:

    def test_addopts_carries_no_coverage_flag(self, pytestconfig):
        """`pytest --collect-only` must not rewrite the coverage report."""
        flags = [opt for opt in pytestconfig.getini('addopts') if opt.startswith('--cov')]
        assert flags == [], f'pytest.ini addopts switches coverage on: {flags}'

    def test_the_guards_that_matter_are_still_on(self, pytestconfig):
        opts = pytestconfig.getini('addopts')
        for required in ('--strict-markers', '--doctest-modules'):
            assert required in opts, f'{required} has left addopts'

    def test_coverage_settings_live_where_coverage_reads_them(self):
        """coverage.py reads pyproject.toml and never pytest.ini, which is why the
        [coverage:*] block that pytest.ini carried for years never did anything."""
        with (ROOT / 'pyproject.toml').open('rb') as fh:
            run = tomllib.load(fh)['tool']['coverage']['run']
        assert run['source'] == ['gttk']
        assert run['branch'] is True


class TestContinuousIntegration:
    """The workflow is the only thing that runs the suite without a person; these pin
    the policy CLAUDE.md states, since YAML cannot be executed here."""

    WORKFLOW = ROOT / '.github' / 'workflows' / 'tests.yml'

    def test_workflow_builds_the_conda_environment_from_environment_yml(self):
        text = self.WORKFLOW.read_text(encoding='utf-8')
        assert 'conda-incubator/setup-miniconda' in text
        assert 'environment-file: environment.yml' in text

    def test_fast_suite_on_every_push_and_the_full_suite_on_main(self):
        text = self.WORKFLOW.read_text(encoding='utf-8')
        assert 'pytest -m "not slow"' in text
        assert "github.ref == 'refs/heads/main'" in text

    def test_line_endings_are_pinned_for_windows_clones(self):
        """GTTK ships an ArcGIS Pro toolbox, so the first Windows clone is not
        hypothetical; without this rule core.autocrlf rewrites every text file."""
        rules = (ROOT / '.gitattributes').read_text(encoding='utf-8').splitlines()
        assert '* text=auto eol=lf' in rules
