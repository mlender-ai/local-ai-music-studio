# V7.1 · 두 장르의 YuE2 연주곡 실험

각 장르에서 세 후보를 검사했다. 두 후보는 악보 단계에서 차단했고 네 개의 실제 스테레오를 생성했다. 128 BPM대 하우스와 144 BPM대 펑크의 템포는 확인했다. 무보컬 기준을 통과한 최종곡은 두 장르 모두 0개였다.

- 하우스 검수본은 목표 템포와 자연 종료를 확보했던 73번 테이크다. [탈락 후보 MP3](house-techno-128/attempts/seed-73/review.mp3)
- 펑크 검수본은 요청 길이와 템포에 가까웠던 419번 테이크다. [탈락 후보 MP3](highteen-punk-144/attempts/seed-419/review.mp3)

두 검수 사본에는 재생 피크 여유를 위해 하우스 −1.59 dB, 펑크 −3.39 dB의 고정 게인을 적용하고 MP3로 인코딩했다. 실제 float 원본 네 개는 로컬 `outputs/v71`의 각 후보 폴더에 보존했다.

## 입력과 검증 방법

128 BPM 하우스 테크노는 아날로그 플럭 훅과 4비트 킥을 중심으로, 144 BPM 하이틴 펑키 펑크 록은 팜뮤트 리프, 열린 파워 코드와 기타 리드가 주고받는 밴드로 요청했다. 음악적 목표와 전개는 장르별 `direction.txt`에 있다.

YuE2-3B Q8_0, F32 VAE, Metal, 32 flow steps와 95초 상한을 사용했다. BPM은 실제 YuE2 스타일 텍스트에 전달했다. 요청의 BPM, ABC의 `Q:`, 오디오의 주기성은 각각 기록했다. 타임스트레칭과 재편곡 없이 생성한 스테레오를 검사했다. [기존 YuE2 설치·가중치](../../docs/V4_ENGINE_STUDY.md) · [공식 연주곡 입력 검증기](https://github.com/multimodal-art-projection/YuE/blob/1116bea76032bee5668e5f097294d082fa0b84f0/skills/yue2-music/instrumental/scripts/instrumental.py)

- Melody CoT는 보컬 성부의 쉼표와 원래 모티프의 약식 기악 가이드에 빈 가사를 사용한다. 하우스는 기악 음표 34개, 펑크는 42개이며 드럼·베이스는 YuE2가 만든다.
- Full CoT 자체 작곡은 같은 실행기 릴리스의 `yue-plan`을 먼저 실행한다. 보컬 성부나 가창 지시가 있는 악보는 보존하고 합성 전에 제외한다. 악보를 통과하면 동일한 계획 텍스트를 YuE2의 지원 입력인 `abc`에 넣는다. [yue-plan 문서](https://github.com/ServeurpersoCom/yue2.cpp/blob/e646d5228911ae1b81ac2a261115a255848ce85f/README.md#server-options)
- 마지막 실험 조건에는 기악 모티프와 소수의 화음 단서, 공식 형식대로 악보와 일치하는 섹션 태그만 사용했다. 보컬 성부의 음은 모두 쉼표다.
- 원본 스테레오와 두 Demucs 추정본을 읽기 전용으로 조사했다. Whisper-small의 무음성 추정과 의심 창 전사, PANNs의 AudioSet 태깅을 비교했다. 음성처럼 울리는 신스나 기타는 분리·전사 단계에서 오판될 수 있다. 원본과 두 추정본에 일치하는 발성, 시간·레벨, 태깅을 함께 검토했다. [PANNs 모델](https://zenodo.org/records/3987831)

오디오 QA의 2초 복제 파형 검사는 코드·리프의 정상 반복과 별도로 해석한다. 킥 대역 어택과 4박 그룹은 런타임 분석 결과다. 훅의 인상, 연주 질감, 장르의 음악적 설득력은 청취 영역으로 남긴다.

## 후보별 결과

아래 BPM은 요청값을 분석에 고정하지 않고 얻은 주기성 후보를 해석한 값이다. 64.0/127.9와 71.5/142.8처럼 배수 관계인 값은 전체 믹스와 드럼 추정치, 킥 대역을 함께 비교했다.

| 장르 · 시드 | 조건 | ABC / 관측 BPM | 길이와 끝부분 | 판단 |
|---|---|---|---|---|
| 하우스 73 | Melody CoT · 기악 가이드 · 빈 가사 | 128 / 127.9 | 78.24초, 모델 종료 후 마지막 100 ms −86.1 dBFS | 0–6초 원본과 두 보컬 추정에서 같은 영어 구절이 검출돼 제외 |
| 하우스 331 | Full CoT · 자체 악보 | 128 / 합성 전 차단 | 악보가 4,096 토큰에서 잘림 | Vocal 성부에 음표가 있어 합성 전 제외 |
| 하우스 311 | Full CoT · 약식 화음 · 섹션 태그 | 128 / 127.9 | 75.00초, 모델 종료 후 마지막 100 ms −52.4 dBFS | 0초 창의 “Ah”, 18초 창의 “Hmm”이 원본과 두 추정본에 함께 나타나 제외 |
| 펑크 73 | Melody CoT · 기악 가이드 · 빈 가사 | 144 / 143.0 믹스, 142.8 드럼 | 66.84초, 모델 종료 후 마지막 100 ms −18.2 dBFS | 요청보다 짧고 끝까지 큰 레벨. 짧은 발성 의심 구간의 전사는 서로 달랐음 |
| 펑크 17 | Full CoT · 자체 악보 | 146 / 합성 전 차단 | 모델 악보를 보존 | Vocal 성부에 음표가 있어 합성 전 제외 |
| 펑크 419 | Full CoT · 약식 화음 · 섹션 태그 | 144 / 144.2 믹스, 144.1 드럼 | 83.32초, 모델 종료 후 마지막 100 ms −29.1 dBFS | 60초 창의 반복 구호가 원본과 두 추정본에 함께 나타나 제외 |

하우스 73에서 127.9 BPM 격자의 41개 4박 그룹 중 29개에 네 박 모두 저역 어택이 있었다. 하우스 311에서는 39개 중 18개였다. 전체 믹스에서 64 BPM도 강하지만 두 테이크의 킥 대역에서 가장 강한 주기는 127.9 BPM이었다. 하우스 311의 보컬 추정 RMS는 원본보다 8.4/9.0 dB 낮았으며, 원본의 허밍 태그 최대값은 0.492, 6원 음성 추정에서는 0.847이었다. 이 값은 음성 유무 확률로 해석하지 않고 보류 근거로 사용했다.

펑크 73의 드럼 추정에서 71.5와 142.8 BPM이 함께 나타났고 전체 믹스 최상위 후보는 143.0 BPM이었다. 킥만 보면 95 BPM대 패턴이 더 강했다. 따라서 킥 패턴이 매 박 반복된다고 해석하지 않았다. 두 모델의 음성 추정 RMS는 −24.3/−24.7 dB 상대였고, 에너지가 높은 30초·48초 구간에서 상이한 자동 전사가 나왔다.

펑크 419의 원본 믹스 후보는 72.2/144.2 BPM, 두 드럼 추정은 72.1/144.1 BPM을 함께 지지했다. 144 BPM 후보의 킥 어택은 절대 박마다 나타나지 않았다. 419의 전체 믹스 대비 음성 추정 RMS는 −7.51/−7.47 dB였다. 네 원본의 복제 파형·고립 임펄스 검사에서 모두 후보 0개를 기록했다. 311과 419의 float 원본 true peak는 각각 +0.19, +1.79 dBTP였다.

가이드 악보의 훅·필인·브레이크를 음악적 성공의 근거로 쓰지 않았다. 무보컬 검사에서 채택한 결과가 없으므로 훅과 라이브 연주감의 비교 청취는 미확인이다.

## 재현

V4 문서의 설치 절차로 고정 YuE2 백본과 VAE, 실행기를 준비한다. Full CoT 사전 검사에는 동일한 소스에서 `yue-plan` 도구를 추가로 빌드한다.

```sh
cmake --build .runtime/v4/yue2cpp/build --target yue-plan -j2

.venv/bin/python -m scripts.v7_native examples/v71/house-techno-128/direction.txt \
  --genre house-techno-128 --bpm 128 --duration-cap 95 --seed 73 --cot melody \
  --score examples/v71/house-techno-128/guide.abc

.venv/bin/python -m scripts.v7_native examples/v71/highteen-punk-144/direction.txt \
  --genre highteen-punk-144 --bpm 144 --duration-cap 95 --seed 73 --cot melody \
  --score examples/v71/highteen-punk-144/guide.abc

.venv/bin/python -m scripts.v7_native examples/v71/house-techno-128/direction.txt \
  --genre house-techno-128 --bpm 128 --duration-cap 95 --seed 331 --screen-score

.venv/bin/python -m scripts.v7_native examples/v71/highteen-punk-144/direction.txt \
  --genre highteen-punk-144 --bpm 144 --duration-cap 95 --seed 17 --screen-score
```

보조 조건은 각 폴더의 `alternate-direction.txt`, `--cot full --score <sparse-harmony.abc> --lyrics-file <sections.txt>`를 사용한다. 시드는 하우스 311, 펑크 419다. 출력 폴더는 `outputs/v71`에 추가된다. 해당 폴더를 `scripts.v71_qa`에 넘기면 생성·악보·파형·템포를 읽기 전용으로 점검한다. `diagnostics/htdemucs*/`에 진단용 WAV를 두면 스템 통계를 함께 기록한다.

저장소 자동 테스트 64개를 통과했다. 기존 Pydantic 경고 한 건이 남아 있다. [하우스 개별 기록](house-techno-128/attempts) · [펑크 개별 기록](highteen-punk-144/attempts)
