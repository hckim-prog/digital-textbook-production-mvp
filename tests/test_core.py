from pathlib import Path
import zipfile

from core.ai.service import approved_master, cost, protected_facts_unchanged, safe_blocks
from core.export.outputs import epub_file, pdf, web
from core.master import Block, Master, file_hash
from core.qa.checks import check
from core.reporting import comparison
from core.manuscript.docx_reader import read_docx
from core.qa.code_fidelity import check_code_fidelity
from core.ai import service
import pytest


def sample(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"original")
    master = Master("테스트 장", source.name, file_hash(source), [
        Block("b1", "heading", "제목"),
        Block("b2", "paragraph", "문장 오탈자"),
        Block("b3", "code-block", "int main() {}"),
        Block("b4", "paragraph", "숫자 123과 수식 x=2"),
        Block("b5", "table", rows=[["항목", "값"], ["A", "B"]]),
    ])
    return source, master


def test_approval_and_protection(tmp_path):
    _, master = sample(tmp_path)
    assert [b.id for b in safe_blocks(master, 20)] == ["b1", "b2", "b4"]
    items = [
        {"block_id": "b2", "status": "approved", "source_text": "문장 오탈자", "suggested_text": "문장 오타"},
        {"block_id": "b3", "status": "approved", "source_text": "int main() {}", "suggested_text": "code"},
        {"block_id": "b4", "status": "approved", "source_text": "숫자 123과 수식 x=2", "suggested_text": "숫자 124와 수식 x=2"},
    ]
    result = approved_master(master, items)
    assert result.blocks[1].text == "문장 오타"
    assert result.blocks[2].text == "int main() {}"
    assert result.blocks[3].text == "숫자 123과 수식 x=2"
    assert not protected_facts_unchanged("1+2", "1+3")


def test_exports_and_hash(tmp_path):
    source, master = sample(tmp_path)
    assets = tmp_path / "assets"
    assets.mkdir()
    outputs = {"web": web(master, assets, tmp_path / "web"),
               "pdf": pdf(master, assets, tmp_path / "pdf"),
               "epub": epub_file(master, assets, tmp_path / "epub")}
    assert "문장 오탈자" in outputs["web"].read_text(encoding="utf-8")
    assert outputs["pdf"].read_bytes().startswith(b"%PDF")
    with zipfile.ZipFile(outputs["epub"]) as book:
        assert "EPUB/nav.xhtml" in book.namelist()
    assert check(master, source, assets, outputs)["passed"]
    source.write_bytes(b"changed")
    assert not check(master, source, assets, outputs)["passed"]


def test_cost_missing_price(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/pricing.yaml").write_text("models: {}", encoding="utf-8")
    assert cost(tmp_path, {"model": "x", "input_tokens": 10, "output_tokens": 20}) is None
    (tmp_path / "config/pricing.yaml").write_text("models:\n  x:\n    input_per_million: 1\n    output_per_million: 2\n", encoding="utf-8")
    assert cost(tmp_path, {"model": "x", "input_tokens": 10, "output_tokens": 20}) == 0.00005


def test_connection_test_uses_selected_responses_model(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config/models.yaml").write_text("models:\n  - id: test-model\n    reasoning_options: [none]\n", encoding="utf-8")
    (tmp_path / "config/pricing.yaml").write_text("models: {}", encoding="utf-8")
    calls = []

    class Client:
        def with_options(self, **options):
            calls.append(options)
            return self

        @property
        def responses(self):
            return self

        def create(self, **args):
            calls.append(args)
            from types import SimpleNamespace
            return SimpleNamespace(output_text='{"ok":true}', usage=SimpleNamespace(input_tokens=10, output_tokens=4))

    monkeypatch.setattr(service, "_client", lambda root: Client())
    info = service.connection_test(tmp_path, "test-model")
    assert calls[0] == {"timeout": 20}
    assert calls[1]["model"] == "test-model"
    assert (info["input_tokens"], info["output_tokens"]) == (10, 4)


def test_background_task_signals_reach_ui():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication
    from app.workers.task import start

    app = QApplication.instance() or QApplication([])
    for action, expected in ((lambda: "ok", ("done", "ok")),
                             (lambda: 1 / 0, ("failed", "작업을 완료하지 못했습니다. 파일과 설정을 확인해 주세요. (오류 유형: ZeroDivisionError)"))):
        loop = QEventLoop()
        outcomes = []
        thread = start(action,
                       lambda value: (outcomes.append(("done", value)), loop.quit()),
                       lambda error: (outcomes.append(("failed", error)), loop.quit()))
        QTimer.singleShot(2000, loop.quit)
        loop.exec()
        assert outcomes == [expected]
        if thread.isRunning():
            cleanup = QEventLoop()
            thread.finished.connect(cleanup.quit)
            QTimer.singleShot(2000, cleanup.quit)
            cleanup.exec()
        assert not thread.isRunning()


def test_model_comparison_contains_suggestions(tmp_path, monkeypatch):
    _, master = sample(tmp_path)
    def fake_proofread(root, selected, model, reasoning, limit):
        return ([{"source_text": "문장 오탈자", "suggested_text": "문장 오타", "level": "A"}],
                [{"input_tokens": 20, "output_tokens": 10, "elapsed_seconds": 1, "success": True, "estimated_cost_usd": .001}])
    monkeypatch.setattr(comparison, "proofread", fake_proofread)
    page = comparison.compare(tmp_path, master, ["a", "b"], "none", 2)
    assert "문장 오타" in page.read_text(encoding="utf-8")
    assert (page.parent / "model-comparison-details.json").is_file()


def test_chapter1_code_fidelity_end_to_end(tmp_path):
    sources = list((Path(__file__).resolve().parents[1] / "input/chapter-01").glob("*.docx"))
    if not sources:
        pytest.skip("실제 Chapter 1 원고가 없습니다.")
    source = sources[0]
    work = tmp_path / "work"
    master = read_docx(source, work)
    code_ids = {block.id for block in master.blocks if block.kind == "code-block"}
    assert len(code_ids) == 6
    assert code_ids.isdisjoint({block.id for block in safe_blocks(master, 1000)})
    page = web(master, work / "assets", tmp_path / "web")
    report = check_code_fidelity(source, master, page)
    assert report["passed"], report
    assert report["counts"] == {"docx": 6, "master": 6, "html": 6}
    debug = next(block for block in report["blocks"] if "int kor = 90;" in "\n".join(block["docx_lines"]))
    assert debug["line_counts"] == {"docx": 16, "master": 16, "html": 16}
    assert debug["docx_lines"] == debug["master_lines"] == debug["html_lines"]
    page.write_text(page.read_text(encoding="utf-8").replace("    int kor = 90;", "   int kor = 90;", 1), encoding="utf-8")
    assert not check_code_fidelity(source, master, page)["passed"]
