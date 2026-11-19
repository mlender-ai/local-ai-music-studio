# Local AI Music Studio · Phase 1

로컬 ACE-Step 음악 생성, 독립 DSP, 한국어 프로듀서 명령, STDIO MCP와 작은 A/B 플레이어입니다. 외부 음악 생성 API를 호출하지 않습니다. 실제 검증 결과는 [QA 보고서](docs/QA_REPORT.md)에 기록합니다.

## 음악 품질 수정 — 2026-11-16

사용자 청취에서 펑키 디스코 요청의 스타일·리듬 불일치가 보고됐습니다. 기존 기능 QA는 요청한 음악적 결과의 합격을 뜻하지 않습니다. 펑크/디스코의 영어 장르·기타·리듬 설명, 4/4 메타데이터, Turbo 권장 `shift=3.0`을 추가했습니다. [실제 재생성 비교](docs/QUALITY_FIX.md)를 참고하세요.

자연어 변환은 제한된 규칙 기반이며 범용 음악 프로듀서 수준의 이해를 보장하지 않습니다. 생성 성공 상태는 파일 생성·형식 검증 성공을 뜻합니다. 새로운 생성의 `rhythm`은 요청 BPM에 유도되지 않은 추정 후보이며 반박/배박이 모호하면 단일 BPM 판정을 하지 않습니다. `quality_review=needs_listening`으로 청취 평가를 별도로 남깁니다.

## 바로 실행

프로젝트 경로로 이동한 뒤 실행합니다.

```bash
cd '/path/to/local-ai-music-studio'
.venv/bin/music player
```

[로컬 플레이어 열기](http://127.0.0.1:8795). 브라우저에서 생성곡을 재생하고 기준 A / 수정 B를 선택할 수 있습니다. 자연어 수정은 A 전체 믹스를 대상으로 새 WAV 버전을 만듭니다. A로 복원해도 다른 버전은 남습니다.

## 음악 제작 CLI

```bash
.venv/bin/music generate '90년대 트립합. 85BPM, 묵직한 드럼, 깊은 베이스. 보컬 없는 30초 음악.' --seed 42 --wait
.venv/bin/music list
.venv/bin/music produce VERSION_ID '베이스를 좀 더 묵직하게 만들어줘.'
.venv/bin/music produce VERSION_ID '조금 더 몽환적으로 만들어줘.'
.venv/bin/music compare ORIGINAL_ID MODIFIED_ID
.venv/bin/music export VERSION_ID
.venv/bin/music restore VERSION_ID
```

`VERSION_ID`는 생성 완료 결과의 `result.id` 또는 `music list`의 `versions[].id`입니다. `generate`에서 `--wait`를 빼면 작업 ID가 즉시 반환됩니다. `music status JOB_ID`로 상태와 오류를 확인하세요. 동일 호출을 재시도할 때는 `--request-key UNIQUE_KEY`를 사용하면 중복 생성되지 않습니다.

직접 설정한 이펙트 체인:

```bash
.venv/bin/music render VERSION_ID '[{"type":"eq","mode":"low_shelf","frequency":110,"gain_db":4,"q":0.707},{"type":"compressor","threshold_db":-18,"ratio":3,"attack_ms":25,"release_ms":140,"makeup_db":1},{"type":"reverb","wet":0.2,"decay":2.5,"pre_delay_ms":25},{"type":"limiter","ceiling_db":-1}]'
```

지원 효과: `eq` (low_shelf / high_shelf / peaking), `compressor`, `reverb`, `distortion`, `limiter`. 단위는 Hz, dB, ms, seconds입니다. 효과 순서를 그대로 적용합니다. 클리핑이 발생하는 체인은 저장을 거부하므로 마지막에 리미터를 추가하세요.

보컬은 프롬프트로 지정하거나 `--vocal --lyrics '가사'`로 요청할 수 있으나, Phase 1 QA는 보컬 없는 음악을 대상으로 합니다. 멜로디·편곡·악기 교체·스템 추출은 DSP 명령으로 처리했다고 주장하지 않고 재생성이 필요하다고 반환합니다.

사용자 WAV는 `outputs/imports/`에 넣고 다음 명령으로 가져옵니다. 가져온 파일의 별도 원본 스냅샷을 저장합니다.

```bash
.venv/bin/music import imports/my-audio.wav
```

## 재설치

Apple Silicon macOS, Python 3 (bootstrap), Git, 약 10 GiB 이상의 여유 디스크가 필요합니다. M5 / 24 GiB에서 30초 생성 3곡 및 MCP 15초 생성을 검증했습니다. 16 GiB에서는 실행 중인 다른 작업과 모델 메모리에 따라 안전 중단될 수 있습니다.

```bash
./scripts/install.sh
.venv/bin/python -m pytest -q
```

프로젝트 내부에만 `.bootstrap`, `.runtime`, `.venv`, `vendor`를 생성합니다. 시스템 Python, 쉘 설정, 다른 프로젝트 환경은 수정하지 않습니다. 고정된 공식 ACE-Step 소스와 약 5.9 GiB의 필수 가중치만 받습니다. 1.7B 작곡용 LLM은 다운로드하지 않습니다. 모델 다운로드 이후 생성은 오프라인입니다.

Hugging Face 대용량 전송이 실패하거나 느릴 때, 기존 다운로드 프로세스를 종료한 후 한 번만 실행합니다. 두 다운로드 방식을 동시에 실행하지 마세요.

```bash
.venv/bin/python scripts/download_parallel.py
# 공식 ModelScope 미러도 동일한 고정 HF 체크섬으로 검증합니다.
MUSIC_DOWNLOAD_MIRROR=modelscope .venv/bin/python scripts/download_parallel.py
HF_HUB_DISABLE_XET=1 .venv/bin/python scripts/download_models.py
```

MLX/MPS 설정과 자원 제한은 [.env.example](.env.example)을 참고하세요. `.env`를 자동 로드하지 않으므로 필요한 값만 쉘에서 `export`합니다. 기본값은 MLX 4-bit DiT + MPS bf16 conditioning / tiled VAE, 단일 생성, 900초 제한, 프로세스 메모리 10 GiB입니다. 공식 가중치로부터 최초 실행 시 약 944 MB의 MLX 캐시를 프로젝트 안에 만들고 이후 재사용합니다. 최초 30초 곡 생성은 약 69초, 캐시 사용 후 두 곡은 각각 약 28초였습니다. `MUSIC_MLX_DIT=0`은 이 장비의 기존 작업 부하에서 메모리 보호에 걸렸으므로 권장하지 않습니다. CPU 단독 실행은 미검증입니다. 낮은 가용 메모리나 macOS critical pressure에서 프로젝트의 생성 자식만 종료합니다. 실패 로그는 `.runtime/logs/`에 남습니다.

`MUSIC_DATA_DIR`를 설정하면 출력 저장소를 변경할 수 있습니다. 모델은 계속 프로젝트의 `.runtime/models/checkpoints/`를 재사용합니다. 데이터 경로를 변경한 모든 프런트엔드(CLI/플레이어/MCP)는 같은 환경 변수를 사용해야 합니다.

## Codex MCP

프로젝트 전용 `.codex/config.toml`에 로컬 서버를 등록합니다. 등록 스크립트는 수정 전 상태를 `.runtime/backups/`에 기록하며 사용자 전역 Codex 설정은 변경하지 않습니다.

```bash
.venv/bin/python scripts/configure_mcp.py
codex mcp get local_music
.venv/bin/python scripts/test_mcp.py
# 설치된 Codex app-server에서도 전체 도구 호출 검증 (먼저 test_mcp.py 실행)
.venv/bin/python scripts/test_codex_mcp.py
```

새 Codex 세션에서 예를 들어 “music.generate로 30초 앰비언트를 만들고 상태를 확인해줘”, “이 버전을 music.produce로 더 몽환적으로 만들어줘”라고 요청합니다. 실제 Codex app-server의 MCP 클라이언트로 도구 호출을 검증했습니다. 로컬 호출 기록 (`docs/codex-mcp-calls.json`, 공개 저장소에는 미포함)을 참고하세요. 이미 열린 대화의 도구 목록은 자동 갱신되지 않을 수 있으므로 새 프로젝트 대화에서 사용합니다.

도구: `music.generate`, `music.apply_effect`, `music.render`, `music.compare`, `music.get_status`, `music.export`, `music.produce`, `music.list_versions`, `music.restore`.

## 파일과 문서

- `outputs/originals`: 모델 생성 원본 및 가져온 원본 스냅샷
- `outputs/processed`: 별도의 DSP 수정본
- `outputs/exports`: 내보낸 WAV
- `outputs/studio.sqlite3`: 작업과 버전 이력
- [환경 진단](docs/ENVIRONMENT.md), [구조와 한계](docs/ARCHITECTURE.md), [라이선스](docs/LICENSES.md), [의존성](docs/DEPENDENCIES.md)

모델, 가상환경, 출력 오디오와 데이터베이스는 Git에서 제외합니다. 리버브 꼬리는 원본 길이 보존을 위해 잘립니다. 리미터는 샘플 피크 제한이며 방송용 true-peak 인증은 없습니다. 곡의 미적 품질은 파일 유효성이나 수치 검사만으로 보증하지 않습니다.

생성 WAV, 모델, 개인 경로가 포함된 QA JSON과 브라우저 스크린샷은 로컬에만 보관됩니다. QA 보고서의 해당 파일 링크는 직접 검증을 실행한 환경에서 사용할 수 있습니다.

## Music Intent와 청취 비교

[스타일 충실도 개선 및 사용법](docs/STYLE_FIDELITY.md). 보컬 여부가 불명확한 요청은 생성 유형 선택이 필요합니다. 플레이어에서 Music Intent 초안을 만들어 수정하거나 Codex의 `music.plan` → `music.generate(intent=...)`를 사용하세요. [로컬 A/B 청취 평가](http://127.0.0.1:8795/fidelity)는 실제 비교 실험 실행 후 사용할 수 있습니다. 점수는 자동 부여하지 않습니다.

## Phase 2.1 · 도입부와 구간 전개

자연어 인트로 요청에 장르별 Arrangement Plan을 추가했습니다. [구현·A/B/C 실험 보고서](docs/ARRANGEMENT_INTRO.md)와 [로컬 청취 평가](http://127.0.0.1:8795/arrangement)를 확인하세요. 같은 조건의 30초 A/B 및 공식 Repaint 실험 C를 실제 생성했으나, 음악적 개선은 청취 미검증입니다. 길이 제한과 메모리 보호 정책은 유지합니다.

## AI Producer V2 · Gate 1 / 2 실험

[기술 검토·구현·실제 측정 보고서](docs/PRODUCER_V2.md). 기존 기능을 유지하면서 검증 가능한 Music Plan, 실제 키 조건, 4/8-bit 비교, 3장르 청취 평가를 추가했습니다. [조건을 가린 청취 비교](http://127.0.0.1:8795/producer)에서 평가하세요. 음악적 개선은 사용자 청취 승인 전 미검증입니다.

플레이어의 기획 방식에서 `Music Director · 실험`을 선택하면 명시적 프리셋 초안으로 독립 실행됩니다. Codex는 `music.director_plan`에 Music Plan JSON을 전달하고 `music.generate(music_plan=...)`로 생성할 수 있습니다. 추가 LLM/유료 API는 필수가 아닙니다. 독립 트랙이나 트랙별 믹싱을 구현한 상태는 아닙니다. 60초는 별도 실험 결과만 제공하며 일반 생성 길이는 15~30초를 유지합니다.

[Session Engine V1 제작·재현 보고서](docs/SESSION_ENGINE.md) · [소울 세션의 A/B/C/D와 독립 트랙 청취](http://127.0.0.1:8795/session-lab)
