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
        print(f"[ERROR] ERROR: Cannot import GDAL: {e}")
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
            print("[WARNING] WARNING: No PROJ search paths returned")
        
        # Try to get PROJ version
        try:
            srs = osr.SpatialReference()
            # This may not work in all GDAL versions
            print(f"\nPROJ Version: {osr.GetPROJVersionMajor()}.{osr.GetPROJVersionMinor()}.{osr.GetPROJVersionMicro()}")
        except:
            pass
            
    except Exception as e:
        print(f"[WARNING] WARNING: Error checking PROJ config: {e}")
    
    return True

def main():
    success = check_environment()
    
    print("\n" + "=" * 70)
    if success:
        print("[OK] Environment check complete")
        print("\nKey Questions:")
        print("  - Is PROJ_LIB set? If not, GDAL may not find proj.db")
        print("  - Do PROJ search paths include the directory with proj.db?")
    else:
        print("[ERROR] Environment check failed")
    print("=" * 70)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
