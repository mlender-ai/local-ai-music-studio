# Magnetic Afterhours · V7.2

**128 BPM · 4/4 · F단조 · 기악 하우스**

## 훅과 편곡

원형 A는 `C5–E♭5–D5–A♭4 | B♭4–E♭5–G4–F4`다. 첫 C는 박 사이에 짧게 치고, E♭을 붙들었다가 D 자연음을 짧게 튕겨 내린다. 둘째 마디에서는 B♭을 길게 남겨 첫 마디와 다른 시작점을 만들고, G에서 F로 해소한다. 여덟 음 사이의 쉼을 베이스 응답에 쓸 수 있게 남겼다.

| 형태 | 원형에서 달라지는 부분 |
|---|---|
| A′ | C–E♭을 유지한다. D와 A♭을 조금 늦추고, 둘째 마디의 끝을 F에서 A♭으로 올려 열린 상태로 둔다. |
| B | 첫 두 음과 둘째 마디 초반을 유지한다. 질문의 끝을 F와 C로 올리고, 종지를 다음 반복까지 미룬다. |
| Final | A의 리듬과 도착음을 유지한다. 둘째 마디의 짧은 E♭ 응답만 한 옥타브 올린다. |

편곡 목표는 1–4마디 훅의 단편, 5–12마디 A, 13–20마디 A′와 베이스 응답, 21–28마디 킥·서브를 걷어내는 브레이크다운, 29–36마디 B의 빌드, 37–48마디 A와 높은 응답이 돌아오는 드롭, 49–56마디 변주와 종지다. 이 시간표는 105초 가이드의 구성이며 실제 오디오 시각은 아래 생성 검증에서 따로 기록한다.

JSON에 리듬, 음정, 길이와 변주의 배치를 저장했다. 공식 컴파일러로 가이드의 모든 음표를 되읽어 확인하고, 기존 V7.1 악보·발성 검사를 통과한 입력만 전달한다. 기악 성부에는 훅의 일부만 써 두어 드럼, 베이스, 나머지 편곡과 음색은 YuE2가 생성하게 했다. [작곡 데이터](magnetic-afterhours.json) · [ABC](magnetic-afterhours.abc) · [YuE2 기악 악보 컴파일러](https://github.com/multimodal-art-projection/YuE/blob/1116bea76032bee5668e5f097294d082fa0b84f0/skills/yue2-music/instrumental/scripts/compile_score.py)

## 검증 경로

28초 시험과 본 생성에는 YuE2-3B Q8_0, F32 VAE, yue2.cpp Metal `e646d5228911ae1b81ac2a261115a255848ce85f`, Melody CoT, 32 flow steps, 48 kHz 스테레오, 기존 10 GiB 메모리 보호를 사용했다. 28초 시험이 V7.1 무보컬 검사와 A·변주의 파형 검사를 통과하면 같은 시드, 가이드와 샘플링 설정으로 본 생성한다. 본 생성에는 다시 전곡 무보컬 검사를 적용한다.

파형 훅 검사에서는 Demucs의 반주 추정에 남은 음이름과 박 내 위치를 예상 모티프, 11개 이조 대조군과 역순 대조군에 비교한다. 반주 전체에서 피치 클래스를 읽으므로 옥타브와 음색은 별개의 문제다. 드롭 분석은 같은 소스에서 시간에 따라 추정 킥·베이스·하이햇 대역과 박별 킥 어택 점유율을 측정한다. 컷을 편곡대로 가정하지 않고 시간상 대비가 큰 위치를 찾는다. 같은 방법을 V7.1 원본에도 적용했다. 훅의 매력, 드롭의 체감과 음색은 청취 평가 항목으로 남긴다.

## 실행 기록

| 조건 | 길이 | 발성 검사 | 결과 |
|---|---:|---|---|
| 56마디 · 시드 518 · 온도 0.80 | 28.00초 | PASS | A와 A′의 분리된 구간이 확인되어 본 생성 |
| 56마디 · 시드 518 · 온도 0.80 | 105.00초 | UNCERTAIN | 42–74초와 88초 이후에 발성 의심 창. 채택 제외 |
| 52마디 · 시드 731 · 온도 0.72 | 28.00초 | UNCERTAIN | 인트로의 발성 의심 창. 본 생성에서 제외 |
| 52마디 · 시드 518 · 온도 0.80 | 28.00초 | PASS | 원형과 변주의 파형 증거 확인 |
| 52마디 · 시드 518 · 온도 0.80 | 100.00초 | UNCERTAIN | 본 생성에서 초반과 후반에 16개 의심 창. 채택 제외 |
| 52마디 · 이어 쓰기 · 시드 647 · 온도 0.75 | 28.00초 | PASS | A를 여러 번 검출했고 분리된 시점에서 변주의 증거도 확인 |
| 52마디 · 이어 쓰기 · 시드 647 · 온도 0.75 | 96.00초 | UNCERTAIN | 28–36초의 세 의심 창. 채택 제외 |
| 52마디 · 토큰 재합성 · 오디오 시드 928 | 28.00초 | PASS | 발성 검사와 훅 검사 통과 |
| 52마디 · 토큰 재합성 · 오디오 시드 928 | 96.00초 | UNCERTAIN | 28초, 30초에 시작하는 의심 창 두 개. 채택 제외 |
| 52마디 · 토큰 재합성 · 오디오 시드 1185 | 28.00초 | PASS | 발성 검사와 훅 검사 통과 |
| 52마디 · 토큰 재합성 · 오디오 시드 1185 | 96.00초 | PASS | **채택. 47개 전곡 검사 창에서 의심 이벤트 0개** |

첫 본편은 길이 상한에서 종료됐다. 51–57초에는 두 음성 추정본에 허밍 태그가 나왔고 원본과 추정본의 전사 결과가 일치하지 않았다. 59–65초 및 67–73초 역시 짧은 모음으로 전사됐으나 자동 확정 기준에는 도달하지 않았다. 원본이 `UNCERTAIN`이므로 사운드 디자인이나 편곡 QA를 적용하지 않았다. [첫 28초 검사](qa/preflight) · [첫 본 생성 발성 검사](qa/first-full/vocal-leakage.json)

두 번째 가이드는 같은 훅을 유지하면서 Groove Development와 Build-up을 각 2마디 줄여 52마디, 97.5초로 설계했다. 짧은 518번 파일의 A와 비슷한 음정 패턴은 약 6.29, 13.47, 17.33, 21.47초에 검출됐다. A′는 약 13.45, 17.36, 19.36초에 잡혔다. 같은 시점에 두 형태와 모두 비슷하다고 나온 구간은 호환되는 음형으로 해석하고, 분리된 시간대도 확인한 뒤 본 생성했다. [52마디 기악 가이드](magnetic-afterhours-compact.abc) · [검사 기록](qa/preflight-compact-518)

두 본편 모두 짧은 테스트와 앞부분 700개 시맨틱 토큰이 일치했다. 두 번째 본편은 이 토큰이 일치하는 초반 10초 이후부터도 의심 창이 발생했다. 이 엔진은 오디오 단계에서 요청 길이 전체의 잠재 표현을 함께 생성한다. 시맨틱 접두부의 일치만으로 초반 WAV의 음색과 발성 판정을 보장할 수 없다. [두 번째 본 생성 발성 검사](qa/second-full/vocal-leakage.json) · [yue2.cpp 오디오 합성 구조](https://github.com/ServeurpersoCom/yue2.cpp/blob/e646d5228911ae1b81ac2a261115a255848ce85f/README.md#pipeline)

이어 쓰기에서는 첫 28초 시험에서 통과한 소스의 첫 14.4초에 해당하는 토큰 360개를 초기 조건으로 전달했다. 새 조건의 짧은 렌더에서 원형 A에 맞는 패턴을 약 5.24, 13.27, 20.21, 21.60, 23.07초에 검출했다. 이 경로는 토큰을 조건으로 받고 시작 구간까지 한 번에 재합성한다. [공식 소스 토큰 이어 쓰기](https://github.com/ServeurpersoCom/yue2.cpp/blob/e646d5228911ae1b81ac2a261115a255848ce85f/src/pipeline.h#L352) · [이어 쓰기 28초 검사](qa/preflight-continuation)

96초 이어 쓰기 원본에서 의심 신호가 세 창으로 줄었다. 확인된 전사는 없었지만 자동 결과가 `UNCERTAIN`이므로 제외했다. 다음 실험에서는 이 테이크의 시맨틱 토큰과 악보를 고정하고 공식 `semantic_tokens` 재합성에서 오디오 시드를 바꿨다. 같은 편곡의 새로운 파형을 생성한 뒤 발성 검사를 처음부터 적용했다. [이어 쓰기 본편 발성 검사](qa/continuation-full/vocal-leakage.json) · [공식 재합성 입력](https://github.com/ServeurpersoCom/yue2.cpp/blob/e646d5228911ae1b81ac2a261115a255848ce85f/README.md#cli-tools) · [재합성 28초 검사](qa/preflight-replay)

**채택본은 1185번 오디오 시드의 새 합성이다.** 원본 조건의 시맨틱 토큰 2,400개가 모두 동일하며, ABC 보컬 성부는 0음이다. 원본 96초를 다시 검사해 가창·허밍·발화 의심 창 없이 `PASS`였다. 291.3초에 생성됐고 프로세스 최대 메모리는 4.46 GiB였다. [1185번 28초 검사](qa/preflight-replay-1185) · [채택본 전곡 발성 검사](magnetic-afterhours/vocal-leakage.json) · [모델 요청](magnetic-afterhours/request.json)

## 실제 오디오에서 확인한 전개

| 분석 구간 | 신호에서 확인한 변화 |
|---|---|
| 초반 | 초반 몇 초는 킥 없이 시작한다. A에 해당하는 음형은 6.21초와 13.11초 등 여러 시점에 잡혔다. |
| 40.42–46.05초 · 브레이크다운 추정 | 킥 어택이 없었고 서브 대역 신호가 줄었다. 41.85초에서 훅 단편이 잡혔다. |
| 46.05–53.56초 · 빌드 추정 | 하이햇·퍼커션 대역이 커졌다. 분석한 박 중 12.5%에 킥 어택이 있었다. |
| 53.56–60.13초 · 드롭 추정 | 분석한 모든 박에서 킥 어택이 돌아왔다. 브레이크 대비 추정 베이스가 6.04 dB 커졌고, 빌드 대비 고역 퍼커션이 6.23 dB 커졌다. 56.78초와 58.64초에서 A 음형이 다시 검출됐다. |
| 후반 | A는 83.09초, 84.95초, 88.64초, 90.60초에도 검출됐다. 종지의 실제 인상은 청취 항목이다. |

V7.1 하우스에는 같은 훅 검사에서 해당 음형이 검출되지 않았다. 비교용 드롭 후보의 킥 대역 증가는 5.36 dB였고, V7.2의 브레이크다운·킥 복귀는 그보다 명확하게 측정됐다. 가이드의 정확한 옥타브 변주와 새 상위 레이어의 스테레오 확장은 검증하지 못했다. 훅의 매력과 클라이맥스의 체감도 청취 확인이 필요하다. [V7.2 음정·구간 검증](magnetic-afterhours/hook-qa.json) · [V7.1 대조 로그](qa/v71-reference.json)

## 마스터

원본은 96초 상한에서 마쳤고 자체 종료 토큰이 없었다. 재생본에는 전체 −2.57 dB로 피크 여유를 확보하고 마지막 3.75초에 코사인 페이드를 적용했다. 길이는 95.999초로 유지했다. WAV −1.60 dBTP, MP3 −1.55 dBTP였으며 클리핑은 두 파일 모두 0샘플이다. 스테레오 좌우 상관도는 0.916, 최종 100 ms RMS는 −101.49 dBFS였다. 원본과 재생 WAV의 파형 복제와 고립 임펄스 후보는 모두 0개였다. 재생 WAV를 다시 분리·검사했으며 전곡 무보컬 판정은 `PASS`였다. [재생용 MP3](magnetic-afterhours/final.mp3) · [24비트 WAV](magnetic-afterhours/final.wav) · [YuE2 생성 원본 WAV](magnetic-afterhours/original.wav) · [마스터 내역](magnetic-afterhours/delivery.json) · [재생 WAV 발성 검사](magnetic-afterhours/playback-vocal-leakage.json)

## 재현

설치한 실행 파일과 모델, 음성 감지 모델은 [V7.1 핫픽스 환경](../v71/hotfix/REPORT.md#환경과-재현)을 사용한다.

```sh
.venv/bin/python -m scripts.v72_house --write-score examples/v72/magnetic-afterhours.abc
.venv/bin/python -m scripts.v72_house
.venv/bin/python -m scripts.v72_house --plan examples/v72/magnetic-afterhours-compact.json \
    --seed 647 --temperature 0.75 --native-prefix <첫-시험-폴더>
.venv/bin/python -m scripts.v72_house --plan examples/v72/magnetic-afterhours-compact.json \
    --seed 647 --temperature 0.75 --native-prefix <첫-시험-폴더> \
    --preflight <이어-쓰기-시험-폴더> --duration-cap 96
.venv/bin/python -m scripts.v72_house --plan examples/v72/magnetic-afterhours-compact.json \
    --seed 1185 --temperature 0.75 --replay-from <이어-쓰기-본편-폴더>
.venv/bin/python -m scripts.v72_house --plan examples/v72/magnetic-afterhours-compact.json \
    --seed 1185 --temperature 0.75 --replay-from <이어-쓰기-본편-폴더> \
    --preflight <재합성-시험-폴더> --duration-cap 96
.venv/bin/python -m evaluation.house_hook <본-생성-폴더> examples/v72/magnetic-afterhours.json
.venv/bin/python -m scripts.v71_delivery <본-생성-폴더> <새-결과-폴더> --outro-fade 3.75
```
