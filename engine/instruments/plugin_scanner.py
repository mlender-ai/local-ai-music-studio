"""Isolated Subprocess macOS Audio Unit (AU) / VST3 / CLAP Plugin Scanner (Phase 05 · GATE 3).

Safety & Honesty Design (Sections 18, 25, 26):
- Scans `/usr/bin/auval -a` (macOS CoreAudio registry) AND filesystem plugin directories
  (`/Library/Audio/Plug-Ins/{Components,VST3,CLAP}`, `~/Library/Audio/Plug-Ins/{Components,VST3,CLAP}`).
- Validates third-party `.component` and `.vst3` files via an **isolated Python subprocess**
  (`pedalboard.load_plugin`) with a hard timeout so a broken or crashing plugin NEVER crashes the DAW server!
- Strictly separates:
  1. Built-in macOS CoreAudio system AUs (Apple stock DSP AUs)
  2. User-installed third-party AU/VST3/CLAP plugins (e.g. Surge XT, Vital, Dexed if installed by user)
  3. Unavailable Logic-exclusive / proprietary plugins (NEVER assumed available!)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PLUGIN_DIRS = [
    ("AU", Path("/Library/Audio/Plug-Ins/Components"), ".component"),
    ("AU", Path.home() / "Library" / "Audio" / "Plug-Ins" / "Components", ".component"),
    ("VST3", Path("/Library/Audio/Plug-Ins/VST3"), ".vst3"),
    ("VST3", Path.home() / "Library" / "Audio" / "Plug-Ins" / "VST3", ".vst3"),
    ("CLAP", Path("/Library/Audio/Plug-Ins/CLAP"), ".clap"),
    ("CLAP", Path.home() / "Library" / "Audio" / "Plug-Ins" / "CLAP", ".clap"),
]

_AUVAL_LINE_RE = re.compile(r"^\s*([a-z0-9]{4})\s+([a-z0-9]{4})\s+([A-Za-z0-9]{4})\s+-\s+(.+?):\s+(.+?)\s*$")


def _scan_auval_system_aus() -> list[dict[str, Any]]:
    """Inspect macOS registered Audio Units via `/usr/bin/auval -a` (read-only, timeout 8s)."""
    auval = Path("/usr/bin/auval")
    if not auval.is_file():
        return []
    try:
        proc = subprocess.run([str(auval), "-a"], capture_output=True, text=True, timeout=8)
    except Exception:
        return []
    results: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        m = _AUVAL_LINE_RE.match(line)
        if not m:
            continue
        au_type, au_sub, au_mfg, vendor, name = m.groups()
        role = (
            "instrument"
            if au_type == "aumu"
            else ("effect" if au_type in ("aufx", "aumf") else ("generator" if au_type == "augn" else "utility"))
        )
        is_apple = au_mfg.lower() == "appl" or vendor.strip().lower() == "apple"
        results.append(
            {
                "id": f"au-{au_type}-{au_sub}-{au_mfg}".lower(),
                "name": name.strip(),
                "vendor": vendor.strip(),
                "format": "AU",
                "category": role,
                "identifier": f"{au_type}:{au_sub}:{au_mfg}",
                "scope": "macos_coreaudio_system" if is_apple else "user_installed_au",
                "hostLoadableViaPedalboard": False if is_apple else True,
                "verificationStatus": "detected_system_au" if is_apple else "detected_unprobed",
            }
        )
    return results


def _probe_plugin_isolated(plugin_path: Path, timeout_sec: float = 6.0) -> dict[str, Any]:
    """Load a .component or .vst3 inside a disposable subprocess so any native C++ crash is safely contained!"""
    probe_code = (
        "import json, sys, pedalboard as pb\n"
        "p = pb.load_plugin(sys.argv[1])\n"
        "params = []\n"
        "for k, v in list(p.parameters.items())[:32]:\n"
        "    params.append({'name': k, 'min': getattr(v, 'min_value', None), 'max': getattr(v, 'max_value', None)})\n"
        "print(json.dumps({'ok': True, 'name': getattr(p, 'name', ''), 'isInstrument': bool(getattr(p, 'is_instrument', False)), 'isEffect': bool(getattr(p, 'is_effect', True)), 'parameters': params}))\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", probe_code, str(plugin_path)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout.strip().splitlines()[-1])
            return {"loadable": True, **data}
        return {"loadable": False, "error": (proc.stderr or f"Exit code {proc.returncode}")[:240]}
    except subprocess.TimeoutExpired:
        return {"loadable": False, "error": f"Plugin load timed out after {timeout_sec}s (quarantined)"}
    except Exception as exc:
        return {"loadable": False, "error": str(exc)[:240]}


def scan_host_plugins(*, probe_external: bool = True) -> dict[str, Any]:
    """Scan all macOS AU/VST3/CLAP plugins safely and report honest host plugin availability."""
    system_aus = _scan_auval_system_aus()
    bundle_plugins: list[dict[str, Any]] = []

    for fmt, directory, ext in PLUGIN_DIRS:
        if not directory.is_dir():
            continue
        for entry in sorted(directory.iterdir()):
            if entry.suffix.lower() != ext:
                continue
            item: dict[str, Any] = {
                "id": f"ext-{fmt.lower()}-{entry.stem.lower().replace(' ', '-')}",
                "name": entry.stem,
                "format": fmt,
                "path": str(entry),
                "scope": "user_installed_plugin",
                "category": "unknown",
                "verificationStatus": "detected_unprobed",
                "hostLoadableViaPedalboard": False,
                "parameters": [],
            }
            if probe_external and fmt in ("AU", "VST3"):
                res = _probe_plugin_isolated(entry)
                if res.get("loadable"):
                    item["hostLoadableViaPedalboard"] = True
                    item["verificationStatus"] = "verified_isolated_probe"
                    item["category"] = "instrument" if res.get("isInstrument") else "effect"
                    item["parameters"] = res.get("parameters", [])
                else:
                    item["verificationStatus"] = "quarantined_failed_probe"
                    item["error"] = res.get("error")
            elif fmt == "CLAP":
                item["verificationStatus"] = "detected_clap_no_host"
            bundle_plugins.append(item)

    surge_installed = any("surge" in p["name"].lower() for p in bundle_plugins)
    return {
        "systemCoreAudioAuCount": sum(1 for a in system_aus if a["scope"] == "macos_coreaudio_system"),
        "userInstalledPluginCount": len(bundle_plugins),
        "surgeXtInstalled": surge_installed,
        "logicExclusiveAvailable": False,
        "systemCoreAudioAus": system_aus,
        "userInstalledPlugins": bundle_plugins,
        "honestyNote": (
            "macOS 시스템 CoreAudio AU 목록과 사용자 설치 AU/VST3/CLAP 번들을 격리된 서브프로세스로 스캔했습니다. "
            "Logic Pro 전용 악기·플러그인은 비-Logic 환경에서 호스팅하지 않으며, 미설치 외부 플러그인은 임의로 설치됨으로 표시하지 않습니다."
        ),
    }
