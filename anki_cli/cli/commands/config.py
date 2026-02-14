from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from anki_cli.cli.dispatcher import register_command
from anki_cli.cli.formatter import formatter_from_ctx
from anki_cli.models.config import AppConfig


@click.command("config")
@click.pass_context
def config_cmd(ctx: click.Context) -> None:
    obj: dict[str, Any] = ctx.obj or {}
    app_config = obj.get("app_config")

    if isinstance(app_config, AppConfig):
        config_data: dict[str, Any] = app_config.model_dump(mode="json")
    else:
        config_data = {}

    collection_override = obj.get("collection_override")
    config_path = obj.get("config_path")

    formatter = formatter_from_ctx(ctx)
    formatter.emit_success(
        command="config",
        data={
            "config_path": str(config_path) if config_path is not None else None,
            "effective": {
                "backend": str(obj.get("requested_backend", "auto")),
                "output_format": str(obj.get("format", "table")),
                "color": not bool(obj.get("no_color", False)),
                "collection_override": (
                    str(collection_override) if collection_override is not None else None
                ),
            },
            "config": config_data,
        },
    )


@click.command("config:path")
@click.pass_context
def config_path_cmd(ctx: click.Context) -> None:
    obj: dict[str, Any] = ctx.obj or {}

    col_path = obj.get("collection_path")
    config_path = obj.get("config_path") or Path("~/.config/anki-cli/config.toml").expanduser()
    backup_path = Path("~/.local/share/anki-cli/backups").expanduser()
    standalone_path = Path("~/.local/share/anki-cli/collection.db").expanduser()

    formatter = formatter_from_ctx(ctx)
    formatter.emit_success(
        command="config:path",
        data={
            "collection": str(col_path) if col_path is not None else "(auto)",
            "config": str(config_path),
            "backups": str(backup_path),
            "standalone_default": str(standalone_path),
        },
    )


register_command("config", config_cmd)
register_command("config:path", config_path_cmd)