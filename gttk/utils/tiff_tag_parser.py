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
TIFF Tag Parser.

A comprehensive tool for extracting and interpreting TIFF metadata including:
- Basic TIFF tags (image dimensions, bit depth, etc.)
- Advanced tags (compression, photometric interpretation)
- Extended TIFF tags
- Custom tag interpretations

Provides detailed tag information with human-readable interpretations
and proper error handling.
"""

import json
import logging
import math
import re
import tifffile
import unicodedata
import lxml.etree as etree
from copy import deepcopy
from importlib import resources
from osgeo import gdal
from pathlib import Path
from typing import Dict, Any, Optional, Union, List
from gttk.utils.geokey_parser import is_geotiff
from gttk.utils.data_models import TiffTag

def _load_tiff_tag_lookup() -> tuple[Dict[int, str], Dict[int, str]]:
    """
    Load TIFF tag definitions from the JSON lookup file.
    
    Returns:
        Tuple of (TIFF_TAGS dict, EXIF_RELATED_TAGS dict)
    """
    # Path to the JSON lookup file
    lookup_file = resources.files('gttk.resources.tiff').joinpath('tiff_tag_lookup.json')
    
    try:
        with lookup_file.open('r', encoding='utf-8') as f:
            data = json.load(f)
        
        tags_data = data.get('tags', {})
        
        # Build TIFF_TAGS dictionary (all tags)
        tiff_tags = {}
        # Build EXIF_RELATED_TAGS dictionary (only Exif source tags)
        exif_tags = {}
        
        for tag_id_str, tag_info in tags_data.items():
            tag_id = int(tag_id_str)
            tag_name = tag_info.get('name', f'UnknownTag ({tag_id})')
            tag_source = tag_info.get('source', '')
            
            # Add to main TIFF_TAGS dict
            tiff_tags[tag_id] = tag_name
            
            # Add to EXIF_RELATED_TAGS if it's an Exif tag
            if tag_source == 'Exif':
                exif_tags[tag_id] = tag_name
        
        return tiff_tags, exif_tags
        
    except FileNotFoundError:
        logging.warning(f"TIFF tag lookup file not found: {lookup_file}")
        logging.warning("Falling back to minimal tag definitions")
        # Return minimal fallback definitions
        return {
            256: 'ImageWidth',
            257: 'ImageLength',
            258: 'BitsPerSample',
            259: 'Compression',
        }, {}
    except Exception as e:
        logging.error(f"Error loading TIFF tag lookup: {e}")
        return {}, {}

# Load TIFF tag definitions from the Library of Congress-based lookup file
TIFF_TAGS, EXIF_RELATED_TAGS = _load_tiff_tag_lookup()

# Tag value interpretation mappings
TAG_VALUE_MAPPINGS = {
    'subfile_type': {  # Tag 254 (NewSubfileType) - bitmap flags
        0: "Default",
        1: "Reduced resolution version",
        2: "Single page of multi-page",
        4: "Transparency mask",
    },
    'old_subfile': {  # Tag 255 (SubfileType) - legacy values
        1: "Full resolution",
        2: "Reduced resolution",
        3: "Single page of multi-page",
    },
    'fill_order': {  # Tag 266 (FillOrder)
        1: "Most significant bit first",
        2: "Least significant bit first",
    },
    'planar_config': {  # Tag 284 (PlanarConfiguration)
        1: "Separate / Pixel Interleave (RGBRGB...)",
        2: "Planar / Band Interleave (RR...GG...BB...)",
    },
    'predictor': {  # Tag 317 (Predictor)
        1: "None",
        2: "Horizontal differencing",
        3: "Floating point",
        34892: "Horizontal floating point",
        34893: "Horizontal floating point byte swap",
    },
    'compression': {  # Tag 259 (Compression)
        1: "Uncompressed",
        2: "CCITT (1D RLE)",
        3: "T4/Group 3 Fax",
        4: "T6/Group 4 Fax",
        5: "LZW",
        6: "JPEG (old-style)",
        7: "JPEG",
        8: "DEFLATE",
        9: "JBIG B&W",
        10: "JBIG Color",
        99: "JPEG (Leaf MOS)",
        103: "IMPACJ",
        262: "Kodak 262 (unconfirmed)",
        32766: "NeXT (2-bit RLE)",
        32767: "Sony ARW",
        32769: "Packed RAW / NIKON_PACK",
        32770: "Samsung SRW",
        32771: "CCITRLEW (2-byte)",
        32773: "PackBits",
        32809: "ThunderScan (4-bit)",
        32845: "CIE LogLuv (LogL)",
        32867: "Kodak KDC",
        32895: "IT8CTPAD",
        32896: "IT8LW",
        32897: "IT8MP",
        32898: "IT8BL",
        32908: "Pixar 10-bit LZW",
        32909: "Pixar 11-bit ZIP",
        32946: "DEFLATE",  # Not used? (GDAL uses 8)
        32947: "Kodak DCS",
        33003: "Aperio SVS",
        33005: "Aperio SVS",
        34661: "JBIG",
        34676: "SGI Log Luminance RLE (32-bit)",
        34677: "SGI Log Luminance packed (24-bit)",
        34692: "LuraDocument",
        34712: "JPEG 2000",
        34713: "Nikon NEF",
        34715: "JBIG2 (TIFF-FX extension)",
        34718: "MDI",
        34719: "MDI",
        34720: "MDI",
        34887: "LERC",
        34892: "Lossy JPEG",
        34925: "LZMA2",
        50000: "ZSTD",
        50001: "WebP",
        50002: "JPEG XL (old)",
        52546: "JPEG XL",
        65000: "Kodak DCR",
        65535: "Pentax PEF",
    },
    'photometric': {  # Tag 262 (PhotometricInterpretation)
        0: "WhiteIsZero",
        1: "BlackIsZero",
        2: "RGB",
        3: "RGB Palette",
        4: "Transparency Mask",
        5: "CMYK",
        6: "YCbCr",
        8: "CIELab",
        9: 'ICCLab',
        10: 'ITULab',
        32803: 'Color Filter Array',
        32844: 'Pixar LogL',
        32845: 'Pixar LogLuv',
        32892: 'Sequential Color Filter',
        34892: 'Linear Raw',
        51177: 'Depth Map',
        52527: 'Semantic Mask',
    },
    'sample_format': {  # Tag 339 (SampleFormat)
        1: "Unsigned integer",
        2: "Signed integer",
        3: "IEEE floating point",
        4: "Undefined",
        5: "Complex integer",
        6: "Complex IEEE floating point",
    },
    'orientation': {  # Tag 274 (Orientation)
        1: "Top-left (normal)",
        2: "Top-right",
        3: "Bottom-right",
        4: "Bottom-left",
        5: "Left-top",
        6: "Right-top",
        7: "Right-bottom",
        8: "Left-bottom",
    },
    'resolution_unit': {  # Tag 296 (ResolutionUnit)
        1: "None (arbitrary)",
        2: "Inches",
        3: "Centimeters",
    },
    'ycbcr_positioning': {  # Tag 531 (YCbCrPositioning)
        1: "Centered",
        2: "Co-sited",
    },
    'extra_samples': {  # Tag 338 (ExtraSamples)
        0: "Unspecified",
        1: "Associated alpha",
        2: "Unassociated alpha",
    }
}

# Tags that might contain binary data and should be summarized
BINARY_TAGS = {
    273,  # StripOffsets
    279,  # StripByteCounts
    324,  # TileOffsets
    325,  # TileByteCounts
}

# Tags that should show all array values regardless of length
FULL_ARRAY_TAGS = {
    258,    # BitsPerSample - bits per color channel
    277,    # SamplesPerPixel - number of color channels
    284,    # PlanarConfiguration - how channels are stored
    318,    # WhitePoint - white point chromaticity coordinates
    319,    # PrimaryChromaticities - RGB chromaticity coordinates
    338,    # ExtraSamples - alpha channel information
    530,    # YCbCrSubSampling - color subsampling factors
    532,    # ReferenceBlackWhite - color calibration values
    33550,  # ModelPixelScaleTag - pixel scale/resolution
    33922,  # ModelTiepointTag - georeferencing tie points
    34264,  # ModelTransformationTag - georeferencing matrix
    34735,  # GeoKeyDirectoryTag - GeoTIFF keys
}

# Tags known to contain XML content
XML_TAGS = {
    700,   # XMP
    42112, # GDAL_METADATA
    50909,  # GEO_METADATA
}

# Non-image IFD tags that contain dictionary tables
SUB_IFD_TAGS = {
    34665,  # ExifIFDPointer
    34853,  # GPSInfo
    40965,   # InteroperabilityIFDPointer
}

# Tags that are excluded from a "Compact* TIFF Tags" section
EXCLUDED_TAGS = {
    273,   # StripOffsets
    278,   # RowsPerStrip
    279,   # StripByteCounts
    284,   # PlanarConfiguration
    324,   # TileOffsets
    325,   # TileByteCounts
    338,   # ExtraSamples
    33550,  # ModelPixelScaleTag
    33922,  # ModelTiepointTag
    34264,  # ModelTransformationTag
    34735,  # GeoKeyDirectoryTag
    34736,  # GeoDoubleParamsTag
    34737,  # GeoAsciiParamsTag
    }

class TiffTagParser:
    """Parser for extracting and interpreting TIFF metadata."""

    def __init__(self, filename: Union[str, Path], tiff_file: Optional[tifffile.TiffFile] = None):
        """
        Initialize the TIFF parser.

        Args:
            filename: Path to the TIFF file.
            tiff_file: An optional, already opened tifffile.TiffFile object.
        """
        self.filename = Path(filename)
        self._tiff_file_external = tiff_file is not None
        self.tif: tifffile.TiffFile

        if self._tiff_file_external:
            assert tiff_file is not None
            self.tif = tiff_file
        else:
            if not self.filename.exists():
                raise FileNotFoundError(f"File not found: {filename}")
            try:
                self.tif = tifffile.TiffFile(str(self.filename))
            except Exception as e:
                raise RuntimeError(f"Cannot read TIFF structure: {e}")

        if not self.tif or not self.tif.pages or not hasattr(self.tif.pages[0], 'tags'):
            if not self._tiff_file_external:
                self.tif.close()
            raise RuntimeError("No valid TIFF pages or tags found")

    def __enter__(self):
        """Enter the context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context manager and close the file."""
        if not self._tiff_file_external:
            self.close()

    def _sanitize_value(self, value: Any) -> Any:
        """Recursively convert tifffile enums to their integer base values."""
        if hasattr(value, 'name') and 'tifffile' in type(value).__module__:
            return int(value)
        if isinstance(value, list) or isinstance(value, tuple):
            return [self._sanitize_value(v) for v in value]
        return value

    def _parse_lerc_parameters(self, raw_value: Any) -> str:
        """
        Parses LercParameters tag to extract MaxZError.
        The tag can contain a struct or be retrieved via GDAL.
        """
        params: Dict[str, Any] = {}

        # Use GDAL to reliably get LERC parameters
        ds = None
        try:
            ds = gdal.Open(str(self.filename))
            if ds:
                md = ds.GetMetadata('IMAGE_STRUCTURE')
                if md and 'MAX_Z_ERROR' in md:
                    params['MAX_Z_ERROR'] = float(md['MAX_Z_ERROR'])
                if md and 'LERC_VERSION' in md:
                    try:
                        # LERC_VERSION can be a float string, so parse as float then cast to int
                        params['LERC_VERSION'] = int(float(md['LERC_VERSION']))
                    except (ValueError, TypeError):
                        logging.warning(f"Could not parse LERC_VERSION: {md['LERC_VERSION']}")
        except Exception as e:
            logging.warning(f"Could not decode LercParameters using GDAL: {e}")
        finally:
            ds = None
        
        return ', '.join(f"{k}={v}" for k, v in params.items())

    
    def _format_exif_value(self, key: str, value: Any) -> Any:
        """
        Format EXIF values for display.

        Args:
            key: EXIF tag name
            value: EXIF tag value

        Returns:
            Formatted value
        """
        # Handle rational numbers (stored as tuples)
        if isinstance(value, tuple) and len(value) == 2:
            if key in ['ExposureTime']:
                return f"1/{value[1]}" if value[0] == 1 else f"{value[0]}/{value[1]}"
            elif key in ['FNumber', 'ApertureValue']:
                return f"f/{value[0]/value[1]:.1f}"
            elif key in ['FocalLength']:
                return f"{value[0]/value[1]:.1f}mm"
            elif key in ['ShutterSpeedValue', 'BrightnessValue', 'ExposureBiasValue']:
                return f"{value[0]/value[1]:.2f}"
            return f"{value[0]/value[1]:.3f}"

        # Handle arrays of rational numbers
        if isinstance(value, (list, tuple)) and len(value) > 0 and isinstance(value[0], tuple):
            if key == 'LensSpecification':
                # Format as min-max focal length and min-max aperture
                if len(value) >= 4:
                    min_focal = value[0][0]/value[0][1] if value[0][1] != 0 else 0
                    max_focal = value[1][0]/value[1][1] if value[1][1] != 0 else 0
                    min_fstop = value[2][0]/value[2][1] if value[2][1] != 0 else 0
                    max_fstop = value[3][0]/value[3][1] if value[3][1] != 0 else 0
                    return f"{min_focal:.1f}-{max_focal:.1f}mm f/{min_fstop:.1f}-{max_fstop:.1f}"
            return [f"{v[0]/v[1]:.3f}" for v in value]

        # Handle version numbers
        if key == 'ExifVersion' and isinstance(value, bytes):
            try:
                return value.decode('ascii')
            except Exception as e:
                return f"Error decoding {value}: {e}"

        # Handle special enums
        if key == 'ExposureProgram':
            PROGRAMS = {
                0: 'Not defined',
                1: 'Manual',
                2: 'Normal program',
                3: 'Aperture priority',
                4: 'Shutter priority',
                5: 'Creative program',
                6: 'Action program',
                7: 'Portrait mode',
                8: 'Landscape mode'
            }
            if isinstance(value, int):
                return f"{value} ({PROGRAMS.get(value, 'Unknown')})"
            return value

        if key == 'MeteringMode':
            MODES = {
                0: 'Unknown',
                1: 'Average',
                2: 'Center-weighted average',
                3: 'Spot',
                4: 'Multi-spot',
                5: 'Pattern',
                6: 'Partial',
                255: 'Other'
            }
            if isinstance(value, int):
                return f"{value} ({MODES.get(value, 'Unknown')})"
            return value

        if key == 'Flash':
            flash_info = []
            if isinstance(value, int) and value & 0x1:
                flash_info.append('Flash fired')
            else:
                flash_info.append('Flash did not fire')
            return f"{value} ({', '.join(flash_info)})"

        # Return other values as-is
        return value

    def _get_tag_interpretation(self, tag_code: int, fundamental_value: Any) -> Optional[str]:
        """
        Get human-readable interpretation for specific tag values.

        Args:
            tag_code: TIFF tag code
            fundamental_value: The fundamental (often numeric) tag value or list of values.

        Returns:
            Human-readable interpretation if available
        """
        value_to_interpret = fundamental_value
        is_list = isinstance(fundamental_value, list)

        if tag_code == 254:  # NewSubfileType - bitmap flags
            if not isinstance(value_to_interpret, int):
                return None
            flags = []
            for bit, desc in TAG_VALUE_MAPPINGS['subfile_type'].items():
                if value_to_interpret & bit: # Bitwise AND
                    flags.append(desc)
            return ' + '.join(flags) if flags else TAG_VALUE_MAPPINGS['subfile_type'].get(0) # Default if 0
        elif tag_code == 338:  # ExtraSamples
            if is_list:
                interpretations = [TAG_VALUE_MAPPINGS['extra_samples'].get(v, 'Unknown') for v in value_to_interpret if isinstance(v, int)]
                return ' + '.join(interpretations) if interpretations else None
            elif isinstance(value_to_interpret, int):
                return TAG_VALUE_MAPPINGS['extra_samples'].get(value_to_interpret)
            return None
        
        # For other tags that expect a single integer value for interpretation
        if is_list: # If it's a list but not handled above (like ExtraSamples), cannot interpret directly
            return None
        
        if not isinstance(value_to_interpret, int):
             # Try to convert if it's a string representing an int
            if isinstance(value_to_interpret, str) and value_to_interpret.isdigit():
                try:
                    value_to_interpret = int(value_to_interpret)
                except ValueError:
                    return None # Not a valid integer string
            else:
                return None # Not an integer or valid integer string

        # Now value_to_interpret is guaranteed to be an int for these cases
        if tag_code == 255:
            return TAG_VALUE_MAPPINGS['old_subfile'].get(value_to_interpret)
        elif tag_code == 259:
            return TAG_VALUE_MAPPINGS['compression'].get(value_to_interpret)
        elif tag_code == 262:
            return TAG_VALUE_MAPPINGS['photometric'].get(value_to_interpret)
        elif tag_code == 266:
            return TAG_VALUE_MAPPINGS['fill_order'].get(value_to_interpret)
        elif tag_code == 274:
            return TAG_VALUE_MAPPINGS['orientation'].get(value_to_interpret)
        elif tag_code == 284:
            return TAG_VALUE_MAPPINGS['planar_config'].get(value_to_interpret)
        elif tag_code == 296:
            return TAG_VALUE_MAPPINGS['resolution_unit'].get(value_to_interpret)
        elif tag_code == 317:
            return TAG_VALUE_MAPPINGS['predictor'].get(value_to_interpret)
        elif tag_code == 339:
            return TAG_VALUE_MAPPINGS['sample_format'].get(value_to_interpret)
        elif tag_code == 531:
            return TAG_VALUE_MAPPINGS['ycbcr_positioning'].get(value_to_interpret)
        
        return None

    def get_exif_tags(self, page_index: int = 0) -> Dict[int, Dict[str, Any]]:
        """
        Extract EXIF-specific tags from a TIFF page.

        Args:
            page_index: Index of the TIFF page to process (default: 0)

        Returns:
            Dictionary mapping tag codes to tag information for EXIF tags
        """
        if page_index >= len(self.tif.pages):
            raise IndexError(f"Page index {page_index} out of range")

        exif_tags = {}
        page = self.tif.pages[page_index]

        # Only proceed if ExifIFD tag exists
        tags = page.tags  # type: ignore
        exif_ifd_tag = tags.get(34665)  # ExifIFD tag
        if not exif_ifd_tag:
            return {}

        # Parse ExifIFD data
        if isinstance(exif_ifd_tag.value, dict):
            for key, value in exif_ifd_tag.value.items():
                try:
                    # Convert numeric keys to strings for consistent handling
                    exif_tags[str(key)] = {
                        'name': str(key),
                        'value': self._format_exif_value(key, value)
                    }
                except Exception:
                    continue

        # Try to read InterColourProfile if it exists
        icc_tag = tags.get(34675)  # InterColourProfile tag
        if icc_tag:
            try:
                import io
                import PIL.ImageCms
                icc_data = io.BytesIO(icc_tag.value)
                icc_profile = PIL.ImageCms.ImageCmsProfile(icc_data)
                profile_info = PIL.ImageCms.getProfileInfo(icc_profile)
                
                exif_tags[34675] = {
                    'name': 'InterColourProfile',
                    'value': {
                        'manufacturer': getattr(profile_info, 'manufacturer', ''),
                        'model': getattr(profile_info, 'model', ''),
                        'description': getattr(profile_info, 'description', ''),
                        'copyright': getattr(profile_info, 'copyright', '')
                    }
                }
            except Exception:
                pass

        # Look for other common EXIF-related tags
        for tag in tags.values():
            if tag.code in EXIF_RELATED_TAGS:
                try:
                    tag_value = self._format_exif_value(EXIF_RELATED_TAGS[tag.code], tag.value)
                    exif_tags[tag.code] = {
                        'name': EXIF_RELATED_TAGS[tag.code],
                        'value': tag_value
                    }
                except Exception:
                    continue

        return exif_tags

    def get_tags(self, page_index: int = 0, tag_scope: str = 'complete') -> List[TiffTag]:
        """
        Extract and interpret all TIFF tags from a specific page.
        """
        if page_index >= len(self.tif.pages):
            raise IndexError(f"Page index {page_index} out of range")

        tags_info: List[TiffTag] = []
        page = self.tif.pages[page_index]

        # Handle both TIFFPage and TIFFFrame - only TIFFPage has tags
        try:
            page_tags = page.tags  # type: ignore
        except AttributeError:
            # TIFFFrame doesn't have tags, so return empty list
            return []

        for tag in page_tags:
            if tag_scope == 'compact' and tag.code in EXCLUDED_TAGS:
                continue
            tag_name = TIFF_TAGS.get(tag.code, f'UnknownTag ({tag.code})')
            try:
                raw_value = deepcopy(tag.value)
                fundamental_value: Any
                interpretation: Optional[str] = None

                # Handle special cases first
                if tag.code == 347:  # JPEGTables
                    if isinstance(raw_value, bytes):
                        fundamental_value = _parse_jpeg_tables(raw_value)
                    else:
                        fundamental_value = str(raw_value)
                elif tag.code == 50674:  # LercParameters
                    parsed_params = self._parse_lerc_parameters(raw_value)
                    fundamental_value = parsed_params
                elif tag.code == 339 and isinstance(raw_value, (list, tuple)): # SampleFormat list
                    sanitized_list = self._sanitize_value(raw_value)
                    formatted_string = ", ".join(f"{v}: {TAG_VALUE_MAPPINGS['sample_format'].get(v, 'Unknown')}" for v in sanitized_list)
                    fundamental_value = f"[{formatted_string}]"
                elif tag.code in SUB_IFD_TAGS and isinstance(raw_value, dict):
                    # Special handling for Exif, GPS, and Interoperability IFDs
                    formatted_items = []
                    for key, val in raw_value.items():
                        # Sanitize and format each value in the dictionary
                        formatted_val = self._format_exif_value(key, val)
                        if isinstance(formatted_val, bytes):
                            formatted_val = formatted_val.decode('utf-8', errors='replace')
                        formatted_items.append(f"{key}: {formatted_val}")
                    fundamental_value = "<br>".join(formatted_items)
                else:
                    # Generic processing for all other tags
                    fundamental_value = self._sanitize_value(raw_value)
                    if isinstance(fundamental_value, bytes):
                        # Decode using utf-8 with replacement characters for errors, then remove null bytes.
                        # This preserves valid text while safely handling invalid byte sequences.
                        decoded_str = fundamental_value.decode('utf-8', errors='replace').replace('\x00', '')
                        fundamental_value = _sanitize_string(decoded_str)
                    elif isinstance(fundamental_value, str):
                        # For existing strings, just ensure nulls and control chars are handled.
                        fundamental_value = _sanitize_string(fundamental_value.replace('\x00', ''))

                    interpretation = self._get_tag_interpretation(tag.code, fundamental_value)

                # For XML tags, verify structure and note if it's malformed
                if tag.code in XML_TAGS and isinstance(fundamental_value, str):
                    if not _is_xml(fundamental_value):
                        interpretation = "Malformed XML (treated as text)"
                    else:
                        try:
                            # Attempt to parse with lxml to confirm it's well-formed
                            etree.fromstring(fundamental_value.encode('utf-8'))
                        except etree.XMLSyntaxError:
                            interpretation = "Malformed XML (treated as text)"

                # Special handling for GDAL_NODATA (42113)
                if tag.code == 42113:
                    nodata_str = str(fundamental_value).strip()
                    ds = None
                    try:
                        ds = gdal.Open(str(self.filename))
                        if ds and ds.RasterCount > 0:
                            nodata_values = []
                            for i in range(1, ds.RasterCount + 1):
                                band = ds.GetRasterBand(i)
                                if not band:
                                    nodata_values.append(None)
                                    continue
                                band_nodata = band.GetNoDataValue()
                                if band_nodata is None:
                                    nodata_values.append(None)
                                    continue
                                data_type = band.DataType
                                is_float_data = data_type in [gdal.GDT_Float32, gdal.GDT_Float64]
                                if is_float_data and math.isnan(band_nodata):
                                    nodata_values.append('NaN')
                                else:
                                    nodata_values.append(band_nodata)
                            if ds.RasterCount == 1:
                                fundamental_value = nodata_values[0] if nodata_values else None
                            else:
                                fundamental_value = nodata_values
                        else:
                            fundamental_value = nodata_str
                    except Exception as e:
                        logging.warning(f"Could not parse GDAL_NODATA using GDAL: {e}")
                        fundamental_value = nodata_str
                    finally:
                        ds = None

                # Apply truncation for BINARY_TAGS before storing in TiffTag
                display_value = fundamental_value
                if tag.code in BINARY_TAGS and isinstance(fundamental_value, list):
                    if len(fundamental_value) <= 8:
                        display_value = f"{', '.join(map(str, fundamental_value))}"
                    else:
                        display_value = f"[{', '.join(map(str, fundamental_value[:5]))}, ...] ({len(fundamental_value)} total)"

                tags_info.append(TiffTag(
                    code=tag.code,
                    name=tag_name,
                    value=display_value,
                    interpretation=interpretation,
                ))
            except Exception as e:
                logging.warning(f"Skipping tag {tag.code} ({tag_name}) due to parsing error: {e}")
                continue

        if not tags_info:
            raise RuntimeError("No valid TIFF tags found")

        return sorted(tags_info, key=lambda t: t.code)


    def is_geotiff(self) -> bool:
        """
         Check if the file is a GeoTIFF using the centralized utility function in utils/geokey_parser.py.

        Returns:
            bool: True if the file appears to be a GeoTIFF
        """
        return is_geotiff(self.filename)

    def close(self):
        """Close the TIFF file."""
        if hasattr(self, 'tif') and self.tif:
            self.tif.close()

def _sanitize_string(input_str: str) -> str:
    """
    Remove non-printable characters from a string, including null bytes.
    Allows common whitespace characters like newline, tab, and carriage return.
    """
    if not isinstance(input_str, str):
        return input_str

    # Remove null bytes first, as they can cause issues with other operations
    sanitized = input_str.replace('\x00', '')

    # Filter out non-printable characters, allowing common whitespace
    # Allow all characters except for specific control characters (excluding whitespace)
    # This will preserve the '�' (U+FFFD) replacement character.
    sanitized = "".join(ch for ch in sanitized if unicodedata.category(ch)[0] != 'C' or ch.isspace())

    # Collapse multiple spaces into a single space
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()

    # Remove leading/trailing whitespace
    sanitized = re.sub(r'> ', '>', sanitized).strip()
    
    return sanitized

def _is_xml(value: str) -> bool:
    """Check if a string is likely XML."""
    if not isinstance(value, str):
        return False
    # Simple check for XML structure; doesn't need to be perfect
    return value.strip().startswith('<') and value.strip().endswith('>')

def _parse_jpeg_tables(data: bytes) -> str:
    """Parses JPEGTables data to identify markers."""
    if not isinstance(data, bytes):
        return str(data)
    
    summary = []
    # Check for DQT (Define Quantization Table) marker
    if b'\xFF\xDB' in data:
        summary.append("DQT")
    # Check for DHT (Define Huffman Table) marker
    if b'\xFF\xC4' in data:
        summary.append("DHT")
    
    if summary:
        return f"Contains {' and '.join(summary)} tables ({len(data)} bytes)"
    return f"binary data ({len(data)} bytes)"


