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
Static Asset Management for GTTK Reports.

This module provides the `ResourceManager` singleton, responsible for loading
and managing static assets like CSS, JavaScript, icons, and theme files (TOML)
that are packaged with the toolkit. It ensures that report generation tools
can reliably access these resources.

Classes:
    ResourceManager: A singleton for accessing packaged static files.
"""
import sys
import re
from pathlib import Path
from typing import Dict, Optional


if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


class ResourceManager:
    """Manages static resources (CSS, JS, themes, icons)"""
    
    def __init__(self, resources_dir: Optional[Path] = None):
        self.resources_dir = resources_dir or Path(__file__).parent.parent / "resources"
        self._theme_cache: Dict[str, Dict] = {}
        self._banner_rules: Optional[list] = None
    
    def get_css(self, theme: str = "material_light", banner_text: Optional[str] = None) -> str:
        """Get combined CSS for a theme
        
        Args:
            theme: Theme name ('material_light' or 'material_dark')
            banner_text: Optional banner text to trigger classification styles
            
        Returns:
            Combined CSS string with theme colors applied
        """
        # Load CSS modules
        css_parts = []
        css_parts.append(self._read_file_safe("styles/base.css"))
        css_parts.append(self._read_file_safe("styles/syntax.css"))
        css_parts.append(self._read_file_safe("styles/layout.css"))
        
        # Apply theme colors
        theme_colors = self.load_theme(theme)
        css = "\n".join([part for part in css_parts if part])
        
        # Apply banner colors if banner_text is provided
        if banner_text:
            css = self._apply_banner_colors(css, banner_text)
            
        return self._apply_theme_colors(css, theme_colors)
    
    def get_javascript(self) -> str:
        """Get combined JavaScript
        
        Returns:
            Combined JavaScript string
        """
        js_parts = []
        js_parts.append(self._read_file_safe("scripts/navigation.js"))
        js_parts.append(self._read_file_safe("scripts/menu_responsive.js"))
        return "\n".join([part for part in js_parts if part])
    
    def load_theme(self, theme: str) -> Dict:
        """Load theme from TOML
        
        Args:
            theme: Theme name
            
        Returns:
            Dictionary of theme colors and settings
        """
        if theme in self._theme_cache:
            return self._theme_cache[theme]
        
        theme_file = self.resources_dir / "styles" / f"{theme}.toml"
        if not theme_file.exists():
            # Return default theme colors
            return self._default_theme_colors()
        
        if tomllib is None:
            return self._default_theme_colors()
        
        try:
            with open(theme_file, "rb") as f:
                theme_data = tomllib.load(f)
            
            self._theme_cache[theme] = theme_data
            return theme_data
        except Exception as e:
            print(f"Warning: Could not load theme {theme}: {e}")
            return self._default_theme_colors()
    
    def _default_theme_colors(self) -> Dict:
        """Default theme colors if theme file is not found"""
        return {
            "colors": {
                "background": "#FFFFFF",
                "text": "#333333",
                "accent": "#007bff"
            },
            "syntax": {
                "xml": {
                    "tag_name": "#E93935",
                    "attr_name": "#9C3EDA",
                    "attr_value": "#196B24",
                    "comment": "#90A4AE",
                    "bracket": "#39ADB5",
                    "text": "#000000"
                },
                "wkt": {
                    "keyword": "#196B24",
                    "number": "#40A070",
                    "text": "#4070A0",
                    "punc": "#3C4A69",
                    "enum": "#000000"
                },
                "json": {
                    "member": "#196B24",
                    "number": "#40A070",
                    "string": "#4070A0",
                    "punc": "#3C4A69",
                    "bool": "#000000"
                }
            }
        }
    
    def get_icon_path(self, icon_name: str, icon_type: str = "menu") -> Path:
        """Get path to icon file
        
        Args:
            icon_name: Icon name (without extension)
            icon_type: Icon type ('menu' or 'favicon')
            
        Returns:
            Path to SVG icon file
        """
        icon_path = self.resources_dir / "icons" / "svg" / icon_type / f"{icon_name}.svg"
        if not icon_path.exists():
            # Try alternate locations
            icon_path = self.resources_dir / "icons" / "working" / f"{icon_name}.png"
            if not icon_path.exists():
                raise FileNotFoundError(f"Icon not found: {icon_name}")
        return icon_path
    
    def _read_file_safe(self, relative_path: str) -> str:
        """Read a file from resources directory, return empty string if not found
        
        Args:
            relative_path: Path relative to resources directory
            
        Returns:
            File content or empty string if file not found
        """
        file_path = self.resources_dir / relative_path
        if not file_path.exists():
            return ""
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")
            return ""
    
    def _read_file(self, relative_path: str) -> str:
        """Read a file from resources directory
        
        Args:
            relative_path: Path relative to resources directory
            
        Returns:
            File content
            
        Raises:
            FileNotFoundError: If file does not exist
        """
        file_path = self.resources_dir / relative_path
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    
    def _apply_theme_colors(self, css: str, theme_colors: Dict) -> str:
        """Apply theme colors to CSS template
        
        Args:
            css: CSS template string
            theme_colors: Theme color dictionary
            
        Returns:
            CSS with colors applied
        """
        # Replace CSS custom properties
        colors = theme_colors.get("colors", {})
        for key, value in colors.items():
            css = css.replace(f"var(--{key})", value)
        
        # Replace syntax highlighting colors
        syntax = theme_colors.get("syntax", {})
        for lang, lang_colors in syntax.items():
            for token, color in lang_colors.items():
                # Handle both underscore and hyphen formats
                css = css.replace(f"var(--{lang}-{token})", color)
                css = css.replace(f"var(--{lang}-{token.replace('_', '-')})", color)
        
        return css


    def _apply_banner_colors(self, css: str, banner_text: str) -> str:
        """
        Apply banner colors to CSS based on matched classification rules.
        
        Args:
            css: The CSS content to modify
            banner_text: The classification banner text
            
        Returns:
            Modified CSS with banner colors applied
        """
        rules = self._load_banner_rules()
        if not rules:
            return css
            
        # Default colors
        text_color = "white"
        bg_color = "#616161"
        
        # Find matches - evaluate all rules, last match wins
        match_found = False
        for rule in rules:
            try:
                pattern = rule.get("pattern", "")
                if not pattern:
                    continue
                    
                if re.search(pattern, banner_text, re.IGNORECASE):
                    # Update colors from this rule
                    if "background_color" in rule:
                        bg_color = rule["background_color"]
                    if "color" in rule:
                        text_color = rule["color"]
                    match_found = True
            except re.error:
                print(f"Warning: Invalid regex pattern in banner rules: {rule.get('pattern')}")
        
        if match_found:
            # Replace colors in CSS using markers
            # Matches: color: white; /* BANNER_TEXT_COLOR */
            css = re.sub(
                r'color:\s*[^;]+;\s*/\*\s*BANNER_TEXT_COLOR\s*\*/',
                f'color: {text_color}; /* BANNER_TEXT_COLOR */',
                css
            )
            # Matches: background-color: #616161; /* BANNER_BG_COLOR */
            css = re.sub(
                r'background-color:\s*[^;]+;\s*/\*\s*BANNER_BG_COLOR\s*\*/',
                f'background-color: {bg_color}; /* BANNER_BG_COLOR */',
                css
            )
            
        return css

    def _load_banner_rules(self) -> list:
        """Load banner classification rules from TOML."""
        if self._banner_rules is not None:
            return self._banner_rules
            
        rules_file = self.resources_dir / "styles" / "banners.toml"
        if not rules_file.exists() or tomllib is None:
            self._banner_rules = []
            return []
            
        try:
            with open(rules_file, "rb") as f:
                data = tomllib.load(f)
                rules = data.get("banners", [])
                if rules is None:
                    rules = []
                self._banner_rules = rules
                return rules
        except Exception as e:
            print(f"Warning: Could not load banner rules: {e}")
            self._banner_rules = []
            return []


# Singleton instance
resource_manager = ResourceManager()