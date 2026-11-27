# Signalsmith Stretch

- 추천일: 2026-11-27
- 상태: NOMINATED
- GitHub: https://github.com/Signalsmith-Audio/signalsmith-stretch
- 공식 문서/청취 데모: https://signalsmith-audio.com/code/stretch/
- 라이선스: MIT (https://github.com/Signalsmith-Audio/signalsmith-stretch/blob/main/LICENSE.txt)
- 유지보수 근거: https://github.com/Signalsmith-Audio (2026-10-22 업데이트 표시), 공식 README 및 C++ API, WASM/AudioWorklet과 Python 바인딩 안내. Qt 채택 사례: https://doc.qt.io/qt-6/qtmultimedia-attribution-signalsmith-stretch.html (1.0.0).
- 버전: Qt 문서의 1.0.0은 채택 버전이며 최신 버전이 아님. GitHub releases 페이지 접근 실패; 설치 전 공식 태그/커밋 및 바인딩 버전 고정 필요.

## 적용 방향
DAW에서 녹음/생성된 오디오 클립의 음정과 재생 길이를 독립적으로 변환하고, 루프의 BPM·키를 프로젝트에 맞추는 비파괴 오프라인 편집 모듈. 기존 합성/생성 모델을 대체하지 않는다. 공개 main 및 Phase 03 Python/프런트엔드 의존성에 직접 포함되지 않으며 기본 브랜치 코드 검색에서 확인되지 않음. Phase 03 공개 상태 문서의 샘플/루프 및 오디오 편집 방향과 관련. 다른 브랜치와 로컬 환경 전체는 미확인.

## 비용·최소 검증
난이도 중간, 오프라인 PoC 2~4일 추정; 라이선스/API 비용 없음. C++11/AppleClang 테스트 근거 및 Python 바인딩/웹 WASM 옵션은 있으나 실제 arm64 빌드와 Python 3.12 바인딩 설치, 종속 라이선스는 미검증. 오프라인 WAV 변환부터 시작하고 4~8마디 루프의 0.8~1.25배 및 ±2 semitone 변환을 비교한다. 길이/키 오차, 트랜지언트 뭉개짐, 클릭, 스테레오 위상, 지연 보정 및 CPU 측정, 레벨 매칭 청취 A/B로 승인 여부를 결정한다. 공식 문서의 권장 stretch 범위는 0.75~1.5배이며 극단적 변환의 음질은 보장되지 않는다. 편곡 재생성 또는 클립 편집 단계에서 검토. 악기 음색 자체나 작곡 품질을 개선하는 모델은 아니다. 설치/실행 미수행.
