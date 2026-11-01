#!/usr/bin/env python3
"""Публикует статьи блога в Telegram-канал и сообщество VK.

По умолчанию берёт полный текст и фото из `_blog/posts/<slug>.md` (как на сайте).
Файл `_blog/announce/<slug>.json` — только хештеги и редкие настройки (см. PERSONA.md).
Учёт отправленного: `_blog/announce/posted.json`.

Секреты только из окружения (GitHub Actions):
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, VK_GROUP_TOKEN, VK_GROUP_ID
DRY_RUN=1 — печать без отправки.
"""
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from build_blog import abs_url, parse_post  # noqa: E402

ANN_DIR = ROOT / "_blog" / "announce"
POSTS_DIR = ROOT / "_blog" / "posts"
POSTED = ANN_DIR / "posted.json"
SITE = "https://electric.vim-scrum.ru"
DRY = os.environ.get("DRY_RUN") == "1"
TG_TEXT_LIMIT = 4096
TG_CAPTION_LIMIT = 1024


def http(url, data=None, timeout=60, headers=None):
    h = {"User-Agent": "vim-blog-announce/1.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
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


def _md_link(m):
    label, url = m.group(1), m.group(2)
    if url.startswith("/"):
        url = abs_url(url)
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label, quote=False)}</a>'


def _md_inline_tg(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<i>\1</i>", text)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _md_link, text)


def _md_inline_vk(text: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"\1", text)

    def link(m):
        label, url = m.group(1), m.group(2)
        if url.startswith("/"):
            url = abs_url(url)
        return f"{label} ({url})"

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)


def _table_to_lines(rows) -> str:
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    if len(cells) < 2:
        return ""
    head, body = cells[0], cells[2:]
    lines = [" · ".join(f"{a} — {b}" for a, b in zip(head, r)) for r in body if len(r) >= len(head)]
    return "\n".join(lines)


def iter_post_blocks(body_md: str):
    """Порядок блоков как в статье: текст / фото."""
    lines = body_md.replace("\r\n", "\n").split("\n")
    i, n = 0, len(lines)
    buf: list[str] = []

    def flush():
        nonlocal buf
        if buf:
            chunk = "\n".join(buf).strip()
            buf = []
            if chunk:
                yield {"type": "text", "md": chunk}
        return

    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if re.match(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$", line):
            yield from flush()
            m = re.match(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$", line)
            yield {"type": "photo", "alt": m.group(1), "path": m.group(2)}
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            yield from flush()
            trows = []
            while i < n and lines[i].lstrip().startswith("|"):
                trows.append(lines[i])
                i += 1
            yield {"type": "text", "md": _table_to_lines(trows)}
            continue
        buf.append(line)
        i += 1
    yield from flush()


def _md_chunk_to_tg(md: str) -> str:
    out = []
    for para in re.split(r"\n\n+", md.strip()):
        para = para.strip()
        if not para:
            continue
        if m := re.match(r"^(#{2,4})\s+(.*)", para):
            out.append(f"<b>{_md_inline_tg(m.group(2))}</b>")
            continue
        if para.startswith(">"):
            q = "\n".join(ln.lstrip("> ").strip() for ln in para.split("\n"))
            out.append(f"<i>{_md_inline_tg(q)}</i>")
            continue
        if re.match(r"^[-*]\s+", para):
            items = re.findall(r"(?m)^[-*]\s+(.*)", para)
            out.append("\n".join(f"• {_md_inline_tg(t)}" for t in items))
            continue
        if re.match(r"^\d+[.)]\s+", para):
            items = re.findall(r"(?m)^\d+[.)]\s+(.*)", para)
            out.append("\n".join(f"{n + 1}. {_md_inline_tg(t)}" for n, t in enumerate(items)))
            continue
        if "\n" in para and all(re.match(r"^[-*]\s+", ln) for ln in para.split("\n")):
            items = [re.sub(r"^[-*]\s+", "", ln) for ln in para.split("\n")]
            out.append("\n".join(f"• {_md_inline_tg(t)}" for t in items))
            continue
        out.append(_md_inline_tg(para.replace("\n", " ")))
    return "\n\n".join(out)


def _md_chunk_to_vk(md: str) -> str:
    out = []
    for para in re.split(r"\n\n+", md.strip()):
        para = para.strip()
        if not para:
            continue
        if m := re.match(r"^(#{2,4})\s+(.*)", para):
            out.append(_md_inline_vk(m.group(2)).upper())
            continue
        if para.startswith(">"):
            q = "\n".join(ln.lstrip("> ").strip() for ln in para.split("\n"))
            out.append(f"💡 {_md_inline_vk(q)}")
            continue
        if re.match(r"^[-*]\s+", para) or (
            "\n" in para and all(re.match(r"^[-*]\s+", ln) for ln in para.split("\n"))
        ):
            items = re.findall(r"(?m)^[-*]\s+(.*)", para)
            out.append("\n".join(f"— {_md_inline_vk(t)}" for t in items))
            continue
        if re.match(r"^\d+[.)]\s+", para):
            items = re.findall(r"(?m)^\d+[.)]\s+(.*)", para)
            out.append("\n".join(f"{n + 1}. {_md_inline_vk(t)}" for n, t in enumerate(items)))
            continue
        out.append(_md_inline_vk(para.replace("\n", " ")))
    return "\n\n".join(out)


def build_full_payload(slug: str, ann: dict, link: str):
    post_path = POSTS_DIR / f"{slug}.md"
    if not post_path.exists():
        return None
    post = parse_post(post_path)
    title = post["title"]
    ops_tg = [{"kind": "text", "html": f"<b>{html.escape(title)}</b>"}]
    parts_vk = [title, ""]

    for block in iter_post_blocks(post["body_md"]):
        if block["type"] == "text":
            tg = _md_chunk_to_tg(block["md"])
            vk = _md_chunk_to_vk(block["md"])
            if tg:
                ops_tg.append({"kind": "text", "html": tg})
            if vk:
                parts_vk.append(vk)
                parts_vk.append("")
        elif block["type"] == "photo":
            url = abs_url(block["path"])
            cap = block["alt"].strip()
            ops_tg.append({"kind": "photo", "url": url, "caption": cap})
            if cap:
                parts_vk.append(f"📷 {cap}")
            parts_vk.append("")

    footer_tg = f'<a href="{html.escape(link, quote=True)}">Страница на сайте →</a>'
    ops_tg.append({"kind": "text", "html": footer_tg})
    tags = " ".join(ann.get("hashtags", []))
    footer_vk = f"На сайте: {link}"
    if tags:
        footer_vk += f"\n\n{tags}"
    parts_vk.append(footer_vk)
    vk_text = "\n".join(parts_vk).strip()
    photo_urls = [op["url"] for op in ops_tg if op["kind"] == "photo"]
    return ops_tg, vk_text, photo_urls


def _split_tg_html(text: str, limit: int = TG_TEXT_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks, rest = [], text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        cut = rest.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    return chunks


def _tg_api(token, method, params):
    data = urllib.parse.urlencode(params).encode()
    http(f"https://api.telegram.org/bot{token}/{method}", data)


def publish_telegram_full(ops, link):
    token, chan = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHANNEL_ID")
    if not (token and chan):
        return "skip"
    if DRY:
        print("[TG full]", len(ops), "ops", link)
        return "dry"
    for op in ops:
        if op["kind"] == "text":
            for chunk in _split_tg_html(op["html"]):
                _tg_api(token, "sendMessage", {
                    "chat_id": chan,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": "true",
                })
                time.sleep(0.35)
        elif op["kind"] == "photo":
            cap = op.get("caption") or ""
            if len(cap) > TG_CAPTION_LIMIT:
                cap = cap[: TG_CAPTION_LIMIT - 1] + "…"
            params = {"chat_id": chan, "photo": op["url"]}
            if cap:
                params["caption"] = cap
            _tg_api(token, "sendPhoto", params)
            time.sleep(0.35)
    return "ok"


def publish_telegram_teaser(text, link):
    token, chan = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHANNEL_ID")
    if not (token and chan):
        return "skip"
    body = f'{text}\n\n<a href="{link}">Читать статью полностью →</a>'
    if DRY:
        print("[TG teaser]", body[:200], "…")
        return "dry"
    data = urllib.parse.urlencode({
        "chat_id": chan, "text": body, "parse_mode": "HTML",
        "link_preview_options": json.dumps({"url": link, "prefer_large_media": True}),
    }).encode()
    http(f"https://api.telegram.org/bot{token}/sendMessage", data)
    return "ok"


def _vk_api(method, params, token):
    params = dict(params, access_token=token, v="5.199")
    _, raw = http(f"https://api.vk.com/method/{method}", urllib.parse.urlencode(params).encode())
    res = json.loads(raw)
    if "error" in res:
        raise RuntimeError(f"VK {method}: {res['error'].get('error_msg')}")
    return res["response"]


def _vk_upload_wall_photo(token, gid, image_url):
    _, img = http(image_url, timeout=90)
    up = _vk_api("photos.getWallUploadServer", {"group_id": gid}, token)
    upload_url = up["upload_url"]
    boundary = "----vimboundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="photo"; filename="photo.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + img + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        upload_url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        saved = json.loads(r.read().decode())
    resp = _vk_api("photos.saveWallPhoto", {
        "group_id": gid,
        "photo": saved["photo"],
        "server": saved["server"],
        "hash": saved["hash"],
    }, token)
    p = resp[0]
    return f"photo{p['owner_id']}_{p['id']}"


def publish_vk_full(text, photo_urls):
    token, gid = os.environ.get("VK_GROUP_TOKEN"), os.environ.get("VK_GROUP_ID")
    if not (token and gid):
        return "skip"
    gid = gid.lstrip("-")
    if DRY:
        print("[VK full]", len(text), "chars,", len(photo_urls), "photos")
        return "dry"
    attachments = []
    for url in photo_urls:
        try:
            attachments.append(_vk_upload_wall_photo(token, gid, url))
            time.sleep(0.5)
        except Exception as e:
            print(f"VK: фото не загрузилось ({url}): {e}", file=sys.stderr)
    base = {"owner_id": f"-{gid}", "from_group": 1, "message": text[:16300]}
    if attachments:
        _vk_api("wall.post", dict(base, attachments=",".join(attachments)), token)
    else:
        _vk_api("wall.post", base, token)
    return "ok"


def publish_vk_teaser(text, link):
    token, gid = os.environ.get("VK_GROUP_TOKEN"), os.environ.get("VK_GROUP_ID")
    if not (token and gid):
        return "skip"
    gid = gid.lstrip("-")
    msg = f"{text}" + chr(10) * 2 + f"Читать полностью: {link}"
    if DRY:
        print("[VK teaser]", msg[:200], "…")
        return "dry"
    base = {"owner_id": f"-{gid}", "from_group": 1, "message": msg}
    try:
        _vk_api("wall.post", dict(base, attachments=link), token)
    except RuntimeError as e:
        print(f"VK: карточка не прошла ({e}), публикую текстом", file=sys.stderr)
        _vk_api("wall.post", base, token)
    return "ok"


def _want_social_version(ann: dict) -> int:
    return int(ann.get("social_version", 1))


def _posted_social_version(done: dict) -> int:
    return int(done.get("social_version", 0))


def needs_social_publish(ann: dict, done: dict) -> bool:
    """Новая статья, неудачная отправка или social_version в announce выше, чем в posted."""
    if _want_social_version(ann) > _posted_social_version(done):
        return True
    return done.get("telegram") != "ok" or done.get("vk") != "ok"


def main():
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    changed, failed = False, False
    only_slug = os.environ.get("REPUBLISH_SLUG", "").strip()
    for f in sorted(ANN_DIR.glob("*.json")):
        slug = f.stem
        if slug == "posted":
            continue
        if only_slug and slug != only_slug:
            continue
        done = posted.setdefault(slug, {})
        ann = json.loads(f.read_text(encoding="utf-8"))
        link = f"{SITE}/blog/{slug}/"
        fmt = ann.get("format", "full")
        if not needs_social_publish(ann, done):
            continue
        todo = [("telegram", None), ("vk", None)]
        if not wait_live(link):
            print(f"{slug}: статья не открылась за отведённое время, пропуск", file=sys.stderr)
            failed = True
            continue

        full = None
        if fmt != "teaser":
            full = build_full_payload(slug, ann, link)

        for name, _ in todo:
            try:
                if full and fmt != "teaser":
                    ops_tg, vk_text, photo_urls = full
                    if name == "telegram":
                        status = publish_telegram_full(ops_tg, link)
                    else:
                        status = publish_vk_full(vk_text, photo_urls)
                else:
                    text = ann.get(name, "").strip()
                    if name == "vk":
                        tags = " ".join(ann.get("hashtags", []))
                        if tags:
                            text += f"\n\n{tags}"
                    if not text:
                        print(f"{slug}/{name}: пустой текст, пропуск", file=sys.stderr)
                        continue
                    status = (
                        publish_telegram_teaser(text, link)
                        if name == "telegram"
                        else publish_vk_teaser(text, link)
                    )
            except Exception as e:
                print(f"{slug}/{name}: ОШИБКА {e}", file=sys.stderr)
                failed = True
                continue
            if status == "ok":
                done[name] = "ok"
                changed = True
            print(f"{slug}/{name}: {status}")
        if done.get("telegram") == "ok" and done.get("vk") == "ok":
            done["social_version"] = _want_social_version(ann)
    if changed and not DRY:
        POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
