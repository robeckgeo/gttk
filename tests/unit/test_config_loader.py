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
Where config.toml comes from, and that finding it makes no noise.

The loader used to look three directories above its own file and nowhere else: the
checkout root in a checkout, ``site-packages`` in an installed copy, where no such file
exists. It announced the miss with ``print()`` at import, so every command run from a
wheel began its stdout with ``Warning: config.toml not found``. The order is now an
explicit ``GTTK_CONFIG``, then a checkout's own file, then the packaged default -- and
nothing is read until a value is asked for.
"""

import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest

import gttk.utils.config_loader as cl

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
PACKAGED = ROOT / 'gttk' / 'resources' / 'config.toml'

#: Every key a module reads through ``config.get`` (inventory finding 2.1). The packaged
#: default carries exactly these; the checkout's config.toml may carry more.
LIVE_KEYS = {
    'paths.osgeo4w',
    'gui.language',
    'statistics.max_pixels_fast_path',
    'statistics.block_size',
    'statistics.force_strategy',
    'statistics.cache_alpha_blocks',
    'statistics.cache_transparency_masks',
    'statistics.alpha_binary_threshold',
    'statistics.alpha_near_binary_threshold',
    'statistics.treat_near_binary_as_mask',
}


def _keys(data, prefix=''):
    for name, value in data.items():
        if isinstance(value, dict):
            yield from _keys(value, f'{prefix}{name}.')
        else:
            yield f'{prefix}{name}'


def _in_subprocess(body: str, env=None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, '-c', textwrap.dedent(body)],
                          capture_output=True, text=True, timeout=120, env=env)


class TestResolutionOrder:

    def test_the_environment_variable_wins(self, tmp_path, monkeypatch):
        explicit = tmp_path / 'mine.toml'
        explicit.write_text('[gui]\nlanguage = "es"\n', encoding='utf-8')
        monkeypatch.setenv(cl.CONFIG_ENV_VAR, str(explicit))
        assert cl.resolve_config_path() == explicit

    def test_the_environment_variable_must_name_an_existing_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv(cl.CONFIG_ENV_VAR, str(tmp_path / 'missing.toml'))
        with pytest.raises(FileNotFoundError):
            cl.resolve_config_path()

    def test_a_checkout_reads_the_file_at_its_root(self, monkeypatch):
        monkeypatch.delenv(cl.CONFIG_ENV_VAR, raising=False)
        assert cl.resolve_config_path() == ROOT / 'config.toml'

    def test_an_installed_copy_reads_the_packaged_default(self, tmp_path, monkeypatch):
        """site-packages/gttk/utils/config_loader.py has no pyproject.toml two levels up."""
        monkeypatch.delenv(cl.CONFIG_ENV_VAR, raising=False)
        installed = tmp_path / 'site-packages' / 'gttk' / 'utils' / 'config_loader.py'
        installed.parent.mkdir(parents=True)
        installed.touch()
        assert cl.resolve_config_path(installed) == PACKAGED

    def test_a_stray_config_beside_site_packages_is_not_a_checkout(self, tmp_path, monkeypatch):
        monkeypatch.delenv(cl.CONFIG_ENV_VAR, raising=False)
        installed = tmp_path / 'site-packages' / 'gttk' / 'utils' / 'config_loader.py'
        installed.parent.mkdir(parents=True)
        installed.touch()
        (tmp_path / 'site-packages' / 'config.toml').write_text('[paths]\n', encoding='utf-8')
        assert cl.resolve_config_path(installed) == PACKAGED


class TestLoading:

    def test_nothing_is_read_until_a_value_is_asked_for(self, tmp_path):
        """Import with GTTK_CONFIG naming a missing file: the import must succeed, and
        the first get() must be what fails."""
        import os
        env = dict(os.environ, GTTK_CONFIG=str(tmp_path / 'missing.toml'))
        result = _in_subprocess("""
            import gttk.utils.config_loader as cl
            print("imported", cl.config.loaded)
            try:
                cl.config.get('gui.language')
            except FileNotFoundError as exc:
                print("get raised", type(exc).__name__)
        """, env=env)
        assert result.returncode == 0, result.stderr
        assert result.stdout.split('\n')[:2] == ['imported False', 'get raised FileNotFoundError']

    def test_loading_writes_nothing_to_stdout(self, tmp_path):
        import os
        env = {k: v for k, v in os.environ.items() if k != cl.CONFIG_ENV_VAR}
        result = _in_subprocess("""
            import gttk.utils.config_loader as cl
            cl.config.get('gui.language')
            import gttk.tools.optimize_compression_arc, gttk.tools.test_compression
        """, env=env)
        assert result.returncode == 0, result.stderr
        assert result.stdout == ''

    def test_the_loader_has_no_print_call(self):
        import ast
        tree = ast.parse(Path(cl.__file__).read_text(encoding='utf-8'))
        calls = [node.lineno for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'print']
        assert calls == []

    def test_reload_follows_the_environment(self, tmp_path, monkeypatch):
        explicit = tmp_path / 'mine.toml'
        explicit.write_text('[gui]\nlanguage = "es"\n', encoding='utf-8')
        try:
            monkeypatch.setenv(cl.CONFIG_ENV_VAR, str(explicit))
            cl.config.reload()
            assert cl.config.get('gui.language') == 'es'
            assert cl.config.path == explicit
        finally:
            monkeypatch.delenv(cl.CONFIG_ENV_VAR, raising=False)
            cl.config.reload()
        assert cl.config.path == ROOT / 'config.toml'


class TestPackagedDefault:

    def test_carries_every_key_the_code_reads_and_nothing_else(self):
        with PACKAGED.open('rb') as fh:
            assert set(_keys(tomllib.load(fh))) == LIVE_KEYS

    def test_the_checkout_config_carries_the_same_keys_and_nothing_else(self):
        """config.toml at the checkout root carried eleven keys nothing read -- [api],
        [logging], four [gui] keys and a statistics tolerance -- and the README documented
        [logging] as live."""
        with (ROOT / 'config.toml').open('rb') as fh:
            assert set(_keys(tomllib.load(fh))) == LIVE_KEYS

    def test_agrees_with_the_checkout_config_on_those_keys(self):
        with PACKAGED.open('rb') as fh:
            packaged = tomllib.load(fh)
        with (ROOT / 'config.toml').open('rb') as fh:
            checkout = tomllib.load(fh)
        for key in LIVE_KEYS:
            section, name = key.split('.')
            assert packaged[section][name] == checkout[section][name], key
