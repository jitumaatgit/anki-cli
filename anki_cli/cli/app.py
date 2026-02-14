from __future__ import annotations

import platform
from pathlib import Path
from typing import Any

import click

from anki_cli import __version__
from anki_cli.backends.detect import DetectionError, detect_backend


def _print_version(ctx: click.Context, param: click.Option, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"anki-cli {__version__}")
    raise click.exceptions.Exit()


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "md", "csv", "plain"], case_sensitive=False),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.option("--col", "collection_path", type=click.Path(path_type=Path), default=None)
@click.option(
    "--backend",
    type=click.Choice(["auto", "ankiconnect", "direct", "standalone"], case_sensitive=False),
    default="auto",
    show_default=True,
)
@click.option("--quiet", is_flag=True, default=False)
@click.option("--verbose", is_flag=True, default=False)
@click.option("--no-color", is_flag=True, default=False)
@click.option("--yes", is_flag=True, default=False)
@click.option("--copy", is_flag=True, default=False)
@click.option(
    "--version",
    "show_version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_print_version,
    help="Show version and exit.",
)
@click.pass_context
def main(
    ctx: click.Context,
    output_format: str,
    collection_path: Path | None,
    backend: str,
    quiet: bool,
    verbose: bool,
    no_color: bool,
    yes: bool,
    copy: bool,
) -> None:
    ctx.ensure_object(dict)

    try:
        detection = detect_backend(forced_backend=backend, col_override=collection_path)
    except DetectionError as exc:
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(exc.exit_code) from exc

    ctx.obj.update(
        {
            "format": output_format.lower(),
            "collection_path": detection.collection_path,
            "backend": detection.backend,
            "backend_reason": detection.reason,
            "quiet": quiet,
            "verbose": verbose,
            "no_color": no_color,
            "yes": yes,
            "copy": copy,
        }
    )


@main.command("version")
@click.pass_context
def version_cmd(ctx: click.Context) -> None:
    obj: dict[str, Any] = ctx.obj or {}
    backend = obj.get("backend", "auto")
    col = obj.get("collection_path")
    click.echo(f"anki-cli {__version__}")
    click.echo(f"python {platform.python_version()}")
    click.echo(f"backend {backend}")
    click.echo(f"collection {col if col else '(none)'}")


@main.command("status")
@click.pass_context
def status_cmd(ctx: click.Context) -> None:
    obj: dict[str, Any] = ctx.obj or {}
    click.echo(f"backend: {obj.get('backend', 'unknown')}")
    click.echo(f"collection: {obj.get('collection_path') or '(none)'}")
    click.echo("status: foundation in progress")