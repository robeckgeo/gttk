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
Configuration Management for the GeoTIFF ToolKit.

This module provides a singleton configuration manager (`Config`) that loads,
parses, and provides access to settings from a central `config.toml` file.
It ensures that configuration values are loaded only once and are available
throughout the application.

Classes:
    Config: A singleton class for managing application-wide configuration.
"""
import sys
from pathlib import Path
from typing import Any, Dict


if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        # Fallback if tomli is not installed
        tomllib = None

class Config:
    """Singleton configuration manager"""
    _instance = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance
    
    def _load_config(self):
        """Load configuration from config.toml"""
        config_path = Path(__file__).parent.parent / "config.toml"
        if config_path.exists() and tomllib is not None:
            try:
                with open(config_path, "rb") as f:
                    self._config = tomllib.load(f)
            except Exception as e:
                print(f"Warning: Could not load config.toml: {e}")
                self._config = self._default_config()
        else:
            # Fallback to defaults if config.toml doesn't exist or tomllib not available
            self._config = self._default_config()
    
    def _default_config(self) -> Dict[str, Any]:
        """Default configuration if config.toml doesn't exist"""
        return {
            "paths": {},
            "gui": {
                "default_layout": "analyst",
                "default_theme": "material_light",
                "window_size": [1200, 900],
                "enable_dark_mode": True
            },
            "api": {
                "host": "0.0.0.0",
                "port": 8000,
                "max_upload_size_mb": 500,
                "cache_ttl_seconds": 3600
            },
            "logging": {
                "level": "INFO",
                "file": "gttk.log"
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation
        
        Args:
            key: Configuration key in dot notation (e.g., "gui.default_theme")
            default: Default value if key is not found
            
        Returns:
            Configuration value or default
            
        Example:
            >>> config.get("gui.default_theme")
            'material_light'
            >>> config.get("gui.window_size")
            [1200, 900]
        """
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire configuration section
        
        Args:
            section: Section name (e.g., "gui", "api", "paths")
            
        Returns:
            Dictionary containing the section configuration
            
        Example:
            >>> config.get_section("gui")
            {'default_layout': 'analyst', 'default_theme': 'material_light', ...}
        """
        return self._config.get(section, {})
    
    def set(self, key: str, value: Any):
        """Set configuration value using dot notation
        
        Args:
            key: Configuration key in dot notation
            value: Value to set
            
        Note:
            This only modifies the in-memory configuration.
            Changes are not persisted to config.toml.
        """
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
    
    def reload(self):
        """Reload configuration from config.toml"""
        self._load_config()

# Singleton instance
config = Config()