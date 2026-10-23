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
GEO_METADATA Tag Writer for GeoTIFFs.

Embeds an XML metadata record (ISO 19115/19139, FGDC, an agency profile) in a GeoTIFF's
GEO_METADATA tag (50909). The record is pretty-printed first, for the people who read
``gdalinfo`` output or a QGIS layer's properties, and the formatting is checked to have
changed nothing: the formatted record and the file canonicalize (C14N) to the same bytes,
or lxml's own indentation of the same document is used instead. The text is embedded as
UTF-8 with a declaration that says so, whatever the file's encoding was.

A record that is already in a file's GEO_METADATA tag when GTTK optimizes it does not come
through here. It travels with the source metadata and reaches the output byte for byte.

Functions:
    prepare_xml_for_gdal: The text to embed for a record on disk.
    write_geo_metadata: Embed a record in an open dataset's GEO_METADATA tag.
"""
import logging
from pathlib import Path
from typing import Optional, Union

import lxml.etree as etree
from osgeo import gdal

from gttk.utils.exceptions import ProcessingStepFailedError
from gttk.utils.xml_formatter import (MAX_XML_SIDECAR_BYTES, canonical_xml, decode_xml_bytes,
                                      pretty_print_xml, read_xml_with_encoding_detection)
from gttk.utils.xml_safety import parse_untrusted

logger = logging.getLogger(__name__)


def prepare_xml_for_gdal(xml_path: Union[str, Path]) -> str:
    """
    Read the record at ``xml_path`` and return the text to embed in GEO_METADATA.

    The record is parsed (well-formed, and safely: no entity resolution, no DTD, no
    network), decoded with the encoding its declaration names, and pretty-printed with
    :func:`gttk.utils.xml_formatter.pretty_print_xml`. The result is kept only if it
    canonicalizes to the same bytes as the file; otherwise lxml's plain indentation of the
    document is used and a warning says so. Either way only whitespace between elements
    changes; every value, attribute, comment and processing instruction is as it was.

    Raises:
        ProcessingStepFailedError: the file is missing, unreadable, larger than
            :data:`gttk.utils.xml_formatter.MAX_XML_SIDECAR_BYTES`, or not well-formed XML.

    Example:
        >>> _ = Path('record.xml').write_text('<?xml version="1.0"?><a x="1"><b>text</b></a>', encoding='utf-8')
        >>> print(prepare_xml_for_gdal('record.xml').split('?>', 1)[1])
        <BLANKLINE>
        <a x="1">
          <b>text</b>
        </a>
        <BLANKLINE>
    """
    xml_path = Path(xml_path)
    if not xml_path.is_file():
        raise ProcessingStepFailedError(f"GEO_METADATA record not found: {xml_path}")
    xml_bytes = read_xml_with_encoding_detection(xml_path)
    if xml_bytes is None:
        raise ProcessingStepFailedError(
            f"Could not read the GEO_METADATA record {xml_path}: unreadable, or larger than "
            f"{MAX_XML_SIDECAR_BYTES:,} bytes.")
    try:
        root = parse_untrusted(xml_bytes, remove_blank_text=True, strip_cdata=False)
    except etree.XMLSyntaxError as e:
        raise ProcessingStepFailedError(f"The GEO_METADATA record {xml_path} is not well-formed XML: {e}") from e

    text = _decode(xml_bytes, root.getroottree().docinfo.encoding)
    original = canonical_xml(xml_bytes)
    formatted = pretty_print_xml(text) if original is not None else None
    if formatted is None or canonical_xml(formatted) != original:
        if original is None:
            logger.debug(f"{xml_path.name} cannot be canonicalized; embedding lxml's own indentation of it.")
        else:
            logger.warning(f"Pretty-printing changed the record {xml_path.name}; embedding lxml's own indentation of it instead.")
        formatted = etree.tostring(root.getroottree(), encoding='utf-8', pretty_print=True,
                                   xml_declaration=True).decode('utf-8')
        if original is not None and canonical_xml(formatted) != original:  # pragma: no cover
            logger.warning(f"Re-indenting {xml_path.name} changed it too; embedding the record as it is.")
            formatted = text
    return formatted


def _decode(xml_bytes: bytes, declared_encoding: Optional[str]) -> str:
    """The record as text, decoded as its declaration says, without a byte order mark."""
    for encoding in (declared_encoding, 'utf-8'):
        if not encoding:
            continue
        try:
            return xml_bytes.decode(encoding).lstrip('\ufeff')
        except (LookupError, UnicodeDecodeError):
            continue
    return (decode_xml_bytes(xml_bytes) or '').lstrip('\ufeff')


def write_geo_metadata(ds: Optional[gdal.Dataset], xml_path: Union[str, Path]) -> str:
    """
    Embed the record at ``xml_path`` in ``ds``'s GEO_METADATA tag (50909).

    Args:
        ds: An open GDAL dataset, in update mode.
        xml_path: The XML record to embed.

    Returns:
        The text that was written.

    Raises:
        ProcessingStepFailedError: no dataset, an unusable record (see
            :func:`prepare_xml_for_gdal`), or GDAL refusing the write.
    """
    if ds is None:
        raise ProcessingStepFailedError("No open GDAL dataset to write GEO_METADATA to.")
    xml_content = prepare_xml_for_gdal(xml_path)
    try:
        ds.SetMetadataItem('GEO_METADATA', xml_content)
        ds.FlushCache()
    except RuntimeError as e:
        raise ProcessingStepFailedError(f"GDAL could not write GEO_METADATA from {xml_path}: {e}") from e
    logger.info(f"Wrote GEO_METADATA ({len(xml_content.encode('utf-8')):,} bytes) from {Path(xml_path).name}.")
    return xml_content
