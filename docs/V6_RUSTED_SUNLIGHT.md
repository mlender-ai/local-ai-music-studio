# RUSTED SUNLIGHT · Warm Mechanical Noise

**107.50초 연주곡.** 첫 기타의 짧은 음형을 중반에 한 옥타브 위로 돌려주고, 타자기의 세 번의 8분음표 간격과 라이브 드럼의 네 박이 엇갈리도록 편곡했다. 55.5초에 기계음이 앞으로 나오고 62.7초에 기타가 공간을 차지한다. 77.1초에 드럼과 베이스가 강하게 돌아온다. [최종 MP3](../examples/v6/rusted-sunlight-master.mp3) · [24-bit WAV](../examples/v6/rusted-sunlight-master.wav) · [YuE2 생성 원본](../examples/v6/rusted-sunlight-original.wav)

## 생성과 보컬 확인

새 A장조 44마디 악보에 E–B–C♯–B–A 모티프와 차용한 F장조 화음을 썼다. 공식 연주곡 입력과 같이 가사 문자열을 비우고 Vocal 성부에는 모든 마디에 코드와 쉼표만 배치했다. Ins 성부가 모든 음을 연주한다. C++ 런타임이 받은 확장 ABC에는 곡 제목과 add9 코드 표기가 들어 있다. 공식 Python 번들 검증기는 이 두 표기를 제한한다. 저장소 테스트는 실제 입력의 양쪽 성부 길이와 보컬 음표 부재를 검사하고, 실행 시 저장된 악보와 입력 악보는 바이트 단위로 일치했다. [공식 연주곡 입력 검증 코드](https://github.com/multimodal-art-projection/YuE/blob/1116bea76032bee5668e5f097294d082fa0b84f0/skills/yue2-music/instrumental/scripts/instrumental.py) · [새 악보](../examples/v6/rusted-sunlight.abc)

YuE2 Q8, F32 VAE, Metal, Full CoT에 작성한 악보를 전달했다. 32 steps, seed 73, 길이 상한 110초로 한 번 생성했다. 모델이 2,645번째 semantic step에서 종료했고 원본은 105.80초였다. 생성 시간은 386.4초, 최대 메모리 footprint는 3.98 GiB였다. [생성 기록](../examples/v6/generation.json)

두 Demucs 모델의 보컬 추정 RMS는 원본보다 각각 48.3 dB, 61.8 dB 낮았다. 원본 전체를 6초씩 검사한 Whisper-small의 무음성 확률은 0.53–0.95였다. 지속 가창을 지지하는 증거는 약하다. 짧은 허밍처럼 들리는 기타나 노이즈를 완전히 분별하는 검사는 없으며 이번 결과에는 사람의 전곡 청취 승인이 필요하다. 보컬 채널을 빼는 처리는 수행하지 않았다. [구간별 악기·음성 검사](../examples/v6/foundation.json)

## 들을 지점과 편집 구조

| 시간 | 실제 세션에 반영한 편곡 |
|---|---|
| 0–19.4초 | 근접한 클린 기타 사이로 금속 파이프가 두 번 울린다. 9.8초부터 짧은 엇박 응답을 배치했다. |
| 19.4–55.5초 | 타자기가 세 개의 8분음표마다 악센트를 만든다. 신스가 짧게 응답하고 29.1초부터 퍼즈 기타의 긴 공간 리턴이 열린다. 두 프레이즈 끝에 타자기와 파이프를 번갈아 배치했다. |
| 55.5–62.7초 | 드럼 추정 트랙을 16 dB, 기타를 2 dB 낮춘다. 파이프 타격의 속도·강세를 바꾸고 왼쪽과 오른쪽에서 타자기로 응답한다. |
| 62.7–77.1초 | 원본에서 드럼·베이스가 물러난 구간의 기타를 3 dB 올렸다. 도입부 기타의 세 조각이 66.9초, 71.1초, 74.7초에 응답한다. 처음 둘은 두 배속 옥타브, 마지막은 원속도로 돌아온다. |
| 77.1–107.5초 | 밴드가 재진입한다. 짧은 신스와 금속 리듬이 합류하고 101.0초부터 리듬을 비워 피드백과 잔향을 남긴다. |

편집 프로젝트에는 뮤트된 원본, 분리 추정 드럼·베이스·기타, 원본에서 이 세 트랙을 뺀 나머지, 세 개의 폴리 트랙, 기타 응답 트랙, ReaSynth MIDI 트랙 및 다섯 개의 리턴이 있다. 분리한 세 트랙과 나머지를 유니티 게인으로 합친 오차는 원본 대비 −154.5 dB다. 분리 누출과 기타 어택의 청감상 손실은 이 수치로 판정할 수 없다. 소스와 이펙트 상태를 담은 로컬 ZIP은 풀어서 RUSTED SUNLIGHT.RPP를 연다. Arrangement.RPP는 공간계 적용 전의 편집본이다.

## 샘플과 공간

파이프 44회, 타자기 24회, 역재생 모터 4회를 개별 오디오 아이템으로 놓았다. 소리는 각 저자가 공개한 CC0 녹음의 HQ MP3를 디코딩해 가공했다. 파이프·키 타격 에너지의 90%가 각각 93 ms, 21 ms 안에 들어온다. 긴 모터음은 550–3100 Hz로 제한하고 구간의 첫 박에 끝나도록 배치했다. 음원별 출처, 원 녹음 길이/레이트, 실제 사용 파일 해시, 가공과 배치 시각을 보관했다. [파이프](https://freesound.org/people/Joao_Janz/sounds/478675/) · [타자기](https://freesound.org/people/cabled_mess/sounds/360602/) · [모터](https://freesound.org/people/derjuli/sounds/418013/) · [샘플 명세](../examples/v6/sample-manifest.json)

REAPER 7.86에서 ReaSynth, ReaEQ, ReaVerbate, ReaDelay와 JS 스테레오 코러스를 로딩했다. 신스 7음은 해당 시각의 베이스·기타 주파수 분포를 기준으로 골랐다. 짧은 룸은 7 ms 프리딜레이, 기타의 긴 잔향은 41 ms, 파이프 전용 공간은 17 ms로 설정했다. 딜레이는 실측 템포의 점8분음표에 맞췄다. 역모터 전환 버스와 나머지 네 버스에서 각각 EQ와 볼륨 커브를 사용했다. 조회한 호스트에서 Surge XT, Valhalla, Dragonfly, Kilohearts, Airwindows 후보는 발견되지 않았다. [호스트 조회](../examples/v6/host-inventory.json) · [실제 FX 상태](../examples/v6/fx-state.tsv) · [아이템과 MIDI 시각](../examples/v6/events.json)

## 오디오 검증과 한계

- 입력 104 BPM에 대해 녹음의 실측 박은 약 100 BPM이었다. 실제 드럼을 따라 보정한 박에서 가장 가까운 트랜지언트까지 중앙값은 12.8 ms다. 여린 엇박과 의도한 카운터리듬도 포함된 모든 샘플의 오차를 뜻하지 않는다.
- 62.7–77.1초의 기타 추정치에서 뚜렷한 주기성이 있는 84개 분석 창을 찾았다. 그 음높이 분포의 10/50/90백분위는 약 163/186/500 Hz다. 도입부를 인용한 세 응답은 실제 오디오다. 기타 솔로의 프레이징과 원곡이 악보의 모든 음을 지켰는지는 청취 미검증이다.
- 드럼의 16분음표 강세 분포를 인접 마디끼리 비교하면 절정 구간의 평균 차이는 약 1.8 dB, Groove A는 12.0 dB다. 절정의 밴드 그루브는 도입 전개보다 반복적이다. 이 구간의 대비는 독립 샘플·신스와 기타 공간 변화가 함께 만든다.
- 새 다섯 연주 트랙을 뮤트한 제어 렌더와 비교하면 기계 브레이크 차분 RMS는 −37.5 dBFS였다. 다섯 공간 리턴을 도입부 레벨에 고정한 별도 렌더와 비교하면 마지막 확장 구간 차분은 −44.8 dBFS였다. 음향 변화가 실제 PCM에 기록됐음을 확인했다. [제어 렌더 결과](../examples/v6/control-results.json)
- 첫 시안은 피크가 +0.01 dBTP에 닿았다. 최종본은 리미터 없이 −1.73 dBTP, −17.14 LUFS, 클리핑 0샘플이다. 원본은 float WAV에서 +1.00 dBTP였다. 최종 저중역 에너지 비율은 28.5%, 모노 접기 변화는 −0.34 dB, 크레스트 팩터는 17.8 dB다. 마지막 100 ms는 −106.9 dBFS다. 프로젝트를 다른 폴더에서 다시 렌더해 PCM이 일치했고 기존 V5도 새 코드로 재생성해 이전 마스터와 PCM이 일치했다. [마스터 측정](../examples/v6/production.json)

## 재현

V5에서 사용한 동일한 YuE2 가중치, 로컬 Demucs 두 체크포인트, Whisper-small, ffmpeg와 REAPER가 필요하다. 설치 및 모델 위치는 [V5 실행 문서](V5_METALLIC_DREAM.md)에 있다. 공개한 원본으로 편곡을 재현하는 명령은 아래와 같다. 출력 인수는 새 폴더로 지정한다.

```sh
source_wav=examples/v6/rusted-sunlight-original.wav
stem_dir=outputs/v6/reproduction-stems
session_dir=outputs/v6/reproduction-session
.venv/bin/python -m scripts.v5_stems "$source_wav" "$stem_dir"
.venv/bin/python -m scripts.v6_screen "$source_wav" "$stem_dir" outputs/v6/reproduction-screen.json
.venv/bin/python -m scripts.v6_produce "$source_wav" "$stem_dir" examples/v6/cues.json "$session_dir"
.venv/bin/python -m scripts.v6_verify "$session_dir" outputs/v6/reproduction-controls
.venv/bin/python -m pytest -q
```

새 추론은 `.venv/bin/python -m scripts.v6_generate --seed 73`로 실행한다. 작업마다 새 원본 폴더를 만든다. 큐시트는 분석한 WAV의 SHA-256에 연결되므로 다른 연주 테이크는 자기 박과 큐를 다시 확인해야 한다.
