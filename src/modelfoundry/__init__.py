# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""ModelFoundry — compile a YAML recipe into a reproducible trained-model instance.

Public API re-exports are added as the package is built out (see docs/specs/stories.md).
The pre-production scaffold exposes only the version string.
"""

from modelfoundry._version import __version__

__all__ = ["__version__"]
