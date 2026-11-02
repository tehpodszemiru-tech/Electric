"""Чтение и правка данных блога в локальном репозитории Electric."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "tehpodszemiru-tech/Electric")
MIN_QUEUED = 4
MIN_FREE_COVERS = 3

PERSONA_ROW = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$"
)
PERSONA_SUITABLE = re.compile(
    r"^\|\s*`([^`]+\.(?:jpg|png))`\s*\|.*\|\s*(да[^|]*)\|\s*$", re.I
)


def repo_root() -> Path:
    env = os.environ.get("BLOG_REPO_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _write(path: Path, text: str) -> None:
    path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def frontmatter(path: Path) -> dict:
    m = re.match(r"^---\n(.*?)\n---", _read(path), re.S)
    d: dict = {}
    if not m:
        return d
    for ln in m.group(1).split("\n"):
        if ":" in ln:
            k, v = ln.split(":", 1)
            d[k.strip()] = v.strip()
    return d


def list_posts() -> list[dict]:
    root = repo_root()
    posts_dir = root / "_blog" / "posts"
    out = []
    for p in sorted(posts_dir.glob("*.md")):
        fm = frontmatter(p)
        out.append(
            {
                "slug": p.stem,
                "title": fm.get("title", p.stem),
                "date": fm.get("date", ""),
                "cover": fm.get("cover", ""),
                "draft": fm.get("draft") == "true",
                "category": fm.get("category", ""),
            }
        )
    return out


def parse_topics() -> list[dict]:
    text = _read(repo_root() / "_blog" / "agent" / "TOPICS.md")
    items = []
    for ln in text.split("\n"):
        m = re.match(
            r"^- \[(queued|done)\]\s*(.+?)(?:\s—\s/blog/([^/]+)/)?\s*$", ln.strip()
        )
        if not m:
            m2 = re.match(r"^- \[(queued|done)\]\s*(.+)$", ln.strip())
            if m2:
                items.append(
                    {"status": m2.group(1), "title": m2.group(2).strip(), "slug": None}
                )
            continue
        slug = m.group(3)
        title = m.group(2).split(" — ")[0].strip()
        items.append({"status": m.group(1), "title": title, "slug": slug})
    return items


def parse_persona_rows() -> list[dict]:
    text = _read(repo_root() / "_blog" / "agent" / "PERSONA.md")
    rows = []
    for ln in text.split("\n"):
        m = PERSONA_ROW.match(ln)
        if not m or m.group(1) == "Файл":
            continue
        fname = m.group(1).strip()
        if "," in fname and "`" not in fname:
            # plan-2d.jpg`, `3d — combined row
            pass
        rows.append(
            {
                "file": fname,
                "description": m.group(2).strip(),
                "cover": m.group(3).strip(),
            }
        )
    return rows


def list_disk_photos() -> list[str]:
    photos = repo_root() / "assets" / "photos"
    if not photos.is_dir():
        return []
    return sorted(
        p.name
        for p in photos.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )


def cover_stats() -> dict:
    persona = _read(repo_root() / "_blog" / "agent" / "PERSONA.md")
    suitable = set()
    for ln in persona.split("\n"):
        m = PERSONA_SUITABLE.match(ln)
        if m:
            suitable.add(m.group(1))
    used = {p.get("cover") for p in list_posts() if p.get("cover")}
    free = suitable - used
    disk = set(list_disk_photos())
    persona_files = {r["file"].split(",")[0].strip("` ") for r in parse_persona_rows()}
    for r in parse_persona_rows():
        for part in re.findall(r"`([^`]+)`", r["file"]):
            persona_files.add(part)
    orphan_disk = sorted(disk - persona_files)
    missing_disk = sorted(
        f for f in persona_files if f and f not in disk and "," not in f
    )
    return {
        "suitable_count": len(suitable),
        "used_covers": sorted(used),
        "free_cover_count": len(free),
        "free_covers": sorted(free),
        "warn_low_covers": len(free) < MIN_FREE_COVERS,
        "orphan_photos": orphan_disk,
        "missing_files": missing_disk,
    }


def pipeline_summary() -> dict:
    topics = parse_topics()
    queued = [t for t in topics if t["status"] == "queued"]
    done = [t for t in topics if t["status"] == "done"]
    posts = [p for p in list_posts() if not p.get("draft")]
    last_date = ""
    if posts:
        last_date = max(p["date"] for p in posts if p["date"])
    covers = cover_stats()
    return {
        "repo_root": str(repo_root()),
        "github_repo": GITHUB_REPO,
        "queued_count": len(queued),
        "done_count": len(done),
        "next_topic": queued[0] if queued else None,
        "published_count": len(posts),
        "last_publish_date": last_date,
        "warn_low_topics": len(queued) < MIN_QUEUED,
        **covers,
    }


def fetch_open_prs() -> list[dict]:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/pulls?state=open&per_page=20"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode())
    except OSError:
        return []
    out = []
    for pr in data:
        ref = pr.get("head", {}).get("ref", "")
        if not ref.startswith("blog/"):
            continue
        out.append(
            {
                "number": pr["number"],
                "title": pr["title"],
                "url": pr["html_url"],
                "branch": ref,
                "draft": pr.get("draft", False),
                "created_at": pr.get("created_at", ""),
            }
        )
    return out


def _facts_section(text: str, start_heading: str, end_heading: str | None) -> str:
    start = text.find(start_heading)
    if start < 0:
        return ""
    start = text.find("\n", start) + 1
    if end_heading:
        end = text.find(end_heading, start)
        if end < 0:
            end = len(text)
    else:
        end = len(text)
    body = text[start:end].strip()
    # strip placeholder lines
    body = re.sub(r"^\(пока пусто.*\)\s*$", "", body, flags=re.M).strip()
    return body


def read_facts() -> dict:
    path = repo_root() / "_blog" / "agent" / "FACTS.md"
    text = _read(path)
    cases_raw = _facts_section(text, "## Реальные случаи", "## Цены")
    prices_raw = _facts_section(text, "## Цены (если готовы публиковать)", "## «Домовой")
    return {
        "cases": cases_raw,
        "prices": prices_raw,
        "bans": _facts_section(text, "## Запреты и пожелания", None),
        "has_cases": "(пока пусто" not in cases_raw
        and bool(re.sub(r"<!--.*?-->", "", cases_raw, flags=re.S).strip()),
        "has_prices": "(пока пусто" not in prices_raw
        and bool(re.sub(r"<!--.*?-->", "", prices_raw, flags=re.S).strip()),
    }


def save_facts_cases(cases: str) -> None:
    path = repo_root() / "_blog" / "agent" / "FACTS.md"
    text = _read(path)
    new_block = cases.strip() + "\n"
    text = re.sub(
        r"(## Реальные случаи с объектов\n\n)(.*?)(\n## Цены)",
        lambda m: m.group(1) + new_block + m.group(3),
        text,
        count=1,
        flags=re.S,
    )
    _write(path, text)


def save_facts_prices(prices: str) -> None:
    path = repo_root() / "_blog" / "agent" / "FACTS.md"
    text = _read(path)
    new_block = prices.strip() + "\n"
    text = re.sub(
        r"(## Цены \(если готовы публиковать\)\n\n)(.*?)(\n## «Домовой)",
        lambda m: m.group(1) + new_block + m.group(3),
        text,
        count=1,
        flags=re.S,
    )
    _write(path, text)


def _cover_cell(cover_ok: bool, focus: str | None) -> str:
    if not cover_ok:
        return "нет"
    if focus:
        return f"да (focus {focus})"
    return "да"


def append_persona_row(filename: str, description: str, cover_ok: bool, focus: str | None) -> None:
    path = repo_root() / "_blog" / "agent" / "PERSONA.md"
    text = _read(path)
    row = f"| `{filename}` | {description.strip()} | {_cover_cell(cover_ok, focus)} |"
    marker = "| `plan-2d.jpg`, `3d-vizualizatsiya.png`"
    if marker in text:
        text = text.replace(marker, row + "\n" + marker, 1)
    else:
        insert_at = text.find("\n\nЕсли сомневаешься, что видно на снимке")
        if insert_at < 0:
            raise ValueError("Не найдена таблица фото в PERSONA.md")
        text = text[:insert_at] + "\n" + row + text[insert_at:]
    _write(path, text)


def sanitize_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^\w.\-]", "-", base, flags=re.I)
    base = re.sub(r"-+", "-", base).strip("-").lower()
    if not base:
        raise ValueError("Некорректное имя файла")
    return base


def post_path(slug: str) -> Path:
    safe = re.sub(r"[^a-z0-9\-]", "", slug.lower())
    if safe != slug:
        raise ValueError("Некорректный slug")
    return repo_root() / "_blog" / "posts" / f"{safe}.md"


def announce_path(slug: str) -> Path:
    safe = re.sub(r"[^a-z0-9\-]", "", slug.lower())
    return repo_root() / "_blog" / "announce" / f"{safe}.json"


def read_post_raw(slug: str) -> str:
    path = post_path(slug)
    if not path.is_file():
        raise FileNotFoundError(slug)
    return _read(path)


def save_post_raw(slug: str, text: str) -> None:
    if not text.strip().startswith("---"):
        raise ValueError("Нужен frontmatter (--- … ---)")
    _write(post_path(slug), text.strip() + "\n")


def count_words_md(text: str) -> int:
    body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    return len(re.findall(r"\w+", body))


def read_announce(slug: str) -> dict:
    path = announce_path(slug)
    if not path.is_file():
        return {"format": "full", "hashtags": ["#электрика", "#самара"], "social_version": 1}
    return json.loads(path.read_text(encoding="utf-8"))


def write_announce(slug: str, data: dict) -> None:
    announce_path(slug).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def ensure_announce(slug: str) -> dict:
    data = read_announce(slug)
    data.setdefault("format", "full")
    data.setdefault("hashtags", ["#электрика", "#самара"])
    data.setdefault("social_version", 1)
    write_announce(slug, data)
    return data


def bump_social_version(slug: str) -> int:
    data = ensure_announce(slug)
    data["social_version"] = int(data.get("social_version", 1)) + 1
    write_announce(slug, data)
    return data["social_version"]


def read_posted(slug: str) -> dict:
    path = repo_root() / "_blog" / "announce" / "posted.json"
    if not path.is_file():
        return {}
    all_p = json.loads(path.read_text(encoding="utf-8"))
    return all_p.get(slug, {})


def article_detail(slug: str) -> dict:
    raw = read_post_raw(slug)
    fm = frontmatter(post_path(slug))
    ann = ensure_announce(slug)
    posted = read_posted(slug)
    site = f"https://electric.vim-scrum.ru/blog/{slug}/"
    return {
        "slug": slug,
        "title": fm.get("title", slug),
        "date": fm.get("date", ""),
        "category": fm.get("category", ""),
        "cover": fm.get("cover", ""),
        "draft": fm.get("draft") == "true",
        "word_count": count_words_md(raw),
        "raw": raw,
        "announce": ann,
        "posted": posted,
        "site_url": site,
    }


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = ["git", "-C", str(repo_root()), *args]
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def run_build() -> str:
    root = repo_root()
    log: list[str] = []
    for script in ("build_blog.py", "make_covers.py"):
        path = root / "tools" / script
        if script == "make_covers.py" and not path.is_file():
            continue
        r = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        log.append(f"=== {script} ===\n{r.stdout}\n{r.stderr}")
        if r.returncode != 0 and script == "build_blog.py":
            raise RuntimeError("build_blog.py завершился с ошибкой:\n" + r.stderr)
    return "\n".join(log)


def portfolio_category(filename: str) -> str | None:
    f = filename.lower()
    if f.startswith(("proekt-", "plan-2d", "3d-viz")):
        return "proektirovanie"
    if any(k in f for k in ("shchitok", "provodka", "stabilizator", "gkl-karkas", "sip-dom")):
        return "elektrika"
    if any(
        k in f
        for k in (
            "boiler",
            "vodonag",
            "kollektor",
            "teply",
            "razvodka",
            "elektrokamenka",
            "greyushchij",
            "vodoprovod",
        )
    ):
        return "santehnika"
    return None


def _persona_filenames(row_file: str) -> list[str]:
    found = re.findall(r"`([^`]+)`", row_file)
    if found:
        return [f.strip() for f in found if f.strip()]
    return [row_file.strip()] if row_file.strip() else []


def sync_gallery_manifest_from_persona() -> dict:
    """Резерв портфолио на GitHub: подписи из PERSONA → assets/gallery-manifest.json."""
    rows = parse_persona_rows()
    disk = set(list_disk_photos())
    out: dict[str, list] = {c: [] for c in ("elektrika", "proektirovanie", "santehnika")}
    seen: set[str] = set()
    for row in rows:
        for fname in _persona_filenames(row["file"]):
            fname = fname.strip()
            if not fname or fname not in disk or "," in fname:
                continue
            cat = portfolio_category(fname)
            if not cat:
                continue
            key = f"{cat}|{fname}"
            if key in seen:
                continue
            seen.add(key)
            cap = row["description"].strip()
            if len(cap) > 140:
                cap = cap[:137] + "…"
            out[cat].append(
                {
                    "id": Path(fname).stem.replace(".", "-"),
                    "file": f"assets/photos/{fname}",
                    "caption": cap,
                }
            )
    path = repo_root() / "assets" / "gallery-manifest.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "path": str(path.relative_to(repo_root())).replace("\\", "/"),
        "counts": {k: len(v) for k, v in out.items()},
    }


def git_publish_gallery_manifest() -> dict:
    root = repo_root()
    sync_gallery_manifest_from_persona()
    _git("add", "assets/gallery-manifest.json")
    st = _git("status", "--porcelain", "assets/gallery-manifest.json")
    if not st.stdout.strip():
        return {"ok": True, "committed": False, "message": "manifest без изменений"}
    email = os.environ.get("BLOG_GIT_EMAIL", "tehpodszemi.ru@gmail.com")
    name = os.environ.get("BLOG_GIT_NAME", "tehpodszemiru-tech")
    commit = _git(
        "-c", f"user.email={email}",
        "-c", f"user.name={name}",
        "commit", "-m", "chore: gallery-manifest из PERSONA (резерв без Beget)",
    )
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr)
    push = _git("push", "origin", "main")
    if push.returncode != 0:
        raise RuntimeError(push.stderr)
    return {"ok": True, "committed": True}


def git_publish_article(
    slug: str,
    *,
    republish_social: bool,
    commit_message: str | None = None,
) -> dict:
    """Сборка, commit и push в origin main. Без агента."""
    root = repo_root()
    if not (root / ".git").is_dir():
        raise RuntimeError("Не git-репозиторий: " + str(root))

    post_path(slug).resolve().relative_to(root.resolve())

    pull = _git("pull", "--rebase", "origin", "main")
    if pull.returncode != 0:
        raise RuntimeError("git pull --rebase не удался:\n" + pull.stderr)

    build_log = run_build()

    social_version = None
    if republish_social:
        social_version = bump_social_version(slug)
    else:
        ensure_announce(slug)

    to_add = [
        f"_blog/posts/{slug}.md",
        f"_blog/announce/{slug}.json",
        "blog/",
        "sitemap.xml",
        "blog/rss.xml",
    ]
    cover = root / "assets" / "covers" / f"{slug}.jpg"
    if cover.is_file():
        to_add.append(str(cover.relative_to(root)).replace("\\", "/"))

    _git("add", *to_add)
    st = _git("status", "--porcelain")
    if not st.stdout.strip():
        raise RuntimeError("Нет изменений для commit (файлы совпадают с main?)")

    msg = commit_message or (
        f"blog: обновление статьи {slug}"
        + (" + соцсети" if republish_social else "")
    )
    email = os.environ.get("BLOG_GIT_EMAIL", "tehpodszemi.ru@gmail.com")
    name = os.environ.get("BLOG_GIT_NAME", "tehpodszemiru-tech")
    commit = _git(
        "-c", f"user.email={email}",
        "-c", f"user.name={name}",
        "commit", "-m", msg,
    )
    if commit.returncode != 0:
        raise RuntimeError("git commit не удался:\n" + commit.stderr)

    push = _git("push", "origin", "main")
    if push.returncode != 0:
        raise RuntimeError("git push не удался (нужны права на GitHub):\n" + push.stderr)

    return {
        "ok": True,
        "commit_message": msg,
        "social_version": social_version,
        "build_log": build_log,
        "git_log": (pull.stdout + commit.stdout + push.stdout).strip(),
    }
