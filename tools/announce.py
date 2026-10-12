#!/usr/bin/env python3
"""Публикует анонсы новых статей в Telegram-канал и сообщество VK.

Берёт _blog/announce/<slug>.json (пишет агент), добавляет ссылку на статью и
отправляет только то, что ещё не отправлялось (учёт в _blog/announce/posted.json).
Ждёт, пока статья реально откроется на сайте (GitHub Pages публикуется с задержкой).

Секреты приходят ТОЛЬКО из переменных окружения (GitHub Actions secrets):
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, VK_GROUP_TOKEN, VK_GROUP_ID
Площадка без секретов пропускается. Переменная DRY_RUN=1 печатает вместо отправки.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANN_DIR = ROOT / "_blog" / "announce"
POSTED = ANN_DIR / "posted.json"
SITE = "https://electric.vim-scrum.ru"
DRY = os.environ.get("DRY_RUN") == "1"


def http(url, data=None, timeout=20):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "vim-blog-announce/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def wait_live(url, minutes=12):
    if DRY:
        return True
    for _ in range(minutes * 4):
        try:
            if http(url, timeout=10)[0] == 200:
                return True
        except Exception:
            pass
        time.sleep(15)
    return False


def tg(text, link):
    token, chan = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHANNEL_ID")
    if not (token and chan):
        return "skip"
    body = f'{text}\n\n<a href="{link}">Читать статью полностью →</a>'
    if DRY:
        print("[TG]", body)
        return "dry"
    data = urllib.parse.urlencode({
        "chat_id": chan, "text": body, "parse_mode": "HTML",
        "link_preview_options": json.dumps({"url": link, "prefer_large_media": True}),
    }).encode()
    http(f"https://api.telegram.org/bot{token}/sendMessage", data)
    return "ok"


def vk(text, link):
    token, gid = os.environ.get("VK_GROUP_TOKEN"), os.environ.get("VK_GROUP_ID")
    if not (token and gid):
        return "skip"
    msg = f"{text}\n\nЧитать полностью: {link}"
    if DRY:
        print("[VK]", msg)
        return "dry"
    data = urllib.parse.urlencode({
        "owner_id": f"-{gid.lstrip('-')}", "from_group": 1, "message": msg,
        "attachments": link, "access_token": token, "v": "5.199",
    }).encode()
    _, raw = http("https://api.vk.com/method/wall.post", data)
    res = json.loads(raw)
    if "error" in res:
        raise RuntimeError(f"VK: {res['error'].get('error_msg')}")
    return "ok"


def main():
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    changed, failed = False, False
    for f in sorted(ANN_DIR.glob("*.json")):
        slug = f.stem
        if slug == "posted":
            continue
        done = posted.setdefault(slug, {})
        ann = json.loads(f.read_text(encoding="utf-8"))
        link = f"{SITE}/blog/{slug}/"
        tags = " ".join(ann.get("hashtags", []))
        todo = [(n, fn) for n, fn in (("telegram", tg), ("vk", vk)) if done.get(n) != "ok"]
        if not todo:
            continue
        if not wait_live(link):
            print(f"{slug}: статья не открылась за отведённое время, пропуск", file=sys.stderr)
            failed = True
            continue
        for name, fn in todo:
            text = ann.get(name, "").strip()
            if name == "vk" and tags:
                text += f"\n\n{tags}"
            if not text:
                continue
            try:
                status = fn(text, link)
            except Exception as e:  # одна площадка не должна ронять другую
                print(f"{slug}/{name}: ОШИБКА {e}", file=sys.stderr)
                failed = True
                continue
            if status in ("ok",):
                done[name] = "ok"
                changed = True
            print(f"{slug}/{name}: {status}")
    if changed and not DRY:
        POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
