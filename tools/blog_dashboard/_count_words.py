import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent / "_blog" / "posts"
rows = []
for p in sorted(root.glob("*.md")):
    t = p.read_text(encoding="utf-8")
    t = re.sub(r"^---\n.*?\n---\n", "", t, flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    words = len(re.findall(r"[\w\-']+", t, re.UNICODE))
    rows.append((words, p.stem))
for w, slug in sorted(rows, key=lambda x: x[0]):
    print(f"{w:5d}  {slug}")
if rows:
    avg = sum(r[0] for r in rows) / len(rows)
    print("---")
    print(f"avg={avg:.0f}  n={len(rows)}")
