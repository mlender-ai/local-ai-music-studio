# 생성 엔진 비교 · 1차 실행

**후속 청취 판정 (2026-11-20).** 사용자가 인디 록, 팝 발라드, 재즈 힙합 세 장르에서 YuE2를 합격, Turbo를 불합격으로 판정했다. 후속 비교는 승인된 YuE2 원본을 기준으로 한다. [새 비교 음원과 조건](YUE2_CHALLENGERS.md)

## 시작점

2026-11-20 원격 fetch 기준이다. main은 `a5085de`다. 다음 여섯 브랜치의 작업은 main 밖에 있다. 이번 연구는 마지막 브랜치에서 분기했다.

| 원격 브랜치 (codex/) | 커밋 | 검증 이력과 범위 |
|---|---|---|
| music-style-fidelity | 565ffd6 | Music Intent, 보컬 선택, 프롬프트 A/B. 별도 PR 없음 |
| arrangement-intro-2-1 | 386de3e | 구간 계획과 Repaint 실험. 별도 PR 없음 |
| music-producer-v2 | aba35c1 | 4/8비트 비교, 60초 실험. PR 1 초안 |
| session-engine-v1 | 989d7d6 | 개별 녹음 단음과 고정 악보의 소울 세션. PR 2 초안 |
| ai-daw-production-engine | 2fe5a96 | 실제 REAPER 렌더·재열기. PR 3 초안 |
| harmony-repair-jazz-hip-hop | 3dda4c5 | 소울 보이싱 수리·12마디 힙합. PR 4 초안 |

**병목.** 기존 Generation 경로는 ACE-Step Turbo 고정 체크포인트에 8스텝, shift 3, CFG 1을 적용한다. 임베딩용 Qwen은 가사·스타일을 조건으로 인코딩하고, 음악을 기획하는 별도 5Hz LM은 꺼져 있다. 검증된 Repaint는 최대 30초 원본에만 노출된다. Production의 MIDI 실험은 두 악보 프로필의 마디 규칙과 제한된 샘플을 여러 번 재생한다. 화성 검사를 통과해도 프레이징과 보컬을 새로 발명할 경로가 없다. REAPER·FX·샘플러는 제작 계층, 입력·MCP·큐·저장·플레이어는 응용 계층으로 유지한다. 이번 비교는 생성 계층만 사용한다. [기존 실험](JAZZ_HIP_HOP.md) · [Suno 조사](SUNO_PRODUCT_RESEARCH.md)

## 후보를 좁힌 근거

| 후보 | 공식 기능 및 실행 조건 | 권리 및 이번 실행 판단 |
|---|---|---|
| ACE-Step 1.5 | Turbo 2B의 기존 4/8비트 MLX 경로, BF16 원본 가중치. SFT는 약 50스텝과 CFG 조절, 0.6B/1.7B 5Hz LM은 별도 semantic code 기획이 가능하다. 공식 Cover, Repaint 및 retake 변주는 버전·태스크별 지원 범위가 있다. 이 앱은 텍스트 생성과 실험용 Repaint만 연결했다. | 공식 코드·DiT는 MIT. SFT/LM은 별도 가중치와 적재·메모리 검증이 필요하다. 작동하는 4비트를 대조군으로 선택했다. 8비트 효과는 직전 연구에 별도 기록돼 있다. |
| YuE2 | 공식 3B·VAE는 가사·스타일 → 생성 악보 → semantic tokens → acoustic flow → 스테레오 오디오 경로를 제공한다. 악보 수정과 참조 기반 cover가 있으며 일부 보조 모델은 별도 접근 조건이 있다. 공식 BF16 실행 안내는 Linux, 24GB NVIDIA GPU와 가용 호스트 RAM 24GB다. 릴리스 카드의 언어 표기는 영어·중국어다. | 공식 코드 Apache-2.0, 가중치 CC BY-NC 4.0에 개인 창작·출력 수익화 추가 허용. 기업의 가중치 상업 사용은 별도 협의 대상이다. 본 연구는 MIT 라이선스의 Metal용 커뮤니티 GGUF 실행기로 Q8 백본 + F32 VAE만 시험했다. 공식 GPU 구현과 동일 출력이라는 가정은 없다. |
| HeartMuLa | 공개 권장판은 oss-3B-happy-new-year와 HeartCodec-oss-20260123. 가사·태그에서 곡을 생성하며 기본 최대 길이 240초. 모델 카드에는 한국어(ko)가 포함된다. 코드 실행 예는 CUDA, 단일 GPU lazy load 또는 모델·코덱 분리다. 코덱 인코딩/복원은 공개됐다. 참조 기반 생성·정밀 제어 및 7B는 공식 TODO에 남아 있다. | 공식 저장소는 코드와 관련 가중치 Apache-2.0을 명시한다. 이 Mac용 메모리와 한국어 가창 성능은 미측정이다. 상업 배포권을 고려할 때 다음 비교 우선 후보이다. |
| Stable Audio 3 | 공개 Small/Medium 오디오 모델. Medium 공식 최대 6분 20초. 기악·음색 실험에 적합한 후보지만 이번 한국어 가사 조건 비교에 대한 검증이 없다. | Stability Community License의 매출 조건(연간 100만 달러 기준)과 기업 라이선스를 확인해야 한다. 이번에는 가중치를 받지 않았다. |

원전은 [ACE-Step 튜토리얼](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/docs/en/Tutorial.md), [ACE-Step 모델 카드](https://huggingface.co/ACE-Step/Ace-Step1.5), [YuE2 공식 모델 카드](https://huggingface.co/m-a-p/YuE2-3B), [YuE2 가중치 조건](https://github.com/multimodal-art-projection/YuE/blob/main/MODEL_LICENSE), [Mac 실행기](https://github.com/ServeurpersoCom/yue2.cpp/tree/e646d5228911ae1b81ac2a261115a255848ce85f), [HeartMuLa 공식 저장소](https://github.com/HeartMuLa/heartlib), [HeartMuLa 가중치 카드](https://huggingface.co/HeartMuLa/HeartMuLa-oss-3B-happy-new-year), [Stable Audio 3](https://stability.ai/research/stable-audio-3), [Stability 라이선스](https://stability.ai/license)다.

## 실험 설계

Apple M5, 통합 메모리 24 GiB, 작업 전 가용 디스크 약 190 GiB, Metal/MLX 사용 가능. 공식 모델의 GPU VRAM 수치와 이 Mac의 프로세스 footprint는 측정 대상이 다르다. 기존 파일 잠금, 동시 추론 1개, 시작 전 가용 메모리·디스크 검사, footprint 10 GiB 상한, 시스템 메모리 압력 중단과 프로세스당 900초 상한을 두 엔진에 동일하게 적용했다. 외부 추론·과금은 0이다.

[세 브리프 및 새 가사](../examples/v4/briefs.json)를 고정했다. 목표 길이는 록 60초, 발라드 45초, 연주곡 40초다. 각 엔진에 같은 스타일·가사·시드 41을 전달한다. 시드 숫자는 모델 간 동일 난수를 뜻하지 않는다. Turbo는 BPM을 별도 필드로, YuE2는 동일한 스타일 본문으로 받는다. 디코더·양자화·샘플링 방식이 달라 이 비교가 분리하는 요인은 구현을 포함한 엔진 전체다. 출력 길이 목표는 종지나 후렴의 완성을 보장하지 않는다. 각 조건은 독립된 원본과 로그를 남기고 추가 시드는 자동 탐색하지 않는다.

### 재현 환경

기존 프로젝트 환경에서 실행한다. YuE2 측정과 동일한 조합은 다음과 같다.

```sh
mkdir -p .runtime/v4/models
git clone https://github.com/ServeurpersoCom/yue2.cpp .runtime/v4/yue2cpp
git -C .runtime/v4/yue2cpp checkout e646d5228911ae1b81ac2a261115a255848ce85f
git -C .runtime/v4/yue2cpp submodule update --init --recursive
cmake -S .runtime/v4/yue2cpp -B .runtime/v4/yue2cpp/build -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON
cmake --build .runtime/v4/yue2cpp/build --target yue-synth -j4
.venv/bin/hf download Serveurperso/YuE2-GGUF YuE2-3B-Q8_0.gguf YuE2-Vae-F32.gguf --revision e630f2b8f6aedf8254c3186438633c1b5eeaf80a --local-dir .runtime/v4/models
.venv/bin/python -m scripts.v4_study turbo rock ballad jazz
.venv/bin/python -m scripts.v4_study yue2 rock ballad jazz
```

실험에서 확인한 GGUF 파일 SHA-256은 백본 `41121ce97786d7795a325bcf123ca196956c03bb252c9e75384cfc1f2fc19e6b`, VAE `93e49dfb1970e89ad64cacb17cf13b5d05f6bb30ef7ed3adae3050bcb728638a`다. YuE2는 full 악보 생성, 최대 컨텍스트 8192, AR/음향 시드 41, flow 32스텝, WAV32로 설정했다. FLOAT 출력에는 실행기의 정수 WAV용 음량 정규화가 적용되지 않는다. 원본을 직접 검수하고 청취 사본에만 일정 게인을 적용한다.

새 요청은 실험 CLI에 직접 입력할 수 있다. 아래에서 jazz는 90 BPM과 목표 길이 40초를 지정한다. 각 실행은 새 폴더를 만들고, `--seed`를 바꾸면 새 해석을 요청한다. 이 스크립트는 연구용 진입점이다.

```sh
.venv/bin/python -m scripts.v4_study yue2 jazz --prompt '멜로디컬한 90년대 재즈 힙합. 베이스가 킥 사이를 채우고 후반에는 피아노가 대답한다.' --instrumental --seed 42
.venv/bin/python -m scripts.v4_evaluate outputs/v4/turbo-*/ outputs/v4/yue2-*/
```

선택적 한국어 가창 검사는 생성과 별도 프로세스에서 수행한다. `openai/whisper-small` 리비전 `973afd24965f72e36ca33b3055d56a652f456b4d`의 safetensors·JSON·merges.txt를 `.runtime/v4/whisper-small`에 내려받은 뒤 평가 명령에 `--asr`를 추가한다. 이 모델은 노래에 특화된 한국어 심사 모델이 아니다.

## 실측 결과

| 장르 | 엔진 | 초 | 총 생성 시간(초) | 최대 footprint(GiB) | LUFS-I | dBTP | 추정 BPM | 한국어 CER |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ballad | turbo | 45.00 | 36.5 | 5.40 | -14.63 | -0.95 | 모호 | 0.645 |
| ballad | yue2 | 45.00 | 186.5 | 3.15 | -16.96 | -1.39 | 모호 | 0.806 |
| jazz | turbo | 40.00 | 56.3 | 5.30 | -15.10 | -0.15 | 98.2 | 연주곡 |
| jazz | yue2 | 40.00 | 172.6 | 3.58 | -16.55 | 0.01 | 89.7 | 연주곡 |
| rock | turbo | 60.00 | 106.0 | 5.75 | -13.99 | -0.88 | 115.0 | 0.243 |
| rock | yue2 | 60.00 | 326.9 | 3.21 | -13.85 | 0.26 | 115.1 | 0.392 |

실험 원본을 그대로 보관했다. GitHub에는 대표 인디 록 두 원본, 전체 여섯 원본의 SHA-256·실행 조건·측정값·ASR 전사 및 YuE2의 모델 생성 악보가 있다. 나머지 원본의 로컬 위치는 results.json의 original_path에 있다. [Turbo 원본](../examples/v4/turbo-rock-original.wav) · [YuE2 원본](../examples/v4/yue2-rock-original.wav) · [전체 결과](../examples/v4/results.json)

- **인디 록**은 같은 가사·같은 목표 길이로 보컬, 밴드, 종지를 한 번에 비교할 수 있어 대표 쌍으로 골랐다. 감쇠만 적용한 청취 사본의 실측 음량은 Turbo −18.00, YuE2 −17.98 LUFS-I다. YuE2 악보에는 intro/verse/chorus/outro와 114 BPM이 있고 오디오 추정치는 115.1 BPM이다. 그러나 세 YuE2 실행 모두 semantic stream이 지정 길이 상한에서 끝났다. 록의 마지막 100ms RMS가 −15.75 dBFS여서 프레이즈 절단 가능성이 있다. Turbo는 같은 지점에서 −67.86 dBFS였다. 파일의 끝을 임의로 페이드하지 않았다.
- **가창**은 독립 Whisper-small에 가사 힌트 없이 한국어 모드로 30초 단위 전사한 뒤, 공백·구두점·구간 표시를 제거해 원문과 문자 편집 거리(CER)를 계산했다. 록에서는 두 모델 모두 후렴의 일부가 전사됐다. Turbo의 CER이 낮았다. 발라드에서는 두 전사 모두 첫 구간에 원문에 없는 같은 문장이 나왔다. 가사 순서와 끝의 반복 생략도 CER에 영향을 준다. 이 수치는 음색, 감정, 사람처럼 들리는지의 순위를 정해주지 않는다.
- **재즈 힙합**은 YuE2의 주기성 추정이 요청에 0.3 BPM 차이로 가까웠다. 두 모델 모두 연주곡 요청에서 ASR이 짧은 말을 출력했다. 비보컬 구간의 환각 가능성이 있어 보컬 유무를 확정할 수 없다. 세션의 레이백, 베이스와 드럼의 상호작용, 이전 MIDI 데모보다 자연스러운지 여부는 청취 미검증이다.
- **오디오 QA**에서 2초 단위 복제 파형 검사와 단일 샘플 임펄스 검사를 수행했다. 여섯 파일 모두 두 검사에서 후보 0건이었다. −60 dBFS 미만 최장 연속 구간은 0~2.3초였다. 반복 스크린은 파형 일치만 보므로 같은 코드·리듬을 다시 연주하는 경우를 놓친다. 음색 왜곡·노이즈와 앞뒤 악구의 음악적 연속성도 별도 청취 대상이다. YuE2 록은 float 원본에서 절댓값 1 이상인 샘플 1개와 +0.26 dBTP, 재즈는 +0.01 dBTP였다. 부동소수점 초과치는 정수 클리핑의 증거와 구분한다. 청취 사본은 피크 여유를 확보했다.
- **자원**은 자식 프로세스의 RSS/footprint를 0.5초마다 표본 추출했다. OS·별도 Metal 컴파일러·전체 시스템 메모리는 합산하지 않았다. 첫 YuE2 실행에는 초기 Metal 컴파일 시간이 포함된다. Turbo 발라드는 두 차례 시스템 critical pressure로 중단됐다. 이후 정상 압력과 약 6.9 GiB 가용 상태를 확인하고 같은 파라미터로 한 번 재시도해 성공했다. 다른 시드를 선별하지 않았고 실패한 기록도 보존했다. 비용은 이번 실행의 외부 GPU·모델 사용료 기준 0이며 전력 비용은 계측하지 않았다.

**1차 생성 당시 판단 (사용자 청취 전).** 앱 기본 엔진은 Turbo로 유지한다. 이번 단일 시드에서 YuE2의 악보와 목표 템포 근접성은 검증할 수 있었지만, 더 자연스러운 보컬이나 일관되게 좋은 완결을 입증하지 못했다. 상업용 제품 채택에는 별도 가중치 사용권도 필요하다. 공개 모델 중 다음 후보는 한국어와 Apache-2.0 가중치를 명시한 HeartMuLa 3B다. 이번 쌍에서 사용자가 가장 먼저 바꾸고 싶은 부분을 확인한 뒤, 같은 발라드와 록 가사로 비교하는 것이 효율적이다. 필요시 CUDA 24GB 단일 GPU·lazy load로 1시간 이내의 실험을 설계할 수 있다. 유료 실행은 견적과 총액 상한을 정해 별도 승인받는 후속 선택지다. 제품 기본 교체, 섹션 편집, 스템·REAPER 확장은 청취 판단 이후 단계로 남긴다.

동일 음량 청취 사본은 다음 명령으로 재현한다. 두 디렉터리는 같은 브리프·시드로 생성하고 QA를 수행한 폴더다. 마스터링이나 리미팅은 적용하지 않는다.

```sh
.venv/bin/python -m scripts.v4_listen "$TURBO_ROCK_RUN" "$YUE_ROCK_RUN" --out outputs/v4/rock-pair-new
```
