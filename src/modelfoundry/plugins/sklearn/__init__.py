# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""sklearn plugin package.

Story C.j lands only the shared `metrics` slice it consumes (the calibration
reliability curve). The full working `MLPClassifier` baseline plugin + the rest
of the shared metric vocabulary arrive in Story C.m, which extends this package.
"""
