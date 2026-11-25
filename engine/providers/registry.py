"""Honest AI Provider detection, real Claude Code CLI / Ollama / Env API execution (Phase 03.1 · Section 4).

Key Phase 03.1 upgrades:
- Discovers native macOS Claude Code binary (`shutil.which("claude")` OR official Claude Desktop bundled
  `~/Library/Application Support/Claude/claude-code/*/*/claude.app/Contents/MacOS/claude`) with ZERO hardcoded personal paths.
- Separates 4 honest Provider states: `uninstalled`, `detected`, `authenticated`, `verified`!
- Strictly isolates AI music production from software development (Section 4.3): invokes Claude CLI with
  `--tools "" --no-session-persistence --output-format json` so it can NEVER execute terminal commands, edit code, or download models.
- Never reports MCP bridge as "connected" merely because the MCP server code exists (`ready_for_client` vs active session).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from engine import paths as engine_paths
from engine.daw_workspace.schema import utc_now_iso

from .base import ProviderInfo


def _config_path() -> Path:
    d = engine_paths.DATA / "daw"
    d.mkdir(parents=True, exist_ok=True)
    return d / "provider_config.json"


def _load_config() -> dict[str, Any]:
    p = _config_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config(cfg: dict[str, Any]) -> None:
    p = _config_path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def _discover_claude_cli() -> Path | None:
    """Locate official native Claude Code CLI on PATH or macOS Claude Desktop bundle."""
    env_bin = os.environ.get("CLAUDE_CLI_BIN", "").strip()
    if env_bin:
        p = Path(env_bin).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return p
    on_path = shutil.which("claude")
    if on_path:
        return Path(on_path)
    # Official macOS Claude Desktop bundled Claude Code binary (sorted newest version first)
    app_support = Path.home() / "Library" / "Application Support" / "Claude" / "claude-code"
    if app_support.is_dir():
        candidates = sorted(
            app_support.glob("*/*/claude.app/Contents/MacOS/claude"),
            reverse=True,
        )
        for cand in candidates:
            if cand.is_file() and os.access(cand, os.X_OK):
                return cand
    return None


def _probe_claude_auth(binary: Path) -> tuple[bool, str | None]:
    """Check official `claude auth status` without accessing or reading credentials directly."""
    try:
        proc = subprocess.run(
            [str(binary), "auth", "status"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if proc.returncode != 0:
            return False, None
        raw = proc.stdout.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return False, None
        data = json.loads(m.group(0))
        if data.get("loggedIn") is True:
            return True, str(data.get("subscriptionType") or data.get("authMethod") or "claude.ai")
        return False, None
    except Exception:
        return False, None


def _probe_ollama() -> tuple[bool, list[str]]:
    url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=0.6) as resp:
            if resp.status != 200:
                return False, []
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
            return True, models
    except Exception:
        return False, []


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Safely parse strict JSON or fenced ```json ... ``` object from LLM response."""
    if not text:
        return None
    cleaned = text.strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(cleaned[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return None


def detect_providers() -> list[dict[str, Any]]:
    """Detect all real local & configured AI Producer providers with 4-state honesty."""
    cfg = _load_config()
    verified_map: dict[str, str] = dict(cfg.get("verifiedProviders") or {})

    ollama_ok, ollama_models = _probe_ollama()
    claude_bin = _discover_claude_cli()
    claude_authed, claude_sub = _probe_claude_auth(claude_bin) if claude_bin else (False, None)
    codex_bin = shutil.which("codex")

    custom_key = bool(os.environ.get("DAW_LLM_API_KEY", "").strip())
    custom_url = os.environ.get("DAW_LLM_BASE_URL", "").strip()
    custom_model = os.environ.get("DAW_LLM_MODEL", "").strip() or "user-configured"
    custom_ok = custom_key and bool(custom_url)

    def claude_state() -> str:
        if not claude_bin:
            return "uninstalled"
        if not claude_authed:
            return "detected"
        return "verified" if "claude-cli" in verified_map else "authenticated"

    c_state = claude_state()

    providers: list[dict[str, Any]] = [
        {
            **ProviderInfo(
                id="claude-cli",
                name="Claude Code (Local Authenticated CLI)",
                kind="cli-agent",
                available=bool(claude_bin and claude_authed),
                connected=bool(claude_bin and claude_authed),
                costModel="existing-subscription",
                requiresApproval=False,
                models=["haiku", "sonnet"] if (claude_bin and claude_authed) else [],
                activeModel="haiku" if (claude_bin and claude_authed) else None,
                capabilities=[
                    "natural_language_composition",
                    "structured_chords_and_motif",
                    "arrangement_edit_planning",
                    "conversational_producer",
                    "no_shell_tools_isolated",
                ],
                statusNoteKo=(
                    f"로컬 Claude Code 인증됨({claude_sub}, 상태: {c_state}). `--tools ''` 격리 모드로 음악 제작 JSON만 생성하며 터미널/코드 수정은 차단됩니다."
                    if (claude_bin and claude_authed)
                    else (
                        "Claude Code 바이너리는 발견되었으나 로그인되지 않았습니다."
                        if claude_bin
                        else "로컬 Claude Code CLI가 설치되어 있지 않습니다."
                    )
                ),
                statusNoteEn=(
                    f"Local Claude Code authenticated ({claude_sub}, state: {c_state}). Runs isolated (`--tools ''`) for structured music JSON only."
                    if (claude_bin and claude_authed)
                    else ("Claude binary found but not logged in." if claude_bin else "Claude Code CLI not found.")
                ),
            ).to_dict(),
            "providerState": c_state,
            "lastVerifiedAt": verified_map.get("claude-cli"),
        },
        {
            **ProviderInfo(
                id="local-music-director",
                name="Built-in Music Composition Director (Offline Fallback)",
                kind="builtin-director",
                available=True,
                connected=True,
                costModel="free-local",
                requiresApproval=False,
                models=["music-director-v4"],
                activeModel="music-director-v4",
                capabilities=["composition_plan", "reference_binding", "midi_variation", "daw_edit_proposals"],
                statusNoteKo="오프라인 내장 음악 이론·편곡 디렉터 (항상 실행 가능, 외부 API 비용 없음).",
                statusNoteEn="Offline deterministic music-theory & arrangement director (always available, zero cost).",
            ).to_dict(),
            "providerState": "verified",
            "lastVerifiedAt": verified_map.get("local-music-director") or "builtin",
        },
        {
            **ProviderInfo(
                id="mcp-external",
                name="External MCP Agent Bridge (STDIO Server Ready)",
                kind="mcp-bridge",
                available=True,
                connected=False,  # Honest: server is ready, not actively attached until external client calls!
                costModel="external-session",
                requiresApproval=False,
                models=["music-mcp-stdio"],
                activeModel="music-mcp-stdio",
                capabilities=["daw_tools", "staged_proposals", "take_management"],
                statusNoteKo="MCP STDIO 서버 준비 완료 (`python -m app.mcp_server`). 외부 에이전트가 실제로 접속할 때 연동됩니다.",
                statusNoteEn="MCP STDIO server ready (`python -m app.mcp_server`). Not counted as connected until an external client attaches.",
            ).to_dict(),
            "providerState": "ready_for_client",
            "lastVerifiedAt": verified_map.get("mcp-external"),
        },
        {
            **ProviderInfo(
                id="ollama",
                name="Ollama Local LLM",
                kind="local-llm",
                available=ollama_ok and len(ollama_models) > 0,
                connected=ollama_ok and len(ollama_models) > 0,
                costModel="free-local",
                requiresApproval=False,
                models=ollama_models,
                activeModel=ollama_models[0] if ollama_models else None,
                capabilities=["natural_language_composition", "arrangement_edit_planning"],
                statusNoteKo=(
                    f"로컬 Ollama 실행 중 ({len(ollama_models)}개 모델 감지)."
                    if ollama_ok and ollama_models
                    else "로컬 Ollama 서비스(127.0.0.1:11434)가 실행 중이 아니거나 모델이 없습니다."
                ),
                statusNoteEn=(
                    f"Local Ollama reachable ({len(ollama_models)} model(s))."
                    if ollama_ok and ollama_models
                    else "Local Ollama (127.0.0.1:11434) is not running or has no models."
                ),
            ).to_dict(),
            "providerState": ("verified" if "ollama" in verified_map else "authenticated") if (ollama_ok and ollama_models) else "uninstalled",
            "lastVerifiedAt": verified_map.get("ollama"),
        },
        {
            **ProviderInfo(
                id="codex-cli",
                name="Codex CLI (Local)",
                kind="cli-agent",
                available=bool(codex_bin),
                connected=False,
                costModel="external-session",
                requiresApproval=True,
                models=["codex-cli"] if codex_bin else [],
                activeModel="codex-cli" if codex_bin else None,
                capabilities=["mcp_client"],
                statusNoteKo=(
                    "Codex CLI 바이너리 감지됨."
                    if codex_bin
                    else "로컬 PATH에 `codex` CLI가 설치되어 있지 않습니다."
                ),
                statusNoteEn=(
                    "Codex CLI binary detected."
                    if codex_bin
                    else "`codex` CLI is not installed on local PATH."
                ),
            ).to_dict(),
            "providerState": "detected" if codex_bin else "uninstalled",
            "lastVerifiedAt": verified_map.get("codex-cli"),
        },
        {
            **ProviderInfo(
                id="custom-api",
                name="User-Configured External LLM API (Env Only)",
                kind="external-api",
                available=custom_ok,
                connected=custom_ok,
                costModel="user-configured",
                requiresApproval=True,
                models=[custom_model] if custom_ok else [],
                activeModel=custom_model if custom_ok else None,
                capabilities=["natural_language_composition", "arrangement_edit_planning"],
                statusNoteKo=(
                    "사용자 환경변수(`DAW_LLM_BASE_URL` / `DAW_LLM_API_KEY`) 설정됨 (키 비노출)."
                    if custom_ok
                    else "미설정 (승인 없는 유료 API 연결 금지; 사용 시 서버 환경변수로만 설정)."
                ),
                statusNoteEn=(
                    "User env (`DAW_LLM_BASE_URL` / `DAW_LLM_API_KEY`) configured on server."
                    if custom_ok
                    else "Not configured (never auto-connects paid APIs without user env config)."
                ),
            ).to_dict(),
            "providerState": ("verified" if "custom-api" in verified_map else "authenticated") if custom_ok else "uninstalled",
            "lastVerifiedAt": verified_map.get("custom-api"),
        },
    ]
    return providers


def _mark_provider_verified(provider_id: str) -> None:
    try:
        cfg = _load_config()
        vm = dict(cfg.get("verifiedProviders") or {})
        vm[provider_id] = utc_now_iso()
        cfg["verifiedProviders"] = vm
        _save_config(cfg)
    except Exception:
        pass


def get_active_provider_id(providers: list[dict[str, Any]] | None = None) -> str:
    provs = providers if providers is not None else detect_providers()
    cfg = _load_config()
    chosen = cfg.get("activeProviderId")
    if chosen and any(p["id"] == chosen and p["available"] for p in provs):
        return str(chosen)
    # Prefer real authenticated local AI provider when available (never paid API without explicit choice)
    for preferred in ("claude-cli", "ollama", "local-music-director"):
        if any(p["id"] == preferred and p["available"] for p in provs):
            return preferred
    return "local-music-director"


def select_provider(provider_id: str, model: str | None = None) -> dict[str, Any]:
    provs = detect_providers()
    match = next((p for p in provs if p["id"] == provider_id), None)
    if not match:
        raise ValueError(f"Unknown provider: {provider_id}")
    if not match["available"]:
        raise ValueError(f"Provider '{provider_id}' is not currently available: {match['statusNoteEn']}")
    cfg = _load_config()
    cfg["activeProviderId"] = provider_id
    if model:
        cfg["activeModel"] = model
    _save_config(cfg)
    return get_provider_summary()


def get_provider_summary() -> dict[str, Any]:
    provs = detect_providers()
    active_id = get_active_provider_id(provs)
    cfg = _load_config()
    return {
        "activeProviderId": active_id,
        "activeModel": cfg.get("activeModel"),
        "providers": provs,
    }


def invoke_llm_json(
    system_prompt: str,
    user_prompt: str,
    provider_id: str | None = None,
    timeout_sec: float = 18.0,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Invoke a real authenticated AI Provider (`claude-cli`, `ollama`, `custom-api`) in strict JSON-only mode.

    When running inside pytest without `DAW_ENABLE_LIVE_LLM_IN_TESTS=1`, skips live external CLI latency
    unless `provider_id` is explicitly requested by a live provider integration test.
    """
    provs = detect_providers()
    active = provider_id or get_active_provider_id(provs)

    # Keep unit tests fast & deterministic unless live LLM is explicitly requested
    if os.environ.get("PYTEST_CURRENT_TEST") and not provider_id and os.environ.get("DAW_ENABLE_LIVE_LLM_IN_TESTS") != "1":
        return None, {
            "providerId": "local-music-director",
            "detectedPrimaryProvider": active,
            "model": "music-director-v4",
            "llmUsed": False,
            "note": "Deterministic test mode (pass explicit provider_id or DAW_ENABLE_LIVE_LLM_IN_TESTS=1 for live LLM).",
        }

    info = next((p for p in provs if p["id"] == active), None)
    if not info or not info["available"]:
        return None, {
            "providerId": "local-music-director",
            "requestedProviderId": active,
            "model": "music-director-v4",
            "llmUsed": False,
            "note": "Requested provider unavailable; used built-in Music Composition Director.",
        }

    if active == "claude-cli":
        claude_bin = _discover_claude_cli()
        if not claude_bin:
            return None, {"providerId": "local-music-director", "model": "music-director-v4", "llmUsed": False}
        model = _load_config().get("activeModel") or "haiku"
        if model not in ("haiku", "sonnet", "opus"):
            model = "haiku"
        combined_prompt = (
            f"{system_prompt}\n\n"
            f"STRICT OUTPUT RULE: Respond with ONLY a single valid JSON object. No markdown fences, no commentary.\n\n"
            f"{user_prompt}"
        )
        try:
            proc = subprocess.run(
                [
                    str(claude_bin),
                    "-p",
                    combined_prompt,
                    "--output-format",
                    "json",
                    "--tools",
                    "",  # ZERO terminal/filesystem/code-edit tools (Section 4.3 isolation!)
                    "--no-session-persistence",
                    "--model",
                    model,
                ],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(proc.stderr[-300:] or f"claude exited {proc.returncode}")
            envelope = json.loads(proc.stdout.strip())
            if envelope.get("is_error"):
                raise RuntimeError(str(envelope.get("result") or "Claude CLI returned error"))
            result_text = str(envelope.get("result") or "")
            parsed = _extract_json_object(result_text)
            if not isinstance(parsed, dict):
                raise ValueError("Claude CLI did not return a JSON object")
            _mark_provider_verified("claude-cli")
            canonical_model = next(iter((envelope.get("modelUsage") or {}).keys()), model)
            return parsed, {
                "providerId": "claude-cli",
                "model": canonical_model,
                "llmUsed": True,
                "durationMs": envelope.get("duration_ms"),
                "isolatedNoTools": True,
            }
        except Exception as exc:
            return None, {
                "providerId": "local-music-director",
                "requestedProviderId": "claude-cli",
                "model": "music-director-v4",
                "llmUsed": False,
                "fallbackReason": str(exc),
            }

    if active == "ollama":
        model = _load_config().get("activeModel") or (info["models"][0] if info["models"] else None)
        if not model:
            return None, {"providerId": "local-music-director", "model": "music-director-v4", "llmUsed": False}
        url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
        payload = json.dumps(
            {
                "model": model,
                "format": "json",
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                parsed = _extract_json_object(body.get("message", {}).get("content", ""))
                if isinstance(parsed, dict):
                    _mark_provider_verified("ollama")
                    return parsed, {"providerId": "ollama", "model": model, "llmUsed": True}
        except Exception as exc:
            return None, {
                "providerId": "local-music-director",
                "requestedProviderId": "ollama",
                "model": "music-director-v4",
                "llmUsed": False,
                "fallbackReason": str(exc),
            }

    if active == "custom-api":
        base = os.environ.get("DAW_LLM_BASE_URL", "").rstrip("/")
        key = os.environ.get("DAW_LLM_API_KEY", "").strip()
        model = os.environ.get("DAW_LLM_MODEL", "gpt-4o-mini").strip()
        if not base or not key:
            return None, {"providerId": "local-music-director", "model": "music-director-v4", "llmUsed": False}
        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        payload = json.dumps(
            {
                "model": model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode("utf-8")
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                parsed = _extract_json_object(body["choices"][0]["message"]["content"])
                if isinstance(parsed, dict):
                    _mark_provider_verified("custom-api")
                    return parsed, {"providerId": "custom-api", "model": model, "llmUsed": True}
        except Exception as exc:
            return None, {
                "providerId": "local-music-director",
                "requestedProviderId": "custom-api",
                "model": "music-director-v4",
                "llmUsed": False,
                "fallbackReason": str(exc),
            }

    return None, {
        "providerId": active,
        "model": info.get("activeModel") or "music-director-v4",
        "llmUsed": False,
    }
