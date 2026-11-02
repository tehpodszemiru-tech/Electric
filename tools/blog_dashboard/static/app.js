async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || r.statusText);
  }
  return r.json();
}

function el(id) {
  return document.getElementById(id);
}

function tabSetup() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      el(`panel-${btn.dataset.tab}`).classList.add("active");
    });
  });
}

function card(label, val, warn) {
  return `<div class="card${warn ? " warn" : ""}"><div class="muted">${label}</div><div class="val">${val}</div></div>`;
}

async function loadPipeline() {
  const s = await api("/api/status");
  el("repo-path").textContent = s.repo_root;
  const next = s.next_topic ? s.next_topic.title.slice(0, 40) + "…" : "—";
  el("status-cards").innerHTML = [
    card("В очереди", s.queued_count, s.warn_low_topics),
    card("Опубликовано", s.published_count, false),
    card("Свободных обложек", s.free_cover_count, s.warn_low_covers),
    card("Последняя дата", s.last_publish_date || "—", false),
  ].join("");

  const prs = s.open_prs || [];
  el("pr-list").innerHTML = prs.length
    ? `<ul>${prs.map((p) => `<li><a href="${p.url}" target="_blank" rel="noopener">#${p.number}</a> ${escapeHtml(p.title)} ${p.draft ? "(draft)" : ""}</li>`).join("")}</ul>`
    : "<p class='muted'>Открытых PR blog/* нет.</p>";

  const links = s.agents.links;
  el("agent-info").innerHTML = `
    <p><strong>Автор статей:</strong> ${escapeHtml(s.agents.author)}</p>
    <p class="muted">${escapeHtml(s.agents.claude_routine)}</p>
    <ul>
      <li><a href="${links.automations}" target="_blank" rel="noopener">Cursor Automations</a> — Run now / расписание</li>
      <li><a href="${links.github_prs}" target="_blank" rel="noopener">Pull requests</a></li>
      <li><a href="${links.github_actions}" target="_blank" rel="noopener">GitHub Actions</a></li>
      <li><a href="${links.blog}" target="_blank" rel="noopener">Сайт /blog</a></li>
    </ul>
    <p class="hint">Статьи правьте во вкладке «Статьи» (push в main без агента). Фото/FACTS — commit + push вручную или через git.</p>`;

  const topics = await api("/api/topics");
  const queued = topics.filter((t) => t.status === "queued").slice(0, 8);
  el("topic-preview").innerHTML = queued
    .map((t) => `<li>${escapeHtml(t.title)}</li>`)
    .join("");
}

async function loadPhotos() {
  const data = await api("/api/photos");
  const st = data.stats;
  el("photo-stats").textContent =
    `Под обложки: ${st.suitable_count}, свободно: ${st.free_cover_count}. ` +
    (st.orphan_photos.length ? `Без PERSONA: ${st.orphan_photos.join(", ")}. ` : "") +
    (st.missing_files.length ? `В PERSONA, но нет файла: ${st.missing_files.join(", ")}` : "");

  const warn = el("photo-warn");
  if (st.warn_low_covers) {
    warn.textContent = `Мало свободных кадров для обложек (${st.free_cover_count} < 3). Добавьте фото.`;
    warn.className = "alert warn show";
  } else {
    warn.className = "alert";
  }

  el("photo-grid").innerHTML = data.photos
    .map((p) => {
      const badges = [];
      if (p.in_persona) badges.push('<span class="badge ok">PERSONA</span>');
      else badges.push('<span class="badge miss">нет в PERSONA</span>');
      if (p.used_as_cover) badges.push('<span class="badge warn">обложка использована</span>');
      const desc = p.persona ? escapeHtml(p.persona.description.slice(0, 80)) : "";
      return `<article class="ph">
        <img src="${p.url}" alt="" loading="lazy" />
        <div class="meta"><strong>${escapeHtml(p.file)}</strong><br>${badges.join(" ")}<br>${desc}</div>
      </article>`;
    })
    .join("");
}

async function loadFacts() {
  const f = await api("/api/facts");
  el("facts-cases").value = f.cases;
  el("facts-prices").value = f.prices;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

async function init() {
  tabSetup();
  articleActions();
  el("btn-refresh").addEventListener("click", () => refreshAll());

  el("upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = el("upload-msg");
    msg.textContent = "";
    const fd = new FormData(e.target);
    fd.set("cover_ok", e.target.cover_ok.checked ? "true" : "false");
    try {
      const res = await api("/api/photos/upload", { method: "POST", body: fd });
      msg.textContent = `Сохранено: ${res.path}. Не забудьте git commit + push.`;
      msg.className = "msg ok";
      e.target.reset();
      await loadPhotos();
      await loadPipeline();
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "msg err";
    }
  });

  el("save-cases").addEventListener("click", async () => {
    await saveFacts("/api/facts/cases", el("facts-cases").value, "случаи");
  });
  el("save-prices").addEventListener("click", async () => {
    await saveFacts("/api/facts/prices", el("facts-prices").value, "цены");
  });

  async function syncManifest(push) {
    const msg = el("manifest-msg");
    msg.textContent = push ? "Manifest и push…" : "Manifest…";
    msg.className = "msg";
    try {
      const r = await api("/api/portfolio/sync-manifest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ push }),
      });
      msg.textContent =
        `Готово: ${JSON.stringify(r.counts || r)}` +
        (r.committed === false ? " (без изменений)" : "");
      msg.className = "msg ok";
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "msg err";
    }
  }
  el("sync-manifest-local").addEventListener("click", () => syncManifest(false));
  el("sync-manifest-push").addEventListener("click", () => syncManifest(true));

  await refreshAll();
}

async function saveFacts(url, text, label) {
  const msg = el("facts-msg");
  try {
    await api(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    msg.textContent = `FACTS: ${label} сохранены локально. Commit + push для агента.`;
    msg.className = "msg ok";
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg err";
  }
}

let currentSlug = null;

async function loadArticlesList() {
  const { articles } = await api("/api/articles");
  const list = el("article-list");
  if (!articles.length) {
    list.innerHTML = "<li class='muted'>Нет статей</li>";
    return;
  }
  list.innerHTML = articles
    .map(
      (a) => `<li><button type="button" data-slug="${escapeHtml(a.slug)}" class="${a.slug === currentSlug ? "active" : ""}">
        ${escapeHtml(a.title.slice(0, 42))}${a.title.length > 42 ? "…" : ""}
        <span class="muted"><br>${escapeHtml(a.date)} · v${a.social_version}</span>
      </button></li>`
    )
    .join("");
  list.querySelectorAll("button[data-slug]").forEach((btn) => {
    btn.addEventListener("click", () => selectArticle(btn.dataset.slug));
  });
}

async function selectArticle(slug) {
  currentSlug = slug;
  const d = await api(`/api/articles/${encodeURIComponent(slug)}`);
  el("editor-title").textContent = d.title;
  el("editor-meta").innerHTML =
    `<a href="${d.site_url}" target="_blank" rel="noopener">На сайте</a> · ` +
    `${escapeHtml(d.category)} · social_version ${d.announce.social_version} ` +
    `(в ТГ/ВК: ${d.posted.social_version || 0}) · ` +
    `ТГ ${d.posted.telegram === "ok" ? "✓" : "—"} · VK ${d.posted.vk === "ok" ? "✓" : "—"}` +
    (d.posted.telegram_message_id ? `<br>TG msg id: ${d.posted.telegram_message_id}` : "") +
    (d.posted.vk_post_id ? ` · VK post id: ${d.posted.vk_post_id}` : "");
  el("article-raw").value = d.raw;
  el("article-raw").disabled = false;
  el("save-article-local").disabled = false;
  el("release-article").disabled = false;
  el("article-wordcount").textContent = `≈ ${d.word_count} слов`;
  el("article-msg").textContent = "";
  el("release-log").className = "log";
  await loadArticlesList();
}

async function loadArticles() {
  await loadArticlesList();
}

function articleActions() {
  el("save-article-local").addEventListener("click", async () => {
    if (!currentSlug) return;
    const msg = el("article-msg");
    try {
      const raw = el("article-raw").value;
      const r = await api(`/api/articles/${encodeURIComponent(currentSlug)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ raw }),
      });
      msg.textContent = `Сохранено локально (~${r.word_count} слов). Для сайта нажмите «Собрать и отправить в GitHub».`;
      msg.className = "msg ok";
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "msg err";
    }
  });

  el("release-article").addEventListener("click", async () => {
    if (!currentSlug) return;
    const msg = el("article-msg");
    const logEl = el("release-log");
    msg.textContent = "Сборка, commit, push…";
    msg.className = "msg";
    logEl.className = "log";
    try {
      const body = {
        raw: el("article-raw").value,
        republish_social: el("republish-social").checked,
        commit_message: el("commit-message").value.trim(),
      };
      const r = await api(`/api/articles/${encodeURIComponent(currentSlug)}/release`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      msg.textContent =
        `Готово: ${r.commit_message}. ` +
        (r.social_version ? `social_version=${r.social_version}. Через 2–5 мин проверьте сайт и Actions «Анонс».` : "Сайт обновится после GitHub Pages (1–3 мин).");
      msg.className = "msg ok";
      logEl.textContent = (r.build_log || "") + "\n" + (r.git_log || "");
      logEl.className = "log show";
      await loadArticlesList();
      await selectArticle(currentSlug);
    } catch (err) {
      msg.textContent = err.message;
      msg.className = "msg err";
    }
  });
}

async function refreshAll() {
  await Promise.all([loadPipeline(), loadPhotos(), loadArticles(), loadFacts()]);
}

init();
