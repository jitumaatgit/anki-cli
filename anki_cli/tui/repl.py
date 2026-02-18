from __future__ import annotations

import os
import shlex
from pathlib import Path
from typing import Any

import click
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style

from anki_cli.cli.dispatcher import get_command, list_commands
from anki_cli.cli.params import preprocess_argv

_IN_REPL = False
_LOGO = r"""
               .....                     
              ........                   
             ...........                 
             ....-+-.....         .      
             ....-+++.................   
            .....+++++-................  
         .......-++++++++---+++++-.....  
     ..........-++++++++++++++++-....#   
   .........-++++++++++++++++++-....+    
  ......++++++++++++++++++++++.....#     
  .......-+++++++++++++++++++-....#      
   #-........-++++++++++++++++.....      
      #-.......-+++++++++++++++.....     
         #+....-++++++++++++++++.....    
           .....++++++-.....---+-.....   
           .....++++-.................   
            ....++-.....-+-..........    
            ..........-#     #######     
            +.......-#                   
             #-...##                     
"""


def _history_path() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    data_dir = base / "anki-cli"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "repl_history"


class _AnkiCompleter(Completer):
    """Tab-completer aware of all registered Click commands and their options."""

    def __init__(self) -> None:
        self._commands: list[str] = []
        self._options_cache: dict[str, list[str]] = {}
        self._builtins = ["help", "quit", "exit", "clear"]

    def _ensure_commands(self) -> None:
        if not self._commands:
            self._commands = list_commands()

    def _options_for(self, name: str) -> list[str]:
        if name in self._options_cache:
            return self._options_cache[name]
        cmd = get_command(name)
        if cmd is None:
            return []
        opts: list[str] = []
        for param in cmd.params:
            if isinstance(param, click.Option):
                opts.extend(param.opts)
                opts.extend(param.secondary_opts)
        self._options_cache[name] = opts
        return opts

    def _command_help(self, name: str) -> str:
        cmd = get_command(name)
        if cmd is not None and cmd.help:
            return cmd.help.strip().split("\n")[0][:50]
        return ""

    def get_completions(self, document, complete_event):  # type: ignore[override]
        text = document.text_before_cursor
        words = text.split()
        word = document.get_word_before_cursor(WORD=True)

        self._ensure_commands()

        if not words or (len(words) == 1 and not text.endswith(" ")):
            candidates = self._commands + self._builtins
            for c in candidates:
                if c.startswith(word):
                    yield Completion(
                        c,
                        start_position=-len(word),
                        display_meta=self._command_help(c),
                    )
        else:
            cmd_name = words[0]
            for opt in self._options_for(cmd_name):
                if opt.startswith(word):
                    yield Completion(opt, start_position=-len(word))


_STYLE = Style.from_dict({
    "prompt.arrow": "ansigreen bold",
})


def _invoke_command(ctx_obj: dict[str, Any], raw_args: list[str]) -> None:
    """Find the Click command and invoke it with the REPL's persistent context."""
    if not raw_args:
        return

    args = preprocess_argv(raw_args)
    cmd_name = args[0]
    cmd_args = args[1:]

    cmd = get_command(cmd_name)
    if cmd is None:
        click.echo(f"Unknown command: {cmd_name}  (try 'help')", err=True)
        return

    parent = click.Context(click.Group("anki"), obj=dict(ctx_obj))
    try:
        with parent:
            ctx = cmd.make_context(cmd_name, list(cmd_args), parent=parent)
            with ctx:
                cmd.invoke(ctx)
    except click.exceptions.Exit:
        pass
    except click.ClickException as exc:
        exc.show()
    except SystemExit:
        pass
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)


def run_repl(ctx_obj: dict[str, Any]) -> None:
    """Launch the Obsidian-style interactive shell."""
    global _IN_REPL
    if _IN_REPL:
        click.echo("Already in interactive shell.", err=True)
        return
    _IN_REPL = True

    try:
        ctx_obj = dict(ctx_obj)
        ctx_obj["format"] = "table"

        session: PromptSession[str] = PromptSession(
            history=FileHistory(str(_history_path())),
            completer=_AnkiCompleter(),
            style=_STYLE,
            complete_while_typing=False,
        )

        backend = ctx_obj.get("backend", "?")

        logo_lines = _LOGO.strip().splitlines()
        info_lines = [
            "",
            "anki-cli 0.1.0",
            "",
            f"{backend} backend",
            "",
            "Tab to complete",
            "Ctrl+R to search",
            "Ctrl+D to quit",
        ]

        max_logo_width = max(len(ln) for ln in logo_lines)
        pad = max_logo_width + 4
        for i in range(max(len(logo_lines), len(info_lines))):
            left = logo_lines[i] if i < len(logo_lines) else ""
            right = info_lines[i] if i < len(info_lines) else ""
            click.echo(f"{left:<{pad}}{right}")
        click.echo("")

        while True:
            try:
                line = session.prompt([
                    ("class:prompt.arrow", "> "),
                ])
            except (EOFError, KeyboardInterrupt):
                click.echo("")
                break

            stripped = line.strip()
            if not stripped:
                continue

            if stripped in {"quit", "exit", ":q"}:
                break

            if stripped in {"help", "?", ":help"}:
                commands = list_commands()
                click.echo("\nCommands:\n")
                for name in commands:
                    cmd = get_command(name)
                    desc = ""
                    if cmd is not None and cmd.help:
                        first = cmd.help.strip().split("\n")[0]
                        desc = f"  -- {first[:60]}"
                    click.echo(f"  {name}{desc}")
                click.echo("\n  help     Show this list")
                click.echo("  clear    Clear the screen")
                click.echo("  quit     Exit the shell\n")
                continue

            if stripped in {"clear", ":clear"}:
                click.clear()
                continue

            try:
                parts = shlex.split(stripped)
            except ValueError as exc:
                click.echo(f"Parse error: {exc}", err=True)
                continue

            _invoke_command(ctx_obj, parts)
    finally:
        _IN_REPL = False