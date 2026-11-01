#!/usr/bin/env python3
"""Публикует статьи блога в Telegram-канал и сообщество VK.

Один пост на площадку: текст из `_blog/posts/<slug>.md`, при необходимости сжимается
под лимит. Полная версия — только на сайте. Настройки: `_blog/announce/<slug>.json`.

Секреты: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, VK_GROUP_TOKEN, VK_GROUP_ID.
DRY_RUN=1 — без отправки.
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
TG_LIMIT = 4096
VK_LIMIT = 16300


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


def _md_link_tg(m):
    label, url = m.group(1), m.group(2)
    if url.startswith("/"):
        url = abs_url(url)
    return f'<a href="{html.escape(url, quote=True)}">{html.escape(label, quote=False)}</a>'


def _md_inline_tg(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<i>\1</i>", text)
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _md_link_tg, text)


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
    return "\n".join(
        " · ".join(f"{a} — {b}" for a, b in zip(head, r))
        for r in body
        if len(r) >= len(head)
    )


def _body_lines(body_md: str) -> list[str]:
    """Строки тела без картинок (подпись фото — одной строкой)."""
    out = []
    for line in body_md.replace("\r\n", "\n").split("\n"):
        if m := re.match(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$", line.strip()):
            alt = m.group(1).strip()
            if alt:
                out.append(f"📷 {alt}")
            continue
        out.append(line)
    return out


def _paragraphs(lines: list[str]) -> list[str]:
    paras, buf = [], []
    for line in lines:
        if not line.strip():
            if buf:
                paras.append("\n".join(buf).strip())
                buf = []
            continue
        if line.lstrip().startswith("|") and buf and buf[-1].lstrip().startswith("|"):
            buf.append(line)
            continue
        if buf and buf[-1].lstrip().startswith("|") and not line.lstrip().startswith("|"):
            paras.append("\n".join(buf).strip())
            buf = [line]
            continue
        buf.append(line)
    if buf:
        paras.append("\n".join(buf).strip())
    return [p for p in paras if p]


def _para_to_tg(para: str) -> str:
    if para.lstrip().startswith("|"):
        return _md_inline_tg(_table_to_lines(para.split("\n")))
    if m := re.match(r"^(#{2,4})\s+(.*)", para):
        return f"<b>{_md_inline_tg(m.group(2))}</b>"
    if para.startswith(">"):
        q = "\n".join(ln.lstrip("> ").strip() for ln in para.split("\n"))
        return f"<i>{_md_inline_tg(q)}</i>"
    if re.match(r"^[-*]\s+", para) or (
        "\n" in para and all(re.match(r"^[-*]\s+", ln) for ln in para.split("\n"))
    ):
        items = re.findall(r"(?m)^[-*]\s+(.*)", para)
        return "\n".join(f"• {_md_inline_tg(t)}" for t in items)
    if re.match(r"^\d+[.)]\s+", para):
        items = re.findall(r"(?m)^\d+[.)]\s+(.*)", para)
        return "\n".join(f"{n + 1}. {_md_inline_tg(t)}" for n, t in enumerate(items))
    return _md_inline_tg(para.replace("\n", " "))


def _para_to_vk(para: str) -> str:
    if para.lstrip().startswith("|"):
        return _table_to_lines(para.split("\n"))
    if m := re.match(r"^(#{2,4})\s+(.*)", para):
        return _md_inline_vk(m.group(2))
    if para.startswith(">"):
        q = "\n".join(ln.lstrip("> ").strip() for ln in para.split("\n"))
        return f"💡 {_md_inline_vk(q)}"
    if re.match(r"^[-*]\s+", para) or (
        "\n" in para and all(re.match(r"^[-*]\s+", ln) for ln in para.split("\n"))
    ):
        items = re.findall(r"(?m)^[-*]\s+(.*)", para)
        return "\n".join(f"— {_md_inline_vk(t)}" for t in items)
    if re.match(r"^\d+[.)]\s+", para):
        items = re.findall(r"(?m)^\d+[.)]\s+(.*)", para)
        return "\n".join(f"{n + 1}. {_md_inline_vk(t)}" for n, t in enumerate(items))
    return _md_inline_vk(para.replace("\n", " "))


def _fit_plain(text: str, limit: int, suffix: str) -> str:
    if len(text) <= limit:
        return text
    room = limit - len(suffix)
    if room < 200:
        return text[:limit]
    cut = text[:room].rfind("\n\n")
    if cut < room // 2:
        cut = text[:room].rfind("\n")
    if cut < room // 2:
        cut = room
    return text[:cut].rstrip() + suffix


def _fit_tg(html_text: str, limit: int, suffix_html: str) -> str:
    if len(html_text) <= limit:
        return html_text
    plain = re.sub(r"<[^>]+>", "", html_text)
    suffix_plain = re.sub(r"<[^>]+>", "", suffix_html)
    fitted = _fit_plain(plain, limit - len(suffix_html) - 20, "\n\n…")
    return f"<b>{html.escape(fitted.split(chr(10))[0][:120])}</b>\n\n" + suffix_html


def build_single_from_post(slug: str, ann: dict, link: str) -> tuple[str, str, str]:
    """Один HTML для TG, один текст для VK, URL обложки."""
    post = parse_post(POSTS_DIR / f"{slug}.md")
    title = post["title"]
    cover = abs_url(post["image"])
    tags = " ".join(ann.get("hashtags", []))
    suffix_vk = f"\n\nЧитать полностью: {link}"
    if tags:
        suffix_vk += f"\n\n{tags}"
    suffix_tg = f'\n\n<a href="{html.escape(link, quote=True)}">Читать полностью →</a>'

    paras = _paragraphs(_body_lines(post["body_md"]))
    tg_parts = [f"<b>{html.escape(title)}</b>"]
    vk_parts = [title, ""]

    for para in paras:
        tg = _para_to_tg(para)
        vk = _para_to_vk(para)
        if tg:
            tg_parts.append(tg)
        if vk:
            vk_parts.append(vk)

    tg_body = "\n\n".join(tg_parts)
    vk_body = "\n\n".join(vk_parts)

    while len("\n\n".join(tg_parts) + suffix_tg) > TG_LIMIT and len(tg_parts) > 2:
        tg_parts.pop(-1)
    while len("\n\n".join(vk_parts) + suffix_vk) > VK_LIMIT and len(vk_parts) > 2:
        vk_parts.pop(-1)
    tg_body = "\n\n".join(tg_parts)
    vk_body = "\n\n".join(vk_parts)
    tg_full = tg_body + suffix_tg
    vk_full = vk_body + suffix_vk

    if len(tg_full) > TG_LIMIT:
        tg_full = _fit_tg(tg_body, TG_LIMIT, suffix_tg)
    if len(vk_full) > VK_LIMIT:
        vk_full = _fit_plain(vk_body, VK_LIMIT, suffix_vk)

    return tg_full, vk_full, cover


def effective_format(ann: dict) -> str:
    f = ann.get("format", "").strip().lower()
    if f in ("teaser", "single"):
        return f
    if f == "full":
        return "single"
    if ann.get("telegram", "").strip() and ann.get("vk", "").strip():
        return "teaser"
    return "single"


def publish_telegram_single(tg_html: str, link: str):
    token, chan = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHANNEL_ID")
    if not (token and chan):
        return "skip"
    if DRY:
        print("[TG]", len(tg_html), "chars")
        return "dry"
    data = urllib.parse.urlencode({
        "chat_id": chan,
        "text": tg_html,
        "parse_mode": "HTML",
        "link_preview_options": json.dumps({"url": link, "prefer_large_media": True}),
    }).encode()
    http(f"https://api.telegram.org/bot{token}/sendMessage", data)
    return "ok"


def publish_telegram_teaser(text, link):
    token, chan = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHANNEL_ID")
    if not (token and chan):
        return "skip"
    body = f"{text}\n\n" + f'<a href="{link}">Читать статью полностью →</a>'
    if len(body) > TG_LIMIT:
        body = _fit_tg(text, TG_LIMIT, f'\n\n<a href="{html.escape(link, quote=True)}">Читать полностью →</a>')
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


def publish_vk_single(vk_text: str, cover_url: str, link: str):
    token, gid = os.environ.get("VK_GROUP_TOKEN"), os.environ.get("VK_GROUP_ID")
    if not (token and gid):
        return "skip"
    gid = gid.lstrip("-")
    if DRY:
        print("[VK]", len(vk_text), "chars")
        return "dry"
    attachments = []
    if cover_url:
        try:
            attachments.append(_vk_upload_wall_photo(token, gid, cover_url))
        except Exception as e:
            print(f"VK: обложка не загрузилась ({e})", file=sys.stderr)
    attachments.append(link)
    base = {"owner_id": f"-{gid}", "from_group": 1, "message": vk_text[:VK_LIMIT]}
    att = ",".join(attachments) if attachments else link
    try:
        _vk_api("wall.post", dict(base, attachments=att), token)
    except RuntimeError:
        _vk_api("wall.post", base, token)
    return "ok"


def publish_vk_teaser(text, link):
    token, gid = os.environ.get("VK_GROUP_TOKEN"), os.environ.get("VK_GROUP_ID")
    if not (token and gid):
        return "skip"
    gid = gid.lstrip("-")
    msg = f"{text}" + chr(10) * 2 + f"Читать полностью: {link}"
    if len(msg) > VK_LIMIT:
        msg = _fit_plain(text, VK_LIMIT, f"\n\nЧитать полностью: {link}")
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


def sync_legacy_version(ann: dict, done: dict) -> bool:
    """Старые посты уже в ТГ/ВК, но без social_version — только синхронизация, без повторной отправки."""
    want = _want_social_version(ann)
    have = _posted_social_version(done)
    if (
        done.get("telegram") == "ok"
        and done.get("vk") == "ok"
        and have < want
        and have == 0
        and want == 1
    ):
        done["social_version"] = want
        return True
    return False


def needs_social_publish(ann: dict, done: dict) -> bool:
    want = _want_social_version(ann)
    have = _posted_social_version(done)
    if done.get("telegram") != "ok" or done.get("vk") != "ok":
        return True
    if want > have and have > 0:
        return True
    if want > have and have == 0:
        return False
    return False


def main():
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    changed, failed = False, False
    only_slug = os.environ.get("REPUBLISH_SLUG", "").strip()
    force = os.environ.get("FORCE_REPOST") == "1"

    for f in sorted(ANN_DIR.glob("*.json")):
        slug = f.stem
        if slug == "posted":
            continue
        if only_slug and slug != only_slug:
            continue
        done = posted.setdefault(slug, {})
        ann = json.loads(f.read_text(encoding="utf-8"))
        link = f"{SITE}/blog/{slug}/"

        if sync_legacy_version(ann, done):
            changed = True
            print(f"{slug}: синхронизация social_version (без повторной отправки)")
            continue

        if not force and not needs_social_publish(ann, done):
            continue

        want, have = _want_social_version(ann), _posted_social_version(done)
        if force or (want > have and have > 0):
            done.pop("telegram", None)
            done.pop("vk", None)

        if not wait_live(link):
            print(f"{slug}: статья не открылась за отведённое время, пропуск", file=sys.stderr)
            failed = True
            continue

        fmt = effective_format(ann)
        for name in ("telegram", "vk"):
            try:
                if fmt == "teaser":
                    text = ann.get(name, "").strip()
                    if name == "vk":
                        tags = " ".join(ann.get("hashtags", []))
                        if tags:
                            text += f"\n\n{tags}"
                    if not text:
                        continue
                    status = (
                        publish_telegram_teaser(text, link)
                        if name == "telegram"
                        else publish_vk_teaser(text, link)
                    )
                else:
                    tg_html, vk_text, cover = build_single_from_post(slug, ann, link)
                    status = (
                        publish_telegram_single(tg_html, link)
                        if name == "telegram"
                        else publish_vk_single(vk_text, cover, link)
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
        POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
