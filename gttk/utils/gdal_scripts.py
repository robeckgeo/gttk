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
Python scripts that GTTK generates for the OSGeo4W interpreter.

The ArcGIS path cannot rely on the GDAL inside its own process, so it writes small
Python scripts and has ``gdal_runner`` execute them under OSGeo4W's interpreter. Six of
those scripts used to carry file paths in their source with only the backslashes
escaped, so a quotation mark in a filename ended the string literal and the rest of the
name ran as Python.

Two rules hold for every generated script now:

- **Paths travel on argv.** A script reads them from ``sys.argv``; its source never
  contains one.
- **Every other value goes through** :func:`literal`, which renders a Python literal by
  construction: ``repr`` for strings, integers, booleans, ``None`` and lists of those;
  ``float('nan')`` for NaN, which ``repr`` would spell as a bare name; and a refusal for
  infinities, paths and anything else that has no literal form.

Example:
    >>> build_script("DECIMALS = {decimals}\\nNAME = {name}\\n", decimals=2, name='x')
    "DECIMALS = 2\\nNAME = 'x'\\n"
"""

import math
import string
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


def literal(value: Any) -> str:
    """
    Render ``value`` as Python source that evaluates back to it.

    Strings go through ``repr``, so a quotation mark, a backslash, a newline or a
    character outside the BMP cannot end the literal early. NaN becomes
    ``float('nan')``; an infinity is refused because no literal spells it.

    Example:
        >>> literal('x"; import os #')
        '\\'x"; import os #\\''
        >>> literal(float('nan')), literal(True), literal(None), literal([1, 'a'])
        ("float('nan')", 'True', 'None', "[1, 'a']")
    """
    if isinstance(value, np.generic):
        value = value.item()        # repr(np.float64(1.0)) is 'np.float64(1.0)', not a literal
    if value is None or isinstance(value, (bool, int, str)):
        return repr(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "float('nan')"
        if math.isinf(value):
            raise ValueError("an infinite value has no Python literal")
        return repr(value)
    if isinstance(value, (list, tuple)):
        return '[' + ', '.join(literal(item) for item in value) + ']'
    if isinstance(value, Path):
        raise TypeError("paths travel on argv, never inside a generated script")
    raise TypeError(f"{type(value).__name__} has no Python literal")


def _placeholders(template: str) -> set:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def build_script(template: str, **values: Any) -> str:
    """
    Fill ``template``'s ``{name}`` placeholders with literals.

    Every placeholder must be supplied and every value must be used, so a template and
    its builder cannot drift apart silently. Literal braces in the template are doubled,
    as for ``str.format``.
    """
    expected, given = _placeholders(template), set(values)
    if expected != given:
        raise ValueError(f"template placeholders {sorted(expected)} do not match values {sorted(given)}")
    return template.format(**{name: literal(value) for name, value in values.items()})


def write_script(script_path: Path, template: str, **values: Any) -> Path:
    """Build the script and write it as UTF-8, returning the path."""
    script_path = Path(script_path)
    script_path.write_text(build_script(template, **values), encoding='utf-8')
    return script_path


def python_command(script_path: Path, *argv: Any, capture_output: bool = False) -> Dict[str, Any]:
    """
    The gdal_runner payload entry that runs ``script_path`` with ``argv``.

    ``gdal_runner.run_gdal_command`` resolves ``"python"`` against the OSGeo4W bin
    directory and passes everything after the script through unchanged, which is how a
    path reaches the script without ever being part of its source.
    """
    command: List[str] = ["python", str(script_path), *(str(arg) for arg in argv)]
    entry: Dict[str, Any] = {"command": command}
    if capture_output:
        entry["capture_output"] = True
    return entry
