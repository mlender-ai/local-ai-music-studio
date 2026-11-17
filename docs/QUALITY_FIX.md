# 펑키 디스코 품질 문제 수정

2026-11-16. 사용자 요청: “90년대 펑키 디스코, MJ 스타일, 124bpm, 신나는 펑키 기타 리프, 디스코 리듬.”

## 확인된 구현 문제

1. 기존 변환 규칙은 Trip-Hop / Ambient / House뿐이었다. 이번 요청은 영어 음악 설명으로 확장되지 않고 한국어 원문 + instrumental로 전달됐다. BPM 124는 올바르게 전달됐으므로 BPM 파싱 오류라고 보고하지 않는다.
2. Turbo에서 `shift`를 명시하지 않아 일반 dataclass 기본값 1.0이 사용됐다. [공식 추론 문서](https://github.com/ace-step/ACE-Step-1.5/blob/ca1e85fe9430179831e6bc6be790c332190a3866/docs/en/INFERENCE.md)는 Turbo에서 3.0을 명시하도록 권장한다. 8 steps는 기존부터 올바른 권장값이었다.
3. 이전 QA는 파일·DSP·전송·재생 검증이었다. 장르 충실도, 기타 리프 존재, 그루브의 청감 정확도를 통과시킨 증거가 아니었다. 사용자 평가를 반영해 이 구분을 README와 기존 QA에 명시했다.

## 변경

- Funk/disco 장르, 1990s, MJ 참조, clean muted syncopated sixteenth-note guitar riff, 전 박 킥·2/4 스네어/클랩·16분음표 하이햇·싱코페이션 베이스로 요청을 확장한다. 원문은 별도 보존하고 알 수 없는 지시도 버리지 않는다. 명시적으로 제외한 드럼/기타는 추가하지 않는다.
- 요청 BPM 124와 4/4를 구조화해 전달한다. Turbo shift=3, distilled guidance=1, 8 steps를 적용하고 실제 설정을 결과에 기록한다.
- 새로운 생성의 리듬 후보 분석 및 `needs_listening` 상태를 기록한다. 추정기에 요청 BPM을 정답으로 강요하지 않는다.
- 동일 요청으로 30초 두 곡을 재생성했다. 첫 곡은 기존과 같은 seed 42, 두 번째는 seed 43. 두 번째는 실행 중인 플레이어 HTTP API를 통해 제출해 수정된 경로가 실제 사용됨을 확인했다. WAV와 기존 버전은 모두 보존했다.

## 측정 결과

| 결과 | 총 시간 | 강한 주기 후보 BPM (상관 강도) | 파일 |
|---|---:|---|---|
| 기존 사용자 결과 | 37.623초 | 63.0 (0.701), 125.9 (0.549) | [WAV](</path/to/local-ai-music-studio/outputs/originals/f3e123953f954bcc8f78c43cbeae6a5d/572d355d-07ed-f2eb-d0fb-0fc6cceda9d8.wav>) |
| 수정본 1 · 같은 seed 42 | 37.678초 | 62.0 (0.807), 124.0 (0.64) | [WAV](</path/to/local-ai-music-studio/outputs/originals/8a97a6437c534fdda53d326c7497b9d2/21d1966e-1d33-c277-90f6-31649a2bfff5.wav>) |
| 수정본 2 · seed 43 | 35.514초 | 62.0 (0.69), 124.4 (0.505) | [WAV](</path/to/local-ai-music-studio/outputs/originals/7f2523a88dfb4876b69ebb769a95557b/f2859a8a-370f-17fd-662a-6cf4af2fe4cd.wav>) |

스펙트럼 onset 자기상관의 60–180 BPM 검색 결과다. 기존은 약 63/125.9, 수정본은 약 62/124 및 62/124.4의 반박·배박 후보다. 이를 “기존 곡은 63 BPM이었다” 또는 “새 곡의 모든 박자가 완벽하다”라고 해석하지 않는다. 리듬 패턴의 음악적 적절성, 장르, 기타 연주 존재는 이 분석으로 판정할 수 없다. 프롬프트와 설정을 함께 바꿨으므로 각각의 개선 기여도도 분리 측정하지 않았다. MLX 4-bit의 음질 영향은 이번 비교로 검증되지 않았다.

수정본 모두 48 kHz stereo, 정확히 30초, 클리핑 0, 유한 샘플. 최대 자식 footprint 약 5.0 GiB로 기존 한도를 유지했다. 원본 SHA-256과 전체 요청·설정·분석은 [JSON](disco-quality-comparison.json)에 기록했다.

검증: 자동화 테스트 31개 통과 (2.45초), Ruff 검사 통과. 템포 분석 테스트는 합성 클릭 fixture만 사용하며 이 fixture를 AI 음악이라고 제시하지 않는다. 최종 음악적 스타일 평가는 아직 합격 처리하지 않았다.
