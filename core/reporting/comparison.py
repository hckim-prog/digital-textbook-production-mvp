from __future__ import annotations

import csv
from html import escape
from pathlib import Path
import json
from datetime import datetime

from core.ai.service import proofread, safe_blocks
from core.master import Master


def compare(root: Path, master: Master, model_ids: list[str], reasoning: str, max_samples: int) -> Path:
    selected = safe_blocks(master, max_samples)
    sample = Master(master.title, master.source_name, master.source_hash, selected)
    rows = []
    details = []
    for model in dict.fromkeys(model_ids):
        suggestions, calls = proofread(root, sample, model, reasoning, len(selected))
        details.append({"model_id": model, "suggestions": suggestions})
        row = {"model_id": model, "response_model_id": next((c.get("response_model") for c in calls if c.get("response_model")), ""),
               "reasoning_effort": reasoning, "sample_count": len(selected),
               "suggestions": len(suggestions), "level_a": sum(s["level"] == "A" for s in suggestions),
               "level_b": sum(s["level"] == "B" for s in suggestions), "level_c": sum(s["level"] == "C" for s in suggestions),
               "input_tokens": sum(c.get("input_tokens", 0) for c in calls),
               "output_tokens": sum(c.get("output_tokens", 0) for c in calls), "api_calls": len(calls),
               "elapsed_seconds": round(sum(c.get("elapsed_seconds", 0) for c in calls), 2),
               "estimated_cost_usd": round(sum(c.get("estimated_cost_usd") or 0 for c in calls), 6)
               if all(c.get("estimated_cost_usd") is not None for c in calls) else "가격 미설정",
               "success": all(c.get("success") for c in calls), "review_status": "비교 제안 미검토",
               "approved": 0, "rejected": 0,
               "source_text": " / ".join(b.text for b in selected),
               "suggestion_texts": " / ".join(s["suggested_text"] for s in suggestions)}
        rows.append(row)
    base = root / "reports" / "model-comparison"
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    for suffix in range(1000):
        dest = base / (stamp + (f"_{suffix + 1}" if suffix else ""))
        try:
            dest.mkdir(exist_ok=False)
            break
        except FileExistsError:
            continue
    else:
        raise RuntimeError("새 모델 비교 보고서 폴더를 만들 수 없습니다.")
    (dest / "model-comparison-details.json").write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    (dest / "model-comparison-rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return refresh(dest)


def refresh(dest: Path) -> Path:
    metadata = dest / "model-comparison-rows.json"
    if metadata.is_file():
        rows = json.loads(metadata.read_text(encoding="utf-8"))
    else:
        with (dest / "model-comparison.csv").open(encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
    details = json.loads((dest / "model-comparison-details.json").read_text(encoding="utf-8"))
    for row in rows:
        items = next(d["suggestions"] for d in details if d["model_id"] == row["model_id"])
        for state in ("approved", "rejected", "hold", "pending"):
            row[state] = sum(i.get("status", "pending") == state for i in items)
        reviewed = row["approved"] + row["rejected"]
        row["approval_rate"] = round(100 * row["approved"] / reviewed, 1) if reviewed else "미검토"
        row["review_status"] = "검토 완료" if items and reviewed == len(items) else "검토 중" if reviewed else "미검토"
    (dest / "model-comparison-rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    columns = list(rows[0]) if rows else ["model_id"]
    with (dest / "model-comparison.csv").open("w", newline="", encoding="utf-8-sig") as out:
        writer = csv.DictWriter(out, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    headings = {"model_id": "모델", "suggestions": "제안 수", "elapsed_seconds": "시간(초)", "input_tokens": "입력 토큰", "output_tokens": "출력 토큰", "estimated_cost_usd": "예상 비용(USD)", "approved": "승인", "rejected": "거절", "hold": "보류", "pending": "미검토", "approval_rate": "승인률(%)"}
    table = "<table><tr>" + "".join(f"<th>{label}</th>" for label in headings.values()) + "</tr>"
    table += "".join("<tr>" + "".join(f"<td>{escape(str(row[c]))}</td>" for c in headings) + "</tr>" for row in rows) + "</table>"
    detail_html = ""
    for model in details:
        detail_html += "<h2>" + escape(model["model_id"]) + "</h2>"
        for item in model["suggestions"]:
            detail_html += "<article>" + "".join(f"<p><b>{label}</b> {escape(str(item.get(key, '')))}</p>" for key, label in (("source_text", "원문"), ("suggested_text", "수정 제안"), ("reason", "이유"), ("status", "검토 상태"))) + "</article>"
    page = dest / "model-comparison.html"
    page.write_text('<!doctype html><html lang="ko"><meta charset="utf-8"><title>AI 모델 비교</title><style>body{font-family:Malgun Gothic,sans-serif;margin:2rem;line-height:1.6}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:.5rem}article{border-bottom:1px solid #ccc}</style><h1>AI 모델 비교</h1><p>승인률 = 승인 / (승인 + 거절). 보류와 미검토는 분모에서 제외합니다. 검토 전에는 미검토로 표시합니다.</p>' + table + detail_html + '</html>', encoding="utf-8")
    (dest / "model-comparison.md").write_text("# AI 모델 비교\n\n승인률 = 승인 / (승인 + 거절). 보류와 미검토 제외.\n\n" + "| " + " | ".join(headings.values()) + " |\n|" + "|".join(["---"] * len(headings)) + "|\n" + "".join("| " + " | ".join(str(row[c]) for c in headings) + " |\n" for row in rows), encoding="utf-8")
    return page


def review(dest: Path, selections: list[tuple[str, str]], status: str):
    if status not in {"approved", "rejected", "hold"}:
        raise ValueError("검토 상태를 확인해 주세요.")
    file = dest / "model-comparison-details.json"
    details = json.loads(file.read_text(encoding="utf-8"))
    for model in details:
        for item in model["suggestions"]:
            if (model["model_id"], item["id"]) in selections:
                item["status"] = status
    file.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
    return refresh(dest)
