# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""CLI verb implementations.

Each module here holds one verb's logic (`run(...) -> int`) plus its `rich`
rendering, kept out of `cli/app.py` so the root app stays a thin wiring layer.
The Typer command in `app.py` delegates to the matching `run`.
"""
