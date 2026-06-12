# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""PyTorch plugin package.

`plugin` is the singleton registered under the `modelfoundry.plugins` entry-point
group; `PyTorchPlugin` is its class and `PyTorchHealthReport` the shape its
`health_check` returns. The vocabulary (architecture / losses / optimizers /
schedules / determinism / data / augmentations / trainer / optimization /
evaluation / visualizations / persistence) is filled in across Stories C.c-C.p.
"""

from __future__ import annotations

from modelfoundry.plugins.pytorch.plugin import (
    PyTorchHealthReport,
    PyTorchPlugin,
    plugin,
)

__all__ = ["PyTorchHealthReport", "PyTorchPlugin", "plugin"]
