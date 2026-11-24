"""Reference media ingestion: audio/video extraction and safe URL metadata probing."""

from __future__ import annotations

import ipaddress
import json
import os
import shutil
import socket
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import soundfile as sf

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
DIRECT_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif"}
TRANSCODE_AUDIO_EXTS = {".m4a", ".aac", ".caf", ".mp4", ".mov", ".m4v", ".webm", ".mkv"}
SUPPORTED_REFERENCE_EXTS = DIRECT_AUDIO_EXTS | TRANSCODE_AUDIO_EXTS

URL_AUDIO_REQUIRED_KO = "레퍼런스 정보는 확인했지만 실제 음향 분석을 위해 오디오 파일이 필요합니다."
URL_AUDIO_REQUIRED_EN = "Reference metadata verified, but a local audio file is required for real acoustic analysis."


def extract_audio_for_analysis(src_path: Path, cache_dir: Path, sha256: str) -> Path:
    """Return a soundfile-readable PCM/audio path without modifying the immutable source file."""
    # First try reading directly via libsndfile (covers WAV, FLAC, MP3, OGG, AIFF)
    try:
        info = sf.info(str(src_path))
        if info.frames > 0 and info.samplerate > 0:
            return src_path
    except Exception:
        pass

    cache_dir.mkdir(parents=True, exist_ok=True)
    out_wav = cache_dir / f"{sha256}.wav"
    if out_wav.is_file() and out_wav.stat().st_size > 44:
        return out_wav

    tmp_wav = cache_dir / f".{sha256}.{os.getpid()}.wav"

    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(src_path),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "48000",
            "-c:a",
            "pcm_s24le",
            str(tmp_wav),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and tmp_wav.is_file() and tmp_wav.stat().st_size > 44:
            os.replace(tmp_wav, out_wav)
            return out_wav
        if tmp_wav.exists():
            tmp_wav.unlink()

    afconvert_bin = shutil.which("afconvert")
    if afconvert_bin:
        # macOS native CoreAudio decoder handles M4A, AAC, MP4, MOV, CAF cleanly
        cmd = [
            afconvert_bin,
            "-f",
            "WAVE",
            "-d",
            "LEI24@48000",
            "-c",
            "2",
            str(src_path),
            str(tmp_wav),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and tmp_wav.is_file() and tmp_wav.stat().st_size > 44:
            os.replace(tmp_wav, out_wav)
            return out_wav
        if tmp_wav.exists():
            tmp_wav.unlink()

    raise ValueError(
        f"Unable to extract audio from '{src_path.name}'. Provide WAV/MP3/FLAC/M4A/MP4 or install ffmpeg."
    )


def _is_safe_public_url(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Only valid http:// or https:// reference URLs are supported.")
    host = parsed.hostname.lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
        raise ValueError("Local/private network URLs are not allowed for external reference lookup.")
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("Private IP addresses are not allowed.")
    except ValueError:
        # Hostname string — verify DNS doesn't resolve to loopback if online
        try:
            resolved = socket.gethostbyname(host)
            ip = ipaddress.ip_address(resolved)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                raise ValueError("Host resolves to a private network address.")
        except Exception:
            pass
    return parsed


def probe_reference_url(url: str) -> dict[str, Any]:
    """Fetch public oEmbed title/author metadata for a reference URL without fabricating audio analysis."""
    parsed = _is_safe_public_url(url)
    host = (parsed.hostname or "").lower()
    title = parsed.path.strip("/") or host
    author = ""
    provider = host

    oembed_url: str | None = None
    if "youtube.com" in host or "youtu.be" in host:
        provider = "YouTube"
        oembed_url = f"https://www.youtube.com/oembed?url={urllib.parse.quote(url, safe='')}&format=json"
    elif "soundcloud.com" in host:
        provider = "SoundCloud"
        oembed_url = f"https://soundcloud.com/oembed?format=json&url={urllib.parse.quote(url, safe='')}"

    metadata_fetched = False
    if oembed_url:
        try:
            req = urllib.request.Request(oembed_url, headers={"User-Agent": "AI-Native-DAW/0.2"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                if data.get("title"):
                    title = str(data["title"])[:140]
                    metadata_fetched = True
                if data.get("author_name"):
                    author = str(data["author_name"])[:100]
        except Exception:
            # Offline or unreachable: keep URL safely without failing
            pass

    return {
        "url": url.strip(),
        "title": title,
        "author": author,
        "provider": provider,
        "metadataFetched": metadata_fetched,
        "audioAvailable": False,
        "noticeKo": URL_AUDIO_REQUIRED_KO,
        "noticeEn": URL_AUDIO_REQUIRED_EN,
    }
