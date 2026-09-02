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
Performance Tracker for Benchmarking Processing Steps.

This module provides the `PerformanceTracker` class, a tool to start and stop
named timers to measure the duration of different parts of a workflow. It is
used to gather metrics on the efficiency of various optimization stages.

Classes:
    PerformanceTracker: A class to manage named timers for performance analysis.
"""
import time
from typing import Dict

class PerformanceTracker:
    """A class to track the duration of various processing steps."""

    def __init__(self):
        self.timings: Dict[str, float] = {}
        self._start_times: Dict[str, float] = {}

    def start(self, step_name: str):
        """Starts the timer for a given step."""
        self._start_times[step_name] = time.perf_counter()

    def stop(self, step_name: str):
        """Stops the timer for a given step and records the duration."""
        if step_name in self._start_times:
            duration = time.perf_counter() - self._start_times[step_name]
            self.timings[step_name] = duration
            del self._start_times[step_name]
