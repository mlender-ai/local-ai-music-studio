# Session Engine V1

116 BPM, D minor, 4/4 소울 디스코 연주곡 한 곡을 실제 녹음 샘플로 제작했다. 소울 Music Plan 입력은 기존 ACE-Step B와 동일하다. 연주 순서와 믹서 설정은 Session Engine V1의 14마디 기획을 사용한다. 비교는 [로컬 Session Lab](http://127.0.0.1:8795/session-lab)에서 할 수 있다.

## 재현

프로젝트 루트에서 기존 설치 환경을 사용한다. 샘플 설치만 네트워크를 사용한다. 203개 원본 파일(로컬 약 115 MiB)의 출처 커밋과 Git blob 체크섬은 `engine/session/banks.json`에 있다. 설치가 끝나면 오프라인으로 재생성할 수 있다.

```sh
.venv/bin/python -m engine.session.bank
.venv/bin/python -m engine.session.render --music-plan examples/director/soul.json
.venv/bin/python -m engine.session.render --session outputs/session-engine/session.json --out outputs/session-replay-check
.venv/bin/python scripts/verify_session.py --replay outputs/session-replay-check
.venv/bin/music player --port 8795
```

위 명령은 새 설치용이다. 이미 생성된 세션은 바로 플레이어에서 들을 수 있다. 다시 렌더할 때는 빈 출력 경로를 지정한다. 기본 경로에 렌더하면 스템과 믹스를 SQLite 버전으로 함께 등록한다. 이미 만든 기본 세션은 `.venv/bin/python -c 'from engine.session.catalog import register; register()'`로 다시 등록할 수 있다. MCP `music.session_lab`은 실제 파일·버전 ID·믹서·소스·구간을 반환한다. 기존 `music.compare`, `music.render`, `music.export`에 개별 트랙 ID를 쓸 수 있다. A 재생에는 이 장비에서 이미 생성한 같은 Music Plan의 producer-v1-soul-B 작업이 필요하다.

## 악기 선정과 사용권

| 파트 | 사용한 녹음 | 연주 방식 |
|---|---|---|
| Drums | [Virtuosity Drums, CC0](https://github.com/sfzinstruments/virtuosity_drums/tree/9f04cf9a734527edfbb0a4eee1f674e45bbf71bc) | 킥 마이크, 스네어 센터, 오버헤드의 닫힌/반열린 하이햇을 각각 샘플링. 약한 고스트와 강한 백비트는 서로 다른 강도로 녹음된 타격을 선택 |
| Bass | [D. Smolken / Karoryfer Fashionbass, CC0](https://github.com/sfzinstruments/karoryfer.fashionbass/tree/0703973b300a6bacb837602be9b588ab64732a72) | 직접 녹음한 일렉트릭 베이스의 강약·테이크 선택. 짧은 감쇠, 옥타브, 다음 루트 반음 아래의 연결음. 슬라이드는 피치 이동으로 근사 |
| Keys | [Greg Sullivan, Wurlitzer EP200 v1.1, SFZ 매핑 kinwie](https://github.com/sfzinstruments/GregSullivan.E-Pianos/tree/8c3e581acda3594b553948ff0222d4f84a698376) | [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/). 녹음의 음높이·길이·음량을 조정하고 코드 연주 및 공간 처리를 적용. Rhodes 역할에 Wurlitzer 리드 전자피아노를 선택 |
| Guitar | [D. Smolken / Karoryfer Emilyguitar, CC0](https://github.com/sfzinstruments/karoryfer.emilyguitar/tree/b4920dc662fd9cad6dcaccdeecffdd91c8725d8c) | 클린 DI 노트와 뮤트 노이즈 녹음. 코드 음을 저음→고음 또는 역순으로 5 ms 간격으로 발음. 실제 업/다운 스트로크 전체를 따로 채집한 라이브러리는 아니므로 기타가 우선 청취 대상 |

샘플 사용권과 재생 소프트웨어의 사용권을 각각 확인했다. 실제 실행은 Python 이벤트 + NumPy 2.5.4/SciPy 1.18.1(BSD 계열), SoundFile 0.14.0(BSD), libsndfile 1.2.2(LGPL), 기존 Numba 0.68.1(BSD) DSP를 쓴다. V1은 고정된 소스별 노트·강약·테이크 맵을 직접 재생한다. 전체 SFZ 규격을 해석하지 않는다. 샘플 원본은 Git에 포함하지 않는다.

검토한 대안은 [FluidSynth 2.6.2](https://github.com/FluidSynth/fluidsynth/releases/tag/v2.6.2)(LGPL-2.1, SF2와 별도의 샘플 라이선스 필요), [sfizz 1.2.3](https://github.com/sfztools/sfizz/releases/tag/1.2.3)(BSD-2-Clause, 원본 SFZ의 키스위치와 복잡한 매핑에 유리), [Faust 2.88.0](https://github.com/grame-cncm/faust/blob/2.88.0/COPYING.txt)(컴파일러 LGPL-2.1-or-later, 물리 모델·DSP 설계 가능)이다. 세 도구는 버전과 사용권을 검토했으며 같은 곡으로 음질 우열을 실험하지 않았다. 이번 하위 집합은 선택된 녹음과 이벤트를 추적하기 쉽고 별도 플러그인 설치가 필요 없어 채택했다.

## 실제 제작 조건

- A는 기존 ACE-Step Turbo의 30초 full mix. 이 비교에서 쓰는 A는 이전 Producer 실험의 soul B다. 목표 키와 템포는 같고 작곡·연주·렌더 방식은 다르다.
- B는 네 Dry 스템의 합. C는 B의 같은 이벤트를 트랙별로 처리한 뒤 마스터를 거친 결과다. D는 같은 믹서에 별도 변주 이벤트를 전달한다.
- 1–2마디는 스네어 픽업, 하이햇과 건반 모티프. 3–6마디는 베이스·기타 진입. 7–10마디는 베이스 싱코페이션과 건반 전위·악센트 변화. 11마디 후반을 비우고 12마디 필인 뒤 13–14마디에 훅을 되돌린다. 14마디는 약 28.97초, 잔향 포함 정확히 30초다.
- Dm9–G13–Cmaj9–A7의 화성 재료, 도미넌트의 서스펜션과 해소, 종지의 Dm9 복귀를 코드·베이스에 함께 적용했다. V1은 이 소울 차트 전용이다. 계획의 자유 텍스트에 따라 모든 장르를 자동 편곡하지 않는다.
- `score.py`가 마디/16분 위치·음높이·길이·강약·주법을 만들고 `bank.py`가 PCM 녹음을 발음한다. `mixer.py`가 기존 DSP를 사용해 트랙을 독립 처리한다. 킥·스네어·햇 레벨과 트랜지언트, 베이스의 킥 연동 감쇠, 기타 하이패스·좌측 패닝·짧은 에코, 건반 변조·우측 배치, 각 트랙의 룸 센드량이 `session.json`에 들어 있다. Wet 스템에는 공통 선형 룸 버스로 보낸 각 트랙의 리턴이 포함된다. 합산 후 마스터 압축·리미터가 적용된다.
- 플레이어는 Web Audio의 한 재생 시계를 공유한다. A/B/C/D는 가장 조용한 비교곡의 전체 RMS에 맞춰 감쇠한다. Solo/Mute와 Dry/Wet은 마스터 전의 스템을 같은 위치에서 재생한다. LUFS 기준의 지각 음량 일치는 별도 검증 대상이다.

## 확인한 결과

12개 WAV가 48 kHz, stereo, 24-bit, 1,440,000 frames로 정렬됐다. 같은 머신에서 저장된 세션을 다시 렌더한 12개 WAV의 체크섬이 일치했다. 4개 Dry 스템 합과 B의 최대 샘플 차이는 0.000000358이다. C와 D의 차이 RMS는 0.03444다. 인트로에 베이스와 기타는 정확히 무음이다. 3–6마디 이벤트 수는 드럼 70, 베이스 28, 건반 8, 기타 16이다. 코드의 여러 음은 한 사건으로 센다.

| 측정 | Dry B | Produced C |
|---|---:|---:|
| 피크 dBFS | −2.13 | −2.57 |
| RMS dBFS | −21.81 | −23.45 |
| 180–500 Hz 파워 비율 | 28.9% | 27.4% |
| 2–6 kHz 파워 비율 | 0.71% | 1.16% |
| 좌우 상관도 | 1.000 | 0.937 |
| 모노 합산 RMS 변화 | 0.00 dB | −0.14 dB |

클리핑은 0샘플이다. Wet 베이스의 좌우 상관도는 1.000, 건반은 0.792다. 트랙별 피크·RMS·crest factor·주파수 분포는 `qa/audio-analysis.json`, 스템 합산 오차·구간별 이벤트·Dry/Wet 차이는 `qa/session-checks.json`에 보관했다. 자동 테스트 46개와 실제 STDIO MCP 세션 조회·스템 비교를 통과했다. 브라우저에서 A/B/C/D 재생 시간 진행과 같은 위치 전환, Solo/Mute, Dry 선택, 메모 저장을 확인했다.

기술적으로 연주와 믹싱을 독립 수정할 수 있다. 현재 사람의 청취 점수는 모두 미검증이다. 추가 투자는 먼저 기타 커팅의 강세·감쇠와 베이스 연결음이 자연스럽게 맞물리는지 들어본 뒤 판단한다. 문제가 기타에 집중되면 동일 이벤트에 실제 뮤트 스트럼 녹음만 교체해 비교할 수 있다. 이번 결과로 ACE-Step과의 하이브리드나 전체 엔진 교체의 필요성은 확정하지 않았다.
