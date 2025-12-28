#!/usr/bin/env python3
"""
Test if setting PROJ_LIB before GDAL import fixes EPSG:4979 recognition.
Run this from ArcGIS Pro's Python environment.

IMPORTANT: This MUST be run as a fresh Python process - do not import GDAL
before running this script!
"""
import os
import sys
from pathlib import Path

def test_proj_lib_override():
    """Test PROJ_LIB override before GDAL import."""
    print("=" * 70)
    print("DIAGNOSTIC 5: Test PROJ_LIB Override")
    print("=" * 70)
    
    # Find proj.db in ArcGIS Pro installation
    print("\n[1] Locating ArcGIS Pro's proj.db")
    print("-" * 70)
    
    archome = os.environ.get('ARCHOME', 'C:/Program Files/ArcGIS/Pro')
    potential_paths = [
        Path(archome) / 'bin',
        Path(archome) / 'Resources' / 'pedata',
    ]
    
    proj_db_dir = None
    for path in potential_paths:
        proj_db = path / 'proj.db'
        if proj_db.exists():
            proj_db_dir = path
            print(f"[OK] Found: {proj_db}")
            print(f"  Size: {proj_db.stat().st_size:,} bytes")
            break
    
    if not proj_db_dir:
        print("[ERROR] ERROR: Cannot find proj.db in ArcGIS Pro installation")
        return False
    
    # Check current PROJ_LIB
    print("\n[2] Current PROJ_LIB Setting")
    print("-" * 70)
    current_proj_lib = os.environ.get('PROJ_LIB')
    if current_proj_lib:
        print(f"[WARNING] WARNING: PROJ_LIB is already set to: {current_proj_lib}")
        print("  This test may not be accurate - restart Python to clear it")
    else:
        print("PROJ_LIB is not currently set (expected)")
    
    # Set PROJ_LIB before importing GDAL
    print("\n[3] Setting PROJ_LIB and Importing GDAL")
    print("-" * 70)
    os.environ['PROJ_LIB'] = str(proj_db_dir)
    print(f"Set PROJ_LIB = {os.environ['PROJ_LIB']}")
    
    # NOW import GDAL
    try:
        from osgeo import osr
        print("[OK] Successfully imported osgeo.osr")
    except ImportError as e:
        print(f"[ERROR] ERROR: Cannot import osgeo.osr: {e}")
        return False
    
    # Check what PROJ sees
    print("\n[4] PROJ Search Paths")
    print("-" * 70)
    try:
        search_paths = osr.GetPROJSearchPaths()
        if search_paths:
            for i, path in enumerate(search_paths, 1):
                matches = str(proj_db_dir) in path
                marker = " [OK] (contains proj.db)" if matches else ""
                print(f"  [{i}] {path}{marker}")
        else:
            print("[WARNING] WARNING: No search paths returned")
    except Exception as e:
        print(f"[WARNING] WARNING: Error getting search paths: {e}")
    
    # Test EPSG:4979
    print("\n[5] Testing EPSG:4979 Recognition")
    print("-" * 70)
    
    srs = osr.SpatialReference()
    result = srs.ImportFromEPSG(4979)
    
    if result == 0:
        print("[OK] SUCCESS: EPSG:4979 is now recognized!")
        print(f"  Authority: {srs.GetAuthorityName(None)}")
        print(f"  Code: {srs.GetAuthorityCode(None)}")
        print(f"  Name: {srs.GetAttrValue('GEOGCS')}")
        success = True
    else:
        print(f"[ERROR] FAILURE: EPSG:4979 still not recognized (error code {result})")
        success = False
    
    # Diagnosis
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    
    if success:
        print("\n[OK] Setting PROJ_LIB FIXES the issue!")
        print("\nROOT CAUSE: Configuration Problem")
        print("  - ArcGIS Pro does not set PROJ_LIB in Python environment")
        print("  - GDAL cannot find proj.db without this variable")
        print("  - The database itself is fine and contains EPSG:4979")
        print("\nRECOMMENDATION:")
        print("  Esri should set PROJ_LIB in the Python environment startup")
        print("  (e.g., in sitecustomize.py or environment activation scripts)")
        print("\nSEVERITY: Medium")
        print("  - Easy fix for Esri (add one environment variable)")
        print("  - Workaround exists for users (set PROJ_LIB manually)")
    else:
        print("\n[ERROR] Setting PROJ_LIB DOES NOT fix the issue!")
        print("\nROOT CAUSE: Deeper Problem")
        print("  Possible causes:")
        print("  1. GDAL compiled with hardcoded or wrong PROJ paths")
        print("  2. proj.db schema incompatible with GDAL version")
        print("  3. Missing grid files or additional resources")
        print("  4. PROJ library version mismatch")
        print("\nRECOMMENDATION:")
        print("  Esri needs to investigate GDAL/PROJ compilation and integration")
        print("\nSEVERITY: High")
        print("  - Requires code changes or recompilation")
        print("  - No simple workaround for users")
    
    return success

def main():
    # Warn if GDAL already imported
    if 'osgeo.osr' in sys.modules or 'osgeo.gdal' in sys.modules:
        print("\n" + "=" * 70)
        print("[WARNING] WARNING: GDAL/OSR already imported!")
        print("=" * 70)
        print("This test must be run in a fresh Python process.")
        print("PROJ_LIB must be set BEFORE the first GDAL import.")
        print("\nRestart Python and run this script again.")
        print("=" * 70)
        sys.exit(1)
    
    success = test_proj_lib_override()
    
    print("\n" + "=" * 70)
    print(f"{'[OK] Test complete' if success else '[ERROR] Test failed'}")
    print("=" * 70)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
