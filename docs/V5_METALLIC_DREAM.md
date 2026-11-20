# METALLIC DREAM · 금속의 꿈

새 한국어 얼터너티브 록을 YuE2로 생성하고 분리 추정 트랙을 REAPER에서 믹싱했다. 제작 경로는 YuE2 Q8 백본, F32 VAE, Metal yue2.cpp, full CoT 프로토콜과 32-step flow를 사용한다. 직접 만든 ABC 악보를 전달했으므로 symbolic planning 단계에서 새 악보를 뽑는 대신 이 악보를 사용한다.

[완성곡 MP3](../examples/v5/metallic-dream-master.mp3) · [마스터 WAV](../examples/v5/metallic-dream-master.wav) · [YuE2 원본 WAV](../examples/v5/metallic-dream-original.wav) · [가사](../examples/v5/metallic-dream.txt) · [ABC 악보](../examples/v5/metallic-dream.abc) · [실행 입력](../examples/v5/metallic-dream.json)

## 곡과 프로젝트

- **형식.** D단조, 112 BPM 악보, 52마디. 클린 기타의 A–E–F–E–D 모티프가 인트로와 솔로 입구, 아웃트로에 돌아온다. E♭ 화음과 A7으로 긴장을 만든 뒤 Dm(add9)으로 끝낸다. 한 번의 추론 결과로 생성 원본을 만들었다. 상한은 120초였고 모델은 semantic step 2696에서 종료 신호를 냈다.
- **현지 파일.** `outputs/v5/METALLIC-DREAM`에 원본, 마스터, 프로젝트와 `Audio`가 있다. REAPER 프로젝트는 `Audio`를 상대 경로로 참조한다. 옮길 때 ZIP 전체를 풀고 `METALLIC DREAM.RPP`를 연다.
- **처리 방식.** 6원 추정치의 보컬·드럼·베이스·기타·피아노·나머지 소스와 원본에서 각 추정치를 뺀 차분 트랙을 사용한다. 기타 네 역할은 악보와 시간 구간으로 다뤘다. 별도 연주로 존재하는 기타 소스는 확보되지 않았다. Lead focus는 60.15–75.75초의 기타 추정치를 사용한 평행 처리다.
- **분리 평가.** 동일 MLX 런타임에서 `htdemucs_6s`와 `htdemucs`를 실행했다. 4원 모델은 재합성 오차가 작지만 기타 출력을 제공하지 않는다. 기타 추정치가 필요한 믹스에는 6원 모델과 차분을 사용했다. ORT 기반 Audio Separator의 RoFormer 계열은 보컬 비교 후보다. 이번 실측에는 두 Demucs 계열 체크포인트를 사용했다. [Demucs 6원 모델](https://github.com/facebookresearch/demucs) · [MLX 포트](https://github.com/ssmall256/demucs-mlx/tree/9950c7daaa6ee3cf9622005e8be350c6c0163142) · [Audio Separator](https://github.com/nomadkaraoke/python-audio-separator)

## REAPER 처리

REAPER 7.86 arm64의 `EnumInstalledFX`로 조회한 뒤 관심 후보를 별도 트랙에서 로딩했다. 플러그인이 보고한 설치 ID, 파라미터 이름과 값, 프리셋 수, 개별 파라미터의 자동화 가능 여부를 기록했다. 플러그인 개별 버전 필드를 제공하지 않는 항목은 번들 호스트 버전으로 기록했다. [플러그인 조회 및 로딩](../examples/v5/plugin-inventory.tsv) · [마스터 렌더의 실제 FX 상태](../examples/v5/fx-state.tsv)

| 위치 | 처리 |
|---|---|
| 기타 | ReaEQ 96 Hz 하이패스, 335 Hz −1.6 dB, 약 4.9 kHz +0.75 dB. 후렴에서 JS Stereo Enhancer의 고대역 폭 100 → 155%, 크로스오버 550 Hz |
| 리드 | 60.15–75.75초, 0.24초 에지 페이드, 400 Hz 하이패스, 2.45 kHz +2.1 dB, −16 dB 평행 레이어와 딜레이 |
| 보컬 | 78 Hz 하이패스, 285 Hz −1.4 dB, 3.95 kHz +1 dB, 6.6 kHz 스테레오 디에서, ReaComp 약 1.35:1, 19 ms 공격 |
| 드럼·베이스 | 드럼 ReaComp 약 1.4:1, 25 ms 공격. 베이스 30 Hz 하이패스와 215 Hz −0.7 dB |
| 공간 | ReaVerbate의 세 리턴. 짧은 룸, 32 ms 프리딜레이를 둔 플레이트 성격의 리턴, 약 42 ms 프리딜레이와 스테레오 코러스가 있는 긴 기타 리턴. 각각 독립 하이·로우컷과 센드 사용 |
| 딜레이와 마스터 | ReaDelay 401.7 ms, 피드백 −12 dB. 마스터 26 Hz 컷, 315 Hz −0.7 dB, 약 6.8 kHz +0.45 dB, 트림 −1.1 dB |

벌스에서 공간 리턴을 낮추고 첫 후렴과 마지막 후렴이 시작되기 직전에 폭과 Wet을 연다. 리드 구간의 딜레이와 긴 잔향은 독립 리턴으로 보낸다. 기존 기타 배음과 피킹을 살리기 위해 앰프 및 왜곡 후보는 로딩 시험에 사용했다. 리미터 없이 헤드룸을 확보했다. [REAPER ReaScript API](https://www.reaper.fm/sdk/reascript/reascripthelp.html)

## 실측 결과

| 항목 | 승인 YuE2 록 | METALLIC DREAM 원본 | 최종 마스터 |
|---|---:|---:|---:|
| 길이 | 60.00초 | 107.84초 | 109.84초 |
| 음량 | −13.85 LUFS | −14.47 LUFS | −15.63 LUFS |
| True Peak | +0.26 dBTP | −0.96 dBTP | −2.15 dBTP |
| 좌우 상관도 | 0.806 | 0.850 | 0.826 |
| 모노 접기 에너지 차이 | −0.44 dB | −0.34 dB | −0.40 dB |

- **실제 전개.** 원본에서 기타가 주로 들리는 것으로 추정되는 인트로는 −23.59 dBFS, 벌스는 −18.30 dBFS, 첫 후렴은 −15.72 dBFS, 브레이크는 −25.24 dBFS, 솔로 큐는 −14.41 dBFS였다. 원본과 마스터의 10–50초 구간 추정 템포는 둘 다 112.6 BPM이다.
- **리드.** 60.15–75.75초의 6원 기타 추정 RMS는 −19.99 dBFS였고 같은 구간의 보컬 추정치는 −52.15 dBFS였다. 4원 모델의 보컬 추정치는 −75.08 dBFS다. 기타 추정치에는 지속되는 음정과 시간에 따른 주기 변화가 확인됐다. 벤딩·프레이징의 자연스러움과 분리 아티팩트는 청취 항목이다.
- **분리와 위상.** 독립 추정치만 합친 신호와 원본 사이의 상대 RMS 오차는 6원 −24.11 dB, 4원 −33.27 dB였다. 차분을 더한 REAPER 드라이 렌더의 상대 오차는 −131.94 dB다. 재합성 일치와 악기 누출은 별개의 측정이다. 6원·4원 추정 모두 솔로 구간에서 보컬 에너지가 낮았고 추정치 사이에는 22.93 dB 차이가 있었다.
- **공간 지시.** 후렴 확대 명령을 넣은 마스터와 동일 세팅의 제어 렌더를 비교했다. Side/Mid 비율이 첫 후렴 +0.98 dB, 마지막 후렴 +0.99 dB 바뀌었다. 인트로와 벌스의 PCM은 제어 렌더와 일치했다. 원본 종료 뒤 첫 0.5초의 잔향은 −95.8 dBFS였고 남은 시간 동안 더 낮아졌다.
- **보컬.** 원본 한국어 자동 전사의 문자 오류율은 33.0%, 마스터는 35.1%였다. 이번 믹스의 보컬 명료도 향상은 입증되지 않았다. 전사는 양쪽에서 악기 구간에 없는 문구도 출력했다.
- **안전과 재현.** 원본 렌더는 약 412초, 최대 footprint 4.05 GiB였다. 마스터는 48 kHz 스테레오 24-bit PCM, 내부 클리핑 0 샘플이다. 상대 경로 프로젝트를 다른 폴더에서 열어 다시 렌더한 PCM이 일치했다. 기존 승인 60초 록과 95.96초 버전은 앞선 비교 기록의 SHA-256과 일치한다. 기존 자동 테스트를 포함해 62개가 통과했다.

[생성 로그 요약](../examples/v5/generation.json) · [측정과 스템별 레벨](../examples/v5/production.json) · [솔로·전사·명령 A/B](../examples/v5/verification.json)

## 재현

[YuE2 로컬 설치 및 체크포인트](V4_ENGINE_STUDY.md)와 기존 생성 잠금 및 10 GiB 보호 한도를 재사용한다. 프리셋 가사·악보를 함께 전달하는 실행은 다음과 같다.

```sh
.venv/bin/python -m scripts.v5_generate --seed 41
```

Demucs 포트는 별도 폴더에 고정한다. 아래 명령은 현재 작업의 Python 3.12 가상환경과 기존 MLX를 기준으로 한다. 새로 생성한 폴더에서 작업하려면 각각 새 출력 경로를 지정한다.

```sh
mkdir -p .runtime/v5
git clone https://github.com/ssmall256/demucs-mlx .runtime/v5/demucs-mlx
git -C .runtime/v5/demucs-mlx checkout 9950c7daaa6ee3cf9622005e8be350c6c0163142
.bootstrap/bin/python -m pip install --no-deps --only-binary=:all: --python-version 3.12 \
  --target .runtime/v5/stem-deps312 mlx-audio-io==1.3.24 mlx-spectro==0.9.10
PYTHONPATH=.runtime/v5/stem-deps312:.runtime/v5/demucs-mlx \
  .venv/bin/python -m demucs_mlx.hub download htdemucs_6s htdemucs --output-dir .runtime/v5/stem-models
.venv/bin/python -m scripts.v5_stems "$YUE2_ORIGINAL" "$SEPARATION_DIR"
.venv/bin/python -m engine.daw.alt_rock "$YUE2_ORIGINAL" --stems "$SEPARATION_DIR" \
  --out "$PROJECT_DIR" --master-db -1.1 --lead 60.15 75.75 \
  --direction '후렴이 시작되면 기타 공간이 갑자기 넓어지게 해줘'
```

위 세션에서 지원하는 한국어 믹스 지시는 후렴 공간 확대, 확인된 기타 구간의 공격적인 EQ, 보컬 전면화와 기타 공간 확대다. 명령은 고정된 세 가지 문장으로 설정한 제어 경로이며, 기타와 보컬 수정은 근거가 되는 스템과 구간을 요구한다. `--direction`을 생략해 별도 제어 렌더를 만들고 다음 명령으로 비교한다.

```sh
.venv/bin/python -m scripts.v5_verify "$PROJECT_DIR" "$CONTROL_DIR" "$SEPARATION_DIR" "$APPROVED_ROCK_WAV"
```
