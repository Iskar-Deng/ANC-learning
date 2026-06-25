#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any, Dict

from utils import derive_language_config


JsonDict = Dict[str, Any]


def config_for_language(language: str) -> JsonDict:
    return derive_language_config(language)
