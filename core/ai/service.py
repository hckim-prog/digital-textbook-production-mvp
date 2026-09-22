from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import time

import yaml
from dotenv import load_dotenv
from openai import OpenAI

from core.master import Block, Master

PROTECTED = {"code-block", "code-output", "table", "figure", "math-expression"}
SENSITIVE = re.compile(r"https?://\S+|[A-Za-z]:\\\S+|\b[01]{6,}\b|0x[0-9A-Fa-f]+|[$][^$]+[$]")
FACT_TOKENS = re.compile(r"\d+(?:[.,]\d+)*|[+*/=<>±∞∑∫√]", re.UNICODE)


def protected_facts_unchanged(source: str, target: str) -> bool:
    return FACT_TOKENS.findall(source) == FACT_TOKENS.findall(target)


def settings(root: Path) -> dict:
    return yaml.safe_load((root / "config/models.yaml").read_text(encoding="utf-8"))


def model_config(root: Path, model_id: str) -> dict:
    return next((m for m in settings(root)["models"] if m["id"] == model_id), {})


def available_models(root: Path) -> dict:
    """Compare configured manuscript models with the current API key's model list."""
    configured = [m["id"] for m in settings(root)["models"] if m.get("enabled", True)]
    available = {m.id for m in _client(root).with_options(timeout=10).models.list().data}
    return {"available": [m for m in configured if m in available],
            "unavailable": [m for m in configured if m not in available]}


def safe_blocks(master: Master, limit: int | None) -> list[Block]:
    return [b for b in master.blocks if editable(b)][:limit]


def editable(block):
    return (block.kind not in PROTECTED and bool(block.text.strip()) and not SENSITIVE.search(block.text)
            and not any(i["kind"] in {"image", "math", "link"} or i.get("script") for i in block.inlines))


def _client(root: Path) -> OpenAI:
    env_path = root / ".env"
    if not env_path.is_file() and root.name == "DigitalTextbookMaker" and root.parent.name.startswith("dist"):
        env_path = root.parent.parent / ".env"
    load_dotenv(env_path, override=False)
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OpenAI API Key를 찾을 수 없습니다.")
    return OpenAI(max_retries=0, timeout=45)


def _response(root: Path, model: str, reasoning: str, prompt: str) -> tuple[dict, dict]:
    config = model_config(root, model)
    if not config or not config.get("enabled", True):
        raise ValueError("설정 파일에서 선택한 AI 모델을 사용할 수 없습니다.")
    options = config.get("reasoning_options", config.get("reasoning", []))
    if reasoning not in options:
        raise ValueError(f"{model} 모델은 '{reasoning}' 추론 강도를 지원하지 않습니다.")
    args = {"model": model, "input": prompt, "text": {"format": {"type": "json_object"}}}
    if options:
        args["reasoning"] = {"effort": reasoning}
    start = time.monotonic()
    response = _client(root).responses.create(**args)
    data = json.loads(response.output_text)
    usage = response.usage
    info = {"model": model, "response_model": getattr(response, "model", model),
            "reasoning_effort": reasoning, "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0, "elapsed_seconds": round(time.monotonic() - start, 2)}
    return data, info


def cost(root: Path, info: dict) -> float | None:
    model = model_config(root, info["model"]) if (root / "config/models.yaml").is_file() else {}
    if "input_price_per_million" in model and "output_price_per_million" in model:
        return round((info["input_tokens"] * model["input_price_per_million"] +
                      info["output_tokens"] * model["output_price_per_million"]) / 1_000_000, 6)
    prices = yaml.safe_load((root / "config/pricing.yaml").read_text(encoding="utf-8")) or {}
    rate = (prices.get("models") or {}).get(info["model"])
    if not rate:
        return None
    return round((info["input_tokens"] * rate["input_per_million"] + info["output_tokens"] * rate["output_per_million"]) / 1_000_000, 6)


def record(root: Path, info: dict, stage: str, source: str, chapter: str, success: bool, error: str = "") -> None:
    path = root / "reports/api-usage.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), "source": source, "chapter": chapter,
           "stage": stage, **info, "success": success, "estimated_cost_usd": cost(root, info), "error": error}
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(row, ensure_ascii=False) + "\n")


def connection_test(root: Path, model: str, reasoning: str = "none") -> dict:
    info = {"model": model, "reasoning_effort": reasoning, "input_tokens": 0, "output_tokens": 0, "elapsed_seconds": 0}
    start = time.monotonic()
    try:
        config = model_config(root, model)
        if not config or not config.get("enabled", True):
            raise ValueError("설정 파일에서 선택한 모델을 찾을 수 없습니다.")
        options = config.get("reasoning_options", config.get("reasoning", []))
        if reasoning not in options:
            raise ValueError(f"{model} 모델은 '{reasoning}' 추론 강도를 지원하지 않습니다.")
        args = {"model": model, "input": 'JSON 객체 {"ok":true}만 답하세요.',
                "text": {"format": {"type": "json_object"}}, "max_output_tokens": 128}
        if options:
            args["reasoning"] = {"effort": reasoning}
        response = _client(root).with_options(timeout=20).responses.create(**args)
        if json.loads(response.output_text).get("ok") is not True:
            raise RuntimeError("선택한 모델이 예상한 형식의 응답을 반환하지 않았습니다.")
        usage = response.usage
        info["input_tokens"] = getattr(usage, "input_tokens", 0) or 0
        info["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
        info["response_model"] = getattr(response, "model", model)
        info["elapsed_seconds"] = round(time.monotonic() - start, 2)
        record(root, info, "connection_test", "", "", True)
        return info
    except Exception as exc:
        info["elapsed_seconds"] = round(time.monotonic() - start, 2)
        record(root, info, "connection_test", "", "", False, type(exc).__name__)
        if type(exc).__name__ in {"NotFoundError", "PermissionDeniedError", "AuthenticationError"}:
            raise RuntimeError("선택한 AI 모델을 현재 API Key로 사용할 수 없습니다. 모델 ID와 접근 권한을 확인해 주세요.") from exc
        raise RuntimeError(friendly_error(exc)) from exc


def proofread(root: Path, master: Master, model: str, reasoning: str, limit: int | None, progress=None, role="proofreading", cancelled=None) -> tuple[list[dict], list[dict]]:
    instructions = {
        "proofreading": "맞춤법, 띄어쓰기, 표현을 중심으로 교정하세요.",
        "technical_review": "C++ 개념 설명의 오류와 논리적 모순을 중심으로 검토하세요. 기술적 의심은 C로 분류하고 근거를 이유에 기록하세요.",
        "final_review": "출판 전 최종 검토자로 문장 명확성, 용어 일관성, 의미 오해 가능성을 검토하세요."
    }
    if role not in instructions:
        raise ValueError("검토 역할을 확인해 주세요.")
    suggestions, calls = [], []
    selected = safe_blocks(master, limit)
    for index, block in enumerate(selected, 1):
        if cancelled and cancelled():
            break
        prompt = instructions[role] + ("한국어 대학 교재 문장을 검토하세요. JSON 객체 {\"suggestions\":[{\"source_text\":\"...\",\"suggested_text\":\"...\",\"reason\":\"...\",\"level\":\"A 또는 B 또는 C\"}]}만 반환하세요. "
                  "입력은 앞 단계 승인 내용이 반영된 문장입니다. 이미 반영된 교정을 불필요하게 되돌리지 마세요. 원문 전체를 source_text로 사용하세요. 코드, URL, 수식, 이진수, 숫자, 기술적 사실은 수정하지 마세요. 기술적 의심은 C로 표시하세요. LMM/LLM 불일치는 B로 제안하세요. "
                  f"원문: {block.text}")
        info = {"model": model, "reasoning_effort": reasoning, "input_tokens": 0, "output_tokens": 0, "elapsed_seconds": 0}
        failed = False
        block_started = time.monotonic()
        try:
            data, info = _response(root, model, reasoning, prompt)
            for item in data.get("suggestions", []):
                if not isinstance(item, dict) or item.get("source_text") != block.text or item.get("level") not in ("A", "B", "C"):
                    continue
                target = item.get("suggested_text", "")
                if not target or target == block.text or SENSITIVE.search(target) or SENSITIVE.search(block.text) or not protected_facts_unchanged(block.text, target):
                    continue
                suggestions.append({"id": f"s{len(suggestions)+1:05d}", "block_id": block.id,
                                    "source_text": block.text, "suggested_text": target, "reason": item.get("reason", ""),
                                    "level": item["level"], "role": role, "model": model, "reasoning_effort": reasoning, "status": "pending"})
            info["block_id"] = block.id
            record(root, info, role, master.source_name, master.title, True)
            calls.append({**info, "success": True, "estimated_cost_usd": cost(root, info)})
        except Exception as exc:
            failed = True
            info["block_id"] = block.id
            info["elapsed_seconds"] = round(time.monotonic() - block_started, 2)
            record(root, info, role, master.source_name, master.title, False, type(exc).__name__)
            calls.append({**info, "success": False, "error": friendly_error(exc)})
        if progress:
            progress({"done": index, "total": len(selected), "calls": len(calls),
                      "input_tokens": sum(c.get("input_tokens", 0) for c in calls),
                      "output_tokens": sum(c.get("output_tokens", 0) for c in calls),
                      "elapsed_seconds": round(sum(c.get("elapsed_seconds", 0) for c in calls), 2),
                      "estimated_cost_usd": sum(c.get("estimated_cost_usd") or 0 for c in calls)
                      if all(c.get("estimated_cost_usd") is not None for c in calls) else None})
        if failed:
            break
    return suggestions, calls


def approved_master(master: Master, suggestions: list[dict]) -> Master:
    import copy
    result = copy.deepcopy(master)
    by_id = {b.id: b for b in result.blocks}
    for item in suggestions:
        block = by_id.get(item.get("block_id"))
        if (item.get("status") == "approved" and block and editable(block)
                and block.text == item.get("source_text") and not SENSITIVE.search(block.text)
                and not SENSITIVE.search(item.get("suggested_text", ""))
                and protected_facts_unchanged(block.text, item.get("suggested_text", ""))):
            block.text = item["suggested_text"]
            block.inlines = [{"kind": "text", "text": block.text}]
    return result


def friendly_error(exc):
    name = type(exc).__name__
    messages = {
        "AuthenticationError": "API 인증에 실패했습니다. 등록된 API Key를 확인해 주세요.",
        "PermissionDeniedError": "선택한 모델에 접근할 권한이 없습니다.",
        "NotFoundError": "선택한 모델을 사용할 수 없습니다. 모델 ID와 접근 권한을 확인해 주세요.",
        "RateLimitError": "API 사용 한도에 도달했습니다. 사용량 또는 결제 설정을 확인해 주세요.",
        "APITimeoutError": "API 응답 시간이 초과됐습니다. 네트워크를 확인한 뒤 다시 시도해 주세요.",
        "APIConnectionError": "API 서버에 연결하지 못했습니다. 네트워크 연결을 확인해 주세요.",
        "BadRequestError": "선택한 모델의 요청 설정을 확인해 주세요. 모델과 추론 강도가 맞지 않을 수 있습니다.",
        "PermissionError": "파일을 읽거나 저장할 권한이 없습니다. 다른 저장 폴더를 선택해 주세요.",
        "BadZipFile": "DOCX 파일을 읽을 수 없습니다. Word에서 다시 저장한 파일을 선택해 주세요.",
    }
    if name in messages:
        return messages[name]
    if isinstance(exc, (RuntimeError, ValueError, FileNotFoundError)):
        return re.sub(r"sk-[A-Za-z0-9_-]+", "[보호된 키]", str(exc))
    return f"작업을 완료하지 못했습니다. 파일과 설정을 확인해 주세요. (오류 유형: {name})"
