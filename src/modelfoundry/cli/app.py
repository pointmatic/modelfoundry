# Copyright (c) 2026 Pointmatic
# SPDX-License-Identifier: Apache-2.0
"""ModelFoundry CLI root (Story D.a, `tech-spec.md` § CLI Design).

The `typer` app that wraps the `ModelFoundry` library API. This module owns the
scaffolding the eight verbs share:

* the root `typer.Typer()` instance + the `@app.callback()` that turns the shared
  options (`--cache-root`, `--data-cache-root`, `--log-level`, `--log-target`,
  `--plugin-path`, `--verbose`, `--quiet`) into a per-invocation `RuntimeConfig`
  stored on the Typer context (`ctx.obj`), with precedence CLI > env > defaults;
* `exit_code_for` — the exception → exit-code mapping (`0` success, `1`
  user/recipe/contract error, `2` system/plugin error, `130` SIGINT);
* `invoke` / `main` — run the app with `standalone_mode=False` so this module,
  not click, owns exception rendering and the process exit code.

The verbs are stubs here; each is fleshed out by its own Phase D story (D.b-D.i).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import click
import typer
from rich.console import Console

from modelfoundry.core.config import RuntimeConfig
from modelfoundry.core.errors import (
    CacheError,
    DataBindingError,
    ExpectationError,
    InspectionError,
    InstanceError,
    MaterializeError,
    ModelArtifactExistsError,
    ModelfoundryError,
    OptimizationError,
    PluginError,
    RecipeError,
    ValidationError,
)

_EXIT_SUCCESS = 0
_EXIT_USER_ERROR = 1
_EXIT_SYSTEM_ERROR = 2
_EXIT_SIGINT = 130

# `1` — user / recipe / contract errors (something the caller can fix).
_USER_ERRORS: tuple[type[ModelfoundryError], ...] = (
    RecipeError,
    ValidationError,
    DataBindingError,
    ExpectationError,
    ModelArtifactExistsError,
    InstanceError,
)
# `2` — system / plugin errors (an environment or execution failure).
_SYSTEM_ERRORS: tuple[type[ModelfoundryError], ...] = (
    PluginError,
    MaterializeError,
    CacheError,
    OptimizationError,
    InspectionError,
)

_err_console = Console(stderr=True)


def exit_code_for(exc: BaseException) -> int:
    """Map an exception to a CLI exit code per `tech-spec.md` § CLI Design.

    `KeyboardInterrupt` → 130; the user/contract error classes → 1; the
    system/plugin classes → 2; any other `ModelfoundryError` defaults to 1 (a
    domain error is caller-facing); anything else → 2 (unexpected = system).
    """
    if isinstance(exc, KeyboardInterrupt):
        return _EXIT_SIGINT
    if isinstance(exc, _USER_ERRORS):
        return _EXIT_USER_ERROR
    if isinstance(exc, _SYSTEM_ERRORS):
        return _EXIT_SYSTEM_ERROR
    if isinstance(exc, ModelfoundryError):
        return _EXIT_USER_ERROR
    return _EXIT_SYSTEM_ERROR


def _render_error(exc: BaseException) -> None:
    """Print a domain/unexpected error to stderr (the user-facing channel)."""
    message = str(exc) or exc.__class__.__name__
    stage = getattr(exc, "stage", None)
    suffix = f" [dim](stage: {stage})[/dim]" if stage else ""
    _err_console.print(f"[red]error:[/red] {message}{suffix}")


def build_runtime_config(
    *,
    cache_root: Path | None,
    data_cache_root: Path | None,
    log_level: str | None,
    log_target: str | None,
    plugin_path: str | None,
    verbose: bool,
    quiet: bool,
    num_workers: int | None = None,
) -> RuntimeConfig:
    """Build the per-invocation `RuntimeConfig` from the shared options.

    Only explicitly-supplied flags become overrides, so unset flags fall through
    to env vars then built-in defaults (`RuntimeConfig.from_env`). `--verbose` /
    `--quiet` are shorthand for a `log_level` of `DEBUG` / `WARNING` and yield to
    an explicit `--log-level`; supplying both is a usage error.
    """
    if verbose and quiet:
        raise click.exceptions.UsageError("--verbose and --quiet are mutually exclusive")

    overrides: dict[str, Any] = {}
    if cache_root is not None:
        overrides["cache_root"] = cache_root
    if data_cache_root is not None:
        overrides["data_cache_root"] = data_cache_root

    level = log_level
    if level is None and verbose:
        level = "DEBUG"
    elif level is None and quiet:
        level = "WARNING"
    if level is not None:
        overrides["log_level"] = level

    if log_target is not None:
        overrides["log_target"] = log_target
    if plugin_path is not None:
        overrides["plugin_path"] = tuple(Path(p) for p in plugin_path.split(",") if p)
    if num_workers is not None:
        overrides["num_workers"] = num_workers

    return RuntimeConfig.from_env(**overrides)


app = typer.Typer(
    name="modelfoundry",
    help="Reproducible model materialization over DataRefinery instances.",
    no_args_is_help=True,
    add_completion=False,
    # This module owns exception rendering + exit codes; keep typer's pretty
    # tracebacks out of the way.
    pretty_exceptions_enable=False,
)


def _version_callback(value: bool) -> None:
    if value:
        from modelfoundry._version import __version__

        typer.echo(f"modelfoundry {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the ModelFoundry version and exit.",
        ),
    ] = False,
    cache_root: Annotated[
        Path | None,
        typer.Option(
            "--cache-root", help="ModelFoundry cache root (env: MODELFOUNDRY_CACHE_ROOT)."
        ),
    ] = None,
    data_cache_root: Annotated[
        Path | None,
        typer.Option(
            "--data-cache-root",
            help="DataRefinery cache root (env: MODELFOUNDRY_DATA_CACHE_ROOT).",
        ),
    ] = None,
    log_level: Annotated[
        str | None,
        typer.Option("--log-level", help="Operator log level: DEBUG / INFO / WARNING / ERROR."),
    ] = None,
    log_target: Annotated[
        str | None,
        typer.Option("--log-target", help="Operator log target: stderr / stdout or a file path."),
    ] = None,
    plugin_path: Annotated[
        str | None,
        typer.Option("--plugin-path", help="Comma-separated extra plugin search paths."),
    ] = None,
    num_workers: Annotated[
        int | None,
        typer.Option(
            "--num-workers",
            help="DataLoader worker count (execution context, env: MODELFOUNDRY_NUM_WORKERS).",
        ),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Verbose output (log level DEBUG).")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Quiet output (log level WARNING).")
    ] = False,
) -> None:
    """Resolve the shared options into a RuntimeConfig on the Typer context."""
    ctx.obj = build_runtime_config(
        cache_root=cache_root,
        data_cache_root=data_cache_root,
        log_level=log_level,
        log_target=log_target,
        plugin_path=plugin_path,
        num_workers=num_workers,
        verbose=verbose,
        quiet=quiet,
    )


def _config(ctx: typer.Context) -> RuntimeConfig:
    """The per-invocation `RuntimeConfig` the callback stored on the context."""
    obj = ctx.obj
    return obj if isinstance(obj, RuntimeConfig) else RuntimeConfig.from_env()


def _not_implemented(verb: str, story: str) -> None:
    _err_console.print(
        f"[yellow]modelfoundry {verb}[/yellow]: not yet implemented (lands in Story {story})."
    )


# --- verb stubs (each fleshed out by its own Phase D story) ---


@app.command("init")
def _cmd_init(
    ctx: typer.Context,
    recipe: Annotated[Path, typer.Argument(help="Path to write the scaffolded recipe.")],
    data: Annotated[
        Path, typer.Option("--data", help="Path to the bound DataRefinery recipe (YAML).")
    ],
    plugin: Annotated[str, typer.Option("--plugin", help="Target plugin.")] = "pytorch",
    force: Annotated[
        bool, typer.Option("--force", help="Overwrite the recipe path if it exists.")
    ] = False,
) -> None:
    """Scaffold a starter recipe (FR-21)."""
    from modelfoundry.cli.commands import init_cmd

    raise typer.Exit(init_cmd.run(recipe, data, _config(ctx), plugin=plugin, force=force))


@app.command("validate")
def _cmd_validate(
    ctx: typer.Context,
    recipe: Annotated[Path, typer.Argument(help="Path to the ModelFoundry recipe (YAML).")],
) -> None:
    """Run the FR-2 static recipe checks; exit 0 if all pass, 1 otherwise."""
    from modelfoundry.cli.commands import validate_cmd

    raise typer.Exit(validate_cmd.run(recipe, _config(ctx)))


@app.command("check")
def _cmd_check(ctx: typer.Context) -> None:
    """Report environment + plugin health (FR-19)."""
    from modelfoundry.cli.commands import check_cmd

    raise typer.Exit(check_cmd.run(_config(ctx)))


@app.command("status")
def _cmd_status(
    ctx: typer.Context,
    recipe: Annotated[Path, typer.Argument(help="Path to the ModelFoundry recipe (YAML).")],
) -> None:
    """Summarize an instance's lifecycle / cache state (FR-16)."""
    from modelfoundry.cli.commands import status_cmd

    raise typer.Exit(status_cmd.run(recipe, _config(ctx)))


@app.command("materialize")
def _cmd_materialize(
    ctx: typer.Context,
    recipe: Annotated[Path, typer.Argument(help="Path to the ModelFoundry recipe (YAML).")],
    overlay: Annotated[
        list[str] | None,
        typer.Option(
            "--overlay",
            help="Recipe overlay to apply (repeatable; applied in order, last-writer-wins).",
        ),
    ] = None,
    seed: Annotated[
        int | None, typer.Option("--seed", help="Override the recipe's master seed.")
    ] = None,
    overwrite: Annotated[
        bool, typer.Option("--overwrite", help="Trash and re-materialize an existing instance.")
    ] = False,
    progress: Annotated[
        bool, typer.Option("--progress/--no-progress", help="Stream stage-level progress.")
    ] = True,
) -> None:
    """Train + optimize + evaluate end-to-end (FR-3)."""
    from modelfoundry.cli.commands import materialize_cmd

    raise typer.Exit(
        materialize_cmd.run(
            recipe,
            _config(ctx),
            overlays=overlay,
            seed=seed,
            overwrite=overwrite,
            progress=progress,
        )
    )


@app.command("report")
def _cmd_report(
    ctx: typer.Context,
    instance: Annotated[Path, typer.Argument(help="Path to a materialized ModelInstance dir.")],
) -> None:
    """Re-render an instance's report (FR-18)."""
    from modelfoundry.cli.commands import report_cmd

    raise typer.Exit(report_cmd.run(instance, _config(ctx)))


@app.command("inspect")
def _cmd_inspect(
    ctx: typer.Context,
    instance: Annotated[Path, typer.Argument(help="Path to a materialized ModelInstance dir.")],
    view: Annotated[
        str, typer.Option("--view", help="View to render (e.g. training_curves, view_manifest).")
    ],
) -> None:
    """Render an exploration-mode view of an instance (FR-17)."""
    from modelfoundry.cli.commands import inspect_cmd

    raise typer.Exit(inspect_cmd.run(instance, _config(ctx), view=view))


@app.command("clean")
def _cmd_clean(
    ctx: typer.Context,
    recipe_hash: Annotated[
        str | None,
        typer.Option("--recipe-hash", help="Remove every instance under this recipe hash."),
    ] = None,
    older_than: Annotated[
        str | None,
        typer.Option("--older-than", help="Remove instances older than this duration (e.g. 7d)."),
    ] = None,
    failed: Annotated[
        bool, typer.Option("--failed", help="Remove temp dirs carrying a FAILED marker.")
    ] = False,
    orphans: Annotated[
        bool,
        typer.Option("--orphans", help="Remove un-marked temp dirs older than --older-than."),
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Report what would be removed; remove nothing.")
    ] = False,
) -> None:
    """Cache management (FR-20)."""
    from modelfoundry.cli.commands import clean_cmd

    raise typer.Exit(
        clean_cmd.run(
            _config(ctx),
            recipe_hash=recipe_hash,
            older_than=older_than,
            failed=failed,
            orphans=orphans,
            dry_run=dry_run,
        )
    )


def invoke(typer_app: typer.Typer, argv: list[str] | None = None) -> int:
    """Run `typer_app` and return a process exit code (no `sys.exit`).

    Runs with `standalone_mode=False` so click does not exit the process itself;
    this function maps click control-flow (`--help`, usage errors, abort) and the
    domain/unexpected exceptions to the documented exit codes.
    """
    try:
        result = typer_app(args=argv, standalone_mode=False)
    except click.exceptions.Exit as exc:
        return int(exc.exit_code or _EXIT_SUCCESS)
    except click.exceptions.UsageError as exc:
        exc.show()
        return _EXIT_SYSTEM_ERROR
    except click.exceptions.Abort:
        _err_console.print("[red]Aborted.[/red]")
        return _EXIT_SIGINT
    except KeyboardInterrupt:
        _err_console.print("[red]Aborted.[/red]")
        return _EXIT_SIGINT
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        return _EXIT_SUCCESS if code is None else _EXIT_USER_ERROR
    except Exception as exc:
        _render_error(exc)
        return exit_code_for(exc)
    # `standalone_mode=False` returns the command's value; typer maps an aborted
    # run (Ctrl-C) to the 130 exit code as a return value rather than raising, so
    # honor an int result. Our verbs return `None`, so this only carries SIGINT.
    return result if isinstance(result, int) else _EXIT_SUCCESS


def main() -> int:
    """Console-script entry point — run the CLI over `sys.argv`."""
    return invoke(app)
