#!/usr/bin/env python3
"""
Test to demonstrate and explore solutions for custom vertical datum storage in GeoTIFF.
"""
import tempfile
from pathlib import Path
from osgeo import gdal, osr
import numpy as np


def test_custom_vertical_datum_storage():
    """Test how GDAL handles custom vertical datums in different storage scenarios."""
    
    # Create a simple test raster
    width, height = 100, 100
    data = np.random.rand(height, width).astype(np.float32)
    
    # Create horizontal SRS (EPSG:6368)
    horiz_srs = osr.SpatialReference()
    horiz_srs.ImportFromEPSG(6368)
    
    # Create custom vertical SRS (GGM10)
    vert_srs = osr.SpatialReference()
    custom_wkt = """
    VERTCRS["GGM10 height",
        VDATUM["Geoide Gravimétrico Mexicano 2010"],
        CS[vertical,1],
        AXIS["gravity-related height (H)",up,LENGTHUNIT["metre",1]],
        ID["PROJ","GGM2010"]]
    """
    vert_srs.ImportFromWkt(custom_wkt)
    
    # Create compound CRS
    compound_srs = osr.SpatialReference()
    compound_srs.SetCompoundCS(
        "Mexico ITRF2008 / UTM zone 13N + GGM10 height",
        horiz_srs,
        vert_srs
    )
    
    print("\n" + "="*80)
    print("ORIGINAL COMPOUND CRS (before writing to file):")
    print("="*80)
    print(compound_srs.ExportToWkt(['FORMAT=WKT2_2019']))
    
    with tempfile.TemporaryDirectory() as tmpdir:
        
        # Test 1: Standard GeoTIFF with GEOTIFF_VERSION=1.1
        print("\n" + "="*80)
        print("TEST 1: GeoTIFF 1.1 (WKT2 support)")
        print("="*80)
        tif_path = Path(tmpdir) / "test_geotiff11.tif"
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(
            str(tif_path), width, height, 1, gdal.GDT_Float32,
            options=['GEOTIFF_VERSION=1.1']
        )
        ds.SetProjection(compound_srs.ExportToWkt())
        ds.GetRasterBand(1).WriteArray(data)
        ds.FlushCache()
        ds = None
        
        # Read back
        ds = gdal.Open(str(tif_path))
        read_srs = ds.GetSpatialRef()
        print("\nRead back from GeoTIFF 1.1:")
        print(read_srs.ExportToWkt(['FORMAT=WKT2_2019']))
        
        # Check VDATUM
        try:
            vert_name = read_srs.GetAttrValue("COMPD_CS|VERT_CS")
            print(f"\nVERT_CS name: {vert_name}")
            vdatum_name = read_srs.GetAttrValue("COMPD_CS|VERT_CS|VERT_DATUM")
            print(f"VDATUM name: {vdatum_name}")
        except:
            print("Could not extract VDATUM information")
        ds = None
        
        # Test 2: Try storing WKT in TIFF metadata tag
        print("\n" + "="*80)
        print("TEST 2: Store full WKT in TIFF metadata")
        print("="*80)
        tif_path2 = Path(tmpdir) / "test_with_metadata.tif"
        ds = driver.Create(
            str(tif_path2), width, height, 1, gdal.GDT_Float32,
            options=['GEOTIFF_VERSION=1.1']
        )
        ds.SetProjection(compound_srs.ExportToWkt())
        
        # Store the full WKT in metadata
        full_wkt = compound_srs.ExportToWkt(['FORMAT=WKT2_2019'])
        ds.SetMetadataItem('COMPOUND_CRS_WKT2', full_wkt)
        
        ds.GetRasterBand(1).WriteArray(data)
        ds.FlushCache()
        ds = None
        
        # Read back
        ds = gdal.Open(str(tif_path2))
        stored_wkt = ds.GetMetadataItem('COMPOUND_CRS_WKT2')
        if stored_wkt:
            print("\nSuccessfully retrieved custom WKT from metadata:")
            print(stored_wkt[:200] + "...")
            
            # Try to import it
            test_srs = osr.SpatialReference()
            if test_srs.ImportFromWkt(stored_wkt) == 0:
                vdatum_name = test_srs.GetAttrValue("COMPD_CS|VERT_CS|VERT_DATUM")
                print(f"\nVDATUM from metadata WKT: {vdatum_name}")
        else:
            print("Could not retrieve custom WKT from metadata")
        ds = None
        
        # Test 3: Try PROJ string storage
        print("\n" + "="*80)
        print("TEST 3: Check PROJ string representation")
        print("="*80)
        proj_string = compound_srs.ExportToProj4()
        print(f"PROJ string: {proj_string}")


if __name__ == "__main__":
    test_custom_vertical_datum_storage()