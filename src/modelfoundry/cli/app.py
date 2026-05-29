# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""Console-script entry point.

Pre-production placeholder: `main` prints the package version and exits 0.
The full Typer command surface replaces this in Phase D.
"""

from modelfoundry._version import __version__


def main() -> int:
    print(f"modelfoundry {__version__}")
    return 0
