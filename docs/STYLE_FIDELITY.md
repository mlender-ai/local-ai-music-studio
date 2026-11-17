# Music Intent와 스타일 충실도 실험 · 2026-11-17

## 실제 경로 감사

플레이어 `/api/generate` → `Generate` → `jobs.submit` → `generation_plan` → `ACEStepBackend` → 격리 worker → ACE-Step.
CLI와 MCP도 같은 경로를 사용한다. 기존 11월 16일 디스코 보강과 Turbo shift=3, guidance=1, 8 steps는 이미 적용돼 있었다. 이번에는 이를 다시 고치지 않고 고정했다. worker의 ODE, thinking=false도 그대로이며 결과 메타데이터에 명시적으로 기록한다. 모델/가중치/MLX 4-bit 캐시는 변경하지 않았다.

## 계획 입력

`music.plan` 또는 플레이어의 Music Intent 초안 버튼은 모델을 실행하지 않는다. 장르/시대/그루브/드럼/베이스/기타/키보드/보컬/편곡/템포/박자/제외 항목을 가진 검증된 JSON과 실제 caption을 반환한다. 펑키 디스코는 명시된 프리셋으로 확장하며 다른 장르는 기존 변환을 일반 기획 초안에 담는다. 규칙 기반이므로 범용 음악 이해를 보장하지 않는다. 원문은 생성 이력에 보존한다. 자연어 초안의 미해석 지시는 additional_direction으로 남기며 사용자가 수정할 수 있다.

Codex는 `music.plan` 결과의 intent를 수정한 뒤 `music.generate(prompt=..., intent=...)`로 전달한다. intent의 음악 필드가 원문보다 우선하고, 명시적인 `instrumental` 인자가 vocal_mode보다 우선한다. 임의 코드는 실행하지 않는다. 예제: `examples/funk-disco-intent.json`.

```bash
.venv/bin/music generate '펑키 디스코 30초' --intent examples/funk-disco-intent.json --wait
.venv/bin/music generate '리드 보컬과 코러스의 디스코 30초' --vocal --lyrics '[Verse] Move with the light' --wait
```

보컬 요청/가사는 보컬을 활성화하고, 보컬 없는 요청은 연주곡을 유지한다. 불명확하면 선택을 요구한다. 플레이어에는 생성 유형 선택, 가사, 수정 가능한 JSON, 실제 프롬프트 확인만 추가했으며 DSP나 시각 디자인 작업은 하지 않았다. 보컬 생성 품질의 청취 평가는 별도 미검증이다.

## 비교 설계와 재현

```bash
.venv/bin/python scripts/compare_fidelity.py
.venv/bin/python scripts/build_fidelity_review.py
.venv/bin/music player
```

`http://127.0.0.1:8795/fidelity`에서 재생과 7항목 1~5점 평가가 가능하다. 점수는 미검증(빈 값)으로 시작하며 브라우저에 보존된다. 청취 평가 JSON 저장 버튼으로 결과를 내려받는다. 자동 분석이 사람 점수를 채우지 않는다.

A: 이전 변환(legacy_generation_plan), seed 42. B: 새 Intent, seed 42. B/C2/C3: 동일 Intent, seed 42/43/44의 세 후보. 총 네 곡이며 B를 후보 세트의 첫 곡으로 재사용한다. 30초, 120 BPM, 4/4, instrumental, batch 1, Turbo/MLX/MPS, shift 3/8 steps/ODE를 고정했다. 시간·원문·caption·Intent·모델 revision·추론 설정·리듬 추정·파일 분석·경로는 `outputs/fidelity/results.json`에 기록한다. 이 파일과 WAV는 로컬 자료로 Git에서 제외한다.

최초 A는 critical memory pressure로 보호 중단됐다. 정상 압력으로 돌아온 뒤 별도 request key로 재시도했다. 실패 이력은 유지했고 메모리/타임아웃 제한은 완화하지 않았다. 재실행은 고정 request key로 완료된 결과를 재사용한다. 새 실험이 필요하면 스크립트의 key 버전을 변경한다.

## 판정 경계와 후속 실험

파일 유효성/클리핑/생성 시간/메모리/주기 후보는 자동 측정이다. 장르, 그루브, 기타 존재감, 악기 간 결합, 편곡, 청감 음질은 사람 청취가 필요하다. **현재 음악적 개선 여부는 미검증**이다. 코드 테스트 합격을 음악 품질 합격으로 보고하지 않는다.

D(5Hz LM)는 미실행이다. 기본 DiT 경로에서도 이 장비의 다른 작업 부하로 critical pressure 중단이 발생해 모델을 추가 설치하지 않았다. 추후 작은 LM을 별도 수명 주기로 실행하고, LM 종료 후 DiT를 실행하는 조건에서 peak footprint/소요 시간과 동일 시드의 청취 결과를 측정한 뒤 선택 기능 여부를 결정한다.

프롬프트만으로 개선이 부족하면 4마디 원본 드럼/베이스 가이드 하나로 조건부 생성부터 비교한다. [공식 Cover API](https://github.com/ace-step/ACE-Step-1.5/blob/main/docs/en/INFERENCE.md)는 src_audio와 audio_cover_strength를 제공한다. 자체 작성 가이드만 사용하고 0.3/0.6/0.9 조건에서 리듬 유지와 악기 구성을 평가한다. 이 경로는 아직 구현·품질 검증하지 않았으며 대규모 리듬 엔진은 만들지 않았다.

## 실제 실행 결과

| 조건 | 시드 | 총 생성 시간 | 최대 자식 footprint | 상태 |
|---|---:|---:|---:|---|
| A | 42 | 28.11초 | 5.044 GiB | 성공 / 청취 미검증 |
| B | 42 | 27.09초 | 5.062 GiB | 성공 / 청취 미검증 |
| C2 | 43 | 25.34초 | 5.117 GiB | 성공 / 청취 미검증 |
| C3 | 44 | 24.87초 | 5.109 GiB | 성공 / 청취 미검증 |

네 곡 모두 48 kHz stereo, 30초, 유한 샘플, 클리핑 0. 기존 STDIO MCP 도구와 실제 Codex app-server 호출은 성공했다. 새 music.plan은 STDIO 경로에서도 확인했다.

자동 테스트: 34개 통과. 설치된 Pydantic Settings/MCP의 lifespan annotation 경고 1개가 있으나 STDIO와 Codex 호출은 정상이다. 이 경고를 음악 품질과 혼동하지 않는다.

구조화된 intent를 실제 STDIO music.generate로 전달해 B 작업의 동일 request key를 재호출했고, 중복 생성 없이 같은 성공 작업이 반환됨을 확인했다. 로컬 기록: outputs/fidelity/mcp-intent-replay.json.
