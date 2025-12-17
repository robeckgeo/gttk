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
Builds a JSON lookup file mapping TIFF tag IDs to their names and sources.

This script fetches TIFF tag definitions from the Library of Congress (LOC)
website, parses the HTML tables, and creates a structured JSON file. This
external lookup file makes the TIFF tag parser more robust and easier to
maintain.

The output file will contain a dictionary mapping tag IDs to objects with
'name' and 'source' attributes.
"""

import argparse
import json
import logging
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser

URL = "https://www.loc.gov/preservation/digital/formats/content/tiff_tags.shtml"
OUTPUT_FILENAME = "tiff_tag_lookup.json"
CACHE_FILENAME = "loc_tiff_tags.shtml"

# --- Basic logging setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class TiffTagParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_tbody = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.current_cell_data = []
        self.tags = {}
        
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.in_table = True
        elif self.in_table and tag == 'tbody':
            self.in_tbody = True
        elif self.in_tbody and tag == 'tr':
            self.in_row = True
            self.current_row = []
        elif self.in_row and tag == 'td':
            self.in_cell = True
            self.current_cell_data = []
    
    def handle_endtag(self, tag):
        if tag == 'table':
            self.in_table = False
        elif tag == 'tbody':
            self.in_tbody = False
        elif tag == 'td':
            self.in_cell = False
            # Join all text collected for this cell and add to row
            cell_text = ''.join(self.current_cell_data).strip()
            self.current_row.append(cell_text)
            self.current_cell_data = []
        elif tag == 'tr':
            self.in_row = False
            # Process the complete row
            # Table has 6 columns: Dec, Hex, Name, Description, Source, Note
            if len(self.current_row) >= 5:
                try:
                    tag_id_str = self.current_row[0]
                    # hex_id = self.current_row[1]  # We don't need this
                    tag_name = self.current_row[2]
                    tag_desc = self.current_row[3]
                    tag_source = self.current_row[4]
                    
                    if tag_id_str.isdigit():
                        tag_id = int(tag_id_str)
                        
                        # Normalize source
                        source_lower = tag_source.lower()
                        if 'baseline' in source_lower:
                            source = 'Baseline'
                        elif 'extended' in source_lower:
                            source = 'Extended'
                        elif 'exif' in source_lower:
                            source = 'Exif'
                        elif 'private' in source_lower:
                            source = 'Private'
                        else:
                            source = tag_source
                        
                        tag_spec = ''
                        if 'tiff/it' in source_lower:
                            tag_spec = 'TIFF/IT'
                        elif 'tiff/ep' in source_lower:
                            tag_spec = 'TIFF/EP'
                        elif 'dng' in source_lower:
                            tag_spec = 'DNG'
                        elif 'hd photo' in source_lower:
                            tag_spec = 'HD Photo'
                        elif tag_id in [33550, 33922, 34264, 34735, 34736, 34737]:
                            tag_spec = 'GeoTIFF'
                        else:
                            tag_spec = 'TIFF 6.0'

                        self.tags[tag_id] = {
                            "name": normalize_text(tag_name),
                            "description": normalize_text(tag_desc),
                            "source": source,
                            "spec": tag_spec
                        }
                except (IndexError, ValueError):
                    pass  # Skip malformed rows
            self.current_row = []
    
    def handle_data(self, data):
        if self.in_cell:
            # Accumulate text data for current cell
            self.current_cell_data.append(data)


def normalize_text(text):
    """Clean up whitespace and special characters in text."""
    import re
    # Replace various whitespace characters with single space
    text = re.sub(r'[\r\n\t]+', ' ', text)
    # Collapse multiple spaces into single space
    text = re.sub(r'\s+', ' ', text)
    # Strip leading/trailing whitespace
    return text.strip()

def fetch_html(url, cache_path):
    """
    Fetches HTML from a URL and saves it to a cache file.
    
    Args:
        url (str): The URL to fetch.
        cache_path (Path): The path to save the cached HTML.
        
    Returns:
        str: The decoded HTML content, or None on failure.
    """
    try:
        with urllib.request.urlopen(url) as response:
            if response.status == 200:
                content = response.read()
                charset = response.headers.get_content_charset() or 'latin-1'
                html_content = content.decode(charset)
                
                # Save to cache
                try:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(cache_path, 'w', encoding=charset) as f:
                        f.write(html_content)
                    logging.info(f"Cached HTML to {cache_path}")
                except IOError as e:
                    logging.warning(f"Could not write to cache file {cache_path}: {e}")
                
                return html_content
            else:
                logging.error(f"Failed to fetch {url} (status: {response.status})")
                return None
    except urllib.error.URLError as e:
        logging.error(f"Failed to fetch {url} ({e.reason})")
        return None

def parse_tags(html_content):
    """Parses the HTML to extract TIFF tag information."""
    if not html_content:
        return None
    parser = TiffTagParser()
    parser.feed(html_content)
    return parser.tags

def apply_manual_corrections(tags):
    """
    Apply manual corrections for tags that have incorrect or incomplete
    information from the Library of Congress website.
    """
    corrections = {
        700: {
            "name": "XMLPacket"  # LOC incorrectly lists as 'XMP'
        },
        50674: {
            "name": "LercParameters",
            "description": "Stores Limited Error Raster Compression (LERC) version and the Maximum Z Error value.",
            "source": "Private",
            "spec": "GeoTIFF"
        },
        50909: {
            "name": "GEO_METADATA",
            "description": "ISO 19115/19139 XML metadata in compliance with DGIWG 108 (GeoTIFF Profile). Uses Byte type to support UTF-8 encoding.",
            "source": "Private",
            "spec": "GeoTIFF"
        }
        # Add more corrections as needed
    }
    
    for tag_id, corrections_dict in corrections.items():
        if tag_id in tags:
            # Update existing tag
            tags[tag_id].update(corrections_dict)
            logging.info(f"Applied manual correction for tag {tag_id}: {corrections_dict.get('name')}")
        else:
            # Add new tag that doesn't exist
            tags[tag_id] = corrections_dict
            logging.info(f"Added missing tag {tag_id}: {corrections_dict.get('name')}")
    
    return tags

def build_lookup(force_online=False):
    """
    Fetches and processes the TIFF tag data to build the lookup file.
    
    Args:
        force_online (bool): If True, forces a fresh download from the URL.
                             Otherwise, uses the cached version if available.
    """
    cache_path = Path(f'resources/tiff/cache/{CACHE_FILENAME}')
    html = None

    if force_online:
        logging.info(f"Force online: fetching TIFF tags from {URL}...")
        html = fetch_html(URL, cache_path)
    else:
        if cache_path.exists():
            logging.info(f"Using cached HTML from {cache_path}")
            try:
                with open(cache_path, 'r', encoding='latin-1') as f:
                    html = f.read()
            except IOError as e:
                logging.error(f"Could not read from cache file {cache_path}: {e}")
                logging.info("Falling back to online fetch...")
                html = fetch_html(URL, cache_path)
        else:
            logging.info(f"Cache not found. Fetching TIFF tags from {URL}...")
            html = fetch_html(URL, cache_path)

    if not html:
        logging.error("No HTML content available to parse.")
        return None

    tags = parse_tags(html)

    if tags is None:
        logging.error("Could not parse HTML content.")
        return None
    
    logging.info(f"Parsed {len(tags)} tags from LOC website")

    # Apply manual corrections/additions
    tags = apply_manual_corrections(tags)
        
    logging.info(f"Final tag count: {len(tags)} tags")

    lookup = {
        'metadata': {
            'title': 'TIFF Tag Lookup',
            'source_url': URL,
            'compile_date': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        },
        'tags': tags
    }
    return lookup

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        '--out',
        dest='out_path',
        type=Path,
        default=Path(f'resources/tiff/{OUTPUT_FILENAME}'),
        help='Path to write the output JSON lookup file.\n(default: %(default)s)'
    )
    parser.add_argument(
        '--force-online',
        action='store_true',
        help='Force a fresh download from the LOC website instead of using the cached version.'
    )
    args = parser.parse_args()

    lookup_data = build_lookup(force_online=args.force_online)

    if not lookup_data or not lookup_data.get('tags'):
        logging.error("Failed to build any lookup data. Aborting.")
        sys.exit(1)

    try:
        logging.info(f"Writing lookup file to {args.out_path}...")
        args.out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(args.out_path, 'w') as f:
            json.dump(lookup_data, f, indent=2)
        logging.info("Done.")
    except IOError as e:
        logging.error(f"Could not write to output file {args.out_path}: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()