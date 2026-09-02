#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ******************************************************************************
# Project: GeoTIFF ToolKit (GTTK)
# Author: Eric Robeck <robeckgeo@gmail.com>
#
# Copyright (c) 2026, Eric Robeck
# Licensed under the MIT License
# ******************************************************************************

"""
Configuration Management for the GeoTIFF ToolKit.

This module provides a singleton configuration manager (`Config`) that loads,
parses, and provides access to settings from a `config.toml` file.

Where the file comes from, in order:

1. The path in the ``GTTK_CONFIG`` environment variable, if it is set. It must exist.
2. ``config.toml`` at the root of a source checkout, when ``gttk`` is imported from
   one -- that is, when ``pyproject.toml`` sits beside it. This is the file a developer
   and the ArcGIS Pro toolbox edit.
3. The packaged default, ``gttk/resources/config.toml``, which ships in the wheel.

The loader used to look three directories above this file and nowhere else, which is
the checkout root in a checkout and ``site-packages`` in an installed copy, where no
such file exists. It then announced the miss with ``print()`` on stdout -- at import,
into the output of every command run from a wheel. Nothing is read until a value is
asked for, and nothing is printed.

Classes:
    Config: A singleton class for managing application-wide configuration.
"""
import logging
import os
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: Names an explicit configuration file, taking precedence over everything else.
CONFIG_ENV_VAR = 'GTTK_CONFIG'


def resolve_config_path(package_file: Optional[Path] = None) -> Path:
    """
    The ``config.toml`` this process should read; see the module docstring for the order.

    Args:
        package_file: The location of this module, for tests that simulate an installed
            copy. Defaults to the real one.

    Raises:
        FileNotFoundError: if ``GTTK_CONFIG`` names a file that does not exist.
    """
    explicit = os.environ.get(CONFIG_ENV_VAR)
    if explicit:
        path = Path(explicit)
        if not path.is_file():
            raise FileNotFoundError(f"{CONFIG_ENV_VAR} names {path}, which does not exist")
        return path

    checkout = Path(package_file or __file__).resolve().parents[2]
    if (checkout / 'pyproject.toml').is_file() and (checkout / 'config.toml').is_file():
        return checkout / 'config.toml'

    return Path(str(resources.files('gttk.resources').joinpath('config.toml')))


class Config:
    """Singleton configuration manager; the file is read on first access."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = None
            cls._instance._path = None
        return cls._instance

    def _load_config(self) -> None:
        """Load configuration from the resolved config.toml."""
        path = resolve_config_path()
        with open(path, "rb") as f:
            self._config = tomllib.load(f)
        self._path = path
        logger.debug(f"Loaded configuration from {path}")

    def _ensure_loaded(self) -> Dict[str, Any]:
        if self._config is None:
            self._load_config()
        return self._config

    @property
    def path(self) -> Path:
        """The file the settings came from (loading it if necessary)."""
        self._ensure_loaded()
        return self._path

    @property
    def loaded(self) -> bool:
        """Whether the file has been read yet."""
        return self._config is not None

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation

        Args:
            key: Configuration key in dot notation (e.g., "statistics.force_strategy")
            default: Default value if key is not found

        Returns:
            Configuration value or default

        Example:
            >>> config.get("statistics.force_strategy")
            'auto'
            >>> config.get("statistics.block_size")
            [4096, 4096]
            >>> config.get("no.such.key", "fallback")
            'fallback'
        """
        value: Any = self._ensure_loaded()
        for k in key.split("."):
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

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
        config = self._ensure_loaded()
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def reload(self):
        """Reload configuration from config.toml (resolving the path again)."""
        self._load_config()


# Singleton instance; nothing is read until a value is asked for.
config = Config()
