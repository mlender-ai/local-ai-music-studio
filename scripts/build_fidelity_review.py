"""Build local listening sheet; human scores remain blank until entered."""

import argparse
import html
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument(
    "--experiment", choices=["fidelity", "arrangement"], default="fidelity"
)
experiment = parser.parse_args().experiment
out = root / "outputs" / experiment
records = json.loads((out / "results.json").read_text())
labels = [
    "장르 일치도",
    "드럼 그루브",
    "베이스 리듬",
    "기타 존재감",
    "악기 간 리듬 결합",
    "편곡 완성도",
    "오디오 음질",
]
if experiment == "arrangement":
    labels = [
        "인트로의 명확함",
        "악기의 점진적 등장",
        "메인 그루브 변화",
        "리듬·음색 일관성",
        "자연스러운 연결",
    ]
sections = []
for record in records:
    if record["job"]["state"] != "succeeded":
        continue
    v = record["job"]["result"]
    meta = v["metadata"]
    ident = v["id"]
    fields = "".join(
        f'<label>{label} <select data-score="{ident}:{i}"><option value="">미검증</option>'
        + "".join(f"<option>{n}</option>" for n in range(1, 6))
        + "</select></label>"
        for i, label in enumerate(labels)
    )
    details = html.escape(
        json.dumps(
            dict(
                metadata=meta,
                section_analysis=record.get("section_analysis"),
                conditioning=record.get("conditioning"),
                source_context_comparison=record.get("source_context_comparison"),
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    sections.append(
        f'<section><h2>{record["label"]} · seed {meta["plan"]["seed"]}</h2><audio controls preload="metadata" src="/audio/{ident}"></audio><p>각 항목 1=매우 부족, 3=부분 충족, 5=매우 잘 충족. 듣지 않은 항목은 미검증으로 남겨주세요.</p>{fields}<label>청취 메모<textarea data-score="{ident}:notes"></textarea></label><details><summary>실제 프롬프트 · 설정 · 자동 측정</summary><pre>{details}</pre></details></section>'
    )
page = (
    """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Music Fidelity 청취 비교</title><style>body{font:16px system-ui;max-width:1000px;margin:30px auto;padding:20px}section{border:1px solid #ccc;padding:20px;margin:20px 0}label{display:inline-block;margin:8px}audio{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}textarea{display:block}button{padding:12px}</style><h1>Music Fidelity 청취 비교</h1><p>A와 B는 동일 시드·모델·설정. B/C2/C3는 새 Intent의 서로 다른 시드 3개입니다. BPM과 파일 검증은 장르·그루브 합격 판정이 아닙니다. 자동 청취 점수는 부여하지 않았습니다.</p><button id="download">청취 평가 JSON 저장</button>"""
    + "".join(sections)
    + """<script>
const inputs=[...document.querySelectorAll('[data-score]')];
for(const field of inputs){field.value=localStorage.getItem('fidelity:'+field.dataset.score)||'';field.onchange=()=>localStorage.setItem('fidelity:'+field.dataset.score,field.value)}
document.querySelector('#download').onclick=()=>{const scores=Object.fromEntries(inputs.map(f=>[f.dataset.score,f.value||null]));const url=URL.createObjectURL(new Blob([JSON.stringify({human_scores:scores,scored_at:new Date().toISOString()},null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='fidelity-listening.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
for(const a of document.querySelectorAll('audio'))a.onplay=()=>{for(const b of document.querySelectorAll('audio'))if(a!==b)b.pause()};
</script></html>"""
)
if experiment == "arrangement":
    page = page.replace("Music Fidelity", "Arrangement & Intro").replace(
        "A와 B는 동일 시드·모델·설정. B/C2/C3는 새 Intent의 서로 다른 시드 3개입니다.",
        "A는 기존 일반 생성, B는 구간 전개 지시입니다. 동일 시드·모델·추론 설정의 30초 비교입니다. C는 B의 첫 4초를 공식 Repaint로 다시 생성한 별도 조건부 실험입니다. B와 C 모두 자동 측정상 메인 에너지 상승이 확인되지 않았으며, 음악적 개선은 청취 미검증입니다.",
    )
    page = page.replace("fidelity:", "arrangement:").replace(
        "fidelity-listening.json", "arrangement-listening.json"
    )
(out / "listen.html").write_text(page)
print("http://127.0.0.1:8795/" + experiment)
