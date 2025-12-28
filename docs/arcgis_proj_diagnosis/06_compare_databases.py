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
        print("\n[ERROR] ERROR: Cannot find ArcGIS Pro's proj.db")
        return False
    
    if not osgeo4w_path.exists():
        print("\n[WARNING] WARNING: Cannot find OSGeo4W's proj.db at", osgeo4w_path)
        print("  Comparison will be limited to ArcGIS Pro database only")
        osgeo4w_path = None
    
    # Analyze databases
    print("\n[1] ArcGIS Pro Database")
    print("-" * 70)
    arcgis_info = analyze_database(arcgis_db)
    
    for key, value in arcgis_info.items():
        if key != 'path':
            print(f"  {key:20}: {value}")
    
    osgeo4w_info = None
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
        print(f"  ArcGIS Pro: {'[OK] Present' if arcgis_info['has_epsg_4979'] else '[ERROR] Missing'}")
        print(f"  OSGeo4W:    {'[OK] Present' if osgeo4w_info['has_epsg_4979'] else '[ERROR] Missing'}")
    
    # Diagnosis
    print("\n" + "=" * 70)
    print("DIAGNOSIS")
    print("=" * 70)
    
    if not arcgis_info['has_epsg_4979']:
        print("\n[ERROR] EPSG:4979 is MISSING from ArcGIS Pro's proj.db!")
        print("\nROOT CAUSE: Incomplete Database")
        print("  ArcGIS Pro ships an outdated or stripped proj.db")
        print("\nRECOMMENDATION:")
        print("  Esri should update proj.db to include modern EPSG codes")
    elif osgeo4w_info and osgeo4w_path and arcgis_info['geographic_3d'] < osgeo4w_info['geographic_3d'] * 0.5:
        print("\n[WARNING] WARNING: ArcGIS Pro has significantly fewer 3D CRS")
        print(f"  ArcGIS Pro: {arcgis_info['geographic_3d']} vs OSGeo4W: {osgeo4w_info['geographic_3d']}")
        print("\nROOT CAUSE: Stripped Database")
        print("  ArcGIS Pro's proj.db is missing many 3D geographic CRS")
    else:
        print("\n[OK] EPSG:4979 is present in ArcGIS Pro's proj.db")
        print("  The database content is not the problem")
        print("  Issue is likely in GDAL configuration (see scripts 3-5)")
    
    return True

if __name__ == "__main__":
    success = main()
    
    print("\n" + "=" * 70)
    print(f"{'[OK] Comparison complete' if success else '[ERROR] Comparison failed'}")
    print("=" * 70)
    
    sys.exit(0 if success else 1)
