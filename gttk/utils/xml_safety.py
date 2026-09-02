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
One parser configuration for every piece of XML that GTTK did not write itself.

GTTK parses XML out of arbitrary GeoTIFFs -- tag 700 (XMP), 42112 (GDAL_METADATA),
50909 (GEO_METADATA), and ``.xml`` and ``.aux.xml`` sidecars -- and did so with lxml's
default parser at nine sites. Whether an external entity such as
``<!ENTITY x SYSTEM "file:///etc/hostname">`` was fetched was then decided by whichever
libxml2 happened to be installed: the one in the development environment refuses, but
that is inherited, not asserted, and the same lxml reads the file the moment a parser is
created with ``load_dtd=True``.

:func:`untrusted_parser` pins the answer. Entities are never substituted -- internal
ones included, which is what a test can observe on every libxml2 -- no DTD is loaded, the
network is never touched, and libxml2's tree-size guard stays on. A site that needs other
options (``recover``, ``remove_blank_text``, ...) passes them through; the four safety
options cannot be overridden.

Example:
    >>> root = parse_untrusted('<!DOCTYPE a [<!ENTITY x "expanded">]><a>&x;</a>')
    >>> root.text is None
    True
"""

from typing import Union

from lxml import etree

#: The options that make a parser safe on untrusted input. Keys, not just values, are
#: fixed: passing one of them to :func:`untrusted_parser` is an error.
SAFE_OPTIONS = {
    'resolve_entities': False,
    'no_network': True,
    'load_dtd': False,
    'huge_tree': False,
}


def untrusted_parser(**options) -> etree.XMLParser:
    """
    An ``XMLParser`` that cannot be talked into reading a file or the network.

    Args:
        options: Any other ``etree.XMLParser`` keyword (``recover``, ``remove_comments``,
            ``remove_blank_text``, ``strip_cdata``, ...).

    Raises:
        ValueError: if one of :data:`SAFE_OPTIONS` is passed, whatever its value.
    """
    overridden = sorted(set(options) & set(SAFE_OPTIONS))
    if overridden:
        raise ValueError(f"{overridden} are fixed for untrusted XML and cannot be passed")
    return etree.XMLParser(**SAFE_OPTIONS, **options)


def parse_untrusted(content: Union[bytes, str], **options) -> etree._Element:
    """
    Parse ``content`` with :func:`untrusted_parser`.

    A ``str`` is encoded as UTF-8 first: lxml refuses a unicode string that carries an
    encoding declaration, and every caller already held its XML as text.
    """
    if isinstance(content, str):
        content = content.encode('utf-8')
    return etree.fromstring(content, untrusted_parser(**options))
