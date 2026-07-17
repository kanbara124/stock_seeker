from dataclasses import dataclass
from pathlib import Path


@dataclass
class Material:
    n: int
    title: str
    url: str
    text: str


def load_materials(cache_dir: Path, urls: set[str] | None = None) -> list[Material]:
    entries: list[tuple[str, str, str]] = []
    for path in sorted(cache_dir.glob("*.txt")):
        content = path.read_text(encoding="utf-8")
        parts = content.split("\n", 2)
        if len(parts) < 3:
            continue
        title, url, body = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if urls is not None and url not in urls:
            continue
        entries.append((title, url, body))
    return [Material(n=i, title=t, url=u, text=b) for i, (t, u, b) in enumerate(entries, start=1)]
