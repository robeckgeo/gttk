#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit (GTTK)
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2025, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
Context Variable Management for GTTK.

This module defines global context variables using Python's `contextvars`.
These variables allow for request-scoped or thread-safe state management,
primarily used to pass user-defined settings (like report format or theme)
down through the call stack without explicitly passing them as arguments.
"""
from contextvars import ContextVar
from typing import Optional

# The output format for the reporttelling low-level formatters thefinal output type.
output_format_context: ContextVar[str] = ContextVar('output_format', default='md')

# The type of XML rendering: XML code block ('text') or markdown table ('table').
xml_type_context: ContextVar[Optional[str]] = ContextVar('xml_type', default='table')

# A banner or title to be included in the report header and footer..
banner_context: ContextVar[Optional[str]] = ContextVar('banner', default=None)