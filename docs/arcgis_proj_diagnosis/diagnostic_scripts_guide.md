# ArcGIS Pro PROJ Diagnostic Scripts

This guide provides executable Python scripts to diagnose why ArcGIS Pro's GDAL fails to recognize modern EPSG codes. Run these scripts **in order** from ArcGIS Pro's Python environment.

## Setup Instructions

1. Open ArcGIS Pro
2. Open the Python Command Prompt (Start Menu → ArcGIS → Python Command Prompt)
3. Navigate to this directory: `cd c:\code\GeoTiffToolKit\plans`
4. Run each script in sequence

---

## Script 1: Find proj.db Files

**Purpose**: Locate all proj.db files in the ArcGIS Pro installation.

**Filename**: `01_find_proj_db.py`

```python
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
        print("\n❌ ERROR: Could not find ArcGIS Pro installation directory")
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
        print("\n❌ ERROR: No proj.db files found in ArcGIS Pro installation")
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
        print(f"✓ SUCCESS: Found {len(proj_dbs)} proj.db file(s)")
        print("\nNext step: Run script 02 to query these databases")
        print("=" * 70)
        sys.exit(0)
    else:
        print("\n" + "=" * 70)
        print("❌ FAILURE: No proj.db files found")
        print("=" * 70)
        sys.exit(1)
```

**Run**: `python 01_find_proj_db.py > results_01.txt`

---

## Script 2: Query proj.db for EPSG:4979

**Purpose**: Check if problematic EPSG codes exist in ArcGIS Pro's database.

**Filename**: `02_query_proj_db.py`

```python
#!/usr/bin/env python3
"""
Query proj.db files for EPSG:4979 and related CRS.
Run this from ArcGIS Pro's Python environment.
"""
import os
import sys
import sqlite3
from pathlib import Path

def query_proj_db(db_path):
    """Query a proj.db file for key information."""
    print(f"\n{'=' * 70}")
    print(f"Analyzing: {db_path}")
    print('=' * 70)
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # Check database metadata
        print("\n[1] Database Metadata")
        try:
            cursor.execute("SELECT key, value FROM metadata WHERE key LIKE 'PROJ%'")
            metadata = cursor.fetchall()
            if metadata:
                for key, value in metadata:
                    print(f"    {key}: {value}")
            else:
                print("    No PROJ metadata found")
        except sqlite3.Error as e:
            print(f"    Error: {e}")
        
        # Check for EPSG:4979 (WGS 84 3D)
        print("\n[2] EPSG:4979 (WGS 84 3D Geographic)")
        try:
            cursor.execute("""
                SELECT auth_name, code, name, type, deprecated 
                FROM crs_view 
                WHERE auth_name = 'EPSG' AND code = '4979'
            """)
            result = cursor.fetchone()
            if result:
                print(f"    ✓ FOUND: {result[2]}")
                print(f"      Type: {result[3]}")
                print(f"      Deprecated: {'Yes' if result[4] else 'No'}")
            else:
                print("    ❌ NOT FOUND")
        except sqlite3.Error as e:
            print(f"    Error: {e}")
        
        # Count CRS by type
        print("\n[3] CRS Counts by Type")
        try:
            cursor.execute("""
                SELECT type, COUNT(*) as count 
                FROM crs_view 
                WHERE auth_name = 'EPSG'
                GROUP BY type 
                ORDER BY count DESC
            """)
            results = cursor.fetchall()
            if results:
                for crs_type, count in results:
                    print(f"    {crs_type}: {count:,}")
            else:
                print("    No CRS found")
        except sqlite3.Error as e:
            print(f"    Error: {e}")
        
        # Check for other problematic 3D CRS
        print("\n[4] Sample 3D Geographic CRS")
        try:
            cursor.execute("""
                SELECT code, name 
                FROM crs_view 
                WHERE auth_name = 'EPSG' 
                  AND type = 'geographic 3D'
                ORDER BY CAST(code AS INTEGER)
                LIMIT 10
            """)
            results = cursor.fetchall()
            if results:
                for code, name in results:
                    print(f"    EPSG:{code} - {name}")
            else:
                print("    ❌ No 3D geographic CRS found")
        except sqlite3.Error as e:
            print(f"    Error: {e}")
        
        # Check for compound CRS
        print("\n[5] Sample Compound CRS")
        try:
            cursor.execute("""
                SELECT code, name 
                FROM crs_view 
                WHERE auth_name = 'EPSG' 
                  AND type = 'compound'
                ORDER BY CAST(code AS INTEGER)
                LIMIT 10
            """)
            results = cursor.fetchall()
            if results:
                for code, name in results:
                    print(f"    EPSG:{code} - {name}")
            else:
                print("    ⚠ No compound CRS found")
        except sqlite3.Error as e:
            print(f"    Error: {e}")
        
        # Get total EPSG count
        print("\n[6] Total EPSG CRS Count")
        try:
            cursor.execute("SELECT COUNT(*) FROM crs_view WHERE auth_name = 'EPSG'")
            count = cursor.fetchone()[0]
            print(f"    Total: {count:,} EPSG codes")
        except sqlite3.Error as e:
            print(f"    Error: {e}")
        
        conn.close()
        
    except sqlite3.Error as e:
        print(f"\n❌ Database error: {e}")
        return False
    
    return True

def main():
    print("=" * 70)
    print("DIAGNOSTIC 2: Query proj.db for EPSG codes")
    print("=" * 70)
    
    # Get proj.db paths from environment or common locations
    proj_dbs = []
    
    archome = os.environ.get('ARCHOME')
    if archome:
        potential_paths = [
            Path(archome) / 'bin' / 'proj.db',
            Path(archome) / 'Resources' / 'pedata' / 'proj.db',
        ]
        proj_dbs.extend([p for p in potential_paths if p.exists()])
    
    if not proj_dbs:
        # Search manually
        base = Path('C:/Program Files/ArcGIS/Pro')
        if base.exists():
            proj_dbs.extend(base.rglob('proj.db'))
    
    if not proj_dbs:
        print("\n❌ ERROR: No proj.db files found")
        print("   Run script 01 first to locate the database")
        sys.exit(1)
    
    success = True
    for db_path in proj_dbs:
        if not query_proj_db(db_path):
            success = False
    
    if success:
        print("\n" + "=" * 70)
        print("✓ Analysis complete - check results above")
        print("=" * 70)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
```

**Run**: `python 02_query_proj_db.py > results_02.txt`

---

## Script 3: Check GDAL Environment

**Purpose**: Document environment variables and GDAL configuration.

**Filename**: `03_check_environment.py`

```python
#!/usr/bin/env python3
"""
Check GDAL/PROJ environment configuration in ArcGIS Pro.
Run this from ArcGIS Pro's Python environment.
"""
import os
import sys

def check_environment():
    """Check environment variables before and after GDAL import."""
    print("=" * 70)
    print("DIAGNOSTIC 3: GDAL/PROJ Environment")
    print("=" * 70)
    
    # Key environment variables to check
    env_vars = [
        'PROJ_LIB',
        'PROJ_DATA',
        'PROJ_NETWORK',
        'GDAL_DATA',
        'GDAL_DRIVER_PATH',
        'GDAL_CONFIG_FILE',
        'ARCHOME',
        'PYTHONHOME',
    ]
    
    print("\n[1] Environment Variables (Before GDAL Import)")
    print("-" * 70)
    for var in env_vars:
        value = os.environ.get(var, '<NOT SET>')
        print(f"{var:20} = {value}")
    
    # Show PATH directories
    print("\n[2] PATH Directories (First 5)")
    print("-" * 70)
    path_dirs = os.environ.get('PATH', '').split(';')
    for i, path_dir in enumerate(path_dirs[:5], 1):
        print(f"  [{i}] {path_dir}")
    print(f"  ... ({len(path_dirs)} total directories)")
    
    # Now import GDAL and check configuration
    print("\n[3] GDAL Configuration")
    print("-" * 70)
    try:
        from osgeo import gdal, osr
        
        print(f"GDAL Version: {gdal.__version__}")
        print(f"GDAL Build: {gdal.VersionInfo('BUILD_INFO')}")
        
        # Check GDAL config options
        gdal_data = gdal.GetConfigOption('GDAL_DATA')
        print(f"GDAL_DATA: {gdal_data if gdal_data else '<Not Set>'}")
        
    except ImportError as e:
        print(f"❌ ERROR: Cannot import GDAL: {e}")
        return False
    
    # Check PROJ configuration
    print("\n[4] PROJ Configuration")
    print("-" * 70)
    try:
        search_paths = osr.GetPROJSearchPaths()
        if search_paths:
            print("PROJ Search Paths:")
            for i, path in enumerate(search_paths, 1):
                print(f"  [{i}] {path}")
        else:
            print("⚠ WARNING: No PROJ search paths returned")
        
        # Try to get PROJ version
        try:
            srs = osr.SpatialReference()
            # This may not work in all GDAL versions
            print(f"\nPROJ Info: {osr.GetPROJVersionMicro()}.{osr.GetPROJVersionMinor()}.{osr.GetPROJVersionMajor()}")
        except:
            pass
            
    except Exception as e:
        print(f"⚠ WARNING: Error checking PROJ config: {e}")
    
    return True

def main():
    success = check_environment()
    
    print("\n" + "=" * 70)
    if success:
        print("✓ Environment check complete")
        print("\nKey Questions:")
        print("  - Is PROJ_LIB set? If not, GDAL may not find proj.db")
        print("  - Do PROJ search paths include the directory with proj.db?")
    else:
        print("❌ Environment check failed")
    print("=" * 70)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
```

**Run**: `python 03_check_environment.py > results_03.txt`

---

## Script 4: Test EPSG:4979 Recognition

**Purpose**: Test whether ArcGIS Pro's GDAL can recognize EPSG:4979.

**Filename**: `04_test_epsg_recognition.py`

```python
#!/usr/bin/env python3
"""
Test EPSG:4979 recognition in ArcGIS Pro's GDAL.
Run this from ArcGIS Pro's Python environment.
"""
import os
import sys

def test_epsg_recognition():
    """Test if GDAL can recognize EPSG:4979."""
    print("=" * 70)
    print("DIAGNOSTIC 4: Test EPSG:4979 Recognition")
    print("=" * 70)
    
    try:
        from osgeo import osr
    except ImportError as e:
        print(f"\n❌ ERROR: Cannot import osgeo.osr: {e}")
        return False
    
    # Test EPSG codes
    test_codes = [
        (4326, "WGS 84 2D", "Should work - common 2D CRS"),
        (4979, "WGS 84 3D", "PROBLEMATIC - 3D geographic CRS"),
        (3857, "Web Mercator", "Should work - common projected CRS"),
        (4936, "ETRS89 3D", "Likely to fail - another 3D CRS"),
    ]
    
    results = []
    
    for code, name, note in test_codes:
        print(f"\n[TEST] EPSG:{code} - {name}")
        print(f"       ({note})")
        print("-" * 70)
        
        srs = osr.SpatialReference()
        result = srs.ImportFromEPSG(code)
        
        if result == 0:  # Success
            print(f"✓ SUCCESS: ImportFromEPSG({code}) returned 0")
            print(f"  Authority: {srs.GetAuthorityName(None)}")
            print(f"  Code: {srs.GetAuthorityCode(None)}")
            print(f"  Name: {srs.GetAttrValue('GEOGCS') or srs.GetAttrValue('PROJCS')}")
            
            # Validate the SRS
            validation = srs.Validate()
            print(f"  Validation: {'OK' if validation == 0 else f'FAILED (code {validation})'}")
            
            results.append((code, True, "Recognized"))
        else:
            print(f"❌ FAILURE: ImportFromEPSG({code}) returned {result}")
            print(f"  GDAL could not recognize this EPSG code")
            results.append((code, False, f"Error code {result}"))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    success_count = sum(1 for _, success, _ in results if success)
    print(f"\nPassed: {success_count}/{len(test_codes)}")
    
    for code, success, message in results:
        status = "✓" if success else "❌"
        print(f"  {status} EPSG:{code}: {message}")
    
    # Diagnosis
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    
    if results[1][1]:  # EPSG:4979 succeeded
        print("\n✓ EPSG:4979 is recognized!")
        print("  Your ArcGIS Pro GDAL is working correctly.")
        print("  The issue may be specific to certain files or operations.")
    else:
        print("\n❌ EPSG:4979 is NOT recognized!")
        print("  This confirms the bug:")
        print("  - ArcGIS Pro's GDAL cannot import modern 3D geographic CRS")
        print("  - Likely cause: PROJ_LIB not set or proj.db not accessible")
        print("\n  Next step: Run script 05 to test PROJ_LIB override")
    
    return results

def main():
    results = test_epsg_recognition()
    
    if not results:
        sys.exit(1)
    
    # Exit with error if EPSG:4979 failed
    epsg_4979_success = results[1][1] if len(results) > 1 else False
    sys.exit(0 if epsg_4979_success else 1)

if __name__ == "__main__":
    main()
```

**Run**: `python 04_test_epsg_recognition.py > results_04.txt`

---

## Script 5: Test PROJ_LIB Override

**Purpose**: Determine if setting PROJ_LIB before GDAL import fixes the issue.

**Filename**: `05_test_proj_lib_override.py`

```python
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
            print(f"✓ Found: {proj_db}")
            print(f"  Size: {proj_db.stat().st_size:,} bytes")
            break
    
    if not proj_db_dir:
        print("❌ ERROR: Cannot find proj.db in ArcGIS Pro installation")
        return False
    
    # Check current PROJ_LIB
    print("\n[2] Current PROJ_LIB Setting")
    print("-" * 70)
    current_proj_lib = os.environ.get('PROJ_LIB')
    if current_proj_lib:
        print(f"⚠ WARNING: PROJ_LIB is already set to: {current_proj_lib}")
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
        print("✓ Successfully imported osgeo.osr")
    except ImportError as e:
        print(f"❌ ERROR: Cannot import osgeo.osr: {e}")
        return False
    
    # Check what PROJ sees
    print("\n[4] PROJ Search Paths")
    print("-" * 70)
    try:
        search_paths = osr.GetPROJSearchPaths()
        if search_paths:
            for i, path in enumerate(search_paths, 1):
                matches = str(proj_db_dir) in path
                marker = " ✓ (contains proj.db)" if matches else ""
                print(f"  [{i}] {path}{marker}")
        else:
            print("⚠ WARNING: No search paths returned")
    except Exception as e:
        print(f"⚠ WARNING: Error getting search paths: {e}")
    
    # Test EPSG:4979
    print("\n[5] Testing EPSG:4979 Recognition")
    print("-" * 70)
    
    srs = osr.SpatialReference()
    result = srs.ImportFromEPSG(4979)
    
    if result == 0:
        print("✓ SUCCESS: EPSG:4979 is now recognized!")
        print(f"  Authority: {srs.GetAuthorityName(None)}")
        print(f"  Code: {srs.GetAuthorityCode(None)}")
        print(f"  Name: {srs.GetAttrValue('GEOGCS')}")
        success = True
    else:
        print(f"❌ FAILURE: EPSG:4979 still not recognized (error code {result})")
        success = False
    
    # Diagnosis
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    
    if success:
        print("\n✓ Setting PROJ_LIB FIXES the issue!")
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
        print("\n❌ Setting PROJ_LIB DOES NOT fix the issue!")
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
        print("⚠ WARNING: GDAL/OSR already imported!")
        print("=" * 70)
        print("This test must be run in a fresh Python process.")
        print("PROJ_LIB must be set BEFORE the first GDAL import.")
        print("\nRestart Python and run this script again.")
        print("=" * 70)
        sys.exit(1)
    
    success = test_proj_lib_override()
    
    print("\n" + "=" * 70)
    print(f"{'✓ Test complete' if success else '❌ Test failed'}")
    print("=" * 70)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
```

**Run**: `python 05_test_proj_lib_override.py > results_05.txt`

**IMPORTANT**: This script must be run in a **fresh Python session** where GDAL has not yet been imported.

---

## Script 6: Compare Database Contents

**Purpose**: Compare ArcGIS Pro's proj.db with OSGeo4W's version.

**Filename**: `06_compare_databases.py`

```python
#!/usr/bin/env python3
"""
Compare ArcGIS Pro and OSGeo4W proj.db files.
Run this from any Python environment with sqlite3.
"""
import sys
import sqlite3
from pathlib import Path

def analyze_database(db_path):
    """Extract statistics from a proj.db file."""
    info = {
        'path': str(db_path),
        'exists': db_path.exists(),
        'size_mb': 0,
        'proj_version': None,
        'total_crs': 0,
        'epsg_crs': 0,
        'has_epsg_4979': False,
        'geographic_2d': 0,
        'geographic_3d': 0,
        'projected': 0,
        'compound': 0,
        'vertical': 0,
    }
    
    if not db_path.exists():
        return info
    
    info['size_mb'] = round(db_path.stat().st_size / 1024 / 1024, 2)
    
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        
        # PROJ version
        try:
            cursor.execute("SELECT value FROM metadata WHERE key = 'PROJ.VERSION'")
            result = cursor.fetchone()
            info['proj_version'] = result[0] if result else 'Unknown'
        except:
            pass
        
        # Total CRS
        cursor.execute("SELECT COUNT(*) FROM crs_view")
        info['total_crs'] = cursor.fetchone()[0]
        
        # EPSG CRS
        cursor.execute("SELECT COUNT(*) FROM crs_view WHERE auth_name = 'EPSG'")
        info['epsg_crs'] = cursor.fetchone()[0]
        
        # EPSG:4979
        cursor.execute("SELECT COUNT(*) FROM crs_view WHERE auth_name = 'EPSG' AND code = '4979'")
        info['has_epsg_4979'] = cursor.fetchone()[0] > 0
        
        # By type
        type_queries = [
            ('geographic_2d', "type = 'geographic 2D'"),
            ('geographic_3d', "type = 'geographic 3D'"),
            ('projected', "type = 'projected'"),
            ('compound', "type = 'compound'"),
            ('vertical', "type = 'vertical'"),
        ]
        
        for key, condition in type_queries:
            cursor.execute(f"SELECT COUNT(*) FROM crs_view WHERE auth_name = 'EPSG' AND {condition}")
            info[key] = cursor.fetchone()[0]
        
        conn.close()
        
    except Exception as e:
        print(f"  Error analyzing {db_path}: {e}")
    
    return info

def main():
    print("=" * 70)
    print("DIAGNOSTIC 6: Compare proj.db Databases")
    print("=" * 70)
    
    # Locate databases
    arcgis_paths = [
        Path('C:/Program Files/ArcGIS/Pro/bin/proj.db'),
        Path('C:/Program Files/ArcGIS/Pro/Resources/pedata/proj.db'),
    ]
    
    osgeo4w_path = Path('C:/OSGeo4W/share/proj/proj.db')
    
    # Find ArcGIS Pro database
    arcgis_db = None
    for path in arcgis_paths:
        if path.exists():
            arcgis_db = path
            break
    
    if not arcgis_db:
        print("\n❌ ERROR: Cannot find ArcGIS Pro's proj.db")
        return False
    
    if not osgeo4w_path.exists():
        print("\n⚠ WARNING: Cannot find OSGeo4W's proj.db at", osgeo4w_path)
        print("  Comparison will be limited to ArcGIS Pro database only")
        osgeo4w_path = None
    
    # Analyze databases
    print("\n[1] ArcGIS Pro Database")
    print("-" * 70)
    arcgis_info = analyze_database(arcgis_db)
    
    for key, value in arcgis_info.items():
        if key != 'path':
            print(f"  {key:20}: {value}")
    
    if osgeo4w_path:
        print("\n[2] OSGeo4W Database")
        print("-" * 70)
        osgeo4w_info = analyze_database(osgeo4w_path)
        
        for key, value in osgeo4w_info.items():
            if key != 'path':
                print(f"  {key:20}: {value}")
        
        # Comparison
        print("\n[3] Comparison")
        print("-" * 70)
        
        metrics = [
            ('size_mb', 'Database Size (MB)'),
            ('proj_version', 'PROJ Version'),
            ('total_crs', 'Total CRS'),
            ('epsg_crs', 'EPSG CRS'),
            ('geographic_3d', '3D Geographic'),
            ('compound', 'Compound CRS'),
        ]
        
        print(f"\n{'Metric':<25} {'ArcGIS Pro':<15} {'OSGeo4W':<15} {'Diff':<15}")
        print("-" * 70)
        
        for key, label in metrics:
            arc_val = arcgis_info[key]
            osg_val = osgeo4w_info[key]
            
            if isinstance(arc_val, (int, float)) and isinstance(osg_val, (int, float)):
                diff = arc_val - osg_val
                diff_str = f"{diff:+,}" if diff != 0 else "same"
            else:
                diff_str = "different" if arc_val != osg_val else "same"
            
            print(f"{label:<25} {str(arc_val):<15} {str(osg_val):<15} {diff_str:<15}")
        
        # EPSG:4979 check
        print("\n[4] EPSG:4979 Status")
        print("-" * 70)
        print(f"  ArcGIS Pro: {'✓ Present' if arcgis_info['has_epsg_4979'] else '❌ Missing'}")
        print(f"  OSGeo4W:    {'✓ Present' if osgeo4w_info['has_epsg_4979'] else '❌ Missing'}")
    
    # Diagnosis
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    
    if not arcgis_info['has_epsg_4979']:
        print("\n❌ EPSG:4979 is MISSING from ArcGIS Pro's proj.db!")
        print("\nROOT CAUSE: Incomplete Database")
        print("  ArcGIS Pro ships an outdated or stripped proj.db")
        print("\nRECOMMENDATION:")
        print("  Esri should update proj.db to include modern EPSG codes")
    elif osgeo4w_path and arcgis_info['geographic_3d'] < osgeo4w_info['geographic_3d'] * 0.5:
        print("\n⚠ WARNING: ArcGIS Pro has significantly fewer 3D CRS")
        print(f"  ArcGIS Pro: {arcgis_info['geographic_3d']} vs OSGeo4W: {osgeo4w_info['geographic_3d']}")
        print("\nROOT CAUSE: Stripped Database")
        print("  ArcGIS Pro's proj.db is missing many 3D geographic CRS")
    else:
        print("\n✓ EPSG:4979 is present in ArcGIS Pro's proj.db")
        print("  The database content is not the problem")
        print("  Issue is likely in GDAL configuration (see scripts 3-5)")
    
    return True

if __name__ == "__main__":
    success = main()
    
    print("\n" + "=" * 70)
    print(f"{'✓ Comparison complete' if success else '❌ Comparison failed'}")
    print("=" * 70)
    
    sys.exit(0 if success else 1)
```

**Run**: `python 06_compare_databases.py > results_06.txt`

---

## Analysis Workflow

### Step-by-Step Execution

1. **Run Scripts 1-6 in Order**
   ```powershell
   python 01_find_proj_db.py > results_01.txt
   python 02_query_proj_db.py > results_02.txt
   python 03_check_environment.py > results_03.txt
   python 04_test_epsg_recognition.py > results_04.txt
   
   # IMPORTANT: Start fresh Python session for script 5
   python 05_test_proj_lib_override.py > results_05.txt
   
   python 06_compare_databases.py > results_06.txt
   ```

2. **Collect All Results**
   ```powershell
   # Combine all results into one file
   type results_*.txt > arcgis_proj_diagnosis_complete.txt
   ```

3. **Interpret Results** using the decision matrix in [`arcgis_proj_diagnosis.md`](arcgis_proj_diagnosis.md)

### Expected Outcome

Based on the diagnostic results, you will identify one of these scenarios:

| Scenario | Script 2 Result | Script 4 Result | Script 5 Result | Root Cause |
|----------|-----------------|-----------------|-----------------|------------|
| **A** | EPSG:4979 missing | Fails | N/A | Incomplete database |
| **B** | EPSG:4979 present | Fails | **Success** | **PROJ_LIB not set (most likely)** |
| **C** | EPSG:4979 present | Fails | Fails | GDAL compilation issue |
| **D** | EPSG:4979 present | **Success** | N/A | Bug is file-specific, not CRS-specific |

**Scenario B is most likely** based on your existing [`arcgis_proj_config.py`](../gttk/utils/arcgis_proj_config.py) workaround.

---

## Bug Report Templates

### Template for Scenario B (PROJ_LIB Not Set)

**Title**: ArcGIS Pro Python environment does not set PROJ_LIB, causing GDAL to fail on modern EPSG codes

**Environment**:
- ArcGIS Pro Version: 3.6.0
- GDAL Version: 3.11.3
- Python Version: 3.13.7
- Operating System: Windows 11

**Description**:

ArcGIS Pro 3.6.0 includes a complete proj.db database with modern EPSG codes (verified: EPSG:4979 is present), but the Python environment does not set the `PROJ_LIB` environment variable. This causes GDAL's PROJ integration to fail when attempting to recognize 3D geographic and compound coordinate reference systems.

**Reproduction**:

1. Open ArcGIS Pro Python Command Prompt
2. Run the attached diagnostic scripts
3. Observe that:
   - `PROJ_LIB` is not set in the environment
   - `osr.GetPROJSearchPaths()` returns no paths or incorrect paths
   - `srs.ImportFromEPSG(4979)` returns non-zero (failure)
   - Setting `os.environ['PROJ_LIB']` before importing GDAL fixes the issue

**Impact**:

- `GetSpatialRef()` returns `None` for GeoTIFF files with modern CRS
- Coordinate transformations fail
- Metadata extraction incomplete
- Affects scientific workflows using EGM2008, compound CRS, or 3D datums

**Root Cause**:

ArcGIS Pro's Python environment initialization does not set `PROJ_LIB` to point to the bundled proj.db location. GDAL requires this variable to locate the PROJ database at runtime.

**Proposed Fix**:

Set `PROJ_LIB` in the Python environment activation script or `sitecustomize.py`:

```python
import os
from pathlib import Path

# Set PROJ_LIB to ArcGIS Pro's proj database
archome = os.environ.get('ARCHOME', r'C:\Program Files\ArcGIS\Pro')
proj_lib = Path(archome) / 'bin'  # Or 'Resources/pedata', depending on location
os.environ['PROJ_LIB'] = str(proj_lib)
```

**Workaround for Users**:

Users can set `PROJ_LIB` manually before importing GDAL:

```python
import os
os.environ['PROJ_LIB'] = r'C:\Program Files\ArcGIS\Pro\bin'
from osgeo import gdal, osr
```

**Severity**: Medium  
**Priority**: Should-fix for next point release

**Attachments**:
- Diagnostic scripts
- Complete diagnostic output showing PROJ_LIB is not set
- Proof that setting PROJ_LIB fixes the issue

---

## Conclusion

After running these diagnostics, you will have:

1. **Definitive proof** of the root cause
2. **Evidence** for the GitHub bug report
3. **Concrete recommendations** for Esri developers
4. **Severity assessment** (simple config fix vs. code changes required)

The most likely outcome is **Scenario B**: a simple configuration issue that Esri can fix by adding one environment variable to their Python initialization.
