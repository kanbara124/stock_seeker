from dataclasses import dataclass
from pathlib import Path


@dataclass
class Material:
    n: int
    title: str
    url: str
    text: str


def load_materials(cache_dir: Path) -> list[Material]:
    materials: list[Material] = []
    for i, path in enumerate(sorted(cache_dir.glob("*.txt")), start=1):
        content = path.read_text(encoding="utf-8")
        parts = content.split("\n", 2)
        if len(parts) < 3:
            continue
        title, url, body = parts[0].strip(), parts[1].strip(), parts[2].strip()
        materials.append(Material(n=i, title=title, url=url, text=body))
    return materials
