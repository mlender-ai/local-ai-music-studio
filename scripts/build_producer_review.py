"""Label-blinded listening with persistent human ratings; originals untouched."""

import html
import json
import random
from engine.paths import DATA

LABELS = [
    "장르 충실도",
    "악기 자연스러움",
    "그루브·리듬",
    "세션 상호작용",
    "인트로·전개",
    "반복·변주",
    "화성·멜로디",
    "EQ·다이내믹·공간",
    "아티팩트 없음",
    "전체 완성도",
]


def build():
    out = DATA / "producer"
    records = json.loads((out / "results.json").read_text())
    mapping_file = out / "blind-order.json"
    mapping = json.loads(mapping_file.read_text()) if mapping_file.exists() else {}
    sections = []
    for genre in dict.fromkeys(r["genre"] for r in records):
        rows = [
            r
            for r in records
            if r["genre"] == genre and r["job"]["state"] == "succeeded"
        ]
        if not rows:
            continue
        by_id = {r["job"]["result"]["id"]: r for r in rows}
        order = [i for i in mapping.get(genre, []) if i in by_id]
        new = [i for i in by_id if i not in order]
        random.SystemRandom().shuffle(new)
        order += new
        mapping[genre] = order
        sections.append("<h2>" + html.escape(genre) + "</h2>")
        for number, ident in enumerate(order, 1):
            r = by_id[ident]
            v = r["job"]["result"]
            db = v["metadata"]["analysis"]["rms_dbfs"]
            gain = min(1, 10 ** ((-22 - db) / 20))
            fields = "".join(
                f'<label>{name}<select data-score="{ident}:{idx}"><option value="">미검증</option>'
                + "".join(f"<option>{i}</option>" for i in range(1, 6))
                + "</select></label>"
                for idx, name in enumerate(LABELS)
            )
            detail = html.escape(json.dumps(r, ensure_ascii=False, indent=2))
            sections.append(
                f'<section><h3>Sample {number}</h3><audio controls preload="metadata" data-gain="{gain}" src="/audio/{ident}"></audio><div>{fields}</div><label>청취 메모<textarea data-score="{ident}:notes"></textarea></label><details class="reveal" hidden><summary>조건·계획·자동 분석 공개</summary><pre>{detail}</pre></details></section>'
            )
    mapping_file.write_text(json.dumps(mapping, indent=2))
    page = (
        """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>AI Producer 청취 비교</title><style>body{font:16px system-ui;max-width:1000px;margin:32px auto;padding:16px;color:#24362d;background:#f5f7f3}section{padding:20px;margin:18px 0;background:white;border:1px solid #d0d9d0;border-radius:10px}audio{width:100%}label{display:inline-block;margin:8px}select,button{padding:8px}textarea{display:block;min-width:280px}pre{white-space:pre-wrap;max-height:400px;overflow:auto}</style><h1>AI Producer · 청취 비교</h1><p>각 장르의 Sample 순서는 무작위이며 저장됩니다. 조건을 공개하기 전에 같은 헤드폰과 볼륨으로 평가하세요. 1=매우 부족, 5=매우 좋음. 미평가 항목은 미검증입니다.</p><p>30초 세 곡: 기존 기획/새 기획/새 기획+8-bit. 60초는 별도의 길이 실험입니다. 자동 분석은 음악적 합격 점수가 아닙니다.</p><p>기본 재생은 전체 RMS를 −22 dBFS에 맞춘 감쇠입니다(LUFS 정규화 아님). 원본 파일은 변경하지 않습니다.</p><label><input id="match" type="checkbox" checked>청취 음량 맞추기</label><button id="reveal">조건 공개</button> <button id="save">평가 JSON 저장</button>"""
        + "".join(sections)
        + """<script>
const fields=[...document.querySelectorAll('[data-score]')],audios=[...document.querySelectorAll('audio')];
for(const f of fields){f.value=localStorage.getItem('producer:'+f.dataset.score)||'';f.onchange=()=>localStorage.setItem('producer:'+f.dataset.score,f.value)}
function volume(){for(const a of audios)a.volume=document.querySelector('#match').checked?Number(a.dataset.gain):1}volume();document.querySelector('#match').onchange=volume;
for(const a of audios)a.onplay=()=>{for(const b of audios)if(a!==b)b.pause()};
document.querySelector('#reveal').onclick=()=>{for(const d of document.querySelectorAll('.reveal'))d.hidden=false;document.querySelector('#reveal').textContent='조건이 공개되었습니다'};
document.querySelector('#save').onclick=()=>{const ratings=Object.fromEntries(fields.map(f=>[f.dataset.score,f.value||null]));const data={ratings,at:new Date().toISOString(),level_matched:document.querySelector('#match').checked,conditions_revealed:!document.querySelector('.reveal').hidden};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='producer-listening.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
</script></html>"""
    )
    (out / "listen.html").write_text(page)
    print("http://127.0.0.1:8795/producer")


if __name__ == "__main__":
    build()
