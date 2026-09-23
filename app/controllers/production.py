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
from core.manuscript.structure import StructureStore
from core.master import Master, file_hash
from core.qa.checks import check, save_report, quality_html
from core.qa.code_fidelity import check_code_fidelity, check_output_codes
from core.cancellation import check_cancelled, OperationCancelled


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

    def structure(self):
        return StructureStore(self.work, self.master())

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

    def build(self, formats: list[str], destination: Path | None = None, progress=None, quick=False, publication=None, theme="auto", cancelled=None) -> dict:
        self._building_folder = None
        try:
            return self._build(formats, destination, progress, quick, publication, theme, cancelled)
        except Exception as exc:
            if self._building_folder:
                save_report({'status': 'cancelled' if isinstance(exc, OperationCancelled) else 'failed',
                             'note': '완료되지 않은 출력입니다. 다시 제작하면 새 폴더에 저장합니다.'},
                            self._building_folder / 'reports/production-state.json')
            raise
        finally:
            self._building_folder = None

    def _build(self, formats, destination, progress, quick, publication, theme, cancelled):
        def stage(text, percent):
            check_cancelled(cancelled)
            if progress:
                progress({"phase": text, "percent": percent})
            check_cancelled(cancelled)
        check_cancelled(cancelled)
        if not formats or set(formats) - {"web", "pdf", "epub"}:
            raise ValueError("WEB, PDF, EPUB 중 하나 이상의 출력 형식을 선택해 주세요.")
        master = self.master()
        stage("승인 내용 반영 중", 5)
        if file_hash(self.source) != master.source_hash:
            raise RuntimeError("원본 DOCX가 분석 이후 변경됐습니다. 다시 분석해 주세요.")
        approved = self.workflow().output_master()
        quick_report = None
        if quick:
            from core.ai.quick import quick_master
            approved, quick_report = quick_master(approved, self.workflow().items())
        if publication is not None:
            from core.manuscript.structure import validate
            if not publication.get('passed') or publication.get('source_hash') != master.source_hash:
                raise ValueError('사전 진단 결과가 현재 원고와 맞지 않습니다.')
            approved.outline = validate(approved, publication['nodes'])
        else:
            approved = self.structure().apply(approved)
        from core.export.themes import resolve
        design = resolve(approved, theme)
        approved.save(self.work / "approved-master.json")
        assets = self.work / "assets"
        base = self._output_base(destination)
        output = self._new_output(base)
        self._building_folder = output
        reports = output / "reports"
        save_report({'status': 'building'}, reports / 'production-state.json')
        outputs = {}
        save_report({"requested": theme, **design}, reports / "design.json")
        if publication is not None:
            save_report(publication, reports / 'publication-preflight.json')
        # Verify the semantic WEB code before allowing other formats to run.
        stage("HTML 제작 중", 20)
        web_path = web(approved, assets, output / "HTML" if "web" in formats else self.work / "qa-web", theme=design["id"], cancelled=cancelled)
        code_report = check_code_fidelity(self.source, approved, web_path)
        save_report(code_report, reports / "code-fidelity.json")
        if not code_report["passed"]:
            counts = code_report['counts']
            mismatch = [item['block_id'] for item in code_report['blocks'] if not item['exact_equal']]
            reason = (f"코드 영역 개수 또는 순서 불일치 · 원본 {counts['docx']} / 준비 {counts['master']} / HTML {counts['html']}"
                      if not code_report['count_equal'] or not code_report['order_equal']
                      else '코드 문자·줄바꿈·들여쓰기 불일치: ' + ', '.join(mismatch[:10]))
            raise RuntimeError(reason + '\n원본 파일은 변경하지 않았습니다. 검사 보고서: ' + str(reports / 'code-fidelity.json'))
        if "web" in formats:
            outputs["web"] = web_path
        if "pdf" in formats:
            stage("PDF 제작 중", 45)
            outputs["pdf"] = pdf(approved, assets, output / "PDF", f"{self.source.stem}.pdf", theme=design["id"], cancelled=cancelled)
        if "epub" in formats:
            stage("EPUB 제작 중", 70)
            outputs["epub"] = epub_file(approved, assets, output / "EPUB", f"{self.source.stem}.epub", theme=design["id"], cancelled=cancelled)
        stage("결과물 품질 확인 중", 85)
        all_codes = check_output_codes(self.source, approved, outputs)
        save_report(all_codes, reports / "code-output-fidelity.json")
        report = check(approved, self.source, assets, outputs, original_master=master)
        check_cancelled(cancelled)
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
        if quick_report is not None:
            save_report(quick_report, reports / "quick-changes.json")
            rows = "".join("<tr><td>" + escape(i['source_text']) + "</td><td>" + escape(i['suggested_text']) + "</td></tr>" for i in quick_report['applied'])
            (reports / "quick-changes.html").write_text(
                '<!doctype html><meta charset="utf-8"><title>빠른 제작 변경 내역</title>'
                '<style>body{font-family:Malgun Gothic;margin:2rem}td{border:1px solid #ccc;padding:1rem;white-space:pre-wrap}</style>'
                '<h1>빠른 제작 변경 내역</h1>'
                f"<p>제한 교정 {quick_report['applied_count']}건 적용 · 미검토 제안 {quick_report['retained_count']}건 미적용</p>"
                '<p>기존 승인·거절·보류 기록은 유지했습니다. 자동 교정을 끄고 다시 제작하면 이번 자동 수정이 제외됩니다.</p>'
                '<table><tr><th>기준 문장</th><th>자동 교정</th></tr>' + rows + '</table>', encoding='utf-8')
        if self.workflow().active:
            save_report(self.workflow().legacy(), reports / "legacy-review-decisions.json")
            self.workflow().baseline().save(reports / "review-baseline.json")
        check_cancelled(cancelled)
        save_report({'status': 'completed' if report['passed'] else 'qa_failed'}, reports / 'production-state.json')
        self.output = output
        self.reports = reports
        result = {"outputs": {k: str(v) for k, v in outputs.items()}, "qa": report,
                  "folder": str(output), "report": str(reports / "QA-report.html"), "quick": quick_report, "design": design}
        if publication is None or report['passed']:
            self.remember(result)
        if progress:
            progress({"phase": "결과물 제작 완료", "percent": 100})
        return result
