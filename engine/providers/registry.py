"""Honest AI Provider detection, selection, and optional local/user-configured LLM invocation (Phase 03-B).

Security & honesty guarantees:
- NEVER connects paid external APIs automatically or without explicit user env configuration.
- NEVER exposes API keys to the browser or writes secrets into Git / project JSON.
- Probes real local binaries / endpoints (Ollama, Claude CLI, Codex CLI) with short timeouts.
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from engine import paths as engine_paths

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


def detect_providers() -> list[dict[str, Any]]:
    """Detect all real local & configured AI Producer providers honestly."""
    ollama_ok, ollama_models = _probe_ollama()
    claude_bin = shutil.which("claude")
    codex_bin = shutil.which("codex")
    custom_key = bool(os.environ.get("DAW_LLM_API_KEY", "").strip())
    custom_url = os.environ.get("DAW_LLM_BASE_URL", "").strip()
    custom_model = os.environ.get("DAW_LLM_MODEL", "").strip() or "user-configured"
    custom_ok = custom_key and bool(custom_url)

    providers: list[ProviderInfo] = [
        ProviderInfo(
            id="local-music-director",
            name="Built-in Music Composition Director",
            kind="builtin-director",
            available=True,
            connected=True,
            costModel="free-local",
            requiresApproval=False,
            models=["music-director-v3"],
            activeModel="music-director-v3",
            capabilities=["composition_plan", "reference_binding", "midi_composition", "multitrack_arrange", "daw_edit_proposals"],
            statusNoteKo="내장 음악 이론·레퍼런스 연동 작곡 디렉터가 즉시 실행 가능합니다 (외부 API 비용 없음).",
            statusNoteEn="Built-in music-theory & reference-aware Composition Director ready offline (zero API cost).",
        ),
        ProviderInfo(
            id="mcp-external",
            name="External MCP Agent Bridge (Antigravity / Claude / Codex)",
            kind="mcp-bridge",
            available=True,
            connected=True,
            costModel="external-session",
            requiresApproval=False,
            models=["music-mcp-stdio"],
            activeModel="music-mcp-stdio",
            capabilities=["composition_plan", "daw_tools", "staged_proposals", "take_management"],
            statusNoteKo="외부 코딩/음악 에이전트가 `python -m app.mcp_server` (STDIO MCP)로 직접 DAW를 제어할 수 있습니다.",
            statusNoteEn="External agents can connect directly via `python -m app.mcp_server` (STDIO MCP).",
        ),
        ProviderInfo(
            id="ollama",
            name="Ollama Local LLM",
            kind="local-llm",
            available=ollama_ok and len(ollama_models) > 0,
            connected=ollama_ok and len(ollama_models) > 0,
            costModel="free-local",
            requiresApproval=False,
            models=ollama_models,
            activeModel=ollama_models[0] if ollama_models else None,
            capabilities=["conversation", "composition_plan_enrichment"],
            statusNoteKo=(
                f"로컬 Ollama 실행 중 ({len(ollama_models)}개 모델 감지)."
                if ollama_ok and ollama_models
                else "로컬 Ollama 서비스(127.0.0.1:11434)가 실행 중이 아니거나 설치된 모델이 없습니다."
            ),
            statusNoteEn=(
                f"Local Ollama reachable ({len(ollama_models)} model(s))."
                if ollama_ok and ollama_models
                else "Local Ollama (127.0.0.1:11434) is not running or has no models installed."
            ),
        ),
        ProviderInfo(
            id="claude-cli",
            name="Claude Code CLI (Local)",
            kind="cli-agent",
            available=bool(claude_bin),
            connected=bool(claude_bin),
            costModel="external-session",
            requiresApproval=True,
            models=["claude-cli"] if claude_bin else [],
            activeModel="claude-cli" if claude_bin else None,
            capabilities=["mcp_client", "conversation"],
            statusNoteKo=(
                f"Claude CLI 감지됨 ({claude_bin})."
                if claude_bin
                else "로컬 PATH에 `claude` CLI가 설치되어 있지 않습니다 (GUI 앱만 있거나 미설치)."
            ),
            statusNoteEn=(
                f"Claude CLI detected ({claude_bin})."
                if claude_bin
                else "`claude` CLI is not installed on local PATH."
            ),
        ),
        ProviderInfo(
            id="codex-cli",
            name="Codex CLI (Local)",
            kind="cli-agent",
            available=bool(codex_bin),
            connected=bool(codex_bin),
            costModel="external-session",
            requiresApproval=True,
            models=["codex-cli"] if codex_bin else [],
            activeModel="codex-cli" if codex_bin else None,
            capabilities=["mcp_client", "conversation"],
            statusNoteKo=(
                f"Codex CLI 감지됨 ({codex_bin})."
                if codex_bin
                else "로컬 PATH에 `codex` CLI가 설치되어 있지 않습니다."
            ),
            statusNoteEn=(
                f"Codex CLI detected ({codex_bin})."
                if codex_bin
                else "`codex` CLI is not installed on local PATH."
            ),
        ),
        ProviderInfo(
            id="custom-api",
            name="User-Configured External LLM API (Env Only)",
            kind="external-api",
            available=custom_ok,
            connected=custom_ok,
            costModel="user-configured",
            requiresApproval=True,
            models=[custom_model] if custom_ok else [],
            activeModel=custom_model if custom_ok else None,
            capabilities=["conversation", "composition_plan_enrichment"],
            statusNoteKo=(
                "사용자 환경변수(`DAW_LLM_BASE_URL` / `DAW_LLM_API_KEY`)가 설정되어 있습니다. 키는 브라우저로 전송되지 않습니다."
                if custom_ok
                else "미설정 (외부 유료 API는 사용자 승인 없이 자동 연결하지 않습니다. 사용 시 서버 환경변수 `DAW_LLM_BASE_URL`, `DAW_LLM_API_KEY`를 설정하세요)."
            ),
            statusNoteEn=(
                "User env (`DAW_LLM_BASE_URL` / `DAW_LLM_API_KEY`) configured on server. Keys are never sent to browser."
                if custom_ok
                else "Not configured (paid external APIs are never auto-connected; set server env `DAW_LLM_BASE_URL` & `DAW_LLM_API_KEY` to enable)."
            ),
        ),
    ]
    return [p.to_dict() for p in providers]


def get_active_provider_id(providers: list[dict[str, Any]] | None = None) -> str:
    provs = providers if providers is not None else detect_providers()
    cfg = _load_config()
    chosen = cfg.get("activeProviderId")
    if chosen and any(p["id"] == chosen and p["available"] for p in provs):
        return str(chosen)
    return "local-music-director"


def select_provider(provider_id: str, model: str | None = None) -> dict[str, Any]:
    provs = detect_providers()
    match = next((p for p in provs if p["id"] == provider_id), None)
    if not match:
        raise ValueError(f"Unknown provider: {provider_id}")
    if not match["available"]:
        raise ValueError(f"Provider '{provider_id}' is not currently available on this machine: {match['statusNoteEn']}")
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
    timeout_sec: float = 12.0,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Optionally call a genuinely available local Ollama or user-configured OpenAI-compatible API.

    Returns (parsed_json_or_None, provenance_meta). Never raises on unavailable provider;
    caller cleanly falls back to deterministic Music Composition Director with honest provenance.
    """
    provs = detect_providers()
    active = provider_id or get_active_provider_id(provs)
    info = next((p for p in provs if p["id"] == active), None)
    if not info or not info["available"]:
        return None, {
            "providerId": "local-music-director",
            "requestedProviderId": active,
            "model": "music-director-v3",
            "llmUsed": False,
            "note": "Requested LLM provider unavailable; used built-in Music Composition Director.",
        }

    if active == "ollama":
        model = _load_config().get("activeModel") or (info["models"][0] if info["models"] else None)
        if not model:
            return None, {"providerId": "local-music-director", "model": "music-director-v3", "llmUsed": False}
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
                content = body.get("message", {}).get("content", "")
                parsed = json.loads(content)
                return parsed, {"providerId": "ollama", "model": model, "llmUsed": True}
        except Exception as exc:
            return None, {
                "providerId": "local-music-director",
                "requestedProviderId": "ollama",
                "model": "music-director-v3",
                "llmUsed": False,
                "fallbackReason": str(exc),
            }

    if active == "custom-api":
        base = os.environ.get("DAW_LLM_BASE_URL", "").rstrip("/")
        key = os.environ.get("DAW_LLM_API_KEY", "").strip()
        model = os.environ.get("DAW_LLM_MODEL", "gpt-4o-mini").strip()
        if not base or not key:
            return None, {"providerId": "local-music-director", "model": "music-director-v3", "llmUsed": False}
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
                content = body["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                return parsed, {"providerId": "custom-api", "model": model, "llmUsed": True}
        except Exception as exc:
            return None, {
                "providerId": "local-music-director",
                "requestedProviderId": "custom-api",
                "model": "music-director-v3",
                "llmUsed": False,
                "fallbackReason": str(exc),
            }

    return None, {
        "providerId": active,
        "model": info.get("activeModel") or "music-director-v3",
        "llmUsed": False,
    }
