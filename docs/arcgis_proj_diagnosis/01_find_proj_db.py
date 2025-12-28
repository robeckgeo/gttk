#!/usr/bin/env python3
"""
Find all proj.db files in ArcGIS Pro installation.
Run this from ArcGIS Pro's Python environment.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

def find_proj_db_files():
    """Locate all proj.db files in ArcGIS Pro directories."""
    print("=" * 70)
    print("DIAGNOSTIC 1: Locate proj.db files")
    print("=" * 70)
    
    # Potential search locations
    search_paths = []
    
    # Check ARCHOME environment variable
    archome = os.environ.get('ARCHOME')
    if archome:
        search_paths.append(Path(archome))
        print(f"\nARCHOME: {archome}")
    
    # Common installation paths
    common_paths = [
        Path('C:/Program Files/ArcGIS/Pro'),
        Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'ArcGIS' / 'Pro',
    ]
    
    for path in common_paths:
        if path.exists() and path not in search_paths:
            search_paths.append(path)
    
    if not search_paths:
        print("\n[ERROR] Could not find ArcGIS Pro installation directory")
        return []
    
    # Search for proj.db files
    proj_dbs = []
    for base_path in search_paths:
        print(f"\nSearching in: {base_path}")
        try:
            found = list(base_path.rglob('proj.db'))
            proj_dbs.extend(found)
            print(f"  Found {len(found)} proj.db file(s)")
        except Exception as e:
            print(f"  Error searching: {e}")
    
    if not proj_dbs:
        print("\n[ERROR] No proj.db files found in ArcGIS Pro installation")
        return []
    
    # Display information about each found file
    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    
    for i, db_path in enumerate(proj_dbs, 1):
        print(f"\n[{i}] {db_path}")
        try:
            stat = db_path.stat()
            print(f"    Size: {stat.st_size:,} bytes ({stat.st_size / 1024 / 1024:.2f} MB)")
            mod_time = datetime.fromtimestamp(stat.st_mtime)
            print(f"    Modified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as e:
            print(f"    Error reading stats: {e}")
    
    return proj_dbs

if __name__ == "__main__":
    proj_dbs = find_proj_db_files()
    
    if proj_dbs:
        print("\n" + "=" * 70)
        print(f"[OK] SUCCESS: Found {len(proj_dbs)} proj.db file(s)")
        print("\nNext step: Run script 02 to query these databases")
        print("=" * 70)
        sys.exit(0)
    else:
        print("\n" + "=" * 70)
        print("[ERROR] FAILURE: No proj.db files found")
        print("=" * 70)
        sys.exit(1)
