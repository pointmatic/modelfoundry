# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""`python -m modelfoundry` entry point — prints the version and exits 0."""

import sys

from modelfoundry.cli.app import main

if __name__ == "__main__":
    sys.exit(main())
