from __future__ import annotations

from pathlib import Path
import json
import re
import tempfile
from datetime import datetime
from html import escape

from core.ai.workflow import ReviewWorkflow, write_json
from core.export.outputs import epub_file, pdf, web
from core.manuscript.docx_reader import read_docx
from core.master import Master, file_hash
from core.qa.checks import check, save_report, quality_html
from core.qa.code_fidelity import check_code_fidelity, check_output_codes


class Production:
    def __init__(self, root: Path, source: Path):
        self.root = root
        self.source = source.resolve()
        self.job = file_hash(self.source)[:12]
        self.work = root / "working" / self.job
        project_root = root.parent.parent if root.name == "DigitalTextbookMaker" and root.parent.name.startswith("dist") else root
        self.default_output_base = project_root / "output"
        self.output = self.default_output_base / self.job
        self.reports = root / "reports" / self.job

    def analyze(self, progress=None) -> Master:
        master = read_docx(self.source, self.work, progress)
        master.save(self.work / "structured-master.json")
        self.remember()
        return master

    def remember(self, result=None):
        path = self.root / "working/recent-jobs.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            rows = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        except (ValueError, OSError):
            rows = []
        old = next((row for row in rows if row["hash"] == self.job), {})
        entry = {**old, "hash": self.job, "source": str(self.source), "name": self.source.name,
                 "updated": datetime.now().isoformat(timespec="seconds")}
        if result:
            entry["result"] = result
            save_report(result, self.work / "last-result.json")
        save_report([entry] + [row for row in rows if row["hash"] != self.job][:29], path)

    @staticmethod
    def recent(root):
        path = root / "working/recent-jobs.json"
        try:
            return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        except (ValueError, OSError):
            return []

    def last_result(self):
        path = self.work / "last-result.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def master(self) -> Master:
        path = self.work / "structured-master.json"
        return Master.load(path) if path.is_file() else self.analyze()

    def workflow(self):
        return ReviewWorkflow(self.root, self.master(), self.work)

    def suggestions(self) -> list[dict]:
        workflow = self.workflow()
        return workflow.items() if workflow.active else workflow.legacy()

    def save_suggestions(self, items: list[dict]) -> None:
        workflow = self.workflow()
        path = workflow.folder / "suggestions.json" if workflow.active else self.work / "suggestions.json"
        write_json(path, items)

    def review_plan(self, model, reasoning, limit=None, role="proofreading", repeat=False):
        return self.workflow().plan(role, model, reasoning, limit, repeat)

    def proofread(self, model: str, reasoning: str, limit=None, progress=None, role="proofreading", repeat=False, cancelled=None) -> dict:
        return self.workflow().run(model, reasoning, limit, progress, role, repeat, cancelled)

    def review(self, ids, status):
        workflow = self.workflow()
        if not workflow.active:
            raise ValueError("이전 검토 기록은 보존됩니다. AI 검토를 시작하면 기존 승인본에서 새 검토를 이어갑니다.")
        return workflow.decide(ids, status)

    def _output_base(self, destination: Path | None) -> Path:
        base = Path(destination) if destination is not None else self.default_output_base
        if destination is None:
            base.mkdir(parents=True, exist_ok=True)
        if not base.is_dir() or base.resolve() == self.source.parent:
            raise RuntimeError("선택한 결과물 저장 폴더를 사용할 수 없습니다. 다른 폴더를 선택해 주세요.")
        try:
            with tempfile.NamedTemporaryFile(dir=base, prefix=".write-check-", delete=True):
                pass
        except OSError as exc:
            raise RuntimeError("선택한 폴더에 파일을 저장할 수 없습니다. 다른 폴더를 선택해 주세요.") from exc
        return base

    def _new_output(self, base: Path) -> Path:
        stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", self.source.stem).strip(" .")[:70] or "manuscript"
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        for suffix in range(1000):
            name = f"{stem}_{stamp}" + (f"_{suffix + 1}" if suffix else "")
            folder = base / name
            try:
                folder.mkdir(exist_ok=False)
                return folder
            except FileExistsError:
                continue
        raise RuntimeError("새 결과물 폴더 이름을 만들 수 없습니다.")

    def build(self, formats: list[str], destination: Path | None = None, progress=None) -> dict:
        def stage(text, percent):
            if progress:
                progress({"phase": text, "percent": percent})
        if not formats or set(formats) - {"web", "pdf", "epub"}:
            raise ValueError("WEB, PDF, EPUB 중 하나 이상의 출력 형식을 선택해 주세요.")
        master = self.master()
        stage("승인 내용 반영 중", 5)
        if file_hash(self.source) != master.source_hash:
            raise RuntimeError("원본 DOCX가 분석 이후 변경됐습니다. 다시 분석해 주세요.")
        approved = self.workflow().output_master()
        approved.save(self.work / "approved-master.json")
        assets = self.work / "assets"
        base = self._output_base(destination)
        output = self._new_output(base)
        reports = output / "reports"
        outputs = {}
        # Verify the semantic WEB code before allowing other formats to run.
        stage("HTML 제작 중", 20)
        web_path = web(approved, assets, output / "HTML" if "web" in formats else self.work / "qa-web")
        code_report = check_code_fidelity(self.source, approved, web_path)
        save_report(code_report, reports / "code-fidelity.json")
        if not code_report["passed"]:
            raise RuntimeError("코드 줄바꿈 또는 들여쓰기 보존 검사에 실패했습니다. code-fidelity.json을 확인해 주세요.")
        if "web" in formats:
            outputs["web"] = web_path
        if "pdf" in formats:
            stage("PDF 제작 중", 45)
            outputs["pdf"] = pdf(approved, assets, output / "PDF", f"{self.source.stem}.pdf")
        if "epub" in formats:
            stage("EPUB 제작 중", 70)
            outputs["epub"] = epub_file(approved, assets, output / "EPUB", f"{self.source.stem}.epub")
        stage("결과물 품질 확인 중", 85)
        all_codes = check_output_codes(self.source, approved, outputs)
        save_report(all_codes, reports / "code-output-fidelity.json")
        report = check(approved, self.source, assets, outputs, original_master=master)
        report["code_fidelity_passed"] = all_codes["passed"]
        for kind, detail in all_codes["formats"].items():
            report["checks"].append({"format": "HTML" if kind == "web" else kind.upper(),
                                     "label": "코드 문자·들여쓰기·빈 줄·순서", "passed": detail["passed"],
                                     "detail": f"원본 {all_codes['original_count']}개 · " + ", ".join(detail.get("visual_errors", []))})
        report["passed"] = report["passed"] and all_codes["passed"]
        save_report(report, reports / "qa.json")
        quality_html(report, reports / "QA-report.html", self.source.name, outputs)
        approved.save(reports / "approved-master.json")
        save_report(self.suggestions(), reports / "review-decisions.json")
        if self.workflow().active:
            save_report(self.workflow().legacy(), reports / "legacy-review-decisions.json")
            self.workflow().baseline().save(reports / "review-baseline.json")
        self.output = output
        self.reports = reports
        result = {"outputs": {k: str(v) for k, v in outputs.items()}, "qa": report,
                  "folder": str(output), "report": str(reports / "QA-report.html")}
        self.remember(result)
        stage("결과물 제작 완료", 100)
        return result
