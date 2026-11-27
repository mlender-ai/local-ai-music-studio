# PHASE 05.3 · NATIVE MUSICAL PERFORMANCE LAB REPORT

**Branch:** `experiment/yue2-native-performance-lab` (stacked on PR #30 `feat/daw-ai-session-loop-production` @ `2999bdf71ffc65d01c212f4e77a866f89da23b3e`)  
**Quality Baseline:** Phase 05.1 `Native Production Test.wav` / `Studio Preview.wav` (PR #29 `feat/daw-yue2-native-production` @ `a124b21`)  
**DAW Project:** `Native Performance Lab 001` (`outputs/daw/projects/proj_bdb68c87bd/`)  
**Subjective Musicality Verdict:** `UNVERIFIED` (awaiting direct user listening of the 8 WAV deliverables below)

---

## 1. 실험 A–H 실제 결과 요약 (8개 독립 청취용 WAV)

모든 8개 파일은 실제 **YuE2 Native Audio (`yue2-native`)** 단일 엔진으로 DAW 파이프라인(`POST /composition/plan` → `POST /generation/jobs` → `apply` → 음향 진단 → 비파괴 EQ/Room → `Studio Renderer`)을 통해 생성·익스포트되었으며, **MIDI Composer / Phase 05.2 MIDI Performer / FluidSynth / SoundFont / Drum Rack 대체는 0건**입니다.  
모든 청취용 WAV 규격 검증 완료: **48 kHz · Stereo · PCM 24-bit · Clipped Samples `0` · True Peak `-1.00 dBTP`**.

| 실험 | WAV 파일 | 실제 엔진 | BPM (측정 / 목표) | 길이 | 중심 악기 | 보컬 QA (Demucs + PANNs) | 상태 |
|---|---|---|---|---:|---|---|---|
| **A** | `outputs/exports/Native_Performance_Lab_001/listening/01_Funk_Guitar_Riff.wav` | YuE2 (`yue2-native`) | `69.1` (목표 `102.0`, 2/3 feel) | `19.999s` | 기타 (Funk Riff) | `PASS` (Demucs `-52.8 dBFS`, PANNs stem `0.055` / mix `0.029`) | `READY_FOR_USER_LISTENING` (음악성 `UNVERIFIED`) |
| **B** | `outputs/exports/Native_Performance_Lab_001/listening/02_Clean_Melodic_Guitar_Riff.wav` | YuE2 (`yue2-native`) | `89.1` (목표 `88.0`) | `21.999s` | 기타 (Clean Melodic) | `PASS` (Demucs `-52.9 dBFS`, PANNs stem `0.074` / mix `0.022`) | `READY_FOR_USER_LISTENING` (음악성 `UNVERIFIED`) |
| **C** | `outputs/exports/Native_Performance_Lab_001/listening/03_NeoSoul_Piano_Rhodes.wav` | YuE2 (`yue2-native`) | `82.5` (목표 `82.0`) | `23.999s` | 건반 (Rhodes / Neo Soul) | `PASS` (Demucs `-41.6 dBFS`, PANNs stem `0.052` / mix `0.030`) | `READY_FOR_USER_LISTENING` (음악성 `UNVERIFIED`) |
| **D** | `outputs/exports/Native_Performance_Lab_001/listening/04_Expressive_Piano_Solo.wav` | YuE2 (`yue2-native`) | `84.5` (목표 `86.0`) | `25.999s` | 피아노 (Expressive Solo) | `PASS` (Demucs `-44.0 dBFS`, PANNs stem `0.073` / mix `0.027`) | `READY_FOR_USER_LISTENING` (음악성 `UNVERIFIED`) |
| **E** | `outputs/exports/Native_Performance_Lab_001/listening/05_Drum_Percussion_Groove.wav` | YuE2 (`yue2-native`) | `65.8` (목표 `98.0`, 2/3 feel) | `19.999s` | 드럼·퍼커션 (Groove) | **`UNCERTAIN`** (Demucs `-25.1 dBFS`, PANNs stem `0.128` / mix `0.234` Speech — 수동 확인 필요) | **`READY_FOR_USER_LISTENING_UNCERTAIN_VOCAL`** (음악성 `UNVERIFIED`) |
| **F** | `outputs/exports/Native_Performance_Lab_001/listening/06_Melodic_Bass_Riff.wav` | YuE2 (`yue2-native`) | `96.8` (목표 `96.0`) | `19.999s` | 베이스 (Melodic Riff) | `PASS` (Demucs `-46.0 dBFS`, PANNs stem `0.047` / mix `0.031`) | `READY_FOR_USER_LISTENING` (음악성 `UNVERIFIED`) |
| **G** | `outputs/exports/Native_Performance_Lab_001/listening/07_Expressive_Guitar_Solo.wav` | YuE2 (`yue2-native`) | `56.2` (목표 `84.0`, 2/3 feel) | `25.999s` | 기타 (Expressive Solo) | `PASS` (Demucs `-25.1 dBFS` 리드 기타 블리드; PANNs stem `0.069` / mix `0.022`) | `READY_FOR_USER_LISTENING` (음악성 `UNVERIFIED`) |
| **H** | `outputs/exports/Native_Performance_Lab_001/listening/08_Musical_Bridge.wav` | YuE2 (`yue2-native`) | `87.4` (목표 `88.0`) | `33.999s` | 합주 (Bridge & Motif) | `PASS` (Demucs `-42.4 dBFS`, PANNs stem `0.124` / mix `0.128`) | `READY_FOR_USER_LISTENING` (음악성 `UNVERIFIED`) |

- **원본 보존 폴더 (비파괴 원본 YuE2 출력):** `outputs/exports/Native_Performance_Lab_001/originals/01_Funk_Guitar_Riff_Native.wav` … `08_Musical_Bridge_Native.wav`
- **실험별 상세 메타데이터 & 프롬프트/ABC/QA 로그:** `outputs/exports/Native_Performance_Lab_001/metadata/01_Funk_Guitar_Riff.json` … `08_Musical_Bridge.json`
- **세션 라이브러리 Native Performance Recipe:** `outputs/daw/session_library.json` (8개 모두 `userRating="unused"`로 보존, 사용자 청취 승인 전 자동 추천 금지)

---

## 2. 실제 모델 및 실행 환경

- **Host:** Apple M5 (24 GiB Unified Memory), macOS Metal Backend
- **Native Audio Engine:** `yue2.cpp` (`e646d52`) `yue-synth` + `YuE2-3B-Q8_0.gguf` + `YuE2-Vae-F32.gguf` (기존 Phase 05.1 공유 Runtime Registry 그대로 활용, 재다운로드·모델 교체 없음)
- **Instrumental Score Compiler:** 공식 `v6/instrumental/compile_score.py` (`official_v6_compile_score_custom_performance`, `V: Vocal` 전 구간 쉼표 + 비보컬 섹션 마커 `% intro` / `% instrumental` / `% interlude` / `% outro`)
- **Dual-Model Vocal QA:** Demucs `htdemucs` (MPS) 보컬 스템 분리 + 로컬 **PANNs MobileNetV1 AudioSet (527-class)** 믹스·보컬 스템 동시 분류 (`demucs_plus_panns_corroborated`). `REJECT` 음원은 대표 청취 폴더(`listening/`)에 배치하지 않으며, `UNCERTAIN`은 무보컬 통과로 확정하지 않고 수동 청취 대상으로 명시.
- **DAW Sound Design & Export:** `engine/sound_design/advisor.py` 트랙별 스펙트럼/스테레오 진단 기반 최소 비파괴 Parametric EQ(및 저폭 트랙 A/F에 한해 `-16.5 dB` Natural Room 센드) + 순수 선형 Gain 레벨 매칭(과도한 컴프레션/리미팅 미적용, `True Peak <= -1.0 dBTP`).

---

## 3. 생성 조건의 차이 (A–H 독립 Brief · 화성 · 음향 설계)

모든 실험에 서로 다른 키·템포·코드 진행·ABC 섹션·CoT 모드·프롬프트를 적용했습니다.

| 실험 | 장르 / 타깃 표현 | 목표 키 → 측정 키 | 코드 진행 | CoT / CFG / Temp / Seed | 적용 DAW Sound Design | 청취 LUFS / TP / Gain / Crest | 상위 PANNs AudioSet 태그 (Mix) |
|---|---|---|---|---|---|---|---|
| **A** | Neo Soul / Funk R&B | `E minor` → `E major` | `Em7 → A7 → Em7 → A7 → Em7 → A7 → Cmaj7 → B7` | `full` / `2.4` / `0.78` / `5501` | EQ (`HPF 32Hz, 3.2k +1.4dB, 9.5k +1.2dB`) + Room `-16.5dB` | `-16.82` / `-1.00` / `+0.79dB` / `17.8dB` | `Guitar 0.42, Drum kit 0.20, Bass guitar 0.18, Funk 0.11` |
| **B** | Alt R&B / Indie Soul | `A minor` → `A minor` | `Am9 → Dm9 → Fmaj7 → E7` | `melody` / `2.5` / `0.78` / `5381` | EQ (`HPF 32Hz, 310Hz -1.8dB, 3.2k +1.4dB, 9.5k +1.2dB`) | `-16.72` / `-1.00` / `+0.42dB` / `17.2dB` | `Guitar 0.67, Electric guitar 0.21, Acoustic guitar 0.13, Bass 0.11` |
| **C** | Neo Soul / Jazz R&B | `Eb major` → `A# major` | `Ebmaj9 → Cm9 → Fm9 → Bb13` | `full` / `2.4` / `0.78` / `5321` | EQ (`HPF 32Hz, 310Hz -1.8dB, 3.2k +1.4dB, 9.5k +1.2dB`) | `-20.14` / `-1.00` / `+1.12dB` / `20.5dB` | `Guitar 0.57, Bass guitar 0.29, Electric piano 0.11, Piano 0.10` |
| **D** | Jazz / Neo Soul Ballad | `F minor` → `A# major` | `Fm9 → Bbm9 → Ebmaj7 → C7` | `full` / `2.4` / `0.78` / `5531` | EQ (`HPF 32Hz, 310Hz -1.8dB, 3.2k +1.4dB, 9.5k +1.2dB`) | `-20.56` / `-1.00` / `+3.03dB` / `21.8dB` | `Piano 0.58, Electric piano 0.38, R&B 0.06, Soul music 0.05` |
| **E** | Boom-bap / Afro-groove | `C minor` → `F minor` | `Cm7 → Fm7` (리듬 중심) | `melody` / `2.4` / `0.80` / `5341` | EQ (`HPF 32Hz, 3.2k +1.4dB, 9.5k +1.2dB`) | `-17.58` / `-1.00` / `-0.63dB` / `19.0dB` | `Music 0.93, Percussion 0.11` (`Speech 0.234` → `UNCERTAIN`) |
| **F** | Neo Soul / Funk Bass | `G minor` → `G minor` | `Gm7 → C9 → Ebmaj7 → D7` | `full` / `2.4` / `0.78` / `5351` | EQ (`HPF 32Hz, 3.2k +1.4dB, 9.5k +1.2dB`) + Room `-16.5dB` | `-19.98` / `-1.00` / `+2.22dB` / `20.6dB` | `Bass 60–200Hz 79.9%`, `Drum kit 0.08, Bass drum 0.06, Funk 0.05` |
| **G** | Soul / Blues-R&B Solo | `B minor` → `B minor` | `Bm9 → Em9 → Gmaj7 → F#7` | `full` / `2.4` / `0.80` / `5361` | EQ (`HPF 32Hz, 310Hz -1.8dB, 3.2k +1.4dB, 9.5k +1.2dB`) | `-18.26` / `-1.00` / `+3.04dB` / `19.4dB` | `Guitar 0.77, Electric guitar 0.21, Bass guitar 0.09` |
| **H** | Alt R&B / Neo Soul Bridge | `D minor` → `D minor` | A: `Dm7→G7→Cmaj7→A7` → B/C (`% interlude`): `Bbmaj7→A7sus4→Gm7→A7` → D: `Dm7→G7→Bbmaj7→Dm7` | `full` / `2.4` / `0.78` / `5577` | EQ (`HPF 32Hz, 310Hz -2.6dB, 3.2k +1.4dB, 9.5k +1.2dB`) | `-20.57` / `-1.00` / `+0.14dB` / `21.0dB` | `Guitar 0.57, Electric guitar 0.18, Soul 0.12, R&B 0.11` |

---

## 4. 실험별 소요 시간 및 리소스 사용

| 실험 | 시도 횟수 | 최종 시도 YuE2 추론 시간 | 최종 시도 전체 시간 (QA 포함) | 누적 소요 시간 (재시도 포함) | 최대 RSS 메모리 |
|---|---:|---:|---:|---:|---:|
| **A** (`01_Funk_Guitar_Riff`) | 3 (초기 `% verse/% chorus` 2회 `REJECT` → 비보컬 섹션 수정 후 1회 `PASS`) | `66.55s` | `82.25s` | `234.09s` | `4.34 GiB` |
| **B** (`02_Clean_Melodic_Guitar_Riff`) | 2 (1회 `REJECT` → 재시도 1회 `PASS`) | `68.41s` | `80.58s` | `163.91s` | `4.48 GiB` |
| **C** (`03_NeoSoul_Piano_Rhodes`) | 1 (첫 시도 `PASS`) | `72.90s` | `86.33s` | `86.33s` | `4.47 GiB` |
| **D** (`04_Expressive_Piano_Solo`) | 3 (초기 `"singing"` 단어·`% verse` 2회 `REJECT` → 수정 후 1회 `PASS`) | `80.96s` | `95.42s` | `279.01s` | `4.46 GiB` |
| **E** (`05_Drum_Percussion_Groove`) | 1 (`UNCERTAIN` 수동 청취 보류) | `63.00s` | `78.01s` | `78.01s` | `4.55 GiB` |
| **F** (`06_Melodic_Bass_Riff`) | 1 (첫 시도 `PASS`) | `63.77s` | `75.98s` | `75.98s` | `4.50 GiB` |
| **G** (`07_Expressive_Guitar_Solo`) | 1 (첫 시도 `PASS`) | `84.21s` | `100.42s` | `100.42s` | `4.39 GiB` |
| **H** (`08_Musical_Bridge`) | 3 (초기 `% bridge` 2회 `Humming 0.93 REJECT` → `% interlude` 수정 후 1회 `PASS`) | `106.36s` | `125.57s` | `361.78s` | `4.50 GiB` |

---

## 5. 확인된 음악적 및 기술적 한계 (핵심 실증 발견 포함)

1. **YuE2 ABC 섹션 헤더 & 프롬프트 보컬 유발 법칙 (실증 규명 및 영구 수정):**
   - `V: Vocal`에 전 구간 쉼표(`z32|` / `Z4|`)를 넣더라도, ABC 섹션 마커에 **`% verse` / `% chorus` / `% bridge`**를 사용하거나 스타일 프롬프트에 **`"singing"` / `"vocal-like"`** 단어가 포함되면 YuE2가 강한 허밍·보컬 누출을 유발했습니다 (실측: Exp A `Speech 0.78`, Exp D `Humming 0.85`, Exp H `% bridge` 2회 연속 `Humming 0.936 / 0.932`, `-20 dBFS`).
   - 이를 **`% intro` / `% instrumental` / `% interlude` / `% outro`**로 전환하고 보컬 연상 단어를 제거하자 Exp A (`-52.8 dBFS`), Exp D (`-44.0 dBFS`), Exp F (`-46.0 dBFS`), Exp G (`mix=0.022`), Exp H (`-42.4 dBFS`, 22 dB 감소)가 **모두 첫 시도에서 `PASS`**했습니다. 이 규칙은 `engine/generation/adapters/yue2_adapter.py`에 영구 반영했습니다.
2. **실험 E (`05_Drum_Percussion_Groove`) 보컬 QA `UNCERTAIN`:**
   - Demucs 보컬 스템 `-25.1 dBFS`, PANNs `Speech` 확률 `stem=0.128 / mix=0.234`로 경계 구간이 감지되었습니다. 타악기 트랜지언트 오탐인지 실제 미세 보이스/카운트인인지 자동 판정으로 확정하지 않고 `UNCERTAIN`으로 정직하게 표기했으므로 사용자 청취 확인이 필요합니다.
3. **악기 중심 비중 편차 (특히 C, F):**
   - YuE2는 자연스러운 앙상블 경향이 강해, 실험 C (`03_NeoSoul_Piano_Rhodes`)에서 Rhodes/Piano(`0.11 / 0.10`) 외에 Guitar(`0.57`)와 Bass(`0.29`)도 함께 강하게 나타났습니다. 반대로 실험 D (`04_Expressive_Piano_Solo`)는 `Piano 0.58 + Electric piano 0.38`로 건반 집중도가 매우 높았고, 실험 G (`07_Expressive_Guitar_Solo`)는 `Guitar 0.77 + Electric guitar 0.21`로 기타 리드가 뚜렷했습니다.
   - 실험 F (`06_Melodic_Bass_Riff`)는 `60–200 Hz` 저역 비중이 `79.85%` (`centroid 94.4 Hz`)로 묵직한 베이스 중심이나, 고역 하모닉스/핑거 어택 선명도는 사용자 청취로 확인이 필요합니다.
4. **템포 추정 2/3 박자 편차 (A, E, G) 및 레벨 매칭 헤드룸 트레이드오프 (C, D, F, H):**
   - 실험 B(`89.1`), C(`82.5`), D(`84.5`), F(`96.8`), H(`87.4`)는 목표 BPM과 ±1.5 BPM 이내로 일치했으나, A(`69.1` vs `102`), E(`65.8` vs `98`), G(`56.2` vs `84`)는 2/3-time 또는 laid-back 그루브로 추정되었습니다.
   - 과도한 리미팅·컴프레션 금지 원칙(Section 17)에 따라 순수 선형 Gain과 `-1.0 dBTP` 천장을 지킨 결과, 다이내믹 레인지가 큰 C/D/F/H (`Crest Factor 20.5–21.8 dB`)는 `-20.0`~`-20.6 LUFS`에 머물렀습니다.
5. **주관적 음악성 미확정 (`UNVERIFIED`):**
   - 연주의 자연스러움, 주법 표현(뮤트/벤딩/비브라토/슬라이드/고스트 노트), 화성 일관성 및 브릿지 전환 완성도는 자동 지표만으로 합격 선언하지 않으며, 사용자의 직접 청취 후 승격 여부를 결정합니다.

---

## 6. 기존 Phase 05.1 / 05.2 대비 변경 사항

- **영구 제작 정책 및 AI Producer 라우팅 전환 (Sections 18–19):**
  - `config/production/default_policy.json` (`schemaVersion: 2`), `config/production/engine_routing.json`, `engine/daw_workspace/proposals.py`, `app/daw_server.py`, `engine/generation/daw_jobs.py`:
  - `"기타 리프 만들어줘"`, `"피아노 솔로 만들어줘"`, `"독특한 드럼 그루브 만들어줘"`, `"베이스 리프 만들어줘"`, `"브릿지 만들어줘"` 등 일반 연주 요청이 더 이상 Phase 05.2 자체 MIDI Performer로 자동 라우팅되지 않고 **기본값으로 `YuE2 Native Performance Mode` (`composition_plan`, `yue2-native`)**로 라우팅됩니다(독립 악기 분리 한계·스템 블리드 가능성 정직 안내 포함).
  - Phase 05.2 `SessionContext` / Layer Protection / Take Lane / Session Library 아키텍처는 보존하되, MIDI Performer는 사용자가 `"편집 가능한 MIDI로"` 등을 **명시적으로 요청한 경우에만 Opt-In**으로 실행됩니다.
- **사용자 취향 피드백 & Session Library 반영 (Sections 19–20):**
  - `engine/production/taste_profile.py` 및 로컬 `outputs/daw/taste_profile.json`에 Phase 05.1 긍정 평가와 Phase 05.2 SoundFont/MIDI Performer 불합격 피드백을 반영하고, 기존 Phase 05.2 SF3 자산 8건을 비교용으로 보존하되 `userRating="poor"`로 표시했습니다.
  - `engine/session_lab/library.py`에 Section 20 **Native Performance Recipe** 전체 필드 및 승인된(`userRating == "good"`) YuE2 레시피만 AI Producer에 자동 매칭하는 `find_approved_native_recipes()`를 추가하고, 실험 A–H 레시피 8건을 `userRating="unused"` 상태로 보존했습니다.
- **YuE2 어댑터 & 음향 진단 개선:**
  - `engine/generation/adapters/yue2_adapter.py`: 로컬 PANNs MobileNetV1 527-class 분류기 연동(Runtime Registry 동적 경로 로딩, 개인 경로 하드코딩 0건), Demucs+PANNs 이중 보컬 QA, 비보컬 ABC 섹션 정규화, 커스텀 `nativePerformance` ABC/스타일 프롬프트 경로 지원.
  - `engine/sound_design/advisor.py`: 순차 타임라인 트랙(`startBeats > 0`)에서도 첫 클립 위치부터 정상 진단하도록 `diagnose_track_audio()` 수정.

---

## 7. DAW 프로젝트 경로 · 검증 결과 · GitHub PR

- **DAW 프로젝트 경로:** `outputs/daw/projects/proj_bdb68c87bd/` (`Native Performance Lab 001`, 8개 순차 비겹침 트랙 `01`–`08`, 8개 섹션 마커, 트랙별 비파괴 EQ/Room, 최신 `Studio Preview` 렌더링 완료)
- **자동 회귀 테스트:**
  - Backend `pytest` (`test_phase052_session_loop.py`, `test_phase051_native_production.py`, `test_phase04_arrangement.py`, `test_phase03_composition.py`, `test_agent_bridge.py`): **`26 passed` (`0 failed`)**
  - Frontend `Vitest` (`apps/daw`): **`14 passed` (`0 failed`)**
- **Live Browser QA (`http://127.0.0.1:8796`):** `Native Performance Lab 001` (`proj_bdb68c87bd`, `102.00 BPM`, `4/4`) 8개 순차 트랙·파형·섹션 마커·Device Rack 비파괴 EQ·녹색 `STUDIO PREVIEW` 배지·재생/정지 및 새로고침 영속성 확인, 콘솔/페이지/HTTP 4xx–5xx 오류 **`0`건**.
- **GitHub PR:** Stacked PR on branch `experiment/yue2-native-performance-lab` targeting `feat/daw-ai-session-loop-production` (PR #30 @ `2999bdf`, 기존 PR #29/#30 보존, 자동 병합 금지).
