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
Language detection, catalogs and picklists for the ArcGIS Pro toolbox.

None of this can run under arcpy here, so every Windows-only signal (registry,
``GetUserDefaultUILanguage``) is a monkeypatched reader; what is pinned is the
precedence between signals, the lenient parsing of an undocumented registry value,
and the promise that nothing in the chain can raise.
"""

import pytest

import gttk.i18n as i18n
from gttk.i18n import Picklist, normalize_language, sync_sidecars

pytestmark = pytest.mark.unit

_ORIGINAL_READ_CONFIG = i18n._read_config


@pytest.fixture(autouse=True)
def restore_language():
    yield
    i18n.activate('en')


@pytest.fixture
def signals(monkeypatch):
    """Silence every signal, then let a test switch individual ones on."""
    monkeypatch.delenv(i18n.ENV_VAR, raising=False)
    state = {name: None for name in ('_read_env', '_read_config', '_read_pro_registry',
                                     '_read_windows_ui_langid', '_read_posix_locale')}

    def install(**overrides):
        state.update(overrides)
        for name, value in state.items():
            reader = value if callable(value) else (lambda v: lambda *a, **k: v)(value)
            monkeypatch.setattr(i18n, name, reader)

    install()
    return install


@pytest.fixture
def catalog_dir(tmp_path, monkeypatch):
    """A private catalog directory; tests write ``es.toml`` into it."""
    monkeypatch.setattr(i18n, 'CATALOG_DIR', tmp_path)
    return tmp_path


def _write_es(catalog_dir, text):
    (catalog_dir / 'es.toml').write_text(text, encoding='utf-8')


class TestNormalizeLanguage:
    @pytest.mark.parametrize('raw, expected', [
        ('es-ES', 'es'), ('es_MX.UTF-8', 'es'), ('ES', 'es'), ('Spanish_Mexico', 'es'),
        ('spanish', 'es'), ('Español', 'es'),
        (3082, 'es'), ('3082', 'es'), ('0x0C0A', 'es'), (0x080A, 'es'),
        (0x0409, 'en'), ('1033', 'en'), ('en-US', 'en'), ('English_United States', 'en'),
        ('auto', None), ('xx', None), ('fr-FR', None), (0x040C, None),
        ('', None), ('   ', None), (None, None), (True, None), (0, None), (3.5, None),
    ])
    def test_maps_every_spelling_to_a_supported_code(self, raw, expected):
        assert normalize_language(raw) == expected


class TestDetectLanguage:
    def test_env_var_wins_over_everything(self, signals):
        signals(_read_env='es', _read_config='en', _read_pro_registry='en-US',
                _read_windows_ui_langid=0x0409)
        assert i18n.detect_language() == 'es'
        assert i18n.explain_detection()[0] == f'Language: es (source: {i18n.ENV_VAR})'

    def test_config_beats_registry(self, signals):
        signals(_read_config='es', _read_pro_registry='en-US')
        assert i18n.detect_language() == 'es'
        assert i18n.explain_detection()[0] == 'Language: es (source: config.toml [gui] language)'

    def test_config_auto_falls_through(self, signals):
        signals(_read_config='auto', _read_pro_registry='es-ES')
        assert i18n.detect_language() == 'es'
        explanation = i18n.explain_detection()
        assert explanation[0] == f'Language: es (source: {i18n.PRO_REGISTRY_VALUE})'
        assert 'config.toml [gui] language: auto' in explanation

    @pytest.mark.parametrize('registry_value', ['es-ES', 'es', 3082, '3082', '0x0C0A', 0x080A])
    def test_registry_string_and_dword_forms(self, signals, registry_value):
        signals(_read_pro_registry=registry_value, _read_windows_ui_langid=0x0409)
        assert i18n.detect_language() == 'es'

    def test_windows_ui_langid_used_when_registry_absent(self, signals):
        signals(_read_windows_ui_langid=0x080A)
        assert i18n.detect_language() == 'es'
        assert i18n.explain_detection()[0] == 'Language: es (source: Windows display language)'

    def test_unsupported_signal_is_skipped_not_fatal(self, signals):
        signals(_read_pro_registry='fr-FR', _read_windows_ui_langid=0x0409)
        assert i18n.detect_language() == 'en'
        explanation = i18n.explain_detection()
        assert explanation[0] == 'Language: en (source: Windows display language)'
        assert any(line.startswith(i18n.PRO_REGISTRY_VALUE) and line.endswith('no match')
                   for line in explanation)

    def test_signal_exception_is_recorded_and_skipped(self, signals):
        def broken():
            raise RuntimeError('boom')
        signals(_read_pro_registry=broken, _read_windows_ui_langid=0x0C0A)
        assert i18n.detect_language() == 'es'
        assert any('unavailable (RuntimeError: boom)' in line for line in i18n.explain_detection())

    def test_default_is_en_and_explain_names_the_source(self, signals):
        assert i18n.detect_language() == 'en'
        explanation = i18n.explain_detection()
        assert explanation[0] == 'Language: en (source: built-in default)'
        assert len(explanation) == 6  # summary + one line per signal consulted

    def test_detection_names_the_language_and_its_source(self, signals):
        signals(_read_pro_registry='es')
        i18n.activate(i18n.detect_language())
        assert i18n.detection() == ('es', i18n.PRO_REGISTRY_VALUE)

    def test_explain_lists_only_consulted_signals(self, signals):
        signals(_read_env='es')
        i18n.detect_language()
        assert len(i18n.explain_detection()) == 2

    def test_posix_locale_is_the_last_resort(self, signals):
        signals(_read_posix_locale='es_MX.UTF-8')
        assert i18n.detect_language() == 'es'

    def test_reload_config_reaches_the_config_singleton(self, signals, monkeypatch):
        import gttk.utils.config_loader as config_loader

        class FakeConfig:
            reloads = 0

            def reload(self):
                self.reloads += 1

            def get(self, key, default=None):
                assert key == i18n.CONFIG_KEY
                return 'es'

        fake = FakeConfig()
        monkeypatch.setattr(config_loader, 'config', fake)
        signals(_read_config=_ORIGINAL_READ_CONFIG)
        assert i18n.detect_language() == 'es'
        assert fake.reloads == 0
        assert i18n.detect_language(reload_config=True) == 'es'
        assert fake.reloads == 1


class TestActivateAndGettext:
    def test_activate_en_is_identity(self):
        assert i18n.activate('en') == 'en'
        assert i18n._('Product Type') == 'Product Type'
        assert i18n.current_language() == 'en'

    def test_activate_es_translates_a_pinned_entry(self):
        assert i18n.activate('es') == 'es'
        assert i18n._('Product Type') == 'Tipo de producto'

    def test_activate_accepts_any_spelling(self):
        assert i18n.activate('es-MX') == 'es'
        assert i18n.activate(0x0409) == 'en'

    def test_unknown_msgid_falls_back_to_msgid(self):
        i18n.activate('es')
        assert i18n._('no such string') == 'no such string'

    def test_non_string_is_returned_untouched(self):
        i18n.activate('es')
        assert i18n._(None) is None
        assert i18n._(5) == 5

    def test_marker_is_identity(self):
        assert i18n.N_('Product Type') == 'Product Type'

    def test_activate_unknown_language_falls_back_to_en(self):
        assert i18n.activate('fr') == 'en'
        assert i18n.activate(None) == 'en'

    def test_malformed_catalog_falls_back_and_explains(self, catalog_dir):
        _write_es(catalog_dir, 'this is = = not toml\n')
        assert i18n.activate('es') == 'en'
        assert any(line.startswith('Catalog es.toml') for line in i18n.explain_detection())

    def test_missing_catalog_falls_back(self, catalog_dir):
        assert i18n.activate('es') == 'en'
        assert i18n._('Product Type') == 'Product Type'

    def test_duplicate_key_across_tables_is_rejected(self, catalog_dir):
        _write_es(catalog_dir, '[a]\n"Hello" = "Hola"\n[b]\n"Hello" = "Buenas"\n')
        assert i18n.activate('es') == 'en'
        assert any('duplicate key' in line for line in i18n.explain_detection())

    def test_activate_rereads_catalog_each_call(self, catalog_dir):
        _write_es(catalog_dir, '"Hello" = "Hola"\n')
        i18n.activate('es')
        assert i18n._('Hello') == 'Hola'
        _write_es(catalog_dir, '"Hello" = "Buenas"\n')
        i18n.activate('es')
        assert i18n._('Hello') == 'Buenas'

    def test_nested_tables_are_flattened(self, catalog_dir):
        _write_es(catalog_dir, '[toolbox]\n"A" = "a"\n[toolbox.messages]\n"B" = "b"\n')
        i18n.activate('es')
        assert (i18n._('A'), i18n._('B')) == ('a', 'b')

    def test_translations_includes_every_catalog(self):
        i18n.activate('en')
        assert i18n.translations('Product Type') == {'Product Type', 'Tipo de producto'}
        assert i18n.translations('unknown') == {'unknown'}


class TestPicklist:
    @pytest.fixture
    def products(self, catalog_dir):
        _write_es(catalog_dir, '"Digital Elevation Model" = "Modelo digital de elevación"\n'
                               '"Error Model" = "Modelo de error"\n')
        i18n.activate('es')
        return Picklist([('dem', 'Digital Elevation Model'), ('error', 'Error Model')],
                        aliases={'Generic Point-cloud Model': 'error'})

    def test_labels_preserve_order_in_the_active_language(self, products):
        assert products.labels() == ['Modelo digital de elevación', 'Modelo de error']
        assert products.codes() == ['dem', 'error']
        i18n.activate('en')
        assert products.labels() == ['Digital Elevation Model', 'Error Model']

    def test_code_accepts_any_language_regardless_of_the_active_one(self, products):
        assert products.code('Error Model') == 'error'
        assert products.code('Modelo de error') == 'error'
        i18n.activate('en')
        assert products.code('Modelo de error') == 'error'
        assert products.code('error') == 'error'
        assert products.code('DEM') == 'dem'

    def test_code_accepts_a_legacy_alias(self, products):
        assert products.code('Generic Point-cloud Model') == 'error'

    def test_code_is_casefold_and_strips(self, catalog_dir):
        i18n.activate('en')
        picklist = Picklist([('table', 'table'), ('text', 'text')])
        assert picklist.code('Text') == 'text'
        assert picklist.code('  TABLE ') == 'table'

    def test_int_codes_match_their_string_form(self):
        i18n.activate('en')
        predictor = Picklist([(1, '1 - None'), (2, '2 - Horizontal differencing')])
        assert predictor.code(2) == 2
        assert predictor.code('2') == 2
        assert predictor.code('2 - Horizontal differencing') == 2
        assert predictor.label(2) == '2 - Horizontal differencing'

    def test_unknown_or_blank_is_none(self, products):
        assert products.code(None) is None
        assert products.code('') is None
        assert products.code('   ') is None
        assert products.code('Imagery') is None
        assert products.label('image') is None
        assert products.label(None) is None

    def test_normalize_returns_the_active_label(self, products):
        assert products.normalize('Error Model') == 'Modelo de error'
        i18n.activate('en')
        assert products.normalize('Modelo de error') == 'Error Model'
        assert products.normalize('nope') is None


class TestSyncSidecars:
    @pytest.fixture
    def toolbox(self, tmp_path):
        pyt = tmp_path / 'X.pyt'
        pyt.write_text('# toolbox\n')
        for lang in ('en', 'es'):
            folder = tmp_path / 'i18n' / lang
            folder.mkdir(parents=True)
            (folder / 'X.pyt.xml').write_bytes(f'<metadata xml:lang="{lang}"/>'.encode())
            (folder / 'X.Tool.pyt.xml').write_bytes(f'<tool lang="{lang}"/>'.encode())
            (folder / 'notes.txt').write_text('ignored')
        return pyt

    def test_copies_the_active_language_set(self, toolbox):
        result = sync_sidecars(toolbox, 'es')
        assert result.copied == ['X.Tool.pyt.xml', 'X.pyt.xml']
        assert result.warnings == []
        assert (toolbox.parent / 'X.pyt.xml').read_bytes() == b'<metadata xml:lang="es"/>'
        assert not (toolbox.parent / 'notes.txt').exists()

    def test_second_call_copies_nothing(self, toolbox):
        sync_sidecars(toolbox, 'es')
        assert sync_sidecars(toolbox, 'es').copied == []

    def test_overwrites_when_the_language_changes(self, toolbox):
        sync_sidecars(toolbox, 'es')
        result = sync_sidecars(toolbox, 'en')
        assert len(result.copied) == 2
        assert (toolbox.parent / 'X.Tool.pyt.xml').read_bytes() == b'<tool lang="en"/>'

    def test_unknown_language_falls_back_to_english(self, toolbox):
        sync_sidecars(toolbox, 'fr')
        assert (toolbox.parent / 'X.pyt.xml').read_bytes() == b'<metadata xml:lang="en"/>'

    def test_missing_i18n_dir_warns_and_does_not_raise(self, tmp_path):
        pyt = tmp_path / 'X.pyt'
        pyt.write_text('# toolbox\n')
        result = sync_sidecars(pyt, 'es')
        assert result.copied == []
        assert result.warnings and 'No help files found' in result.warnings[0]

    def test_write_failure_is_a_warning(self, toolbox, monkeypatch):
        from pathlib import Path

        def refuse(self, data):
            raise OSError('read-only')
        monkeypatch.setattr(Path, 'write_bytes', refuse)
        result = sync_sidecars(toolbox, 'es')
        assert result.copied == []
        assert len(result.warnings) == 2
        assert 'read-only' in result.warnings[0]
