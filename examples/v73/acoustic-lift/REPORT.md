# Strange Afternoon · Acoustic Lift

## 레퍼런스를 확인한 범위

앞선 V7.3에서는 〈Godspeed!〉의 발매 소개와 크레딧을 확인했다. 이번 수정에서 Apple Music이 제공하는 29.98초 공식 미리듣기 신호를 분석했다. 발성이 있는 발매본의 한 구간이며, 원곡 전체에서 해당 구간의 위치는 확인되지 않는다. 이 짧은 신호에서는 약 75.8 BPM과 두 배의 151.6 BPM 주기가 잡혔고 기타 태그들은 낮았다. 이 결과로 인트로에서 하이라이트까지의 악기 전환이나 원곡 코드 진행을 확정할 수 없다. 통기타로 시작해 하이라이트에서 일렉기타가 합류하는 구성은 사용자 청취 피드백을 반영했다. 외부 미리듣기 음원은 분석에만 사용했다. [공식 Apple Music 미리듣기](https://music.apple.com/us/album/godspeed-single/6800201199) · [혁오 공식 영상](https://www.youtube.com/watch?v=-czMu2ADVu4)

## 새 작곡과 편곡

계획은 D장조, 94 BPM, 4/4, 38마디다. `D–Gmaj7`의 통기타 핑거피킹으로 시작하고 `Dsus2`로 여백을 남긴다. 하이라이트 전에는 `Asus4–A`로 긴장을 모아 D장조로 돌아온다. `Em7`은 중간에 짧게 머문다. 기타 주제는 `A3–F♯4–E4–D4 | B3–A3–D4–F♯4`로, 첫 마디에서 크게 뛰고 내려온 뒤 다음 마디가 다시 위로 열린다. 일렉기타는 뒤쪽에서 같은 윤곽을 긴 음과 높은 옥타브로 받는 역할이다.

이번에는 화음표를 공식 기악 ABC에 함께 넣고 Full CoT를 사용했다. 보컬 성부의 음표는 0개다. 29초 시험에서 원형에 해당하는 구간이 0.52초, 4.98초 등에서 검출됐다. 0–16초에 걸친 일곱 검사 창에서 믹스와 기타 추정 신호에 통기타가 강하게 잡혔고, 일렉기타가 우세한 창은 없었다. 이 값은 음색 분류 근거다. 실제 출력이 계획과 일치하는지는 전곡 오디오와 별도로 비교한다. [작곡 계획](plan.json) · [YuE2에 전달한 ABC](guide.abc)

## 실제 결과

시드 1185로 99초 원본을 생성했다. YuE2-3B Q8_0, F32 VAE, Full CoT, CFG 2.5, 온도 0.70, 32 flow steps, 48 kHz 스테레오를 사용했다. 앞서 통과한 29초 조건을 그대로 유지했다. 생성에는 383.9초가 걸렸고 프로세스 최대 메모리는 4.16 GiB였다. 실측 전체 박 주기는 약 86.3 BPM, 후반 킷은 약 87.7 BPM이었다. 94 BPM은 작곡 가이드의 설정이다. [29초 검사](qa/preflight) · [전곡 원본 검사](qa/native)

| 시점 | 실제 오디오 확인 |
|---|---|
| 0:00–0:16 | 믹스와 기타 추정에서 통기타 태그가 우세하다. 기타 추정의 F♯ 활성도는 F보다 높았고 D와 A도 두드러졌다. |
| 0:44.5–0:50.1 | YuE2 원본에서 드럼·베이스가 자연스럽게 쉬고 기타가 남는다. |
| 1:27–1:33 | 베이스 추정의 세 분석 창에서 `G–A–D` 저음 진행을 확인했다. 전곡 코드 전사를 의미하지 않는다. |
| 1:28.73 | 별도 일렉 응답 트랙의 시작점이다. A 위에서 짧게 응답하고 D가 돌아올 때 F♯을 길게 유지한 뒤 D로 내린다. |

원본의 하이라이트에서 일렉 음색이 확실히 분리되지 않아, 실제 픽업으로 녹음한 CC0 Emilyguitar 샘플로 6.57초짜리 응답 트랙을 렌더했다. 국소 RMS는 기존 믹스보다 4.5 dB 낮다. 약한 새츄레이션과 짧은 잔향을 적용했다. 일렉 트랙의 존재와 시점은 녹음 출처, 별도 WAV와 삽입 전후 샘플 검사로 확인했다. 음색 자동 분류기는 단독 처리 트랙에서도 일렉을 강하게 분류하지 못했다. 최종 파일의 첫 88.73초는 전역 재생 게인을 적용하기 전까지 원본과 샘플 단위로 일치한다. [후반 베이스 확인](qa/native/late-bass.json) · [일렉 소스와 처리 기록](master/electric-response.json) · [실제 녹음 소스](https://github.com/sfzinstruments/karoryfer.emilyguitar)

원본, 일렉 응답을 더한 믹스, 최종 WAV 모두 전곡 발성 자동 검사에서 `PASS`였다. 마스터는 99초 상한에서 끝난 원본의 마지막 4.4초에 페이드를 적용했다. WAV와 MP3는 48 kHz 스테레오로 디코딩했고 클리핑은 0샘플이었다. 최종 true peak는 각각 −1.60 dBTP와 −1.61 dBTP다. 레퍼런스 전체의 직접 청취, 새 곡의 따뜻함과 하이라이트의 체감은 별도의 청취 항목이다. [마스터 WAV](master/final.wav) · [MP3](master/final.mp3) · [YuE2 원본](master/yue2-original.wav) · [최종 음성 검사](master/playback-vocal-leakage.json)

## 재현

기존 YuE2와 검사 모델, 버전 고정 샘플 저장 위치를 사용한다. [설치 환경](../../v71/hotfix/REPORT.md#환경과-재현)

```sh
parts=examples/v73/acoustic-lift
.venv/bin/python -m scripts.v73_indie --plan "$parts/plan.json" \
  --output-root outputs/v73-acoustic-lift --seed 1185 --temperature 0.70 --cfg-scale 2.5
.venv/bin/python -m scripts.v73_indie --plan "$parts/plan.json" \
  --output-root outputs/v73-acoustic-lift --seed 1185 --temperature 0.70 --cfg-scale 2.5 \
  --preflight <29초-검사-폴더> --duration-cap 99
.venv/bin/python -m scripts.v73_acoustic_lift <본편-폴더> <새-믹스-폴더> \
  "$parts/electric-part.json" "$parts/plan.json"
.venv/bin/python -m scripts.v71_delivery <믹스-폴더> <새-마스터-폴더> --outro-fade 4.4
```
