# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""ModelFoundry CLI package.

`app.py` holds the root `typer` application, the shared options, the
exception → exit-code mapping, and the console-script `main()` entry point. Each
verb (`init` / `validate` / `check` / `status` / `materialize` / `report` /
`inspect` / `clean`) is implemented by its own Phase D story.
"""
