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
Mock GeoTIFF Factory for Testing.

This module provides the MockGeoTIFF class, a factory for creating in-memory
GeoTIFF files for testing purposes. Using GDAL's MEM (memory) driver, it creates
realistic GeoTIFF datasets without touching disk storage.

Key advantages:
- Fast: In-memory operations are orders of magnitude faster than disk I/O
- Precise: Exact control over all GeoTIFF properties
- Flexible: Easy to create edge cases and specific scenarios
- Clean: No cleanup required, no temporary files left behind

Example:
    >>> # Create a basic test GeoTIFF
    >>> mock = MockGeoTIFF(width=256, height=256, bands=1)
    >>> ds = mock.to_gdal_dataset()
    >>> assert ds.RasterXSize == 256
    
    >>> # Create a DEM with specific properties
    >>> mock_dem = MockGeoTIFF(
    ...     width=1024,
    ...     height=1024,
    ...     bands=1,
    ...     data_type=gdal.GDT_Float32,
    ...     crs='EPSG:32610+5703',
    ...     nodata_value=-9999.0,
    ...     compression='ZSTD'
    ... )
    >>> ds = mock_dem.to_gdal_dataset()
"""

import numpy as np
from osgeo import gdal, osr
from pathlib import Path
from typing import Optional, Tuple, Union


class MockGeoTIFF:
    """
    Factory for creating in-memory mock GeoTIFF files for testing.
    
    This class creates realistic GeoTIFF datasets using GDAL's MEM driver,
    allowing fast, flexible testing without disk I/O. All properties can be
    precisely controlled for testing specific scenarios.
    
    Attributes:
        width: Raster width in pixels
        height: Raster height in pixels
        bands: Number of bands
        data_type: GDAL data type constant (e.g., gdal.GDT_Float32)
        crs: Coordinate reference system (EPSG code or WKT)
        geo_transform: Affine transformation tuple (6 values)
        nodata_value: NoData value for the raster
        nodata_pixel_count: Number of NoData pixels to include
        compression: Compression algorithm ('NONE', 'DEFLATE', 'LZW', etc.)
        predictor: Predictor for compression (1, 2, or 3)
        tiled: Whether to use tiling
        tile_size: Tile dimensions in pixels
        pixel_data: Custom pixel data (numpy array)
    
    Example:
        >>> # Basic usage
        >>> mock = MockGeoTIFF(width=512, height=512)
        >>> ds = mock.to_gdal_dataset()
        >>> 
        >>> # Advanced usage with specific properties
        >>> mock = MockGeoTIFF(
        ...     width=1024,
        ...     height=1024,
        ...     bands=3,
        ...     data_type=gdal.GDT_Byte,
        ...     crs='EPSG:32610',
        ...     compression='DEFLATE',
        ...     predictor=2,
        ...     tiled=True
        ... )
    """
    
    def __init__(
        self,
        width: int = 256,
        height: int = 256,
        bands: int = 1,
        data_type: int = gdal.GDT_Float32,
        crs: Optional[str] = 'EPSG:4326',
        geo_transform: Optional[Tuple[float, ...]] = None,
        nodata_value: Optional[float] = None,
        nodata_pixel_count: int = 0,
        compression: str = 'NONE',
        predictor: Optional[int] = None,
        tiled: bool = False,
        tile_size: int = 256,
        pixel_data: Optional[np.ndarray] = None,
        photometric: Optional[str] = None,
        quality: Optional[int] = None,
    ):
        """
        Initialize MockGeoTIFF with specified parameters.
        
        Args:
            width: Raster width in pixels (default: 256)
            height: Raster height in pixels (default: 256)
            bands: Number of bands (default: 1)
            data_type: GDAL data type (default: GDT_Float32)
            crs: Coordinate system as EPSG code or WKT (default: 'EPSG:4326')
            geo_transform: Affine transformation (default: auto-generated)
            nodata_value: NoData value (default: None)
            nodata_pixel_count: Number of NoData pixels (default: 0)
            compression: Compression algorithm (default: 'NONE')
            predictor: Predictor type for compression (default: None)
            tiled: Use tiling instead of strips (default: False)
            tile_size: Tile dimensions in pixels (default: 256)
            pixel_data: Custom pixel data as numpy array (default: auto-generated)
            photometric: Photometric interpretation (default: None)
            quality: JPEG/JXL quality 1-100 (default: None)
        """
        self.width = width
        self.height = height
        self.bands = bands
        self.data_type = data_type
        self.crs = crs
        self.nodata_value = nodata_value
        self.nodata_pixel_count = nodata_pixel_count
        self.compression = compression
        self.predictor = predictor
        self.tiled = tiled
        self.tile_size = tile_size
        self.photometric = photometric
        self.quality = quality
        
        # Set default geotransform if not provided
        if geo_transform is None:
            # Default: 1-degree pixels starting at (0, 0)
            self.geo_transform = (0.0, 1.0, 0.0, 0.0, 0.0, -1.0)
        else:
            self.geo_transform = geo_transform
        
        # Generate or use provided pixel data
        if pixel_data is not None:
            self.pixel_data = pixel_data
        else:
            self.pixel_data = self._generate_pixel_data()
    
    def _generate_pixel_data(self) -> np.ndarray:
        """
        Generate synthetic pixel data for the mock GeoTIFF.
        
        Creates realistic test data with controlled properties including
        NoData pixels if specified.
        
        Returns:
            numpy array with shape (bands, height, width)
        """
        # Map GDAL data types to numpy dtypes
        dtype_map = {
            gdal.GDT_Byte: np.uint8,
            gdal.GDT_UInt16: np.uint16,
            gdal.GDT_Int16: np.int16,
            gdal.GDT_UInt32: np.uint32,
            gdal.GDT_Int32: np.int32,
            gdal.GDT_Float32: np.float32,
            gdal.GDT_Float64: np.float64,
        }
        
        np_dtype = dtype_map.get(self.data_type, np.float32)
        
        # Generate base data based on data type
        if np_dtype in (np.uint8, np.uint16, np.uint32):
            # Integer types: use range appropriate for type
            if np_dtype == np.uint8:
                data = np.random.randint(0, 255, size=(self.bands, self.height, self.width), dtype=np_dtype)
            else:
                data = np.random.randint(0, 1000, size=(self.bands, self.height, self.width), dtype=np_dtype)
        else:
            # Float types: use realistic elevation-like values
            data = np.random.uniform(100.0, 500.0, size=(self.bands, self.height, self.width))
            data = data.astype(np_dtype)
        
        # Add NoData pixels if specified
        if self.nodata_value is not None and self.nodata_pixel_count > 0:
            total_pixels = self.height * self.width
            if self.nodata_pixel_count < total_pixels:
                # Randomly distribute NoData pixels across first band
                nodata_indices = np.random.choice(
                    total_pixels,
                    min(self.nodata_pixel_count, total_pixels),
                    replace=False
                )
                data_flat = data[0].flatten()
                data_flat[nodata_indices] = self.nodata_value
                data[0] = data_flat.reshape(self.height, self.width)
        
        return data
    
    def to_gdal_dataset(self) -> gdal.Dataset:
        """
        Convert to actual GDAL Dataset in memory.
        
        Creates an in-memory GDAL Dataset using the MEM driver with all
        specified properties. This is fast and doesn't touch disk.
        
        Returns:
            gdal.Dataset: In-memory GDAL dataset
            
        Example:
            >>> mock = MockGeoTIFF(width=256, height=256)
            >>> ds = mock.to_gdal_dataset()
            >>> assert ds is not None
            >>> assert ds.RasterXSize == 256
        """
        # Create in-memory dataset
        driver = gdal.GetDriverByName('MEM')
        ds = driver.Create('', self.width, self.height, self.bands, self.data_type)
        
        if ds is None:
            raise RuntimeError("Failed to create in-memory dataset")
        
        # Set geotransform
        ds.SetGeoTransform(self.geo_transform)
        
        # Set projection
        if self.crs:
            srs = osr.SpatialReference()
            if self.crs.startswith('EPSG:'):
                # Parse EPSG code (may include +vertical)
                if '+' in self.crs:
                    # Compound CRS (e.g., 'EPSG:32610+5703')
                    srs.SetFromUserInput(self.crs)
                else:
                    # Simple EPSG
                    epsg_code = int(self.crs.split(':')[1])
                    srs.ImportFromEPSG(epsg_code)
            else:
                # Assume WKT
                srs.ImportFromWkt(self.crs)
            
            ds.SetProjection(srs.ExportToWkt())
        
        # Write pixel data to bands
        for band_idx in range(self.bands):
            band = ds.GetRasterBand(band_idx + 1)
            band.WriteArray(self.pixel_data[band_idx])
            
            # Set NoData value if specified
            if self.nodata_value is not None:
                band.SetNoDataValue(float(self.nodata_value))
        
        # Flush to ensure data is written
        ds.FlushCache()
        
        return ds
    
    def save_to_file(self, filepath: Union[str, Path], **creation_options):
        """
        Save to an actual GeoTIFF file on disk.
        
        Useful for debugging or creating test fixtures. Not normally used
        in tests (prefer in-memory datasets for speed).
        
        Args:
            filepath: Path where to save the GeoTIFF
            **creation_options: Additional GDAL creation options
            
        Example:
            >>> mock = MockGeoTIFF(width=256, height=256)
            >>> mock.save_to_file('test.tif', COMPRESS='DEFLATE')
        """
        filepath = Path(filepath)
        
        # Build creation options
        options = []
        
        if self.compression and self.compression != 'NONE':
            options.append(f'COMPRESS={self.compression}')
        
        if self.predictor is not None:
            options.append(f'PREDICTOR={self.predictor}')
        
        if self.tiled:
            options.append('TILED=YES')
            options.append(f'BLOCKXSIZE={self.tile_size}')
            options.append(f'BLOCKYSIZE={self.tile_size}')
        
        if self.photometric:
            options.append(f'PHOTOMETRIC={self.photometric}')
        
        if self.quality is not None:
            if self.compression == 'JPEG':
                options.append(f'JPEG_QUALITY={self.quality}')
            elif self.compression == 'JXL':
                # JXL uses DISTANCE parameter
                distance = (100 - self.quality) * 0.1
                options.append(f'JXL_DISTANCE={distance}')
        
        # Add any additional options
        for key, value in creation_options.items():
            options.append(f'{key}={value}')
        
        # Create dataset
        driver = gdal.GetDriverByName('GTiff')
        ds = driver.Create(
            str(filepath),
            self.width,
            self.height,
            self.bands,
            self.data_type,
            options=options
        )
        
        if ds is None:
            raise RuntimeError(f"Failed to create GeoTIFF at {filepath}")
        
        # Set geotransform
        ds.SetGeoTransform(self.geo_transform)
        
        # Set projection
        if self.crs:
            srs = osr.SpatialReference()
            if self.crs.startswith('EPSG:'):
                if '+' in self.crs:
                    srs.SetFromUserInput(self.crs)
                else:
                    epsg_code = int(self.crs.split(':')[1])
                    srs.ImportFromEPSG(epsg_code)
            else:
                srs.ImportFromWkt(self.crs)
            
            ds.SetProjection(srs.ExportToWkt())
        
        # Write pixel data
        for band_idx in range(self.bands):
            band = ds.GetRasterBand(band_idx + 1)
            band.WriteArray(self.pixel_data[band_idx])
            
            if self.nodata_value is not None:
                band.SetNoDataValue(float(self.nodata_value))
        
        # Close dataset (writes to disk)
        ds.FlushCache()
        ds = None
    
    def __repr__(self) -> str:
        """String representation of MockGeoTIFF."""
        return (
            f"MockGeoTIFF(width={self.width}, height={self.height}, "
            f"bands={self.bands}, data_type={self.data_type}, "
            f"crs='{self.crs}', compression='{self.compression}')"
        )