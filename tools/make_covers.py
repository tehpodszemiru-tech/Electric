#!/usr/bin/env python3
"""Делает горизонтальные обложки 1200x630 для статей (превью в соцсетях и карточки блога).

Для каждой статьи _blog/posts/<slug>.md с полем `cover:` берёт фото из assets/photos/,
вырезает горизонтальный кадр (точка фокуса `focus:` 0..1 по вертикали, по умолчанию 0.5),
ставит бейдж с логотипом и сохраняет assets/covers/<slug>.jpg.
build_blog.py подхватывает этот файл автоматически.

Нужен Pillow:  pip install pillow
Запуск из корня репозитория:  python tools/make_covers.py
"""
import re
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Нужен Pillow: pip install pillow")

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "_blog" / "posts"
PHOTOS = ROOT / "assets" / "photos"
OUT = ROOT / "assets" / "covers"
W, H = 1200, 630


def meta(path):
    m = re.match(r"^---\n(.*?)\n---", path.read_text(encoding="utf-8").replace("\r\n", "\n"), re.S)
    d = {}
    for ln in (m.group(1).split("\n") if m else []):
        if ":" in ln:
            k, v = ln.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def make(photo: Path, focus: float, dest: Path):
    im = Image.open(photo).convert("RGB")
    scale = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left = (im.width - W) // 2
    top = round((im.height - H) * min(max(focus, 0), 1))
    im = im.crop((left, top, left + W, top + H))
    logo_p = ROOT / "assets" / "brand" / "logo.png"
    if logo_p.exists():
        logo = Image.open(logo_p).convert("RGBA").resize((96, 96), Image.LANCZOS)
        im.paste(logo, (36, H - 132), logo)
    dest.parent.mkdir(parents=True, exist_ok=True)
    im.save(dest, "JPEG", quality=88, optimize=True)


def main():
    made = 0
    for p in sorted(POSTS.glob("*.md")):
        m = meta(p)
        cover = m.get("cover")
        if not cover:
            continue
        src = PHOTOS / cover
        if not src.exists():
            print(f"{p.stem}: нет фото {cover}", file=sys.stderr)
            continue
        make(src, float(m.get("focus", 0.5)), OUT / f"{p.stem}.jpg")
        made += 1
        print(f"{p.stem}: обложка из {cover}")
    print(f"Готово обложек: {made}")


if __name__ == "__main__":
    main()
