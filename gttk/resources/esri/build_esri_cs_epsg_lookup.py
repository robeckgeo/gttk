

"""
Builds a JSON lookup file mapping Esri CRS names to EPSG codes.

This script fetches Coordinate System definitions from Esri's
projection-engine-db-doc GitHub repository, filters for those with EPSG
authority, and creates a simplified JSON file that maps the CRS name
to the corresponding EPSG code (latestWkid).

The output file contains three top-level keys:
- ProjectedCoordinateSystems
- GeographicCoordinateSystems
- VerticalCoordinateSystems

Each key holds an object mapping the `name` of the CRS to its `latestWkid`.
"""

import argparse
import json
import logging
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

# --- Basic logging setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

URL_PREFIX = 'https://raw.githubusercontent.com/Esri/projection-engine-db-doc/master/json/'
CACHE_DIR = Path('resources/esri/cache')
CS_CONFIG = {
    'ProjectedCoordinateSystems': 'pe_list_projcs.json',
    'GeographicCoordinateSystems': 'pe_list_geogcs.json',
    'VerticalCoordinateSystems': 'pe_list_vertcs.json',
}
PACKAGE_URL = 'https://raw.githubusercontent.com/Esri/projection-engine-db-doc/master/json/package.json'

def fetch_json(url, cache_path):
    """
    Fetches JSON from a URL and saves it to a cache file.
    
    Args:
        url (str): The URL to fetch.
        cache_path (Path): The path to save the cached JSON.
        
    Returns:
        dict: The decoded JSON content, or None on failure.
    """
    try:
        with urllib.request.urlopen(url) as response:
            if response.status == 200:
                content = response.read().decode('utf-8')
                
                # Save to cache
                try:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logging.info(f"Cached JSON to {cache_path}")
                except IOError as e:
                    logging.warning(f"Could not write to cache file {cache_path}: {e}")
                
                return json.loads(content)
            else:
                logging.error(f"Failed to fetch {url} (status: {response.status})")
                return None
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        logging.error(f"Failed to fetch or parse {url}: {e}")
        return None

def get_json_data(url, filename, force_online=False):
    """
    Gets JSON data, either from cache or by fetching online.
    """
    cache_path = CACHE_DIR / filename
    data = None

    if force_online:
        logging.info(f"Force online: fetching from {url}...")
        data = fetch_json(url, cache_path)
    else:
        if cache_path.exists():
            logging.info(f"Using cached data from {cache_path}")
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (IOError, json.JSONDecodeError) as e:
                logging.error(f"Could not read from cache file {cache_path}: {e}")
                logging.info("Falling back to online fetch...")
                data = fetch_json(url, cache_path)
        else:
            logging.info(f"Cache not found. Fetching from {url}...")
            data = fetch_json(url, cache_path)
    return data

def build_lookup(force_online=False):
    """
    Fetches and processes the CRS data to build the name-to-code lookup.
    """
    combined_lookup = {}
    package_info = get_json_data(PACKAGE_URL, 'package.json', force_online)
    
    combined_lookup['metadata'] = {
        'title': 'Esri PE Name to EPSG Code Lookup',
        'source_repository': 'https://github.com/Esri/projection-engine-db-doc',
        'version': package_info.get('version', 'unknown') if package_info else 'unknown',
        'compile_date': datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }

    for cs_type, filename in CS_CONFIG.items():
        url = URL_PREFIX + filename
        data = get_json_data(url, filename, force_online)
        
        if not data or cs_type not in data:
            logging.error(f"Could not find '{cs_type}' key in data from {filename}")
            continue

        name_to_wkid = {}
        items = data[cs_type]
        for item in items:
            if item.get('authority') == 'EPSG':
                name = item.get('name')
                latest_wkid = item.get('latestWkid')
                if name and latest_wkid is not None:
                    if name in name_to_wkid:
                        logging.warning(f"Duplicate name '{name}' in {cs_type}. Keeping first occurrence.")
                    else:
                        name_to_wkid[name] = latest_wkid
        
        combined_lookup[cs_type] = name_to_wkid
        logging.info(f"Processed {len(name_to_wkid)} EPSG-based entries for {cs_type}.")

    return combined_lookup

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        '--out',
        dest='out_path',
        type=Path,
        default=Path('resources/esri/esri_cs_epsg_lookup.json'),
        help='Path to write the output JSON lookup file.\n(default: %(default)s)'
    )
    parser.add_argument(
        '--force-online',
        action='store_true',
        help='Force a fresh download from the Esri repository instead of using the cached version.'
    )
    args = parser.parse_args()

    lookup_data = build_lookup(force_online=args.force_online)

    if not any(lookup_data.values()):
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