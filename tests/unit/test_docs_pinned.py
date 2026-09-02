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
The documents that describe the suite and the code are held to both.

CLAUDE.md and tests/README.md state how many tests there are, by category and by file;
CLAUDE.md lists the pytest markers; all four documents name files, directories and
dotted names in backticks. Each of those had drifted at least once -- a count that matched
no measurement, a marker list one short, a dataclass and two paths that did not exist --
and nothing but a reader noticing would catch the next drift. So: one ``--collect-only``
run against every count, ``pytest.ini`` against the marker list, the filesystem against
every path, and ``importlib`` against every ``gttk.`` name.
"""

import configparser
import importlib
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
DOCS = ('CLAUDE.md', 'DEVELOPER.md', 'README.md', 'tests/README.md')

#: Backticked names that are outputs the tools write, not files in the repository.
OUTPUTS = {'validation_results.json'}
#: Directories a path in backticks must start with to be checked against the tree.
TOP_LEVEL = ('gttk/', 'tests/', 'toolbox/', '.github/', 'example_reports/')
#: Bare file names with these extensions must exist somewhere in the repository.
SOURCE_EXTENSIONS = ('.py', '.md', '.toml', '.ini', '.yml', '.cff', '.in', '.pyt', '.txt')

DOCTEST_ITEM = re.compile(r'^(gttk|tests|conftest)\.')
COUNTS_LINE = re.compile(
    r'(\d+) tests total \((\d+) unit, (\d+) integration, (\d+) E2E, (\d+) benchmark smoke, '
    r'(\d+) doctests -- (\d+) in `gttk/`\nand (\d+) in `tests/`')
TREE_DIR = re.compile(r'^(?:├──|└──) (\w+)/')
TREE_FILE = re.compile(r'^(?:│   |    )(?:├──|└──) (test_\w+\.py)\s+#.*\((\d+)\)\s*$')


@pytest.fixture(scope='module')
def collected():
    """{node id} for everything pytest collects, from one --collect-only run."""
    result = subprocess.run(
        # -qq: pytest.ini's addopts carry -v, and node ids are printed only below verbosity 0
        [sys.executable, '-m', 'pytest', '--collect-only', '-qq', '-p', 'no:cacheprovider'],
        capture_output=True, text=True, cwd=ROOT, env={**os.environ, 'MPLBACKEND': 'Agg'}, timeout=600)
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return [line for line in result.stdout.splitlines() if '::' in line]


@pytest.fixture(scope='module')
def counts(collected):
    """Per test file, plus the two doctest totals."""
    per_file, doctests_gttk, doctests_tests = Counter(), 0, 0
    for nodeid in collected:
        path, rest = nodeid.split('::', 1)
        if DOCTEST_ITEM.match(rest):
            if path.startswith('gttk/'):
                doctests_gttk += 1
            else:
                doctests_tests += 1
        else:
            per_file[path] += 1
    return per_file, doctests_gttk, doctests_tests


def _in(per_file, directory):
    return sum(n for path, n in per_file.items() if path.startswith(f'tests/{directory}/'))


class TestClaudeMd:

    def test_the_counts(self, collected, counts):
        per_file, doctests_gttk, doctests_tests = counts
        match = COUNTS_LINE.search((ROOT / 'CLAUDE.md').read_text(encoding='utf-8'))
        assert match, 'CLAUDE.md no longer states the counts in the expected form'
        expected = (len(collected), _in(per_file, 'unit'), _in(per_file, 'integration'), _in(per_file, 'e2e'),
                    _in(per_file, 'benchmarks'), doctests_gttk + doctests_tests, doctests_gttk, doctests_tests)
        assert tuple(int(n) for n in match.groups()) == expected, \
            f'CLAUDE.md says {match.groups()}, pytest collects {expected}; paste the second'

    def test_the_validation_test_count(self, counts):
        per_file, _, _ = counts
        expected = sum(n for path, n in per_file.items() if re.match(r'tests/unit/test_validation_\w+\.py', path))
        match = re.search(r'including (\d+) validation tests', (ROOT / 'CLAUDE.md').read_text(encoding='utf-8'))
        assert match and int(match.group(1)) == expected, f'CLAUDE.md validation count should be {expected}'

    def test_the_marker_list(self):
        ini = configparser.ConfigParser()
        ini.read(ROOT / 'pytest.ini', encoding='utf-8')
        markers = {line.split(':')[0].strip() for line in ini['pytest']['markers'].strip().splitlines()}
        line = next(l for l in (ROOT / 'CLAUDE.md').read_text(encoding='utf-8').splitlines()
                    if l.startswith('- `pytest.ini`'))
        assert set(re.findall(r'`(\w+)`', line.split('markers', 1)[1].split(';')[0])) == markers


class TestTestsReadme:

    def test_the_statistics(self, collected, counts):
        per_file, doctests_gttk, doctests_tests = counts
        text = (ROOT / 'tests' / 'README.md').read_text(encoding='utf-8')
        stated = {
            'total': int(re.search(r'\*\*Total Tests\*\*: ([\d,]+)', text).group(1).replace(',', '')),
            'unit': int(re.search(r'Unit Tests: ([\d,]+) tests', text).group(1).replace(',', '')),
            'doctests': tuple(int(n) for n in re.search(r'Doctests: (\d+) \((\d+) in `gttk/`, (\d+) in `tests/`\)', text).groups()),
            'integration': int(re.search(r'Integration Tests: (\d+) tests', text).group(1)),
            'e2e': int(re.search(r'E2E Tests: (\d+) tests', text).group(1)),
            'benchmarks': int(re.search(r'Benchmark smoke tests: (\d+) tests', text).group(1)),
        }
        assert stated == {
            'total': len(collected), 'unit': _in(per_file, 'unit'),
            'doctests': (doctests_gttk + doctests_tests, doctests_gttk, doctests_tests),
            'integration': _in(per_file, 'integration'), 'e2e': _in(per_file, 'e2e'),
            'benchmarks': _in(per_file, 'benchmarks'),
        }

    def test_the_tree_names_every_test_file_with_its_count(self, counts):
        per_file, _, _ = counts
        text = (ROOT / 'tests' / 'README.md').read_text(encoding='utf-8')
        tree = text.split('### Directory Structure', 1)[1].split('```text', 1)[1].split('```', 1)[0]
        stated, directory = {}, None
        for line in tree.splitlines():
            if TREE_DIR.match(line):
                directory = TREE_DIR.match(line).group(1)
            elif TREE_FILE.match(line) and directory:
                name, count = TREE_FILE.match(line).groups()
                stated[f'tests/{directory}/{name}'] = int(count)
        wrong = {path: (stated[path], per_file.get(path)) for path in stated if stated[path] != per_file.get(path)}
        assert wrong == {}, f'tests/README.md tree (stated, collected): {wrong}'
        assert sorted(set(per_file) - set(stated)) == [], 'test files missing from the tree'


class TestBackticks:

    @staticmethod
    def _tokens(doc):
        return set(re.findall(r'`([^`\n]+)`', (ROOT / doc).read_text(encoding='utf-8')))

    @pytest.mark.parametrize('doc', DOCS)
    def test_every_path_exists(self, doc):
        missing = []
        for token in self._tokens(doc):
            t = token.strip()
            if any(c in t for c in ' *<>{}$|,()=\\"\'') or ':' in t or t in OUTPUTS or t.startswith('.'):
                continue  # a bare extension such as `.pyt` names no file
            if t.startswith(TOP_LEVEL):
                if not (ROOT / t.rstrip('/')).exists():
                    missing.append(t)
            elif '/' not in t and t.endswith(SOURCE_EXTENSIONS) and len(t) > len(Path(t).suffix):
                if not any('.git' not in p.parts for p in ROOT.rglob(t)):
                    missing.append(t)
        assert sorted(missing) == [], f'{doc} names files that do not exist: {sorted(missing)}'

    @pytest.mark.parametrize('doc', DOCS)
    def test_every_gttk_dotted_name_resolves(self, doc):
        unresolved = []
        for token in self._tokens(doc):
            if not re.fullmatch(r'gttk(?:\.\w+)+', token):
                continue
            parts, obj, rest = token.split('.'), None, None
            for i in range(len(parts), 0, -1):
                try:
                    obj, rest = importlib.import_module('.'.join(parts[:i])), parts[i:]
                    break
                except ImportError:
                    continue
            try:
                for name in rest or []:
                    obj = getattr(obj, name)
            except AttributeError:
                obj = None
            if obj is None:
                unresolved.append(token)
        assert sorted(unresolved) == []
