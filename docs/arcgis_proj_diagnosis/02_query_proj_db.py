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
                print(f"    [OK] FOUND: {result[2]}")
                print(f"      Type: {result[3]}")
                print(f"      Deprecated: {'Yes' if result[4] else 'No'}")
            else:
                print("    [ERROR] NOT FOUND")
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
                print("    [ERROR] No 3D geographic CRS found")
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
                print("    [WARNING] No compound CRS found")
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
        print(f"\n[ERROR] Database error: {e}")
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
        print("\n[ERROR] ERROR: No proj.db files found")
        print("   Run script 01 first to locate the database")
        sys.exit(1)
    
    success = True
    for db_path in proj_dbs:
        if not query_proj_db(db_path):
            success = False
    
    if success:
        print("\n" + "=" * 70)
        print("[OK] Analysis complete - check results above")
        print("=" * 70)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
