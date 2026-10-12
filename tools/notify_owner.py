#!/usr/bin/env python3
"""Уведомления владельцу блога в личный Telegram.

Режимы (переменная MODE):
  pr_opened  — агент открыл PR со статьёй: «статья ждёт проверки»
  health     — плановая проверка: кончается контент-план, кончаются фото для обложек,
               PR висит без слияния, блог давно без публикаций

Секреты берутся из окружения (GitHub Actions): TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_CHAT_ID,
GITHUB_TOKEN, GITHUB_REPOSITORY. DRY_RUN=1 печатает вместо отправки.
Тексты уведомлений не содержат секретов и персональных данных.
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DRY = os.environ.get("DRY_RUN") == "1"
MIN_QUEUED = 4         # меньше тем в очереди: предупреждаем
MIN_FREE_COVERS = 3    # меньше свободных фото для обложек: предупреждаем
PR_STALE_DAYS = 3      # PR без слияния дольше: напоминаем
SILENCE_DAYS = 10      # блог без новых статей дольше: предупреждаем


def send(text: str):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if DRY or not (token and chat):
        print("[TG ВЛАДЕЛЬЦУ]", text, "" if (token and chat) else "(нет секретов, не отправлено)")
        return
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
    urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data), timeout=20)


def frontmatter(path: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---", path.read_text(encoding="utf-8").replace("\r\n", "\n"), re.S)
    d = {}
    for ln in (m.group(1).split("\n") if m else []):
        if ":" in ln:
            k, v = ln.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def posts():
    return [frontmatter(p) | {"slug": p.stem} for p in sorted((ROOT / "_blog" / "posts").glob("*.md"))]


def queued_topics() -> int:
    t = (ROOT / "_blog" / "agent" / "TOPICS.md").read_text(encoding="utf-8")
    return len(re.findall(r"^- \[queued\]", t, re.M))


def free_covers() -> int:
    persona = (ROOT / "_blog" / "agent" / "PERSONA.md").read_text(encoding="utf-8")
    suitable = set()
    for ln in persona.split("\n"):
        m = re.match(r"^\|\s*`([^`]+\.(?:jpg|png))`\s*\|.*\|\s*(да[^|]*)\|\s*$", ln)
        if m:
            suitable.add(m.group(1))
    used = {p.get("cover") for p in posts() if p.get("cover")}
    return len(suitable - used)


def open_blog_prs():
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not (token and repo):
        return []
    req = urllib.request.Request(f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=30",
                                 headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return [p for p in json.loads(r.read()) if p["head"]["ref"].startswith("blog/")]


def mode_pr_opened():
    title, url = os.environ.get("PR_TITLE", "Новая статья"), os.environ.get("PR_URL", "")
    send(f"Новая статья ждёт вашей проверки.\n\n{title}\n\nОткройте PR, проверьте раздел «Что проверить мастеру» и нажмите Merge, "
         f"чтобы опубликовать. После этого анонс сам уйдёт в Telegram и VK.\n{url}")


def mode_health():
    problems = []
    q = queued_topics()
    if q < MIN_QUEUED:
        problems.append(f"Контент-план: в очереди осталось тем: {q}. Агент пополняет его сам в первый понедельник месяца, "
                        f"но можно запустить рутину вручную или добавить темы в _blog/agent/TOPICS.md.")
    fc = free_covers()
    if fc < MIN_FREE_COVERS:
        problems.append(f"Фото: свободных кадров для обложек осталось: {fc}. Добавьте новые фото объектов в assets/photos "
                        f"и опишите их в _blog/agent/PERSONA.md (таблица фото).")
    now = datetime.now(timezone.utc)
    for pr in open_blog_prs():
        created = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
        days = (now - created).days
        if days >= PR_STALE_DAYS:
            problems.append(f"Статья «{pr['title']}» ждёт проверки уже {days} дн.: {pr['html_url']}")
    ps = [p for p in posts() if not p.get("draft") == "true" and p.get("date")]
    if ps:
        last = max(datetime.strptime(p["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc) for p in ps)
        gap = (now - last).days
        if gap >= SILENCE_DAYS and not open_blog_prs():
            problems.append(f"Блог без новых статей уже {gap} дн. Проверьте, запускалась ли рутина (claude.ai/code/routines).")
    if problems:
        send("Блог ВИМ-ИНЖЕНЕРКА: что требует внимания\n\n" + "\n\n".join(f"• {p}" for p in problems))
    else:
        print("Всё в порядке, уведомлений нет.")
    print(f"queued={q}, free_covers={fc}")


if __name__ == "__main__":
    {"pr_opened": mode_pr_opened, "health": mode_health}[os.environ.get("MODE", "health")]()
