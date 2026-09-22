from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
import json


@dataclass
class Block:
    id: str
    kind: str
    text: str = ""
    style: str = ""
    number: str = ""
    assets: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    cell_kinds: list[list[str]] = field(default_factory=list)
    group: str = ""
    inlines: list[dict] = field(default_factory=list)
    rich_cells: list[list[list[dict]]] = field(default_factory=list)
    list_label: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class Master:
    title: str
    source_name: str
    source_hash: str
    blocks: list[Block]
    assets_dir: str = "assets"

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Master":
        data = json.loads(path.read_text(encoding="utf-8"))
        data["blocks"] = [Block(**block) for block in data["blocks"]]
        return cls(**data)


def file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
