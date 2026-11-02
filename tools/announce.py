#!/usr/bin/env python3
"""Публикует статьи блога в Telegram-канал и сообщество VK.

Один пост на площадку: текст из `_blog/posts/<slug>.md`, при необходимости сжимается
под лимит. Полная версия — только на сайте. Настройки: `_blog/announce/<slug>.json`.

Секреты: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, VK_GROUP_TOKEN, VK_GROUP_ID.
Опционально VK_USER_TOKEN — личный ключ админа (scope: photos, wall, groups) для загрузки
обложки; ключ сообщества часто не даёт photos.getWallUploadServer (ошибка 27).
DRY_RUN=1 — без отправки.
VK_ADD_PHOTO=1 + REPUBLISH_SLUG — обложка к записи через wall.edit (нужны VK_USER_TOKEN и VK_POST_ID).
При повторной публикации (social_version выше) скрипт редактирует посты по
telegram_message_id и vk_post_id из posted.json, без новых записей.
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
        body = r.read()
        ctype = r.headers.get("Content-Type", "")
        return r.status, body, ctype


def http_status(url, data=None, timeout=60, headers=None):
    status, _body, _ctype = http(url, data, timeout, headers)
    return status


def wait_live(url, minutes=12):
    if DRY:
        return True
    for _ in range(minutes * 4):
        try:
            if http_status(url, timeout=10) == 200:
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
        return "skip", None
    if DRY:
        print("[TG]", len(tg_html), "chars")
        return "dry", None
    data = urllib.parse.urlencode({
        "chat_id": chan,
        "text": tg_html,
        "parse_mode": "HTML",
        "link_preview_options": json.dumps({"url": link, "prefer_large_media": True}),
    }).encode()
    status, body, _ctype = http(f"https://api.telegram.org/bot{token}/sendMessage", data)
    res = json.loads(body)
    if not res.get("ok"):
        raise RuntimeError(f"Telegram sendMessage: {res}")
    return "ok", res["result"]["message_id"]


def edit_telegram_single(message_id: int, tg_html: str, link: str):
    token, chan = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHANNEL_ID")
    if not (token and chan):
        return "skip"
    if DRY:
        print(f"[TG edit] msg_id={message_id}", len(tg_html), "chars")
        return "dry"
    data = urllib.parse.urlencode({
        "chat_id": chan,
        "message_id": int(message_id),
        "text": tg_html,
        "parse_mode": "HTML",
        "link_preview_options": json.dumps({"url": link, "prefer_large_media": True}),
    }).encode()
    status, body, _ctype = http(f"https://api.telegram.org/bot{token}/editMessageText", data)
    res = json.loads(body)
    if not res.get("ok"):
        raise RuntimeError(f"Telegram editMessageText: {res}")
    return "ok"


def publish_telegram_teaser(text, link):
    token, chan = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHANNEL_ID")
    if not (token and chan):
        return "skip", None
    body = f"{text}\n\n" + f'<a href="{link}">Читать статью полностью →</a>'
    if len(body) > TG_LIMIT:
        body = _fit_tg(text, TG_LIMIT, f'\n\n<a href="{html.escape(link, quote=True)}">Читать полностью →</a>')
    if DRY:
        print("[TG teaser]", body[:200], "…")
        return "dry", None
    data = urllib.parse.urlencode({
        "chat_id": chan, "text": body, "parse_mode": "HTML",
        "link_preview_options": json.dumps({"url": link, "prefer_large_media": True}),
    }).encode()
    status, raw, _ctype = http(f"https://api.telegram.org/bot{token}/sendMessage", data)
    res = json.loads(raw)
    if not res.get("ok"):
        raise RuntimeError(f"Telegram sendMessage: {res}")
    return "ok", res["result"]["message_id"]


def edit_telegram_teaser(message_id: int, text, link):
    token, chan = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHANNEL_ID")
    if not (token and chan):
        return "skip"
    body = f"{text}\n\n" + f'<a href="{link}">Читать статью полностью →</a>'
    if len(body) > TG_LIMIT:
        body = _fit_tg(text, TG_LIMIT, f'\n\n<a href="{html.escape(link, quote=True)}">Читать полностью →</a>')
    if DRY:
        print(f"[TG teaser edit] msg_id={message_id}")
        return "dry"
    data = urllib.parse.urlencode({
        "chat_id": chan,
        "message_id": int(message_id),
        "text": body,
        "parse_mode": "HTML",
        "link_preview_options": json.dumps({"url": link, "prefer_large_media": True}),
    }).encode()
    status, raw, _ctype = http(f"https://api.telegram.org/bot{token}/editMessageText", data)
    res = json.loads(raw)
    if not res.get("ok"):
        raise RuntimeError(f"Telegram editMessageText: {res}")
    return "ok"


def _vk_api(method, params, token):
    params = dict(params, access_token=token, v="5.199")
    _status, raw, _ctype = http(
        f"https://api.vk.com/method/{method}",
        urllib.parse.urlencode(params).encode(),
    )
    res = json.loads(raw)
    if "error" in res:
        err = res["error"]
        raise RuntimeError(f"VK {method}: {err.get('error_msg')} ({err.get('error_code')})")
    return res["response"]


def _vk_group_ids():
    token, gid = os.environ.get("VK_GROUP_TOKEN"), os.environ.get("VK_GROUP_ID")
    if not (token and gid):
        return None, None
    return token, gid.lstrip("-")


def _vk_photo_api_token():
    """Загрузка фото на стену сообщества — через ключ админа или ключ сообщества с правом «Фото»."""
    user = os.environ.get("VK_USER_TOKEN", "").strip()
    if user:
        return user
    token, _gid = _vk_group_ids()
    return token


def _vk_edit_api_token():
    user = os.environ.get("VK_USER_TOKEN", "").strip()
    if user:
        return user
    token, _gid = _vk_group_ids()
    return token


def _image_part(image_url: str) -> tuple[bytes, str, str]:
    if not wait_live(image_url, minutes=3):
        raise RuntimeError(f"обложка недоступна: {image_url}")
    _status, img, ctype = http(image_url, timeout=90)
    if len(img) < 256:
        raise RuntimeError(f"обложка слишком мала или пустая: {image_url}")
    if img[:3] == b"\xff\xd8\xff":
        mime, ext = "image/jpeg", "jpg"
    elif img[:4] == b"\x89PNG":
        mime, ext = "image/png", "png"
    elif "png" in ctype.lower():
        mime, ext = "image/png", "png"
    else:
        mime, ext = "image/jpeg", "jpg"
    return img, mime, ext


def _vk_upload_wall_photo(token, gid, image_url):
    img, mime, ext = _image_part(image_url)
    photo_token = _vk_photo_api_token()
    if not photo_token:
        raise RuntimeError("нет VK_GROUP_TOKEN / VK_USER_TOKEN для загрузки фото")
    up = _vk_api("photos.getWallUploadServer", {"group_id": gid}, photo_token)
    upload_url = up["upload_url"]
    boundary = "----vimboundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="photo"; filename="cover.{ext}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + img + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        upload_url,
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "vim-blog-announce/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        saved = json.loads(r.read().decode())
    for key in ("photo", "server", "hash"):
        if key not in saved:
            raise RuntimeError(f"VK upload: нет поля {key!r} в ответе сервера")
    resp = _vk_api("photos.saveWallPhoto", {
        "group_id": gid,
        "photo": saved["photo"],
        "server": saved["server"],
        "hash": saved["hash"],
    }, photo_token)
    p = resp[0]
    return f"photo{p['owner_id']}_{p['id']}"


def _vk_wall_post_id(response):
    if isinstance(response, int):
        return response
    if isinstance(response, dict):
        return response.get("post_id")
    return None


def _vk_post_wall(token, gid, message: str, cover_url: str, link: str, require_photo: bool = True):
    """Один успешный wall.post; без второго поста «только текст» при ошибке вложений."""
    owner = f"-{gid}"
    base = {"owner_id": owner, "from_group": 1, "message": message[:VK_LIMIT]}
    photo_att = None
    if cover_url:
        photo_att = _vk_upload_wall_photo(token, gid, cover_url)
    # Ссылка во вложениях без фото у VK часто отклоняется (link_photo_sizing_rule).
    att_variants = []
    if photo_att:
        att_variants.append(f"{photo_att},{link}")
        att_variants.append(photo_att)
    elif not require_photo:
        att_variants.append(link)
    last_err = None
    for att in att_variants:
        try:
            resp = _vk_api("wall.post", dict(base, attachments=att), token)
            post_id = _vk_wall_post_id(resp)
            if post_id is None:
                raise RuntimeError(f"VK wall.post: неожиданный ответ {resp!r}")
            return post_id
        except RuntimeError as e:
            last_err = e
    if require_photo and not photo_att:
        raise RuntimeError(f"VK: не удалось загрузить обложку ({cover_url})") from last_err
    raise last_err or RuntimeError("VK wall.post failed")



def vk_add_cover_to_existing_post(slug: str, link: str, cover_url: str) -> str:
    """Добавляет обложку к записи на стене (wall.edit), без нового wall.post."""
    _group_token, gid = _vk_group_ids()
    edit_token = _vk_edit_api_token()
    if not (edit_token and gid):
        return "skip"
    owner = f"-{gid}"
    post_id_raw = os.environ.get("VK_POST_ID", "").strip()
    if not post_id_raw:
        raise RuntimeError(
            "VK_POST_ID не задан: откройте запись на стене, id в адресе wall-242240569_<число>"
        )
    post_id = int(post_id_raw)
    if DRY:
        print(f"[VK patch] {slug} post_id={post_id} cover={cover_url}")
        return "dry"
    photo_att = _vk_upload_wall_photo(_group_token or edit_token, gid, cover_url)
    _vk_api(
        "wall.edit",
        {
            "owner_id": owner,
            "post_id": post_id,
            "attachments": f"{photo_att},{link}",
        },
        edit_token,
    )
    print(f"{slug}: обложка добавлена к записи id={post_id}")
    return "ok"


def vk_edit_wall_post(post_id: int, message: str, cover_url: str, link: str) -> str:
    """Обновляет текст и вложения существующей записи (без wall.post)."""
    _group_token, gid = _vk_group_ids()
    edit_token = _vk_edit_api_token()
    if not (edit_token and gid):
        return "skip"
    owner = f"-{gid}"
    params = {
        "owner_id": owner,
        "post_id": int(post_id),
        "message": message[:VK_LIMIT],
    }
    if cover_url:
        photo_att = _vk_upload_wall_photo(_group_token or edit_token, gid, cover_url)
        params["attachments"] = f"{photo_att},{link}"
    else:
        params["attachments"] = link
    if DRY:
        print(f"[VK edit] post_id={post_id} cover={cover_url}")
        return "dry"
    _vk_api("wall.edit", params, edit_token)
    return "ok"


def publish_vk_single(vk_text: str, cover_url: str, link: str):
    token, gid = _vk_group_ids()
    if not (token and gid):
        return "skip", None
    if DRY:
        print(f"[VK] {len(vk_text)} chars cover={cover_url}")
        return "dry", None
    post_id = _vk_post_wall(token, gid, vk_text, cover_url, link, require_photo=True)
    return "ok", post_id


def publish_vk_teaser(text, link, cover_url: str = ""):
    token, gid = _vk_group_ids()
    if not (token and gid):
        return "skip", None
    msg = f"{text}" + chr(10) * 2 + f"Читать полностью: {link}"
    if len(msg) > VK_LIMIT:
        msg = _fit_plain(text, VK_LIMIT, f"\n\nЧитать полностью: {link}")
    if DRY:
        print("[VK teaser]", msg[:200], "…")
        return "dry", None
    if cover_url:
        post_id = _vk_post_wall(token, gid, msg, cover_url, link, require_photo=False)
    else:
        resp = _vk_api(
            "wall.post",
            {"owner_id": f"-{gid}", "from_group": 1, "message": msg, "attachments": link},
            token,
        )
        post_id = _vk_wall_post_id(resp)
    return "ok", post_id


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


def cover_for_slug(slug: str) -> str:
    return abs_url(parse_post(POSTS_DIR / f"{slug}.md")["image"])


def main():
    posted = json.loads(POSTED.read_text(encoding="utf-8")) if POSTED.exists() else {}
    changed, failed = False, False
    only_slug = os.environ.get("REPUBLISH_SLUG", "").strip()
    force = os.environ.get("FORCE_REPOST") == "1"
    vk_patch = os.environ.get("VK_ADD_PHOTO") == "1"

    if vk_patch:
        if not only_slug:
            print("VK_ADD_PHOTO=1 требует REPUBLISH_SLUG=<slug>", file=sys.stderr)
            return 1
        link = f"{SITE}/blog/{only_slug}/"
        try:
            status = vk_add_cover_to_existing_post(only_slug, link, cover_for_slug(only_slug))
            print(f"{only_slug}/vk-patch: {status}")
        except Exception as e:
            print(f"{only_slug}/vk-patch: ОШИБКА {e}", file=sys.stderr)
            return 1
        return 0

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
        is_republish = force or (want > have and have > 0)
        tg_edit_id = done.get("telegram_message_id")
        vk_edit_id = done.get("vk_post_id")
        can_edit_tg = is_republish and tg_edit_id
        can_edit_vk = is_republish and vk_edit_id

        if is_republish and not (can_edit_tg or can_edit_vk):
            done.pop("telegram", None)
            done.pop("vk", None)
            print(
                f"{slug}: нет telegram_message_id / vk_post_id в posted.json — "
                "будет новый пост (старый вручную удалите или оставьте)",
                file=sys.stderr,
            )

        if not wait_live(link):
            print(f"{slug}: статья не открылась за отведённое время, пропуск", file=sys.stderr)
            failed = True
            continue

        fmt = effective_format(ann)
        tg_html, vk_text, cover = None, None, None
        if fmt != "teaser":
            tg_html, vk_text, cover = build_single_from_post(slug, ann, link)
        else:
            cover = cover_for_slug(slug)

        for name in ("telegram", "vk"):
            vk_post_id = None
            try:
                if fmt == "teaser":
                    text = ann.get(name, "").strip()
                    if name == "vk":
                        tags = " ".join(ann.get("hashtags", []))
                        if tags:
                            text += f"\n\n{tags}"
                    if not text:
                        continue
                    if name == "telegram":
                        if can_edit_tg:
                            status = edit_telegram_teaser(int(tg_edit_id), ann.get("telegram", "").strip(), link)
                        else:
                            status, tg_msg_id = publish_telegram_teaser(text, link)
                            if status == "ok" and tg_msg_id:
                                done["telegram_message_id"] = tg_msg_id
                    else:
                        vk_msg = f"{text}\n\nЧитать полностью: {link}"
                        if len(vk_msg) > VK_LIMIT:
                            vk_msg = _fit_plain(text, VK_LIMIT, f"\n\nЧитать полностью: {link}")
                        if can_edit_vk:
                            status = vk_edit_wall_post(int(vk_edit_id), vk_msg, cover, link)
                            vk_post_id = int(vk_edit_id)
                        else:
                            status, vk_post_id = publish_vk_teaser(ann.get("vk", "").strip(), link, cover)
                elif name == "telegram":
                    if can_edit_tg:
                        status = edit_telegram_single(int(tg_edit_id), tg_html, link)
                    else:
                        status, tg_msg_id = publish_telegram_single(tg_html, link)
                        if status == "ok" and tg_msg_id:
                            done["telegram_message_id"] = tg_msg_id
                else:
                    if can_edit_vk:
                        status = vk_edit_wall_post(int(vk_edit_id), vk_text, cover, link)
                        vk_post_id = int(vk_edit_id)
                    else:
                        status, vk_post_id = publish_vk_single(vk_text, cover, link)
            except Exception as e:
                print(f"{slug}/{name}: ОШИБКА {e}", file=sys.stderr)
                failed = True
                continue
            if status == "ok":
                done[name] = "ok"
                if name == "vk" and vk_post_id:
                    done["vk_post_id"] = vk_post_id
                changed = True
            action = "edit" if (name == "telegram" and can_edit_tg) or (name == "vk" and can_edit_vk) else "post"
            print(f"{slug}/{name}: {status} ({action})")

        if done.get("telegram") == "ok" and done.get("vk") == "ok":
            done["social_version"] = _want_social_version(ann)

    if changed and not DRY:
        POSTED.write_text(json.dumps(posted, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
