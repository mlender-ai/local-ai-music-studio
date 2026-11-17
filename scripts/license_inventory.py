"""Record installed runtime distribution metadata and bundled license files."""

import importlib.metadata as metadata
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    records = []
    for distribution in sorted(
        metadata.distributions(), key=lambda d: d.metadata.get("Name", "").lower()
    ):
        name = distribution.metadata.get("Name", "unknown")
        expression = distribution.metadata.get("License-Expression")
        classifiers = [
            v
            for v in distribution.metadata.get_all("Classifier", [])
            if v.startswith("License ::")
        ]
        raw = distribution.metadata.get("License", "")
        summary = (
            expression
            or "; ".join(classifiers)
            or raw.split("\n")[0][:200]
            or "Review bundled license files"
        )
        texts = []
        for file in distribution.files or []:
            if re.search(
                r"(license|copying|notice)", str(file), re.I
            ) and ".dist-info/" in str(file):
                path = Path(distribution.locate_file(file))
                if path.is_file() and path.stat().st_size < 1_000_000:
                    texts.append(
                        dict(file=str(file), text=path.read_text(errors="replace"))
                    )
        records.append(
            dict(
                name=name,
                version=distribution.version,
                license=summary,
                project_urls=distribution.metadata.get_all("Project-URL", []),
                notices=texts,
            )
        )
    (ROOT / "docs/dependency-licenses.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2)
    )
    lines = [
        "# Installed dependency license inventory",
        "",
        "Generated from the isolated environment; full bundled notices are in `dependency-licenses.json`.",
        "",
        "| Distribution | Version | Declared license |",
        "|---|---|---|",
    ]
    lines += [
        f"| {r['name']} | {r['version']} | {r['license'].replace('|', '/')} |"
        for r in records
    ]
    (ROOT / "docs/DEPENDENCIES.md").write_text("\n".join(lines) + "\n")
    print("Recorded", len(records), "distributions")


if __name__ == "__main__":
    main()
