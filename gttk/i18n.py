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
Language selection and string catalogs for the ArcGIS Pro toolbox.

ArcGIS Pro reads a Python toolbox's labels, descriptions and parameter names by
*executing* the ``.pyt``, so the toolbox can decide its own language at load time.
Nothing in ``arcpy`` reports which language Pro is displaying, though.  Esri's own
shipped scripts read the registry value Pro writes when the user picks a display
language (``HKCU\\Software\\ESRI\\ARCGISPRO_UILANGID``), and Pro's documented default
is to follow the Windows display language, so that is the chain used here:

1. ``GTTK_LANG`` environment variable -- explicit, for scripts and testing.
2. ``config.toml`` ``[gui] language`` -- ``"auto"`` (default), ``"en"`` or ``"es"``.
3. ``ARCGISPRO_UILANGID`` -- the language chosen in Pro's Options when
   "Match Microsoft Windows" is unchecked.  Its format is undocumented, so
   :func:`normalize_language` accepts anything from ``"es-ES"`` to a numeric LANGID.
4. The Windows display language (``GetUserDefaultUILanguage``).
5. ``LANG``/``locale`` on other platforms, then English.

Python's ``locale`` module is deliberately last: on Windows it reflects the *region
format* (dates and decimals), which Esri documents as independent of the display
language.

Esri's documented alternative -- shipping the toolbox as an installed Python module
with an ``esri/help/<lang>/gp`` tree -- was not used: it requires a wheel install
where the toolbox is delivered by cloning the repository, and it still leaves the
``.pyt`` labels in English.

The catalogs are plain TOML (``resources/i18n/<lang>.toml``) keyed by the English
source string, so a reviewer can read them without tooling.  :func:`activate` re-reads
them on every call, which is what lets a Pro "Refresh" of the toolbox pick up an edit
without restarting Pro.  The help sidecars (``.pyt.xml``) are static files Pro loads by
name, so :func:`sync_sidecars` copies the active language's set next to the toolbox.
"""

from __future__ import annotations

import locale
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

#: Languages with a catalog.  English is the source language and needs no file.
SUPPORTED: tuple[str, ...] = ('en', 'es')
DEFAULT_LANGUAGE = 'en'
CATALOG_DIR = Path(__file__).resolve().parent / 'resources' / 'i18n'

ENV_VAR = 'GTTK_LANG'
CONFIG_KEY = 'gui.language'
#: Where ArcGIS Pro records the display language chosen in Options (Esri's own
#: ``CreateIndoorsDatabase.py`` reads the same value).
PRO_REGISTRY_KEY = r'Software\ESRI'
PRO_REGISTRY_VALUE = 'ARCGISPRO_UILANGID'

#: Directory beside the ``.pyt`` holding one sub-directory of help sidecars per language.
SIDECAR_DIRNAME = 'i18n'
SIDECAR_GLOB = '*.pyt.xml'

# Windows LANGIDs: the low 10 bits are the primary language (0x0A = Spanish for every
# country: es-ES 0x0C0A, es-MX 0x080A, ...).
_PRIMARY_LANGID = {0x09: 'en', 0x0A: 'es'}
_ALIASES = {
    'en': 'en', 'eng': 'en', 'english': 'en',
    'es': 'es', 'spa': 'es', 'esp': 'es', 'spanish': 'es', 'español': 'es', 'espanol': 'es',
}

_language: str = DEFAULT_LANGUAGE
_catalog: dict[str, str] = {}
_catalogs: dict[str, dict[str, str]] = {}
_detection: list[str] = [f'Language: {DEFAULT_LANGUAGE} (source: built-in default)']
_source: str = 'built-in default'
_catalog_notes: list[str] = []


# --- Language codes -----------------------------------------------------------------

def normalize_language(value: Any) -> Optional[str]:
    """Map any spelling of a language to a supported code, or None.

    Accepts BCP-47 tags (``es-MX``), POSIX locales (``es_MX.UTF-8``), the names
    Windows' ``locale.getlocale()`` returns (``Spanish_Mexico``), English names, and
    LANGIDs as ``int``, decimal string or hex string (``3082``, ``0x0C0A``).  Anything
    else -- including ``"auto"`` -- is None, so callers fall through to the next signal.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _from_langid(value)
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None
    if re.fullmatch(r'0x[0-9a-f]+', text):
        return _from_langid(int(text, 16))
    if text.isdigit():
        return _from_langid(int(text))
    token = re.split(r'[-_.@\s]', text, maxsplit=1)[0]
    return _ALIASES.get(token)


def _from_langid(langid: int) -> Optional[str]:
    if langid <= 0:
        return None
    return _PRIMARY_LANGID.get(langid & 0x3FF)


# --- Signals ------------------------------------------------------------------------
# One function per signal, each monkeypatchable in tests.  ``winreg`` and ``ctypes``
# are imported inside the Windows-only readers so no other platform ever touches them.

def _read_env() -> Optional[str]:
    return os.environ.get(ENV_VAR)


def _read_config(reload: bool = False) -> Any:
    from gttk.utils.config_loader import config
    if reload:
        config.reload()
    return config.get(CONFIG_KEY, 'auto')


def _read_pro_registry() -> Any:
    if sys.platform != 'win32':
        return None
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PRO_REGISTRY_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, PRO_REGISTRY_VALUE)
    except OSError:
        return None
    return value


def _read_windows_ui_langid() -> Optional[int]:
    if sys.platform != 'win32':
        return None
    try:
        import ctypes
        return int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
    except (ImportError, AttributeError, OSError, ValueError):
        return None


def _read_posix_locale() -> Optional[str]:
    if sys.platform == 'win32':
        return None
    for name in ('LC_ALL', 'LC_MESSAGES', 'LANG'):
        value = os.environ.get(name)
        if value:
            return value
    try:
        return locale.getlocale()[0]
    except ValueError:
        return None


def _describe(raw: Any) -> str:
    return f'0x{raw:04X}' if isinstance(raw, int) and not isinstance(raw, bool) else repr(raw)


def detect_language(*, reload_config: bool = False) -> str:
    """The language the toolbox should use, per the chain in the module docstring.

    Every signal is consulted inside ``try``: a broken registry read must never stop
    the toolbox from loading.  :func:`explain_detection` reports what was seen.
    ``reload_config`` re-reads ``config.toml`` first, so a Pro "Refresh" honours an
    edit to the file.
    """
    global _detection, _source
    notes: list[str] = []
    winner: Optional[str] = None
    source = 'built-in default'
    signals = (
        (ENV_VAR, _read_env),
        ('config.toml [gui] language', lambda: _read_config(reload_config)),
        (PRO_REGISTRY_VALUE, _read_pro_registry),
        ('Windows display language', _read_windows_ui_langid),
        ('locale', _read_posix_locale),
    )
    for name, reader in signals:
        try:
            raw = reader()
        except Exception as exc:  # noqa: BLE001 - a signal must never break toolbox load
            notes.append(f'{name}: unavailable ({exc.__class__.__name__}: {exc})')
            continue
        if raw is None or raw == '':
            notes.append(f'{name}: not set')
            continue
        if isinstance(raw, str) and raw.strip().lower() == 'auto':
            notes.append(f'{name}: auto')
            continue
        lang = normalize_language(raw)
        notes.append(f'{name}: {_describe(raw)} -> {lang or "no match"}')
        if lang:
            winner, source = lang, name
            break
    winner = winner or DEFAULT_LANGUAGE
    _source = source
    _detection = [f'Language: {winner} (source: {source})', *notes]
    return winner


def explain_detection() -> list[str]:
    """One summary line (``Language: es (source: ...)``) followed by the signals seen."""
    return [*_detection, *_catalog_notes]


def detection() -> tuple[str, str]:
    """The active language and the signal that chose it, for callers that word it themselves."""
    return _language, _source


# --- Catalogs -----------------------------------------------------------------------

def _flatten(table: Mapping[str, Any], out: Optional[dict[str, str]] = None) -> dict[str, str]:
    """Collapse a TOML document to ``{msgid: msgstr}``.

    Tables exist only to organise the file for review; a key must be unique across the
    whole document, so the same English string cannot be translated two ways.
    """
    if out is None:
        out = {}
    for key, value in table.items():
        if isinstance(value, dict):
            _flatten(value, out)
        elif isinstance(value, str):
            if key in out:
                raise ValueError(f'duplicate key {key!r}')
            out[key] = value
    return out


def _load_catalog(code: str) -> dict[str, str]:
    with open(CATALOG_DIR / f'{code}.toml', 'rb') as handle:
        return _flatten(tomllib.load(handle))


def activate(lang: Any) -> str:
    """Make ``lang`` the language :func:`_` translates to; returns what was activated.

    Re-reads every catalog from disk.  A missing or malformed catalog degrades to
    English with a note in :func:`explain_detection` rather than an exception, so the
    toolbox always loads.
    """
    global _language, _catalog, _catalogs, _catalog_notes
    requested = normalize_language(lang) or DEFAULT_LANGUAGE
    catalogs: dict[str, dict[str, str]] = {}
    notes: list[str] = []
    for code in SUPPORTED:
        if code == DEFAULT_LANGUAGE:
            continue
        try:
            catalogs[code] = _load_catalog(code)
        except (OSError, tomllib.TOMLDecodeError, ValueError) as exc:
            catalogs[code] = {}
            notes.append(f'Catalog {code}.toml: {exc.__class__.__name__}: {exc}')
    _catalogs = catalogs
    _language = requested
    _catalog = catalogs.get(requested, {})
    if requested != DEFAULT_LANGUAGE and not _catalog:
        notes.append(f'Catalog {requested}.toml has no entries -- using English')
        _language = DEFAULT_LANGUAGE
    _catalog_notes = notes
    return _language


def current_language() -> str:
    return _language


def _(msgid: Any) -> Any:
    """The active language's rendering of an English source string.

    Unknown strings come back unchanged, so a missing translation shows English
    rather than failing.  Non-strings pass through untouched.
    """
    if not isinstance(msgid, str):
        return msgid
    return _catalog.get(msgid, msgid)


def N_(msgid: str) -> str:
    """Mark a string for translation without translating it yet.

    Used for table entries (picklists) that are translated at display time with
    :func:`_`, so the catalog tests can still find the English source string.
    """
    return msgid


def translations(msgid: str) -> set[str]:
    """Every spelling of ``msgid`` across all loaded catalogs, English included."""
    spellings = {msgid}
    for catalog in _catalogs.values():
        rendered = catalog.get(msgid)
        if rendered:
            spellings.add(rendered)
    return spellings


class Picklist:
    """A dialog ValueList whose labels are translated but whose values are codes.

    ArcGIS validates a choice parameter against ``filter.list`` and hands ``execute``
    the label the user saw.  Keeping the code -> label mapping in one object means
    the ``.pyt`` compares codes, never labels, and :meth:`code` accepts the label in
    *any* language (plus the code itself and legacy labels) so a run saved to History
    or copied as a Python command under one language still resolves under another.
    """

    def __init__(self, entries: Sequence[tuple[Any, str]],
                 aliases: Optional[Mapping[str, Any]] = None):
        self._entries = [(code, msgid) for code, msgid in entries]
        self._aliases = dict(aliases or {})

    def codes(self) -> list:
        return [code for code, _msgid in self._entries]

    def labels(self) -> list[str]:
        """The active language's labels, in dialog order."""
        return [_(msgid) for _code, msgid in self._entries]

    def label(self, code: Any) -> Optional[str]:
        for candidate, msgid in self._entries:
            if candidate == code:
                return _(msgid)
        return None

    def code(self, text: Any) -> Any:
        if text is None:
            return None
        needle = (text.strip() if isinstance(text, str) else str(text)).casefold()
        if not needle:
            return None
        for code, msgid in self._entries:
            if needle == str(code).casefold():
                return code
            if any(needle == spelling.casefold() for spelling in translations(msgid)):
                return code
        for alias, code in self._aliases.items():
            if needle == alias.casefold():
                return code
        return None

    def normalize(self, text: Any) -> Optional[str]:
        """The active language's label for any recognised spelling, or None."""
        code = self.code(text)
        return None if code is None else self.label(code)


# --- Help sidecars ------------------------------------------------------------------

@dataclass
class SidecarSync:
    copied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def sync_sidecars(pyt_path: Path | str, lang: Any) -> SidecarSync:
    """Put the ``lang`` help sidecars (``*.pyt.xml``) next to the toolbox.

    ArcGIS Pro looks for ``<toolbox>.pyt.xml`` and ``<toolbox>.<Tool>.pyt.xml`` beside
    the ``.pyt`` and has no per-language lookup, so the language-specific copies live
    under ``<toolbox dir>/i18n/<lang>/`` and the active set is copied into place when
    the toolbox loads.  Files are only written when their bytes differ, and every
    failure is reported rather than raised: a read-only checkout loses the help
    panel, not the toolbox.
    """
    pyt_path = Path(pyt_path)
    result = SidecarSync()
    root = pyt_path.parent / SIDECAR_DIRNAME
    source = root / (normalize_language(lang) or DEFAULT_LANGUAGE)
    if not source.is_dir():
        source = root / DEFAULT_LANGUAGE
    if not source.is_dir():
        result.warnings.append(f'No help files found under {root}')
        return result
    for src in sorted(source.glob(SIDECAR_GLOB)):
        dest = pyt_path.parent / src.name
        try:
            data = src.read_bytes()
            if dest.exists() and dest.read_bytes() == data:
                continue
            dest.write_bytes(data)
            result.copied.append(src.name)
        except OSError as exc:
            result.warnings.append(f'Could not update help file {src.name}: {exc}')
    return result


if __name__ == '__main__':
    # ``python -m gttk.i18n``: show which signals were seen and which language won,
    # useful on a machine where ArcGIS Pro's language setting is in doubt.
    activate(detect_language(reload_config=True))
    print('\n'.join(explain_detection()))
