"""Calls Claude through the Claude Code CLI in headless mode (`claude -p`).

This uses your Claude subscription login (Pro/Max) instead of a paid API key,
so usage counts against your plan's limits. It's meant for personal use on
your own machine.

Responses are constrained with --json-schema and validated against the
pydantic schemas in hq/.

Optional .env settings:
    CLAUDE_MODEL=...   model alias or ID (default: your Claude Code default)
    CLAUDE_EFFORT=...  low | medium | high (default: medium)
    CLAUDE_BIN=...     path to the claude executable, if it can't be found
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from .paths import ROOT

T = TypeVar("T", bound=BaseModel)
TIMEOUT_SECONDS = 600

SYSTEM_PROMPT = (
    "You are an expert technical resume and cover letter writer. "
    "Follow the user's instructions exactly and use only the information they provide."
)


def _version_key(path: Path) -> tuple:
    # anthropic.claude-code-2.1.332-darwin-arm64 -> (2, 1, 332)
    parts = path.parts[-4].split("-")
    nums = parts[2].split(".") if len(parts) > 2 else []
    return tuple(int(n) for n in nums if n.isdigit())


def find_claude() -> str:
    load_dotenv(ROOT / ".env")
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    found = shutil.which("claude")
    if found:
        return found
    home = Path.home()
    for candidate in (home / ".local/bin/claude", home / ".claude/local/claude"):
        if candidate.exists():
            return str(candidate)
    # The VS Code / Cursor extensions ship a copy of the CLI; use the newest one.
    bundled = []
    for ext_dir in (home / ".vscode/extensions", home / ".cursor/extensions"):
        bundled += ext_dir.glob("anthropic.claude-code-*/resources/native-binary/claude")
    if bundled:
        return str(max(bundled, key=_version_key))
    raise SystemExit(
        "Could not find the Claude Code CLI. Install it (https://claude.com/claude-code) "
        "or set CLAUDE_BIN in .env to the path of the claude executable."
    )


def generate(prompt: str, schema: type[T]) -> T:
    """Send one prompt and get back a validated instance of `schema`."""
    cmd = [
        find_claude(), "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(schema.model_json_schema()),
        "--system-prompt", SYSTEM_PROMPT,
        "--effort", os.environ.get("CLAUDE_EFFORT", "medium"),
        "--tools", "",               # no file, shell or web access: text in, JSON out
        "--strict-mcp-config",       # don't start any MCP servers
        "--setting-sources", "",     # ignore user/project settings and hooks
        "--disable-slash-commands",
        "--no-session-persistence",  # don't clutter your Claude Code history
    ]
    if os.environ.get("CLAUDE_MODEL"):
        cmd += ["--model", os.environ["CLAUDE_MODEL"]]

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)  # make sure the subscription login is used, not a paid key

    try:
        proc = subprocess.run(
            cmd,
            input=prompt,  # via stdin: long prompts don't fit safely in argv
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT_SECONDS,
            cwd=tempfile.gettempdir(),  # keep this repo's files and CLAUDE.md out of context
            env=env,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(f"Claude didn't answer within {TIMEOUT_SECONDS // 60} minutes. Try again.")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        detail = (proc.stderr or proc.stdout).strip()[-1500:]
        if "login" in detail.lower() or "auth" in detail.lower():
            raise SystemExit("Claude Code isn't logged in. Run `claude` once and sign in with your Pro account.")
        raise SystemExit(f"Claude Code failed (exit {proc.returncode}):\n{detail}")

    if data.get("is_error"):
        message = str(data.get("result") or data.get("subtype") or "unknown error")
        if "limit" in message.lower():
            raise SystemExit(f"You've hit your Claude plan's usage limit: {message}")
        raise SystemExit(f"Claude Code returned an error: {message}")

    output = data.get("structured_output")
    try:
        if output is not None:
            return schema.model_validate(output)
        return schema.model_validate_json(data.get("result") or "")
    except ValidationError as e:
        raise SystemExit(f"Claude's answer didn't match the expected format:\n{e}")


class _Ping(BaseModel):
    reply: str


if __name__ == "__main__":
    # Connection check: python -m hq.llm
    print(f"Using {find_claude()}")
    print(generate("Reply with the single word: ready", _Ping).reply)
