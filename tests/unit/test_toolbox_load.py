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
Load the ArcGIS toolbox the way ArcGIS Pro does -- by executing the ``.pyt`` -- and
build every dialog, with ``arcpy`` replaced by a stub that records what the toolbox
asks of it.

Nothing else in the suite executes the ``.pyt``, so until now a load-time error was
only ever discovered inside ArcGIS Pro.  Each scenario runs in a subprocess because
the toolbox may deliberately drop ``gttk`` from ``sys.modules`` (see
``_prefer_this_checkout``), which must not touch the modules this process holds.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
PYT = ROOT / 'toolbox' / 'GTTK_Toolbox.pyt'

# Executed in a subprocess: a minimal arcpy, then the toolbox, then the scenario.
HARNESS = textwrap.dedent('''
    import importlib.util, json, os, sys, types
    from importlib.machinery import SourceFileLoader

    class _Filter:
        def __init__(self): self.type = None; self.list = []

    class Parameter:
        def __init__(self, displayName=None, name=None, datatype=None, parameterType=None,
                     direction=None, category=None, multiValue=False):
            self.displayName, self.name, self.parameterType = displayName, name, parameterType
            self.category, self.filter, self.value, self.enabled = category, _Filter(), None, True
        @property
        def valueAsText(self):
            return None if self.value is None else str(self.value)
        def setErrorMessage(self, m): pass
        def setWarningMessage(self, m): pass
        def clearMessage(self): pass

    messages = []
    arcpy = types.ModuleType('arcpy')
    arcpy.Parameter = Parameter
    arcpy.AddMessage = lambda m: messages.append(('message', m))
    arcpy.AddWarning = lambda m: messages.append(('warning', m))
    arcpy.AddError = lambda m: messages.append(('error', m))
    sys.modules['arcpy'] = arcpy

    def load(pyt):
        loader = SourceFileLoader('GTTK_Toolbox', pyt)
        spec = importlib.util.spec_from_loader('GTTK_Toolbox', loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    SCENARIO
''')


def run(scenario, env=None):
    script = HARNESS.replace('SCENARIO', textwrap.dedent(scenario))
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                            cwd=ROOT, env={**dict(__import__('os').environ), **(env or {})},
                            timeout=300)
    assert result.returncode == 0, result.stderr[-3000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


class TestToolboxLoads:
    @pytest.mark.parametrize('lang', ['en', 'es'])
    def test_every_dialog_builds_in_each_language(self, lang):
        report = run(f'''
            module = load({str(PYT)!r})
            toolbox = module.Toolbox()
            dialogs = {{}}
            for cls in toolbox.tools:
                tool = cls()
                params = tool.getParameterInfo()
                dialogs[cls.__name__] = [tool.label, len(params),
                                         all(isinstance(p.displayName, str) and p.displayName for p in params)]
            print(json.dumps({{"language": module.LANG, "toolbox": toolbox.label, "dialogs": dialogs,
                               "errors": [m for kind, m in messages if kind == "error"]}}))
        ''', env={'GTTK_LANG': lang})
        assert report['errors'] == []
        assert report['language'] == lang
        assert {name: n for name, (_, n, _) in report['dialogs'].items()} == {
            'OptimizeCompression': 28, 'ReadMetadata': 30, 'CompareCompression': 6,
            'TestCompression': 8, 'ValidateMetadata': 11}
        assert all(ok for _, _, ok in report['dialogs'].values())
        expected_label = 'Optimizar compresión' if lang == 'es' else 'Optimize Compression'
        assert report['dialogs']['OptimizeCompression'][0] == expected_label

    def test_product_type_drives_the_optimize_dialog(self):
        report = run(f'''
            module = load({str(PYT)!r})
            PT, CA = module.PT, module.CA
            tool = module.OptimizeCompression()
            params = tool.getParameterInfo()
            tool.updateParameters(params)
            opening = params[6].value
            params[2].value = module.PRODUCT_TYPE.label(PT.IMAGE.value)
            tool.updateParameters(params)
            imagery = params[6].value
            params[2].value = "Modelo de error"          # a Spanish label in an English session
            params[8].value = "2 - Diferenciación horizontal"
            tool.updateParameters(params)
            print(json.dumps({{"opening": opening, "imagery": imagery,
                               "settled": [params[2].value, params[8].value],
                               "nodata_enabled_for_imagery": params[5].enabled}}))
        ''', env={'GTTK_LANG': 'en'})
        assert report['opening'] == 'DEFLATE'
        assert report['imagery'] == 'JPEG'
        assert report['settled'] == ['Error Model', '2 - Horizontal differencing']


class TestThisCheckoutWins:
    """ArcGIS Pro keeps modules across Refreshes, and a `gttk` installed into the Pro
    conda environment registers an import finder that outranks sys.path.  Neither may
    answer the toolbox's imports."""

    @pytest.fixture
    def other_checkout(self, tmp_path):
        other = tmp_path / 'other' / 'gttk'
        other.mkdir(parents=True)
        (other / '__init__.py').write_text('')
        return other

    def test_a_gttk_loaded_earlier_from_elsewhere_is_released(self, other_checkout):
        report = run(f'''
            import types
            stale = types.ModuleType('gttk')
            stale.__file__ = {str(other_checkout / '__init__.py')!r}
            stale.__path__ = [{str(other_checkout)!r}]
            sys.modules['gttk'] = stale
            sys.modules['gttk.stale_child'] = types.ModuleType('gttk.stale_child')
            module = load({str(PYT)!r})
            print(json.dumps({{"gttk_file": sys.modules['gttk'].__file__,
                               "stale_child_gone": 'gttk.stale_child' not in sys.modules,
                               "notice": [m for kind, m in messages if 'released a gttk' in m]}}))
        ''')
        assert Path(report['gttk_file']).resolve() == (ROOT / 'gttk' / '__init__.py').resolve()
        assert report['stale_child_gone']
        assert len(report['notice']) == 1

    def test_an_installed_gttk_finder_is_unhooked(self, other_checkout):
        report = run(f'''
            import importlib.util
            class InstalledElsewhere:            # what `pip install -e` leaves in sys.meta_path
                @staticmethod
                def find_spec(fullname, path=None, target=None):
                    if fullname == 'gttk':
                        return importlib.util.spec_from_file_location(
                            'gttk', {str(other_checkout / '__init__.py')!r},
                            submodule_search_locations=[{str(other_checkout)!r}])
                    return None
            sys.meta_path.insert(0, InstalledElsewhere)
            module = load({str(PYT)!r})
            print(json.dumps({{"gttk_file": sys.modules['gttk'].__file__,
                               "finder_gone": InstalledElsewhere not in sys.meta_path,
                               "notice": [m for kind, m in messages if 'ignored a gttk installed' in m]}}))
        ''')
        assert Path(report['gttk_file']).resolve() == (ROOT / 'gttk' / '__init__.py').resolve()
        assert report['finder_gone']
        assert len(report['notice']) == 1
