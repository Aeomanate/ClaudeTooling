#!/usr/bin/env python
# -*- coding: UTF-8 -*-
"""Shared test double for asserting stdout.reconfigure() calls."""

import io


class ReconfigurableStringIO(io.StringIO):
    """io.StringIO stand-in exposing reconfigure() like a real TextIOWrapper."""

    def __init__(self):
        super().__init__()
        self.reconfigure_calls = []

    def reconfigure(self, **kwargs):
        self.reconfigure_calls.append(kwargs)
