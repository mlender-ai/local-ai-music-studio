"""Install only this project's Codex MCP entry, preserving prior config."""

from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import tomllib

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".codex/config.toml"


def main():
    CONFIG.parent.mkdir(exist_ok=True)
    backups = ROOT / ".runtime/backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backups / f"codex-config-{stamp}.toml"
    old = CONFIG.read_text() if CONFIG.exists() else ""
    if CONFIG.exists():
        shutil.copy2(CONFIG, backup)
    else:
        backup.with_suffix(".absent.txt").write_text(
            "Project .codex/config.toml did not exist before registration. Global Codex config was not modified.\n"
        )
    section = "mcp_servers.local_music"
    # Replace only our own exact table. Keep other project settings intact.
    updated = re.sub(
        r"(?ms)^\[mcp_servers\.local_music\]\n.*?(?=^\[|\Z)", "", old
    ).rstrip()
    entry = f"""[{section}]
command = {json.dumps(str(ROOT / ".venv/bin/python"))}
args = ["-m", "app.mcp_server"]
cwd = {json.dumps(str(ROOT))}
startup_timeout_sec = 30
tool_timeout_sec = 120
"""
    updated = updated + "\n\n" + entry if updated else entry
    tomllib.loads(updated)
    CONFIG.write_text(updated)
    print("Configured:", CONFIG)
    print(
        "Prior state backup:",
        backup if backup.exists() else backup.with_suffix(".absent.txt"),
    )


if __name__ == "__main__":
    main()
