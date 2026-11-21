# V7.1 핫픽스 · 무보컬 검사

## 이전 결과와 원인

V7의 Full CoT 자체 악보 두 개는 빈 가사였지만 각각 보컬 음표 180개와 91개를 생성했다. Melody CoT의 SHALE은 가이드의 보컬 음표가 0개였고 실제 오디오에서는 짧은 발성이 검출됐다. V7.1에서는 사전 악보 검사로 자체 생성 악보 두 개를 차단했지만, 쉼표만 있던 가이드를 사용한 하우스와 펑크에서도 허밍·구호가 검출됐다. 이 비교에서 CoT, 가이드, 시드, 음악 방향이 함께 달랐으므로 CoT 모드의 단독 효과는 확인되지 않았다. [V7 오디오 근거](../../v7/candidate-qa.json) · [V7.1 비교](../comparison.md)

고정한 yue2.cpp의 요청은 스타일과 가사를 그대로 문맥에 넣는다. 빈 가사와 금지 표현은 조건문이며 보컬 음표나 오디오를 강제로 마스킹하는 별도 제어는 이 경로에서 확인되지 않았다. 오디오는 보컬과 악기를 분리한 채널로 반환하지 않는다. 따라서 기악 스코어가 통과한 뒤에도 가창처럼 들리는 합성음이 나올 수 있다. 정확히 어느 학습 특성이나 모델 단계가 각 발성을 원인으로 만들었는지는 불명확하다. [요청 텍스트와 CoT 구현](https://github.com/ServeurpersoCom/yue2.cpp/blob/e646d5228911ae1b81ac2a261115a255848ce85f/src/prompt.h) · [스테레오 생성 구현](https://github.com/ServeurpersoCom/yue2.cpp/blob/e646d5228911ae1b81ac2a261115a255848ce85f/src/pipeline.h)

## 변경한 실행 경로

1. 공식 검증기로 실제 ABC의 박, 기악 성부, 보컬 성부, CoT와 가사 형식을 검사한다. 본 실험에는 빈 가사와 보컬 쉼표를 사용했다. 화음 있는 가이드는 Full CoT, 화음 없는 가이드는 Melody CoT에 전달했다. 기악 음표와 코드 표기는 요청에 유지한다. [공식 Instrumental 검증기](https://github.com/multimodal-art-projection/YuE/blob/1116bea76032bee5668e5f097294d082fa0b84f0/skills/yue2-music/instrumental/scripts/instrumental.py)
2. 24초 테스트를 만든다. 본 생성 명령은 테스트의 `PASS`와 WAV·요청 SHA-256을 검증하고, 길이 상한 외의 시드·스타일·ABC·CoT·CFG가 같은지 검사한다.
3. 실제 WAV와 시간 정렬된 두 Demucs 음성 추정본을 전곡 검사한다. 4초 창을 2초마다 배치하고 끝부분까지 덮는다. AudioSet PANNs가 말·가창·허밍·합창·숨소리 등에서 의심 창을 찾는다. 발성이 의심되면 Whisper-small로 원본과 두 음성 추정본의 같은 시각을 비교한다. 태그나 전사가 음성 추정과 같은 시점에서 일치하는 경우 `REJECT`한다. 조사한 단서가 불일치하거나 모델 검사가 중단되면 `UNCERTAIN`이다. 레벨만 높은 음성 추정은 단독 탈락 근거로 사용하지 않는다. [PANNs 체크포인트](https://zenodo.org/records/3987831) · [Demucs](https://github.com/facebookresearch/demucs)
4. 본 생성의 자동 무보컬 판정이 `PASS`일 때만 길이, 자체 종료, 템포, 샘플 반복과 임펄스를 검사한다. 자동 판정은 시험한 신호 범위에서 음성 증거가 없었다는 뜻이다. 사람의 청취 여부는 별도 필드로 남긴다.

## 환경과 재현

YuE2-3B Q8_0, F32 VAE, 48 kHz stereo float, 32 flow steps, yue2.cpp `e646d5228911ae1b81ac2a261115a255848ce85f`의 Metal 경로를 썼다. 생성과 분리는 기존 잠금과 메모리 보호를 사용한다. 진단은 로컬 모델로 실행했다.

학습 가중치와 YuE2 실행기 설치·체크섬은 [V4 환경 문서](../../../docs/V4_ENGINE_STUDY.md)를 따른다. 공식 Instrumental 스크립트 묶음을 `.runtime/v6/instrumental`, Whisper-small을 `.runtime/v4/whisper-small`에 둔다. PANNs 소스의 `pytorch/models.py`와 `pytorch/pytorch_utils.py`, `metadata/class_labels_indices.csv`를 고정 커밋 `d2f4b8c18eab44737fcc0de1248ae21eb43f6aa4`에서 받아 `.runtime/v7/panns`에 놓는다. CSV 파일명은 `classes.csv`다. 같은 디렉터리의 `mobilenet.pth`는 기록 3987831의 `MobileNetV1_mAP=0.389.pth`이며 MD5는 `a419303e1c88aa1b9d2ac3811563d371`다. MLX Demucs 캐시는 V7에서 사용한 `.runtime/v5`의 `demucs-mlx`, `stem-deps312`, `stem-models`를 재사용한다. 모델 진단 실패 시 결과는 `UNCERTAIN`으로 남는다.

```sh
guide=examples/v71/hotfix
.venv/bin/python -m scripts.v71_strict house-techno-128 "$guide/house-direction.txt" "$guide/house-short-form.abc" --seed 518 --cot melody --cfg-scale 2.4 --semantic-temperature 0.80
.venv/bin/python -m scripts.v71_strict highteen-punk-144 "$guide/punk-direction.txt" "$guide/punk.abc" --seed 43 --cfg-scale 1.8
```

본 생성은 같은 명령에 `--preflight <통과한 테스트 폴더>`와 각 장르의 `--duration-cap`을 추가한다. 채택본의 상한은 하우스 86초, 펑크 90초였다. 기존 후보 WAV는 `python -m evaluation.vocal_leakage <후보 폴더>`로 검사한다. 본 생성이 두 검사를 통과하면 `python -m scripts.v71_delivery <본 생성 폴더> <새 결과 폴더>`로 원본, WAV, MP3 및 검증 기록을 내보낸다.

## 24초 사전 검사

| 장르 | 시드 | CoT | CFG | 결과 |
|---|---:|---|---:|---|
| 하우스 | 151 | Full | 1.0 기본값 | REJECT · 원본과 두 음성 추정본에서 같은 구절 |
| 하우스 | 647 | Full | 1.8 | PASS · 의심 창 0개 |
| 하우스 | 518 | Melody | 2.4 | PASS · 의심 창 0개 |
| 하우스 · 짧은 가이드, 온도 0.80 | 518 | Melody | 2.4 | PASS · 의심 창 0개 |
| 펑크 | 73 | Full | 1.0 기본값 | REJECT · 짧은 발성과 반복 구절 |
| 펑크 | 43 | Full | 1.8 | PASS · 의심 창 0개 |
| 펑크 | 121 | Melody | 2.4 | PASS · 의심 창 0개 |

사전 검사 WAV는 23.999초였으며 모두 보컬 성부 음표가 0개였다. 312개의 유성 보컬 음표가 있던 기존 펑크 악보는 이 핫픽스의 공식 검증 함수에서 REJECT를 반환했다. [사전 검사 증거](preflight) · [실패 대조 악보 검사](score-negative-control.json)

소스에서 지원하는 `cfg_scale`은 시맨틱 토큰 추론에서 조건부와 무조건부 문맥의 비중을 조정한다. 보컬 전용 게이트는 오디오 검사로 구현했다. 이번 비교에서는 CFG와 시드를 함께 바꾸었으므로 양호한 결과를 CFG 단독 효과로 해석할 수 없다. [실행기 CFG 파라미터](https://github.com/ServeurpersoCom/yue2.cpp/blob/e646d5228911ae1b81ac2a261115a255848ce85f/src/request.h)

## 본 생성 비교

하우스 647의 24초와 90초 요청은 길이 상한 외에 일치했고, 실제 시맨틱 토큰 첫 600개도 동일했다. 그럼에도 본 생성의 52–68초 창에서 음성 후보가 나왔고 60초 전후 다수 창에서 동일 어구가 세 입력에 걸쳐 검출됐다. 이 후보는 `REJECT`로 분류했다. 길이 상한까지 재생됐으며 마지막 100 ms는 −12.41 dBFS RMS였다. [하우스 647 본 생성 판정](full-runs/house-techno-128/647)

하우스 518의 두 번째 본 생성은 89.999초, 44개 검사 창에서 무보컬 `PASS`였다. 킥에서 128.0 BPM, 믹스에서 127.9 BPM을 확인했다. 킥이 줄었다 다시 들어오는 구간이 관찰됐으며, 길이 상한에서 음이 남은 채 출력이 끝났다. 원본 마지막 100 ms는 −24.44 dBFS RMS였다. [하우스 518 본 생성 판정](full-runs/house-techno-128/518)

하우스 518의 마지막 본 생성에는 같은 모티프의 짧은 가이드와 공식 시맨틱 샘플링 온도 0.80을 사용했다. 64.239초에서 모델 자체 종료했으며 32개 검사 창에서 유사 발성 증거가 없었다. 킥 대역과 믹스 모두 127.9 BPM으로 측정됐다. 킥 대역 4박 그룹 33개 중 20개에서는 네 박에 모두 어택이 있었다. 추정 드럼은 0–8초에 거의 없고 12–16초부터 커진다. 24–32초에 에너지가 한 차례 내려가고 32초부터 다시 높아진다. 마지막 100 ms RMS는 −63.53 dBFS다. 파형 복제와 고립 임펄스 후보는 0개였다. 별도의 브레이크다운과 훅의 재등장으로 들리는지는 청취 미확인이다. [공식 샘플링 파라미터](https://github.com/ServeurpersoCom/yue2.cpp/blob/e646d5228911ae1b81ac2a261115a255848ce85f/src/request.cpp) · [하우스 채택본 QA](full-runs/house-techno-128/518-temp080)

펑크 43은 70.039초에서 자연 종료했다. 35개 검사 창에 유사 발성 이벤트가 검출되지 않았다. 전곡 음성 추정 RMS는 두 모델에서 전체 믹스보다 약 64.35 dB와 69.05 dB 낮았다. 믹스의 143.2 BPM과 킷의 71.8 BPM이 배수 관계를 이뤘다. 기타 추정 성분이 0–4초에 앞서고, 4–8초에 킷과 베이스가 함께 들어온다. 끝부분의 100 ms RMS는 −88.23 dBFS다. 파형 복제·고립 임펄스 검사 후보는 0개였다. 프레이징과 훅의 청감 평가는 미확인이다.

## 채택본과 기술 검증

| 장르 | 시드 | 실측 BPM | 길이 | 보컬 음표 | 자동 발성 검사 |
|---|---:|---:|---:|---:|---|
| 하우스 테크노 | 518 | 127.9 | 64.239초 | 0 | PASS · 32개 창 |
| 하이틴 펑키 펑크 록 | 43 | 143.2 | 70.039초 | 0 | PASS · 35개 창 |

재생본에 고정 게인만 적용했다. 하우스는 −3.12 dB, 펑크는 −3.03 dB로 조정했다. 두 WAV는 −1.60 dBTP이며, MP3는 각각 −1.59, −1.55 dBTP였다. 재생본 네 개 모두 48 kHz 스테레오로 디코딩했으며 원본 길이를 보존했고 클리핑 0샘플을 기록했다. [하우스 원본](house-techno-128/original.wav) · [하우스 WAV](house-techno-128/final.wav) · [하우스 MP3](house-techno-128/final.mp3) · [펑크 원본](highteen-punk-144/original.wav) · [펑크 WAV](highteen-punk-144/final.wav) · [펑크 MP3](highteen-punk-144/final.mp3)

생성 모델은 실제 보컬과 닮은 소리를 낼 수 있어 두 채택본에서도 전곡 검사의 범위 안에서만 결론을 내렸다. PANNs 임계값은 이 생성 모델의 모든 유사 발성에 대해 감도와 오탐률을 검증한 값이 아니다. 청취에 의한 무보컬 확정, 훅의 인상과 악기 질감은 미확인이다. [하우스 발성 검사](house-techno-128/vocal-leakage.json) · [펑크 발성 검사](highteen-punk-144/vocal-leakage.json)
