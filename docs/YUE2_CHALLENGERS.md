# YuE2 청취 기준과 다음 비교

사용자는 기존 한국어 인디 록, 한국어 팝 발라드, 재즈 힙합 연주곡을 듣고 세 장르 모두 YuE2 합격, ACE-Step Turbo 불합격으로 판정했다. 후속 비교는 각 장르에서 사용자가 들은 YuE2 원본을 재사용한다. 새 후보의 사용자 청취 결과는 대기 중이다.

## 청취 파일

장르별 24비트 WAV 세 곡의 음량을 0.04 LU 이내로 맞췄다. 록과 발라드는 약 −18 LUFS, 재즈 힙합은 −18.88 LUFS다. 아래는 같은 청취 사본의 256 kbps MP3다. 전체 길이 WAV와 32비트 모델 원본의 로컬 위치, 실행 설정, 전사 및 체커 기록은 [측정 결과 JSON](../examples/challengers/results.json)에 있다.

| 장르 | 승인 기준 YuE2 | HeartMuLa | 새 YuE2 |
|---|---|---|---|
| 인디 록 | [60.00초](../examples/challengers/previews/rock-1-yue2-reference.mp3) | [60.00초](../examples/challengers/previews/rock-2-heartmula.mp3) | [95.96초 · 모델이 끝낸 버전](../examples/challengers/previews/rock-3-yue2-ending.mp3) |
| 팝 발라드 | [45.00초](../examples/challengers/previews/ballad-1-yue2-reference.mp3) | [44.96초](../examples/challengers/previews/ballad-2-heartmula.mp3) | [43.96초 · 새 멜로디와 화성](../examples/challengers/previews/ballad-3-yue2-score.mp3) |
| 재즈 힙합 | [40.00초](../examples/challengers/previews/jazz-1-yue2-reference.mp3) | [40.00초](../examples/challengers/previews/jazz-2-heartmula.mp3) | [34.00초 · 새 모티프와 브레이크](../examples/challengers/previews/jazz-3-yue2-score.mp3) |

## 확인된 차이

- **록.** 상한을 늘린 YuE2는 승인본과 악보 및 첫 1,500개 음악 토큰이 동일했고, 2,399번째 프레임에서 종료 신호를 냈다. 최종 0.1초의 RMS는 기준의 −15.75에서 −69.49 dBFS로 내려갔다. 전체 길이에서 음향 디코딩을 다시 수행했다. 자동 가사 오류율은 기존 YuE2 39.2%, 새 엔딩 47.3%, HeartMuLa 52.7%였다.
- **발라드.** HeartMuLa의 한국어 자동 가사 오류율은 17.7%였다. 기준 YuE2는 80.6%, 악보 지정 YuE2는 71.0%였다. HeartMuLa의 지배적 주기 추정은 106 BPM으로 요청한 72 BPM과 차이가 났다. 첫 번째 지정 악보는 18.80초에 끝났고 마지막 0.1초 RMS는 −14.55 dBFS였다. 프레이즈 사이 여백을 둔 두 번째 시도는 43.96초에 모델 종료 신호가 나왔고 마지막 0.1초 RMS는 −53.03 dBFS였다.
- **재즈 힙합.** 지정 악보 YuE2의 주기 추정은 89.9 BPM으로 기준의 89.7 BPM과 가까웠다. 새 파일 마지막 0.1초의 RMS는 −87.96 dBFS였다. HeartMuLa의 템포는 자동 분석에서 모호했다. 무보컬 입력에도 전사기가 반복되는 문구를 출력했으므로 실제 보컬 혼입 여부는 청취로 확인해야 한다.
- **메모리.** HeartMuLa 첫 실행은 macOS 메모리 보호로 중단됐다. 가중치 텐서를 순차적으로 읽고 다시 실행한 결과, 세 곡 모두 79~150초에 렌더했다. 단계별 최대 footprint는 6.24 GiB였다. 모델 가중치는 내려받아 로컬 Apple M5 24GB에서 실행했다. 외부 생성 사용료는 없었다.
- **검증 범위.** 60초 이하 파일에서 단일 임펄스와 거의 동일한 2초 반복 파형 선별 결과는 모두 0건이었다. 95.96초 록은 끝부분 RMS, 음량·트루피크 및 가사 전사를 확인했다. Whisper-small 자동 전사 결과에는 가창 인식 오류가 포함된다. 가창, 장르 충실도, 편곡, 악기 상호작용과 전체 선호는 청취 판정을 기다린다.

## 비교 설계

- **HeartMuLa**는 같은 가사·BPM 목표·길이 상한·시드 41에서 다른 모델이 어떻게 노래하고 연주하는지 비교한다. 두 모델은 다른 난수 생성기를 사용한다. 같은 시드 번호가 같은 잠재 노이즈를 보장하지 않는다. HeartMuLa에는 같은 제작 의도를 쉼표로 구분된 태그로 전달한다. 실제 입력은 각 실행의 request.json에 있다.
- **악보 지정 YuE2**는 모델·가사·스타일 입력·시드·상한·32스텝을 유지하고 ABC 악보만 교체한다. 재즈는 Dm9–G13에 짧은 응답을 두고, Bbmaj9–Am7–Gm9–C13 변주 뒤 두 마디 브레이크와 첫 모티프 귀환을 썼다. 발라드는 D장조 한 마디 피아노 인트로, 짧은 절, 높은 음역으로 시작하는 후렴, 마지막 피아노 응답을 썼다. 악보의 화성·악기 등장이 녹음에 얼마나 반영됐는지는 청취 항목이다. [재즈 악보](../examples/challengers/jazz.abc) · [발라드 악보](../examples/challengers/ballad.abc)
- **인디 록 엔딩**은 YuE2에서 기존 60초 상한을 120초로만 늘린 별도 실험이다. 모델의 종료 신호, 동일 시드의 악보와 첫 60초 음악 토큰, 파일 끝의 에너지를 확인한다. 파형을 이어 붙이거나 페이드아웃을 추가하지 않는다.

## 재현

기존 YuE2 준비 절차는 [1차 엔진 비교](V4_ENGINE_STUDY.md)에 있다. 아래 명령은 매번 새 실행 폴더를 만든다.

```sh
.venv/bin/python -m scripts.v4_study yue2 jazz --score examples/challengers/jazz.abc
.venv/bin/python -m scripts.v4_study yue2 ballad --score examples/challengers/ballad.abc
.venv/bin/python -m scripts.v4_study yue2 rock --duration-cap 120
```

HeartMuLa는 실험 전용 Swift 실행기를 사용한다. 8비트 작곡 모델과 FP16 디코더를 각기 다른 프로세스에서 실행한다. 두 단계 사이에 8개 코드북을 저장하고 모델 메모리를 반환한다. 기존 생성 잠금, 프로세스당 10 GiB·900초, 시스템 메모리 보호를 적용한다. 디코딩은 10스텝, guidance 1.25, 시드에서 독립적으로 파생한 디코더 노이즈를 쓴다. 디코더의 피크가 0.891을 넘으면 원 포트와 같은 일정 게인으로 감쇠한다. 청취 음량 보정은 별도 WAV에만 적용한다. [모델](https://huggingface.co/mlx-community/HeartMuLa-oss-3B-8bit) · [코덱](https://huggingface.co/mlx-community/HeartCodec-oss-fp16) · [Swift 포트](https://github.com/xocialize/mlx-heartmula-swift/tree/286ec73dce44f8d470d85ae7ad1db000feac5e06)

macOS 26, Swift 6.2 이상과 Xcode Metal Toolchain에서 빌드한다. 프로젝트 루트에서 실행한다.

```sh
hf download mlx-community/HeartMuLa-oss-3B-8bit --revision 7381f061892852cd71b18be01332ce9ef4730911 --local-dir .runtime/v41/lm
hf download mlx-community/HeartCodec-oss-fp16 --revision f36294004e63cf6c66848dbdd43ff6f8ed65dde9 --local-dir .runtime/v41/codec
swift build --package-path experiments/heartmula --scratch-path .runtime/v41/build -c release --build-system swiftbuild --arch arm64 --product HeartStudy
STUDY_BIN="$(swift build --package-path experiments/heartmula --scratch-path .runtime/v41/build -c release --build-system swiftbuild --arch arm64 --show-bin-path)/HeartStudy"
.venv/bin/python -m scripts.heartmula_study --binary "$STUDY_BIN" rock ballad jazz
```

각 장르에서 첫 번째 인자로 승인 원본 폴더를 전달한다. 나머지 인자는 같은 시드와 브리프로 만든 후보 폴더다. 모든 파일에 일정 게인을 적용해 24비트 WAV로 저장하고 음량과 트루피크를 재측정한다. 기존 생성 원본은 각 실행 폴더에 보관한다.

```sh
.venv/bin/python -m scripts.challenger_listen "$REFERENCE" "$CHALLENGER" --out "$NEW_LISTENING_DIRECTORY"
```
