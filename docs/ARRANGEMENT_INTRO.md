# Phase 2.1 · Arrangement & Intro — 2026-11-17

구현과 실제 생성 실험은 완료했다. **음악적 개선 성공으로 판정하지 않는다.** A/B/C 모두 청취 점수는 미검증이다. B와 C의 메인 구간 RMS는 인트로보다 낮았으며, 요청한 점진적 에너지 상승의 증거를 확보하지 못했다. 사용자 청취 전 Groove & Variation Engine은 개발하지 않는다.

## 기준 상태와 보존

작업 전 fetch 후 `main` / `origin/main`은 `a5085de`, `codex/music-style-fidelity` / 원격 동일 브랜치는 `565ffd6`임을 확인했다. 후자를 기준으로 새 브랜치 `codex/arrangement-intro-2-1`에서 작업했다. 기존 Music Intent, 보컬 선택, 실제 프롬프트 미리보기, MCP, DSP와 버전 저장을 재사용한다. main과 기존 작업 브랜치는 변경하지 않는다. 기존 WAV의 SHA-256 보존 검증과 A/B 원본 보존 검증을 수행했다. WAV·DB·모델·로컬 QA JSON은 공개 Git에서 제외한다.

## 구현

- `engine/schema.py`: Music Intent 아래 선택적 `arrangement_plan`. intro → groove_entry → main_groove → 선택적 outro, 시작·종료 시각, 악기 목록, 제외/보류 악기, 전개 지시, 연속성 지시. 시간은 연속된 목표 구간이며 오디오 제어 신호가 아니다.
- `agent/arrangement.py`: 인트로/점진적 진입을 요청한 자연어를 감지하고 장르별 초안을 만든다. 펑키 디스코는 기타·하이햇 → 킥·베이스 → 브라스·신스·로즈, 하우스는 필터된 코드·하이햇 → 킥·신스 베이스 → 열린 코드·클랩·키보드, 앰비언트는 패드 → 드론 → 넓은 텍스처. 알 수 없는 장르는 일반적인 소수 악기 모티프 초안이다.
- `agent/music_intent.py`: 기존 즉시 그루브 시작 지시와 충돌하지 않도록, 계획이 있을 때는 구간별 프롬프트로 컴파일한다. 계획 없는 요청과 기존 저장된 요청의 직렬화는 유지한다. 명시적 intent 입력은 사용자의 계획으로 취급하므로 plan이 없으면 자동 추가하지 않는다. 자연어만 입력하면 초안을 자동 생성한다.
- 기존 플레이어의 **Music Intent 초안/JSON 수정**, `/api/plan`, MCP `music.plan` → `music.generate(intent=...)`가 동일한 데이터를 사용한다. 별도 LLM은 필요 없다. 규칙 기반 초안이므로 임의의 악기·시점 지시를 모두 이해하지는 않는다. 다른 진입 순서는 JSON의 계획을 수정해 검토할 수 있다.
- `scripts/compare_arrangement.py`: 기존 일반 생성 A와 계획 기반 B를 같은 조건으로 순차 생성하고 프롬프트, 설정, 시간, 메모리, 구간 측정과 미검증 청취 항목을 저장한다.
- `engine/generation/worker.py`, `scripts/repaint_arrangement.py`: 공식 Repaint를 사용한 제한적 로컬 실험 경로. 출력 저장소의 30초 이하 원본, 유효 범위와 동일 길이를 검증한다. 일반 Generate/MCP 인터페이스에는 미검증 조건부 생성 옵션을 노출하지 않았다. WAV 세 개를 이어 붙이지 않는다.
- `scripts/build_fidelity_review.py`, `app/player/server.py`: 기존 평가 페이지 생성기를 재사용한 `/arrangement` 청취 화면. 5개 수동 점수(1~5), 메모, 브라우저 저장 및 JSON 내보내기. 기존 플레이어는 `?a=VERSION&b=VERSION`으로 비교 대상을 선택할 수 있다.

## 실행 경로와 모델 제약 감사

기존 command parser → Music Intent compiler → jobs → backend → 독립 worker → 공식 `generate_music` 경로를 사용한다. 11월 16일 수정된 Turbo `shift=3.0`, CFG 1.0, 4/4 메타데이터는 실제 실행에 반영돼 있었으며 다시 구현하지 않았다.

- ACE-Step vendor: `ca1e85fe9430179831e6bc6be790c332190a3866`.
- Turbo 모델 revision: `19671f406d603126926c1b7e2adc169acbcade22`.
- Apple Silicon M5 / 24 GiB, MLX 4-bit DiT, MPS bf16 conditioning, tiled VAE.
- 8 steps, ODE, shift 3, guidance 1, batch 1, seed 42, 120 BPM, 4/4, instrumental, 30초. 5Hz LM/thinking 비활성화.
- 기존 메모리 정책 유지: 단일 생성 작업, 10 GiB child footprint, 900초 시간 제한, critical memory pressure 안전 중단, MLX 메모리 제한. 실제 피크는 아래 표 참조.

공식 [Inference API](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INFERENCE.md)의 duration 범위는 10~600초지만, 이는 이 로컬 adapter에서 45~60초 품질·메모리가 검증됐다는 의미가 아니다. 앱의 15~30초 제한을 유지한다. Cover의 `src_audio` / `audio_cover_strength`, Repaint의 `src_audio` / `repainting_start` / `repainting_end`를 확인했다. 이번에는 Repaint만 실제 실행했다. Cover와 장시간 연속 확장 생성은 미실험이며 Base 전용 작업을 Turbo에서 지원한다고 주장하지 않는다.

고정 소스의 `acestep/core/generation/handler/conditioning_text.py`는 instruction + caption + metas 전체를 **256 토큰으로 자른다**. 상세 계획을 그대로 길게 나열하는 대신 간결한 실제 caption으로 전달했다. 실행 로그를 공식 로컬 tokenizer로 확인한 A=202, B=256 토큰은 잘리지 않았다. 사용자 편집으로 길어진 프롬프트에 대한 범용 자동 압축/차단은 아직 없으며, 긴 입력은 잘릴 수 있다. 실험 JSON의 conditioning은 실제 전체 텍스트·토큰 수·유효 텍스트를 기록한다.

## 실제 A/B/C 결과

모두 30.000초, 48 kHz stereo WAV, finite, clipped_samples=0. 생성 시간은 로딩을 포함한 worker 감시 전체 시간이며, 추론만의 시간과 구분한다.

| 결과 | 방식 | 전체 시간 | peak footprint | 0–4초 RMS | 4–12초 RMS | 12–28초 RMS | 메인−인트로 |
|---|---|---:|---:|---:|---:|---:|---:|
| A | 기존 일반 Music Intent | 27.690초 | 5.098 GiB | −17.283 dBFS | −16.663 | −17.723 | −0.440 dB |
| B | 새 Arrangement Plan | 28.192초 | 5.053 GiB | −15.055 dBFS | −15.376 | −17.195 | −2.140 dB |
| C | B의 0–4초 공식 Repaint | 34.567초 | 6.116 GiB | −14.865 dBFS | −15.652 | −17.470 | −2.605 dB |

A/B는 seed·모델·추론 설정이 같은 텍스트 조건 비교다. C는 별도 오디오 조건부 실험이며 동일한 A/B 통제로 해석하면 안 된다. 서로 다른 시드 실험은 이번에는 수행하지 않았다.

A/B의 지배적 주기 후보는 약 120.2 BPM이지만 반박/배박이 모호해 단일 BPM 합격 판정을 보류했다. RMS는 악기 수나 에너지의 음악적 체감과 같지 않다. A/B/C의 28~30초는 약 −67 dBFS로 거의 무음이다. 따라서 마지막까지 펄스가 유지됐다고도 주장하지 않는다.

C의 비수정 본문 6~26초는 B와 이득 보정 후 상관계수 0.999999998, 잔차 RMS 약 0.0000176으로 매우 유사하다(전체 이득 약 0.9688). 이는 본문 맥락 보존에 관한 파형 증거다. 그러나 첫 4초가 더 조용해지거나 메인의 상대 에너지가 상승하지는 않았다. Repaint 기능의 실행 가능성은 확인했지만, 원하는 sparse intro 및 자연스러운 음악 전개를 달성했다고 판정하지 않는다. 경계 샘플 차이도 기록했으나 클릭·중복·부자연스러움의 청취 판정을 대체하지 않는다.

## 청취 파일과 실행

프로젝트 디렉터리에서:

```bash
.venv/bin/python scripts/compare_arrangement.py --run v1
.venv/bin/python scripts/repaint_arrangement.py
.venv/bin/python scripts/build_fidelity_review.py --experiment arrangement
.venv/bin/music player --port 8795
```

기존 run key는 같은 작업을 재사용한다. 새로운 A/B 실험에는 다른 `--run` 값을 사용한다. Repaint 스크립트는 이번 v1 실험용 고정 key이므로 다른 원본에 재사용하면 key 충돌 오류로 중단한다.

- [세 곡과 5항목 청취 평가](http://127.0.0.1:8795/arrangement)
- [기존 플레이어의 A/B 비교](http://127.0.0.1:8795/?a=8036194f1f864b5da11f1cc316180ec9&b=ade98c0723ab4fb8914b0729ff21523f)
- A: `outputs/originals/a3332abc9aa34e39a069715fccb61f94/271110cb-4b23-0afd-ecda-3ee13d1ec40d.wav`
- B: `outputs/originals/8eb2eff28cc645ff8ce2df61d33b56d7/bf378c69-2be6-d09e-b36e-07e8b71c1c43.wav`
- C: `outputs/originals/2bc4adad78d3463e878b3d5519918289/fff5cfa3-0e8a-2d23-ef82-c0b6787e8278.wav`
- 전체 실제 프롬프트·설정·측정: `outputs/arrangement/results.json`; A/B 원기록: `results-v1.json`; 원본 보존 체크섬: `preservation-v1.json`.

악기 등장 시점은 자동으로 검출하지 않았다. 인트로의 명확함, 점진적 악기 등장, 메인 변화, 리듬·음색 일관성, 연결 자연스러움 모두 **청취 미검증**이다. 사용자가 각 곡을 듣고 점수와 메모를 남긴 뒤, 추가 시드/프롬프트 실험 또는 다음 엔진 검토 여부를 판단한다.

## 회귀 검증

자동 테스트 39개 통과. 실제 STDIO MCP 및 Codex app-server 도구 호출(생성 재시도, DSP, 비교, 내보내기, 복원 포함) 통과. 긴 버전 목록에 대응하도록 Codex 테스트 클라이언트의 JSONL 수신 버퍼를 확장했다. 기존 Pydantic Settings lifespan annotation 경고는 남아 있으나 실제 MCP 호출은 통과했다. 파일 생성·코드 테스트·브라우저 재생 검증은 음악적 품질의 합격을 의미하지 않는다.

브라우저에서 A/B/C 각각 30초 메타데이터와 실제 재생 시간 진행, 다른 곡 재생 시 기존 곡 정지, 기존 플레이어의 A/B URL 선택을 검증했다. 15개 수동 점수는 모두 미검증으로 유지했다. 증거: `outputs/arrangement/browser-playback.json`, `outputs/arrangement/review.png`. 자연어 MCP 계획의 caption이 실제 B와 동일하고 같은 key의 구조화된 재요청이 기존 작업을 재사용하는 것도 확인했다.
