# V7 · YuE2 Native Music Recovery

## 복구한 기준 음원

[PR #6](https://github.com/mlender-ai/local-ai-music-studio/pull/6)의 head인 `af58c45b79e62def24ce1ea9034586781437fdce`에서 V7 브랜치를 시작했다. 기준음원 두 개의 실제 float WAV를 복사하고 PR의 SHA-256과 일치를 확인했다. MP3와 원본을 디코딩한 PCM의 상관도는 각각 0.99961, 0.99959였다. MP3는 당시 청취용 게인과 손실 인코딩을 포함한다.

| 기준 | 원본과 길이 | 당시 청취본 | 실제 종료 |
|---|---|---|---|
| YuE2 인디 록 | [WAV 60.00초](../examples/v7/golden/reference-original.wav) | [MP3](../examples/challengers/previews/rock-1-yue2-reference.mp3) | 60초 상한, 1,500 토큰 |
| YuE2 자연 종료 | [WAV 95.96초](../examples/v7/golden/ending-original.wav) | [MP3](../examples/challengers/previews/rock-3-yue2-ending.mp3) | 120초 상한 내 종료 토큰, 2,399 토큰 |

두 요청은 길이 상한만 바뀌었다. 시드 41을 AR과 음향 모델에 사용했다. 두 원본의 **모델 생성 ABC와 처음 1,500개 semantic 토큰이 일치**했다. 전체 파형을 다시 생성하는 대신 당시 출력물을 보존했다. 새 실행의 비트 단위 동일성은 미검증이다. 원래 요청 JSON, 모델이 출력한 악보, 토큰 스트림, 생성 기록과 파일 해시를 보관했다. 당시 스타일 설명은 116 BPM을 요청했고 모델 악보에는 114 BPM이 기록됐다. 두 원본은 당시 곡의 보컬을 포함한다. [골든 레퍼런스 명세](../examples/v7/golden/manifest.json)

백본은 YuE2-3B Q8_0, VAE는 F32이며, 두 로컬 가중치의 SHA-256을 모델 배포 목록과 대조했다. yue2.cpp `e646d5228911ae1b81ac2a261115a255848ce85f`의 Metal 백엔드, Full CoT, 32 flow steps, 8,192 토큰 KV 제한, 48 kHz stereo float WAV를 사용했다. [고정 모델 버전](https://huggingface.co/Serveurperso/YuE2-GGUF/tree/e630f2b8f6aedf8254c3186438633c1b5eeaf80a) · [실행기 소스](https://github.com/ServeurpersoCom/yue2.cpp/tree/e646d5228911ae1b81ac2a261115a255848ce85f)

## 제작 경로에서 달라진 점

| 버전 | 실제로 달라진 오디오 | 해석 |
|---|---|---|
| PR #6 | YuE2 자체 작곡·기악·보컬·전개를 하나의 스테레오로 생성. 청취용 사본에만 일정 게인 적용. | 원래 어택, 박자 사이의 움직임, 악기 간 응답과 잔향이 함께 남는다. |
| V5 | 52마디 D단조 ABC를 입력으로 고정. Demucs 추정과 차분 트랙을 다시 믹스하고 컴프레서·EQ·공간 센드 처리. 기타 후렴 고대역 폭 100→155%, 솔로 구간에 평행 처리. | 드라이 재합성 오차는 원본 대비 −131.94 dB였다. 각 추정치를 서로 다르게 처리하면 재합성의 상쇄 조건이 달라진다. 원본과 마스터의 모노 접기 차이는 −0.34→−0.40 dB였고 가창 명료도 향상 근거는 없었다. [V5 제작 로그](https://github.com/mlender-ai/local-ai-music-studio/blob/4d1a370/docs/V5_METALLIC_DREAM.md) |
| V6 | 고정 A장조 44마디 ABC, 분리 추정치에 샘플·신스·기타 응답 추가. 샘플·신스 트랙을 뮤트한 제어 렌더와 브레이크 차분은 −37.46 dBFS RMS. | 추가 레이어가 실제로 출력에 들어갔다. 원본 기반 솔로 구간에서 베이스와 드럼이 거의 물러난 상태도 그대로 이어졌다. [V6 비교 기록](https://github.com/mlender-ai/local-ai-music-studio/blob/d0aade9/docs/V6_RUSTED_SUNLIGHT.md) |
| V6.1 | 48마디 D단조 108 BPM에 맞춰 샘플 기타·베이스·드럼 1,506 이벤트 연주. YuE2 기타 38개·드럼 40개 마디 조각 사용. 기타 조각 4개 피치 이동. 기타 3파트를 드라이브와 캐비닛 IR에 보냄. | 마디 조각 내부의 속도 변화는 약 −1.6%~+1.9%였다. 더 큰 구조적 변화는 마디 교체·반복과 새 연주다. 기타 38개 배치에 소스 마디는 29개였다. 샘플 반복, 재생 속도로 만든 벤딩, 서로 다른 소스 마디를 연결한 위치에서 원래의 연속적 프레이징이 달라진다. [V6.1 편집 로그](https://github.com/mlender-ai/local-ai-music-studio/blob/8c69099/examples/v61/edits.json) · [FX 상태](https://github.com/mlender-ai/local-ai-music-studio/blob/8c69099/examples/v61/fx.tsv) |

시기별 원본과 편곡이 함께 달라졌다. 사용자 청취에서 보고된 자연스러움 저하를 개별 플러그인이나 특정 분리 모델의 청감 효과 하나로 귀속할 수 없다. V7은 입출력 경로를 간단하게 복구했다. 자연어로 밴드의 성격과 전개를 전달하고, 빈 가사로 YuE2 자체 ABC와 스테레오 오디오를 생성한다. QA는 완성된 WAV를 읽는다. REAPER에서 선택적으로 편집할 때는 전체 스테레오 WAV를 한 트랙으로 연다.

## 재현

기존 Metal 실행기와 Q8_0/F32 가중치를 재사용한다. 생성 잠금, 900초 제한, 메모리 10 GiB 보호 장치로 실행한다. 설치 및 고정 리비전은 [기존 YuE2 재현 문서](V4_ENGINE_STUDY.md)에 있다.

```sh
.venv/bin/python -m scripts.v7_native examples/v7/granite.txt --seed 73
.venv/bin/python -m scripts.v7_native examples/v7/slate.txt --seed 41
.venv/bin/python -m scripts.v4_evaluate outputs/v7/yue2-instrumental-rock-*/
.venv/bin/python -m pytest -q
```

각 실행의 새 폴더는 `outputs/v7`에 있다. `request.json`은 실제 모델 입력, `plan.abc`는 모델이 쓴 악보, `original.json`은 복원 가능한 토큰과 모델 출력 정보다. `original.wav`가 QA와 청취의 근거다.
