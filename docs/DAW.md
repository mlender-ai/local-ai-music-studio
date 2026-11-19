# 소울 디스코 DAW 제작 실험

Session Engine V1의 116 BPM, D minor, 4/4 세션을 기준으로 삼았다. 14마디 뒤의 잔향을 포함해 30초다. 실제 렌더를 완료한 백엔드는 Session Engine이다. REAPER 호스트 검증은 설치 승인 대기 상태다.

## 들을 파일

프로젝트의 `outputs/daw-session/03-keys/session-preview.wav`가 두 수정 명령을 적용한 대표곡이다. 16.55초에 기타가 쉬고, 24.83초에 기타가 돌아온다. `01-reference`는 기존 Processed Mix와 디코딩한 PCM이 일치한다. `02-region`에는 기타와 베이스 변경만 있다. 각 폴더의 `dry.wav`, `premaster.wav`, `session-preview.wav`로 믹싱 및 마스터 처리 전후를 분리할 수 있다. `raw/`에는 건반·기타·베이스·드럼에서 한 녹음씩 골라 원래 샘플레이트와 진폭을 유지해 WAV로 디코딩한 파일이 있다.

| 48 kHz 스테레오 실측 | 기존 | 9–12마디 편곡 | 편곡 + 건반 수정 |
|---|---:|---:|---:|
| WAV 길이 | 30.00 s | 30.00 s | 30.00 s |
| 전체 믹스 LUFS-I | −21.42 | −21.50 | −21.90 |
| 전체 믹스 True Peak, dBTP | −2.54 | −2.54 | −2.74 |
| 건반 Wet의 180–500 Hz 에너지 비율 | 57.76% | 57.76% | 53.80% |
| 건반 Wet의 2–6 kHz 에너지 비율 | 0.35% | 0.35% | 0.43% |
| 건반 Wet의 좌우 상관도 | 0.792 | 0.792 | 0.873 |

기타 연주 이벤트 14개를 쉬게 하고 베이스 11개의 시작·길이·강세를 바꿨다. 실제 MIDI 노트 수는 518개에서 480개로 줄었다. 베이스의 음높이와 다운비트는 유지했다. 해당 구간에서 기타 Dry 스템은 완전히 무음이다. 편곡 전후 PCM의 마지막 차이는 기타 24.681초, 베이스 24.320초였다. 두 스템은 편집 구간 바깥에서 샘플 단위로 일치한다. 스냅샷 간 변경 전후 데이터는 `edit.json`에 있다.

## 먹먹함 진단

- 기존 건반 선택기는 104개 노트 모두 같은 강도층을 선택했고 파일별 피크를 정규화했다. Greg Sullivan의 Wurlitzer EP200 공식 매핑에서 이 세션의 6개 노트는 mp, 98개는 f에 해당한다. 새 렌더는 원래 샘플 간 레벨, 키 구간, 강도 구간, 센트 튜닝과 게인을 적용한다. 악기 입력 RMS를 기존 연주와 맞췄다. 전체 SFZ 오퍼코드를 재현하는 엔진은 개발 범위 밖이다.
- 같은 MIDI로 Greg Sullivan의 Yamaha CP80도 측정했다. Dry의 180–500 Hz 비율은 기존 64.25%, 공식 매핑 EP200 66.58%, CP80 81.09%였다. 이 곡의 명료도 요구에 맞춰 Wurlitzer를 유지했다. 원음 변경만으로 저중역 축적은 줄지 않았다. 기존 건반 벨 EQ의 360 Hz 감쇄를 −2.3 dB에서 −4.8 dB로 조정하고 룸 센드를 0.18에서 0.09로 낮췄다. 지연된 측면 신호의 양도 0.28에서 0.24로 조정했다. 처리된 건반은 기존보다 1.85 LU 조용해졌다. 이 변화도 청취에 영향을 준다.
- 리샘플러 비교에서는 각 악기의 가장 큰 전조 중 한 녹음을 골라 같은 위치에서 최대 350 ms를 읽었다. 선형 보간과 polyphase 출력의 차이 RMS는 출력 대비 건반 −59.1 dB, 베이스 −59.3 dB, 기타 −44.0 dB였다. 이 구간의 전조는 각각 4, 1, 1반음이다. 시간 스트레치는 사용하지 않는다. 이 실험으로 리샘플러를 먹먹함의 주원인으로 지목할 근거는 부족하다.
- 기존 건반에서 룸만 끄면 좌우 상관도가 0.792에서 0.855로, 측면 지연만 끄면 0.922로 올라갔다. 기타는 단음 DI를 5 ms씩 벌려 재생하며, 베이스 슬라이드는 55 ms의 피치 이동으로 근사한다. 실제 연주자가 녹음한 코드 스트로크나 슬라이드의 품질은 검증하지 못했다.
- 기존 믹스의 마스터 전후 crest factor는 20.95 dB와 20.89 dB였다. 전체 수치에서 큰 트랜지언트 손실은 관찰되지 않았다. 기존 final.wav와 processed-mix.wav의 PCM은 동일했다. 새 버전의 premaster와 session-preview는 실제로 다르다.
- `qa.json`에는 원음별 피크와 양 끝 진폭, 사용된 레이어와 최대 피치 이동, 스템·구간별 레벨, LUFS와 True Peak가 있다. `diagnosis.json`에는 고정 입력에서 바꾼 보간기·룸·측면 지연의 측정값이 있다. 클릭의 가청성, 기타의 자연스러움, 음색 선호도와 곡의 완성도는 미검증이다.

## 실행

기존 Python 환경, FFmpeg, Session Engine V1 기준 세션이 필요하다. 최초 소스 확인 시 고정된 저장소 버전에서 필요한 샘플만 받아 Git blob 체크섬을 검증한다. 샘플 캐시 및 결과는 출력 폴더에 남고 Git에는 올라가지 않는다.

```sh
.venv/bin/python -m engine.daw.demo
.venv/bin/python -m engine.daw.diagnose
.venv/bin/python -m pytest -q
```

기존 결과가 있으면 `demo --out outputs/another-daw-session`으로 별도 사본을 만들 수 있다. MCP는 기본 `outputs/daw-session`의 스냅샷을 사용한다. 새 세션은 임시 폴더에서 완성한 다음 공개한다. 이전 스냅샷은 별도 ID로 계속 사용할 수 있다.

| MCP 도구 | 입력과 결과 |
|---|---|
| music.session.inspect | 버전 ID를 받아 템포·키·구간·스코어·미리듣기 WAV 반환. 기본값은 01-reference |
| music.region.inspect | first, last, version으로 실제 마디의 이벤트와 코드를 반환 |
| music.region.edit | command, version으로 두 유형의 한국어 지시를 적용하고 새로운 MIDI/WAV 버전 반환 |
| music.session.undo | version의 부모 버전을 반환. 반환한 ID로 재생하거나 편집 가능 |

실제 STDIO 세션에서 «9~12마디의 기타를 쉬게 하고 베이스를 변주해줘.»를 적용한 후 그 결과에 «키보드가 먹먹하니까 악기 소스를 점검하고 더 명료하게 믹싱해줘.»를 적용했다. 두 결과의 WAV가 데모에서 독립 생성한 파일과 바이트 단위로 일치했다. 기존 music.session_lab 조회도 통과했다. 지원되는 자연어는 위 두 명령 계열로 제한한다.

## REAPER 호스트 상태

이 Mac에서 Logic Pro와 GarageBand, Apple AUSampler와 DLSMusicDevice, 48 kHz 스테레오 내장 출력을 확인했다. 점검 당시 REAPER 설치본, 사용자·시스템 추가 AU/VST3 및 실행 중인 Logic/GarageBand/REAPER 프로세스는 발견되지 않았다. 기존 상용 앱의 구입 계정·사용권 보유 여부는 확인하지 않았다. 공식 macOS Universal 배포본은 Apple Silicon과 60일 평가 사용을 지원한다. 외부 플러그인이나 ReaPack은 이 경로에 필요하지 않다. [REAPER 다운로드](https://www.reaper.fm/download.php) · [공식 ReaScript API](https://www.reaper.fm/sdk/reascript/reascript.php)

`Score.RPP`는 8개 악기 레인, 마디별 MIDI 아이템 112개, 마디와 섹션 마커를 포함하는 **악보 단계**다. 별도 샘플 파일과 존 배치를 함께 내보낸다. REAPER 설치 및 사용 동의 후 아래 명령으로 전용 인스턴스의 내장 Lua에서 샘플러·룸·EQ·라우팅을 구성하고 별도 프로젝트로 저장하도록 구현했다. 입력은 고정된 작업 양식이며 외부 Lua를 실행하는 MCP 도구는 없다.

```sh
.venv/bin/python -m engine.daw.host outputs/daw-session/03-keys
```

호스트 실행 시 고유 작업 폴더에 Studio.RPP 및 REAPER Mixed, 후단 Python DSP Master, 호스트 상태와 렌더 검증 기록을 남기는 경로다. 이 장비에서 현재까지 실증한 범위는 호스트 부재 오류 반환까지다. 샘플러 로딩, 프로젝트 재열기·재생과 REAPER 렌더는 미검증이며 해당 결과 파일은 아직 없다. DAW 연동 화면과 일반 목적의 FX 편집은 후속 검증 대상이다.

## 음원 출처

Virtuosity Drums, Karoryfer Fashionbass 및 Emilyguitar의 녹음은 CC0다. Greg Sullivan의 Wurlitzer EP200와 Yamaha CP80 녹음 및 kinwie의 매핑은 CC BY 3.0이다. 이 실험에서 선택한 구간, 전조, 튜닝, 음량, 감쇠와 믹싱을 변경했다. 버전별 소스에는 원 저장소와 고정 리비전 및 각 녹음의 Git blob ID가 있다. [원 프로젝트와 라이선스](https://github.com/sfzinstruments/GregSullivan.E-Pianos/tree/8c3e581acda3594b553948ff0222d4f84a698376) · [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) · [드럼·베이스·기타 출처](SESSION_ENGINE.md)
