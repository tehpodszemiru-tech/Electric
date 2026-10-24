#!/usr/bin/env python3
"""Сборщик блога: _blog/posts/*.md -> blog/<slug>/index.html, blog/index.html,
blog/rss.xml, sitemap.xml.

Только стандартная библиотека. Запуск из корня репозитория:
    python tools/build_blog.py

Формат поста (_blog/posts/<slug>.md):
    ---
    title: Заголовок
    description: Описание для поиска и соцсетей (до ~160 символов)
    date: 2026-10-13
    image: /assets/photos/shchitok-montazh.jpg   # обложка, необязательно
    category: Электрика
    draft: false                                  # true — не публиковать
    ---
    Текст в markdown...
"""
import html
import re
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "_blog" / "posts"
OUT_DIR = ROOT / "blog"
SITE = "https://electric.vim-scrum.ru"
SITE_NAME = "ВИМ-ИНЖЕНЕРКА"
BLOG_TITLE = "Блог мастера: электрика и сантехника в каркасных и СИП-домах"
BLOG_DESC = ("Практические заметки мастера: как делать электрику, сантехнику и "
             "инженерные сети в частном доме, каркасном и СИП-доме. Без воды и с примерами.")
PHONE = "+7 993 466-05-55"
OG_DEFAULT = f"{SITE}/assets/brand/og-banner.jpg"


# ---------------------------------------------------------------- markdown
def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<em>\1</em>", text)

    def link(m):
        label, url = m.group(1), html.unescape(m.group(2))
        if not re.match(r"^(https?://|/|#|mailto:|tel:)", url):
            return m.group(0)
        ext = ' target="_blank" rel="noopener"' if url.startswith("http") and SITE not in url else ""
        return f'<a href="{html.escape(url, quote=True)}"{ext}>{label}</a>'

    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)


def render_table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], cells[2:]
    out = ['<div class="table-wrap"><table><thead><tr>']
    out += [f"<th>{inline(c)}</th>" for c in head]
    out.append("</tr></thead><tbody>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def markdown(src: str) -> str:
    lines = src.replace("\r\n", "\n").split("\n")
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if re.match(r"^-{3,}\s*$", line):
            out.append("<hr>")
            i += 1
        elif m := re.match(r"^(#{2,4})\s+(.*)", line):
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{inline(m.group(2))}</h{lvl}>")
            i += 1
        elif m := re.match(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$", line):
            alt, src_ = m.group(1), html.escape(m.group(2), quote=True)
            out.append(f'<figure><img src="{src_}" alt="{html.escape(alt, quote=True)}" loading="lazy">'
                       f"<figcaption>{inline(alt)}</figcaption></figure>")
            i += 1
        elif line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i].lstrip("> ").rstrip())
                i += 1
            out.append(f'<blockquote class="callout">{markdown(chr(10).join(buf))}</blockquote>')
        elif line.lstrip().startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            buf = []
            while i < n and lines[i].lstrip().startswith("|"):
                buf.append(lines[i])
                i += 1
            out.append(render_table(buf))
        elif re.match(r"^\s*[-*]\s+", line):
            items = []
            while i < n and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(t)}</li>" for t in items) + "</ul>")
        elif re.match(r"^\s*\d+[.)]\s+", line):
            items = []
            while i < n and re.match(r"^\s*\d+[.)]\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+[.)]\s+", "", lines[i]))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline(t)}</li>" for t in items) + "</ol>")
        else:
            buf = []
            while i < n and lines[i].strip() and not re.match(
                    r"^(#{2,4}\s|>|!\[|\s*[-*]\s+|\s*\d+[.)]\s+|\s*\||-{3,}\s*$)", lines[i]):
                buf.append(lines[i].strip())
                i += 1
            if not buf:  # защита от зацикливания на неожиданной строке
                buf = [lines[i].strip()]
                i += 1
            out.append(f"<p>{inline(' '.join(buf))}</p>")
    return "\n".join(out)


# ---------------------------------------------------------------- posts
def parse_post(path: Path):
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw.replace("\r\n", "\n"), re.S)
    if not m:
        raise SystemExit(f"{path.name}: нет frontmatter (--- ... ---)")
    meta = {}
    for ln in m.group(1).split("\n"):
        if ":" in ln:
            k, v = ln.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    for req in ("title", "description", "date"):
        if not meta.get(req):
            raise SystemExit(f"{path.name}: в frontmatter нет поля '{req}'")
    meta["slug"] = path.stem
    meta["body_md"] = m.group(2).strip()
    meta["draft"] = meta.get("draft", "false").lower() == "true"
    meta["date_obj"] = datetime.strptime(meta["date"], "%Y-%m-%d")
    meta.setdefault("category", "Электрика")
    meta["image"] = meta.get("image") or "/assets/brand/og-banner.jpg"
    if (ROOT / "assets" / "covers" / f"{path.stem}.jpg").exists():  # обложка из tools/make_covers.py
        meta["image"] = f"/assets/covers/{path.stem}.jpg"
    words = len(re.findall(r"\w+", meta["body_md"]))
    meta["minutes"] = max(1, round(words / 180))
    return meta


def ru_date(d: datetime) -> str:
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
    return f"{d.day} {months[d.month - 1]} {d.year}"


def abs_url(u: str) -> str:
    return u if u.startswith("http") else SITE + u


# ---------------------------------------------------------------- templates
METRIKA = """<script>
(function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};m[i].l=1*new Date();
for(var j=0;j<document.scripts.length;j++){if(document.scripts[j].src===r){return;}}
k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
(window,document,'script','https://mc.yandex.ru/metrika/tag.js?id=112788163','ym');
ym(112788163,'init',{clickmap:true,trackLinks:true,accurateTrackBounce:true});
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/112788163" style="position:absolute;left:-9999px;" alt=""></div></noscript>"""

HEADER = f"""<header class="site-header">
  <div class="wrap header-inner">
    <a href="/" class="brand"><img src="/assets/brand/logo.png" alt="{SITE_NAME}" width="40" height="40">
      <span><b>{SITE_NAME}</b><small>Электрика и сантехника · Самара</small></span></a>
    <nav>
      <a href="/#services">Услуги</a>
      <a href="/#portfolio">Портфолио</a>
      <a href="/blog/" class="active">Блог</a>
      <a href="/#final-cta" class="nav-cta">Заявка</a>
    </nav>
  </div>
</header>"""

FOOTER = f"""<footer class="site-footer">
  <div class="wrap footer-inner">
    <div><b>{SITE_NAME}</b> — частная бригада электрики и сантехники<br>Самара и Самарская область</div>
    <div class="footer-links">
      <a href="/">Главная</a><a href="/blog/">Блог</a><a href="/privacy-policy.html">Политика конфиденциальности</a>
      <a href="https://t.me/i_modelirovanie" target="_blank" rel="noopener">Telegram</a>
    </div>
    <div><a href="tel:+79934660555">{PHONE}</a></div>
  </div>
</footer>"""

CTA = f"""<aside class="cta-box">
  <h2>Нужна электрика или сантехника в частном доме?</h2>
  <p>Рассчитаем стоимость по вашему плану, проектируем и монтируем под ключ — каркасные и СИП-дома, Самара и область. Расчёт сметы бесплатный.</p>
  <p><a class="btn" href="/#final-cta">Оставить заявку</a> <a class="btn btn-ghost" href="tel:+79934660555">{PHONE}</a></p>
</aside>"""


def page(title, desc, canonical, og_image, body, extra_head="", og_type="website"):
    t = html.escape(title, quote=True)
    d = html.escape(desc, quote=True)
    return f"""<!doctype html>
<html lang="ru">
<head>
{METRIKA}
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{t}</title>
<meta name="description" content="{d}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/assets/brand/favicon-32.png">
<link rel="apple-touch-icon" href="/assets/brand/apple-touch-icon.png">
<link rel="alternate" type="application/rss+xml" title="{SITE_NAME} — блог" href="{SITE}/blog/rss.xml">
<meta name="robots" content="index, follow, max-image-preview:large">
<meta name="theme-color" content="#00243d">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:locale" content="ru_RU">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{og_image}">
<link rel="stylesheet" href="/assets/blog.css">
{extra_head}
</head>
<body>
{HEADER}
{body}
{FOOTER}
</body>
</html>
"""


def card(p):
    return f"""<a class="card" href="/blog/{p['slug']}/">
  <img src="{html.escape(p['image'], quote=True)}" alt="" loading="lazy">
  <div class="card-body"><span class="tag">{html.escape(p['category'])}</span>
    <h3>{html.escape(p['title'])}</h3>
    <p>{html.escape(p['description'])}</p>
    <small>{ru_date(p['date_obj'])} · {p['minutes']} мин чтения</small></div>
</a>"""


def build_post(p, all_posts):
    import json
    url = f"{SITE}/blog/{p['slug']}/"
    ld = {
        "@context": "https://schema.org", "@type": "Article",
        "headline": p["title"], "description": p["description"],
        "datePublished": p["date"], "dateModified": p.get("updated", p["date"]),
        "image": abs_url(p["image"]), "mainEntityOfPage": url,
        "inLanguage": "ru",
        "author": {"@type": "Organization", "name": SITE_NAME, "url": SITE},
        "publisher": {"@type": "Organization", "name": SITE_NAME,
                      "logo": {"@type": "ImageObject", "url": f"{SITE}/assets/brand/logo.png"}},
    }
    crumbs = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Главная", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "Блог", "item": SITE + "/blog/"},
            {"@type": "ListItem", "position": 3, "name": p["title"], "item": url},
        ],
    }
    extra = ""
    for obj in (ld, crumbs):
        extra += f'<script type="application/ld+json">{json.dumps(obj, ensure_ascii=False)}</script>\n'
    more = [x for x in all_posts if x["slug"] != p["slug"]][:3]
    more_html = ""
    if more:
        more_html = '<section class="more"><h2>Читайте также</h2><div class="grid">' + \
                    "".join(card(x) for x in more) + "</div></section>"
    body = f"""<main class="wrap">
<nav class="crumbs" aria-label="Хлебные крошки"><a href="/">Главная</a> / <a href="/blog/">Блог</a></nav>
<article class="post">
  <header>
    <span class="tag">{html.escape(p['category'])}</span>
    <h1>{html.escape(p['title'])}</h1>
    <p class="meta">{ru_date(p['date_obj'])} · {p['minutes']} мин чтения · Мастер бригады {SITE_NAME}</p>
  </header>
  <div class="post-body">
{markdown(p['body_md'])}
  </div>
  {CTA}
</article>
{more_html}
</main>"""
    d = OUT_DIR / p["slug"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(
        page(f"{p['title']} — {SITE_NAME}", p["description"], url, abs_url(p["image"]), body, extra, "article"),
        encoding="utf-8")


def build_index(posts):
    cards = "".join(card(p) for p in posts) or "<p>Первые статьи скоро появятся.</p>"
    body = f"""<main class="wrap">
<header class="blog-head"><h1>Блог мастера</h1>
<p class="lead">Электрика, сантехника и инженерные сети в частных, каркасных и СИП-домах — так, как это делается на реальных объектах.</p></header>
<div class="grid">{cards}</div>
{CTA}
</main>"""
    (OUT_DIR / "index.html").write_text(
        page(BLOG_TITLE, BLOG_DESC, f"{SITE}/blog/", OG_DEFAULT, body), encoding="utf-8")


def build_rss(posts):
    items = ""
    for p in posts[:20]:
        dt = p["date_obj"].replace(hour=9, tzinfo=timezone.utc)
        items += (f"<item><title>{html.escape(p['title'])}</title>"
                  f"<link>{SITE}/blog/{p['slug']}/</link>"
                  f"<guid isPermaLink=\"true\">{SITE}/blog/{p['slug']}/</guid>"
                  f"<pubDate>{format_datetime(dt)}</pubDate>"
                  f"<description>{html.escape(p['description'])}</description></item>\n")
    rss = ('<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
           f"<title>{SITE_NAME} — блог</title><link>{SITE}/blog/</link>"
           f"<description>{html.escape(BLOG_DESC)}</description><language>ru</language>\n{items}</channel></rss>\n")
    (OUT_DIR / "rss.xml").write_text(rss, encoding="utf-8")


def build_sitemap(posts):
    today = datetime.now().strftime("%Y-%m-%d")
    urls = [(f"{SITE}/", today, "weekly", "1.0"),
            (f"{SITE}/blog/", posts[0]["date"] if posts else today, "weekly", "0.8")]
    urls.append((f"{SITE}/domovoy/", "2026-10-24", "monthly", "0.7"))
    urls += [(f"{SITE}/blog/{p['slug']}/", p.get("updated", p["date"]), "monthly", "0.7") for p in posts]
    urls.append((f"{SITE}/privacy-policy.html", "2026-10-05", "yearly", "0.2"))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for loc, last, freq, prio in urls:
        xml += (f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{last}</lastmod>\n"
                f"    <changefreq>{freq}</changefreq>\n    <priority>{prio}</priority>\n  </url>\n")
    (ROOT / "sitemap.xml").write_text(xml + "</urlset>\n", encoding="utf-8")


def main():
    posts = [parse_post(p) for p in sorted(POSTS_DIR.glob("*.md"))]
    published = sorted((p for p in posts if not p["draft"]), key=lambda p: p["date_obj"], reverse=True)
    for p in posts:  # убрать устаревшие страницы черновиков
        if p["draft"] and (OUT_DIR / p["slug"] / "index.html").exists():
            (OUT_DIR / p["slug"] / "index.html").unlink()
    for p in published:
        build_post(p, published)
    build_index(published)
    build_rss(published)
    build_sitemap(published)
    print(f"Опубликовано статей: {len(published)}; черновиков: {len(posts) - len(published)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
