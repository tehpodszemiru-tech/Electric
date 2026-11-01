#!/usr/bin/env python3
"""Локальная панель блога ВИМ-ИНЖЕНЕРКА.

Запуск из корня репозитория Electric:
    pip install -r tools/blog_dashboard/requirements.txt
    python tools/blog_dashboard/server.py

Откроется http://127.0.0.1:8765
"""
from __future__ import annotations

import re
import shutil
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import blog_ops as ops  # noqa: E402
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

APP = FastAPI(title="Блог ВИМ-ИНЖЕНЕРКА — панель")
STATIC = Path(__file__).resolve().parent / "static"
PHOTOS = ops.repo_root() / "assets" / "photos"


@APP.get("/api/status")
def api_status():
    return {
        **ops.pipeline_summary(),
        "open_prs": ops.fetch_open_prs(),
        "agents": {
            "author": "Cursor Automation (cloud, по понедельникам + Run now)",
            "claude_routine": "claude.ai/code/routines — отключить, если нет подписки",
            "links": {
                "automations": "https://cursor.com/automations",
                "cloud_agents": "https://cursor.com/dashboard/cloud-agents",
                "github_prs": f"https://github.com/{ops.GITHUB_REPO}/pulls",
                "github_actions": f"https://github.com/{ops.GITHUB_REPO}/actions",
                "blog": "https://electric.vim-scrum.ru/blog/",
            },
        },
    }


@APP.get("/api/topics")
def api_topics():
    return ops.parse_topics()


@APP.get("/api/photos")
def api_photos():
    rows = {r["file"]: r for r in ops.parse_persona_rows()}
    disk = ops.list_disk_photos()
    used = set(ops.cover_stats()["used_covers"])
    items = []
    for name in disk:
        meta = rows.get(name)
        in_persona = name in rows or any(
            name in re.findall(r"`([^`]+)`", r["file"]) for r in ops.parse_persona_rows()
        )
        items.append(
            {
                "file": name,
                "url": f"/assets/photos/{name}",
                "in_persona": in_persona,
                "persona": meta,
                "used_as_cover": name in used,
            }
        )
    return {"photos": items, "stats": ops.cover_stats(), "persona_rows": ops.parse_persona_rows()}


@APP.post("/api/photos/upload")
async def api_upload_photo(
    file: UploadFile = File(...),
    description: str = Form(...),
    cover_ok: str = Form("true"),
    focus: str = Form(""),
    filename: str = Form(""),
):
    if not description.strip():
        raise HTTPException(400, "Укажите описание для PERSONA.md")
    name = ops.sanitize_filename(filename or file.filename or "photo.jpg")
    if not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        name += ".jpg"
    dest = PHOTOS / name
    PHOTOS.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    focus_val = focus.strip() or None
    if name in {r["file"] for r in ops.parse_persona_rows()}:
        raise HTTPException(409, f"{name} уже есть в PERSONA.md — измените имя или отредактируйте файл вручную")
    cover_bool = cover_ok.lower() in ("true", "1", "on", "yes")
    ops.append_persona_row(name, description.strip(), cover_bool, focus_val)
    return {"ok": True, "file": name, "path": str(dest.relative_to(ops.repo_root()))}


@APP.get("/api/facts")
def api_facts():
    return ops.read_facts()


@APP.put("/api/facts/cases")
def api_facts_cases(body: dict):
    ops.save_facts_cases(body.get("text", ""))
    return {"ok": True}


@APP.put("/api/facts/prices")
def api_facts_prices(body: dict):
    ops.save_facts_prices(body.get("text", ""))
    return {"ok": True}


@APP.get("/api/articles")
def api_articles():
    items = []
    for p in sorted(ops.list_posts(), key=lambda x: x.get("date") or "", reverse=True):
        slug = p["slug"]
        ann = ops.read_announce(slug) if ops.announce_path(slug).is_file() else {}
        posted = ops.read_posted(slug)
        items.append(
            {
                **p,
                "social_version": int(ann.get("social_version", 1)),
                "posted_version": int(posted.get("social_version", 0)),
                "telegram_ok": posted.get("telegram") == "ok",
                "vk_ok": posted.get("vk") == "ok",
                "site_url": f"https://electric.vim-scrum.ru/blog/{slug}/",
            }
        )
    return {"articles": items}


@APP.get("/api/articles/{slug}")
def api_article_get(slug: str):
    try:
        return ops.article_detail(slug)
    except FileNotFoundError:
        raise HTTPException(404, "Статья не найдена")


@APP.put("/api/articles/{slug}")
def api_article_put(slug: str, body: dict):
    raw = body.get("raw", "")
    if not raw:
        raise HTTPException(400, "Пустой текст")
    try:
        ops.save_post_raw(slug, raw)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, "word_count": ops.count_words_md(raw)}


@APP.post("/api/articles/{slug}/release")
def api_article_release(slug: str, body: dict):
    raw = body.get("raw")
    if raw:
        try:
            ops.save_post_raw(slug, raw)
        except ValueError as e:
            raise HTTPException(400, str(e))
    republish = bool(body.get("republish_social"))
    msg = (body.get("commit_message") or "").strip() or None
    try:
        result = ops.git_publish_article(slug, republish_social=republish, commit_message=msg)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return result


@APP.get("/assets/photos/{name}")
def serve_photo(name: str):
    path = PHOTOS / Path(name).name
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


APP.mount("/", StaticFiles(directory=STATIC, html=True), name="static")


def main():
    import uvicorn

    url = "http://127.0.0.1:8765"
    print(f"Репозиторий: {ops.repo_root()}")
    print(f"Панель: {url}")
    webbrowser.open(url)
    uvicorn.run(APP, host="127.0.0.1", port=8765, log_level="info")


if __name__ == "__main__":
    main()
