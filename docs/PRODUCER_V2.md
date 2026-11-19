# AI Music Producer V2 — Gate 1 / Gate 2

작업일: 2026-11-19. **구현·기술 실험과 음악적 승인은 별개다. 사용자 청취 승인 전 제품 품질 개선 완료로 판정하지 않는다.**

## 기준 상태와 범위

작업 전 원격 fetch, clean 상태 및 브랜치를 확인했다. main `a5085de`, Music Intent 브랜치 `565ffd6`, Arrangement 브랜치 `386de3e`. 새 `codex/music-producer-v2`는 Arrangement 브랜치에서 시작해 앞선 기능을 모두 포함한다. main에 자동 병합하지 않는다. 기존 WAV 해시, DB 이력, 모델 캐시를 보존한다. 기존 버전 위에 새 생성 버전을 추가하며 오디오·DB·캐시는 Git에 올리지 않는다.

이번 구현은 Gate 1의 **정밀도 기여도 실험**, Gate 2의 **검증 가능한 기획 계약과 추론 연결**이다. Gate 3의 60초 실험을 별도로 수행한다. Session Engine, 독립 악기 트랙, 스템 분리, 트랙별 믹싱은 구현하지 않았다.

## 병목과 아키텍처

기존 Music Intent/Arrangement도 실제로는 하나의 caption으로 축약되어 stereo full mix를 생성한다. 구간별 악기 진입, 코드 보이싱, 세션 변주는 정확한 제어 신호가 아니다. 기존 Phase 2.1 A/B/C는 메인의 상대 RMS 상승도 확인하지 못했다. 이 증거는 현재 방식의 제약을 보여주지만 원인이 4-bit 양자화라는 증거는 아니다.

새 경로:

```text
Natural language / Codex Music Plan JSON
→ Music Director: schema 검증 + 명시적 preset fallback
→ capability-aware compiler: 실제 caption + 전체 256-token 예산 검사
→ 기존 단일 작업 큐 / 메모리 supervisor
→ 선택적 Turbo 4-bit 또는 8-bit decoder
→ stereo model_full_mix + 실제 설정/계획/자동 지표
→ 무작위 조건 라벨 청취 비교 + 수동 점수
```

후속 경계는 Music Plan → composition/events → 검증된 generation/instrument adapter → source provenance → session/mix → 평가다. 지금 실행되는 것은 full-mix adapter뿐이다. `GenerationBackend` 경계를 유지하므로 다른 모델을 연결할 수 있으나 설치되지 않은 모델을 호출하는 가짜 adapter는 만들지 않았다.

Music Plan은 rhythm(BPM, 박자, 패턴, 악센트·쉼), harmony(키, 진행, 보이싱), sessions(악기 역할과 상호작용), events(곡 길이에 대한 상대 시점과 음악적 사건), production(톤·다이내믹·공간), exclusions, vocal mode로 구성한다. 키·BPM·박자는 모델의 실제 파라미터로 전달한다. 이 역시 생성 결과의 정확도를 보장하지 않는다. 나머지는 `soft_text_targets`이며 `not_executed`에 독립 트랙·트랙별 DSP·정확한 음표/시각을 명시한다.

단순 장르 문구 추가만이 변경의 전부는 아니다. 스키마 검증, 초과 입력 거부, 실제 키 메타데이터, 정밀도 선택 및 캐시 분리, 실험 조건 분리, 수동 평가 연결을 추가했다. 그러나 **현재 오디오 제어 자체는 여전히 텍스트/메타데이터 조건부 전체 믹스 생성**이다. 이를 멀티트랙 프로듀서 완성이라고 부르지 않는다.

## Gate 1 — 공식 자료와 후보 검토

현재 소스 pin은 `ca1e85fe9430179831e6bc6be790c332190a3866`, 공식 weights pin은 `19671f406d603126926c1b7e2adc169acbcade22`. upstream main의 새 기능은 이 고정 adapter에서 검증됐다고 간주하지 않는다.

| 후보 | 문서상 구조/자원·라이선스 | 이번 판정 |
|---|---|---|
| 현행 Turbo 4-bit | 2B DiT, MLX Linear affine 4-bit, group 64. 공식 weights에서 로컬 변환 | 기준 A/B 실제 실행 |
| 같은 Turbo 8-bit | 같은 원본 가중치·비선형 층·conditioning, Linear만 8-bit | C 실제 실행. 정밀도 효과 분리, 음악 품질 우위 미검증 |
| ACE-Step 2B SFT / Base | 비증류 구성, 더 많은 스텝/CFG; Base의 추가 작업은 Turbo에 자동 적용 불가. 공식 bf16 DiT weights 추정 4.7 GB + text encoder 1.2 + VAE .33 및 activation | 검토만. 새 weights 미다운로드, 해당 MLX 변환 호환성/피크 RAM/오디오 미검증 |
| ACE-Step XL | 더 큰 DiT, 공식 추정 weights 약 9 GB부터, conditioning/activation 별도 | 10 GiB child 제한과 24 GB 공유 메모리에서 우선 후보 아님. 미다운로드 |
| ACE-Step 5Hz LM | 단순 caption 변환뿐 아니라 음악 semantic code hint를 만들 수 있는 별도 LM. bf16 weights+4k KV 추정: 0.6B 1.2+.6 GB, 1.7B 3.4+1 GB, 4B 8+1.6 GB | 검토만. 다음 비교 우선 후보는 0.6B. 이번에는 off 유지, 성능/품질 결과 없음 |
| Turbo bf16 MPS | 양자화 없는 원본, 기존 QA에서 메모리 보호 중단 경험 있음 | 이번에는 8-bit로 정밀도 비교. bf16 재실행하지 않았고 제한도 완화하지 않음 |
| MusicGen | autoregressive audio tokens; medium 약1.5B에 공식 권장 GPU memory 16 GB. 코드 MIT, weights CC-BY-NC 4.0 | 상용 제품 기본 모델로 단순 채택하지 않음. 로컬 속도·RAM·품질 미측정 |
| Stable Audio Open 1.0 | autoencoder+T5 conditioning+diffusion, 최대47초/44.1kHz stereo, Stable Audio Community license 및 접근 조건 | 루프/텍스처 후보. 60초 곡 구조의 직접 대체로 간주하지 않음. 동의·다운로드·실행 없음, 이 Mac의 요구 메모리 미확인 |

공식 출처: [ACE-Step 설치/구성](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INSTALL.md), [메모리 추정 코드](https://github.com/ace-step/ACE-Step-1.5/blob/main/acestep/gpu_config.py), [공식 MIT 모델 카드](https://huggingface.co/ACE-Step/Ace-Step1.5), [MusicGen 문서](https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md), [MusicGen 라이선스](https://github.com/facebookresearch/audiocraft/blob/main/model_cards/MUSICGEN_MODEL_CARD.md), [Stable Audio 모델 카드](https://huggingface.co/stabilityai/stable-audio-open-1.0).

위 메모리 추정은 공식 CUDA/weights 계산이며 Apple unified memory의 측정 피크가 아니다. 고정 소스/공식 자료를 검토한 뒤 이번에는 **새 모델 weights 다운로드 0개**로 실험 범위를 제한했다. 8-bit derived cache는 약1.7 GiB이며 기존 944 MiB 4-bit cache는 그대로다.

## Gate 2 — Codex와 독립 앱

- `music.director_plan(prompt, music_plan=...)`: Codex가 만든 JSON 검증/미리보기. `music.generate(music_plan=..., inference_profile=...)`로 연결한다.
- `MusicPlan.model_json_schema()`가 외부 planner 계약이다. 잘못된 키, 중복/역순 사건, 과도한 필드 길이, Music Intent와 Plan 동시 지정은 거부한다.
- 독립 앱에서는 기획 방식 `Music Director · 실험`을 고르면 자연어에서 세 장르의 명시적 preset 초안을 제공한다. LLM이라고 표시하지 않는다. 자연어의 모든 세부 조건을 이해하지 못하며, 지원하지 않는 장르/악기 제외는 오류와 기존 Music Intent 대안을 안내한다. JSON 수정은 고급 선택 기능이다.
- 경량 로컬 LLM 후보는 [Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B)(Apache-2.0). 모델 저장공간은 bf16 파라미터만 계산하면 대략1.2GB이며 runtime/KV는 추가된다. 한국어 음악 기획 정확성, JSON 유효성, 음악 효과가 아직 검증되지 않아 설치하지 않았다. 설치된 Qwen3-Embedding-0.6B는 텍스트 임베딩 모델이며 기획용 대화 LLM으로 재사용할 수 없다.
- `examples/director/*.json`은 이 Codex 작업에서 설계한 세 계획이다. fallback은 이 계획을 명시적으로 재사용하며, 고정 오디오 루프를 출력하지 않는다. 실제 음악은 seed를 받아 모델이 새로 생성한다.

기획 입력을 풍성하게 만드는 것과 음악적으로 구현하는 것을 구분한다. 256토큰은 instruction/caption/metas 전체의 제한이다. Director는 토큰 수를 미리 검증하고 초과 시 오류로 끝낸다. 실제 worker 로그와 preflight text 일치도 실험에서 검사한다. 기존 Music Intent 경로는 호환성을 위해 변경하지 않았으므로 긴 입력의 기존 truncation 가능성은 남는다.

## 실제 비교 설계와 재현

세 장르 각각 A=기존 Music Intent(기존 Arrangement 동작 포함)+4-bit, B=새 Director+4-bit, C=같은 Director+8-bit. 모두 30초, seed42, instrumental, 4/4. soul116BPM, house122BPM, ambient72BPM. steps8/ODE/shift3/CFG1/thinking false, batch1. B/C는 caption·key·BPM·duration·seed가 같고 양자화 비트만 바뀐다. A/B는 기획을 바꾸므로 key conditioning도 기획 변경의 일부다. 이는 새로운 모델 family의 비교가 아니라 **같은 모델의 추론 정밀도 비교**다. 하나의 seed만으로 일반화하지 않는다.

60초 D는 별도 길이 실험이다. 일반 API/UI/CLI `Generate` 제한은 여전히15~30초다. 제한은 upstream 모델이 아니라 앱의 schema/parser에 있다. 내부 실험 seam으로만 60초를 요청하고 같은 메모리 보호·길이/파일 검증을 적용했다. 무조건적인 WAV 이어붙이기는 없다. 성공해도 반복/전개는 청취 확인 전 합격이 아니다.

```bash
.venv/bin/python scripts/compare_producer.py --run v1 --long
.venv/bin/python scripts/build_producer_review.py
.venv/bin/music player --port 8795
# 구조화된 Codex/user 계획:
.venv/bin/music generate '부드러운 소울 디스코' --music-plan examples/director/soul.json --instrumental --wait
```

동일 run key는 기존 결과를 재사용한다. 계획을 바꿨으면 다른 run 이름을 사용한다. JSON의 job/metadata에 실제 caption·model revision·inference·elapsed/total time·peak footprint·WAV 경로가 저장된다. `outputs/producer/results.json`, `preservation-v1.json`과 worker logs는 로컬에 보존한다.

[청취 비교](http://127.0.0.1:8795/producer): 장르별 샘플 순서를 무작위화하고 고정 저장한다. 모델/기획 조건은 버튼으로 공개하기 전 숨긴다. 이는 라벨을 가린 비교이며 개발자 도구까지 막는 엄격한 이중맹검은 아니다. 기본 재생 감쇠는 전체 RMS 약 −22dBFS(증폭 없이 감쇠만)이며 LUFS 정규화가 아니다. 원본 WAV는 변경하지 않고 상대 볼륨만 조정한다. 수동 10항목 점수/메모는 localStorage 및 JSON으로 저장한다.

## 음악적 평가와 후속 결정

그루브·전개·화성·공간·악기 자연스러움의 개선은 **모두 청취 미검증**이다. 클리핑, RMS, 피크, 1초 에너지, 활성 구간 RMS 분포, 스테레오 상관도/side-mid ratio는 기술 참고 지표다. 코드 진행·악기 등장·정확한 BPM이나 실제 뮤지션 같은 느낌을 자동 검증하지 않는다.

1. 먼저 세 장르 A/B/C 블라인드 청취를 받고, 특히 B/C 차이가 반복적으로 들리는지 확인한다. 기본 설정은 여전히4-bit이다.
2. 기획만의 개선이 약하면 5Hz 0.6B LM의 semantic-code 조건 비교를 다음 작은 실험으로 수행한다. 그 다음 2B SFT를 한 구성만 검증한다. 현재 결과만으로 모델 교체를 결정하지 않는다.
3. 60초가 반복만 늘렸다면 길이 확장보다 event-conditioned Repaint/guide의 특정 한 사건(필인/브레이크)을 검증한다. 이전 Repaint는 본문 보존은 확인했지만 sparse intro 개선을 입증하지 못했다.
4. Gate 5는 독립 트랙의 실제 확보가 선행해야 한다. 지금 전체 stereo에 개별 악기 EQ/공간 처리를 적용한 것처럼 보고하지 않는다.

청취 승인 전 Gate 3~5 전체 개발이나 main 병합은 진행하지 않는다.

## 실행 측정 결과

| 장르/조건 | 길이 | 총 생성 시간 | 피크 footprint | RMS dBFS | stereo corr | 활성 RMS 변화폭 |
|---|---:|---:|---:|---:|---:|---:|
| soul A | 30s | 32.73s | 5.050 GiB | -17.64 | 0.911 | 3.71 dB |
| soul B | 30s | 28.97s | 5.051 GiB | -18.52 | 0.958 | 5.13 dB |
| soul C | 30s | 38.35s | 5.768 GiB | -16.70 | 0.955 | 4.33 dB |
| house A | 30s | 29.74s | 5.015 GiB | -17.65 | 0.961 | 8.67 dB |
| house B | 30s | 30.18s | 5.036 GiB | -17.94 | 0.956 | 3.69 dB |
| house C | 30s | 32.99s | 5.749 GiB | -17.78 | 0.959 | 3.93 dB |
| ambient A | 30s | 27.79s | 5.084 GiB | -18.41 | 0.206 | 13.20 dB |
| ambient B | 30s | 27.54s | 5.032 GiB | -18.60 | 0.269 | 9.26 dB |
| ambient C | 30s | 31.14s | 5.762 GiB | -22.03 | 0.374 | 13.35 dB |
| soul-60s D-duration | 60s | 39.90s | 5.718 GiB | -18.34 | 0.889 | 3.79 dB |

10개 모두 48kHz stereo, finite, clipping 0. 총 생성 시간은 모델 로딩·감시를 포함한다. 초기 8-bit 변환도 해당 C 시간에 포함된다. 활성 RMS 변화폭은 1초 RMS가 −60dBFS를 넘는 구간의 p95−p10이며, 음악적 변주 점수가 아니다. 각 수치의 증가가 품질 개선을 뜻하지 않는다.

### 로컬 WAV 목록

- soul A: `outputs/originals/1b90a2dc229f4c6ba7802e72975aee1b/0e30f19f-57cb-67af-ddde-6438bcb23936.wav`
- soul B: `outputs/originals/1992a70b2a384e128a29a0a996359c79/74407512-3850-54f4-0b2a-b2dcaab4fa36.wav`
- soul C: `outputs/originals/ae0018b4dd7642919d77c8dc75aaa00b/74407512-3850-54f4-0b2a-b2dcaab4fa36.wav`
- house A: `outputs/originals/6ee7a01035e24aa5963aead2358e8b8f/59c140e6-5d7d-1ac8-1d0e-1907b5658a7a.wav`
- house B: `outputs/originals/d6b2305707fd466099658aadd6149862/f70b1051-44b5-8cc4-6dad-9cd3701f622c.wav`
- house C: `outputs/originals/94adcb27ace8408f9c855bfc4fb8423d/f70b1051-44b5-8cc4-6dad-9cd3701f622c.wav`
- ambient A: `outputs/originals/b3dc3f346e5a4281a6df78eff949851e/a7bfe560-860e-1f22-a21e-207cc5492fc7.wav`
- ambient B: `outputs/originals/d5b866ac5629467f974a14936a2d19d6/cc355cc3-8284-5d5b-1a3e-e7da2e58dcd9.wav`
- ambient C: `outputs/originals/91ebe8dac76943b1a369acfad06d366c/cc355cc3-8284-5d5b-1a3e-e7da2e58dcd9.wav`
- soul-60s D-duration: `outputs/originals/3d84f547925b47bf9c396b99447a7d5e/6b85f617-1900-1108-8410-f6126ef13a2f.wav`

## 회귀·전달 검증

- 자동 테스트 **44개 통과**, Ruff E4/E7/E9/F 및 diff whitespace 검사 통과.
- 실제 STDIO MCP의 기존 생성 재시도/DSP/비교/내보내기/복원 통과. 실제 Codex app-server에서도 새 `music.director_plan` 및 기존 도구 호출 통과.
- 외부 Music Plan JSON을 실제 MCP로 전달했을 때 생성된 soul B의 caption과 동일함을 확인. 동일 request key 재시도는 같은 job을 재사용했다.
- B/C 요청은 세 장르 모두 `inference_profile` 외 동일함을 검증했다. 실제 worker text와 Director preflight text 일치 확인.
- 기존 오디오 SHA-256 유지. 기존 메모리10GiB/시간900초/단일 작업/critical pressure 중단 정책 변경 없음.
- 격리된 Chrome에서 **10개 WAV 모두 재생 진행·길이 확인**, 100개 점수 입력칸 확인, 점수 저장/복원, 조건 공개 동작, 자연어 Director 초안 생성 확인. 테스트 점수는 비워 복원했다. `outputs/producer/browser-qa.json`, `review.png`에 증거 보관.
- 기존 Pydantic Settings의 lifespan annotation 경고 1개는 남아 있으나 실제 MCP 호출은 통과했다.
- UI는 기획 방식 선택과 기존 JSON 편집을 재사용한다. 별도의 DAW나 모델 선택 화면은 추가하지 않았다.

주요 변경: `engine/music_plan.py`, `agent/director.py`, `engine/schema.py`, `agent/music_intent.py`, `engine/generation/{mlx_quantized,worker,backend}.py`, `engine/jobs.py`, `app/{cli,mcp_server}.py`, `app/player/{server.py,index.html}`, `scripts/{compare_producer,build_producer_review,test_director_mcp}.py`, `examples/director/*.json`, `tests/test_director.py`.

병합 전 검토: 세 장르의 10항목 사용자 청취 점수, 4/8-bit 선호가 일관되는지, 60초가 음악적 전개를 늘렸는지, 프리셋 fallback의 세부 요청 누락, 새 MCP 스키마의 실제 사용 경험. 현재 draft는 기존 Arrangement 브랜치 위에 쌓인 변경이며, main으로 이전 기능을 포함해 병합하려면 선행 브랜치 검토도 필요하다.
