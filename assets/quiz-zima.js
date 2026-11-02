(function () {
  var QUESTIONS = [
    {
      text: "Дом зимой постоянно проживаете или он закрывается?",
      options: [
        { label: "Живём постоянно", score: 0 },
        { label: "Приезжаем периодически (дача)", score: 1 },
        { label: "Закрываем на зиму, воду сливаем", score: 1 },
      ],
    },
    {
      text: "Водопровод проходит на улице или в неотапливаемом цоколе?",
      options: [
        { label: "Да, есть такие участки", score: 2 },
        { label: "Частично", score: 1 },
        { label: "Нет, всё в тёплом контуре", score: 0 },
      ],
    },
    {
      text: "Зимой свет отключают дольше, чем на несколько часов?",
      options: [
        { label: "Бывает часто", score: 2 },
        { label: "Иногда", score: 1 },
        { label: "Редко или не бывает", score: 0 },
      ],
    },
    {
      text: "Одновременно включаете обогреватель, чайник и мощную технику?",
      options: [
        { label: "Да, часто", score: 2 },
        { label: "Иногда", score: 1 },
        { label: "Нет, следим за нагрузкой", score: 0 },
      ],
    },
    {
      text: "Щиток проверяли за последние 2 года (УЗО, заземление)?",
      options: [
        { label: "Да, мастером", score: 0 },
        { label: "Сами смотрели", score: 1 },
        { label: "Не помню / не проверяли", score: 2 },
      ],
    },
    {
      text: "Канализация или выпуск — есть риск промерзания?",
      options: [
        { label: "Да, есть риск", score: 2 },
        { label: "Не уверен", score: 1 },
        { label: "Утеплено, уклоны в порядке", score: 0 },
      ],
    },
    {
      text: "Греющий кабель на трубах, если он нужен по ситуации?",
      options: [
        { label: "Есть и включаем по сезону", score: 0 },
        { label: "Нет, но задумывались", score: 1 },
        { label: "Не нужен (всё в тепле / воду сливаем)", score: 0 },
      ],
    },
  ];

  var RESULTS = [
    {
      max: 2,
      badge: "Низкий приоритет",
      title: "Похоже, база в порядке",
      text: "Критичных сигналов мало. Всё равно имеет смысл раз в сезон пройтись по щитку и вводу воды — это дешевле, чем авария в мороз.",
      links: [
        { href: "/blog/podgotovka-doma-k-zime-elektrika-santehnika/", label: "Чек-лист подготовки к зиме" },
        { href: "/blog/vybivaet-avtomat-zimoj/", label: "Почему выбивает автомат зимой" },
      ],
    },
    {
      max: 5,
      badge: "Средний приоритет",
      title: "Есть 2–3 зоны риска",
      text: "У многих домов в Самарской области в этих пунктах «плавает» электрика или ввод воды. Стоит проверить до стабильных минусов.",
      links: [
        { href: "/blog/podgotovka-doma-k-zime-elektrika-santehnika/", label: "Подготовка дома к зиме" },
        { href: "/blog/greyushchij-kabel-vodoprovod-kanalizatsiya/", label: "Греющий кабель: когда нужен" },
        { href: "/blog/shchitok-v-chastnom-dome/", label: "Щиток в частном доме" },
      ],
    },
    {
      max: 99,
      badge: "Высокий приоритет",
      title: "Лучше не откладывать",
      text: "Сочетание мороза, нагрузки и воды/канализации часто даёт и выбивание автоматов, и проблемы с трубами. Имеет смысл плановый осмотр щитка и ввода или выезд мастера.",
      links: [
        { href: "/blog/podgotovka-doma-k-zime-elektrika-santehnika/", label: "Подготовка к зиме" },
        { href: "/blog/greyushchij-kabel-vodoprovod-kanalizatsiya/", label: "Греющий кабель" },
        { href: "/blog/shchitok-v-chastnom-dome/", label: "Щиток в частном доме" },
        { href: "/blog/oshibki-elektriki-karkasnyj-sip-dom/", label: "Ошибки электрики в каркасном и СИП-доме" },
      ],
    },
  ];

  var ENDPOINT = "https://leads.vim-scrum.ru/lead";
  var step = -1;
  var scores = [];
  var answers = [];

  var root = document.getElementById("quiz-app");
  if (!root) return;

  var progress = document.getElementById("quiz-progress-bar");
  var stepLabel = document.getElementById("quiz-step-label");
  var titleEl = document.getElementById("quiz-title");
  var leadEl = document.getElementById("quiz-lead");
  var hintEl = document.getElementById("quiz-hint");
  var optionsEl = document.getElementById("quiz-options");
  var navEl = document.getElementById("quiz-nav");
  var resultEl = document.getElementById("quiz-result");
  var leadFormWrap = document.getElementById("quiz-lead-form");

  function utmQuery() {
    var p = new URLSearchParams(window.location.search);
    var keys = ["utm_source", "utm_medium", "utm_campaign", "utm_content"];
    var parts = [];
    keys.forEach(function (k) {
      if (p.get(k)) parts.push(k + "=" + encodeURIComponent(p.get(k)));
    });
    return parts.length ? parts.join("&") : "";
  }

  function ctaHref() {
    var q = utmQuery();
    var base = "/#final-cta?utm_source=quiz&utm_medium=result&utm_campaign=zima-2026";
    if (!q) return base;
    return base + "&" + q.replace(/utm_source=[^&]+&?/, "").replace(/^&/, "");
  }

  function setProgress() {
    var total = QUESTIONS.length + 1;
    var current = step < 0 ? 0 : step + 1;
    var pct = Math.round((current / total) * 100);
    progress.style.width = pct + "%";
  }

  function renderIntro() {
    step = -1;
    resultEl.hidden = true;
    optionsEl.hidden = false;
    navEl.hidden = false;
    leadFormWrap.hidden = true;
    stepLabel.textContent = "Тест";
    titleEl.textContent = "Проверьте дом перед морозами";
    leadEl.textContent =
      "7 коротких вопросов про электрику и сантехнику — увидите, что проверить самому, а где лучше подключить мастера.";
    hintEl.textContent = "Нет «правильных» ответов — только ваша ситуация. ~2 минуты.";
    optionsEl.innerHTML = "";
    navEl.innerHTML =
      '<button type="button" class="btn" id="quiz-start">Начать проверку</button>';
    document.getElementById("quiz-start").onclick = function () {
      if (window.ym) ym(112788163, "reachGoal", "quiz_start");
      step = 0;
      scores = [];
      answers = [];
      renderQuestion();
    };
    setProgress();
  }

  function renderQuestion() {
    resultEl.hidden = true;
    leadFormWrap.hidden = true;
    var q = QUESTIONS[step];
    stepLabel.textContent = "Вопрос " + (step + 1) + " из " + QUESTIONS.length;
    titleEl.textContent = q.text;
    leadEl.textContent = "";
    hintEl.textContent = "";
    optionsEl.hidden = false;
    optionsEl.innerHTML = "";
    q.options.forEach(function (opt, i) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "quiz-opt";
      btn.textContent = opt.label;
      btn.onclick = function () {
        scores.push(opt.score);
        answers.push(opt.label);
        if (step < QUESTIONS.length - 1) {
          step += 1;
          renderQuestion();
        } else {
          renderResult();
        }
      };
      optionsEl.appendChild(btn);
    });
    navEl.hidden = false;
    navEl.innerHTML = "";
    if (step > 0) {
      var back = document.createElement("button");
      back.type = "button";
      back.className = "btn btn-secondary";
      back.textContent = "Назад";
      back.onclick = function () {
        step -= 1;
        scores.pop();
        answers.pop();
        renderQuestion();
      };
      navEl.appendChild(back);
    }
    setProgress();
  }

  function totalScore() {
    return scores.reduce(function (a, b) {
      return a + b;
    }, 0);
  }

  function pickResult(score) {
    for (var i = 0; i < RESULTS.length; i++) {
      if (score <= RESULTS[i].max) return RESULTS[i];
    }
    return RESULTS[RESULTS.length - 1];
  }

  function renderResult() {
    var score = totalScore();
    var r = pickResult(score);
    optionsEl.hidden = true;
    navEl.hidden = true;
    resultEl.hidden = false;
    leadFormWrap.hidden = false;
    stepLabel.textContent = "Результат";
    titleEl.textContent = r.title;
    leadEl.textContent = r.text;
    hintEl.textContent = "Баллы (для себя): " + score + " · " + r.badge;

    var linksHtml = r.links
      .map(function (l) {
        return '<li><a href="' + l.href + '">' + l.label + "</a></li>";
      })
      .join("");
    resultEl.innerHTML =
      '<p class="quiz-result-title">' +
      r.badge +
      "</p>" +
      '<ul class="quiz-links">' +
      linksHtml +
      "</ul>" +
      '<p style="margin-top:22px"><a class="btn" href="' +
      ctaHref() +
      '">Бесплатный расчёт сметы</a> ' +
      '<a class="btn btn-secondary" href="tel:+79934660555" style="display:inline-block;margin-left:8px">Позвонить</a></p>';

    setProgress();
    if (window.ym) ym(112788163, "reachGoal", "quiz_complete");

    var form = document.getElementById("quiz-lead");
    if (form && !form.dataset.bound) {
      form.dataset.bound = "1";
      form.addEventListener("submit", onLeadSubmit);
    }
    window.__quizResultMeta = { score: score, badge: r.badge, answers: answers.slice() };
  }

  async function onLeadSubmit(e) {
    e.preventDefault();
    var form = e.target;
    var btn = form.querySelector('button[type="submit"]');
    var msg = document.getElementById("quiz-lead-msg");
    var orig = btn.textContent;
    var meta = window.__quizResultMeta || {};
    var utm = utmQuery();
    var name = (form.elements.namedItem("name") && form.elements.namedItem("name").value) || "";
    var phone = (form.elements.namedItem("phone") && form.elements.namedItem("phone").value) || "";
    var objectType = (form.elements.namedItem("object") && form.elements.namedItem("object").value) || "";
    var commentExtra = (form.elements.namedItem("comment") && form.elements.namedItem("comment").value) || "";
    var website = (form.elements.namedItem("website") && form.elements.namedItem("website").value) || "";
    var turnstileEl = form.querySelector('[name="cf-turnstile-response"]');
    var comment =
      "[Квиз «Зима»] " +
      (meta.badge || "") +
      ", баллы: " +
      (meta.score != null ? meta.score : "?") +
      ". " +
      (utm ? utm + ". " : "") +
      commentExtra.trim();

    btn.disabled = true;
    btn.textContent = "Отправляем…";
    msg.textContent = "";
    msg.className = "quiz-msg";

    try {
      var res = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          phone: phone.trim(),
          objectType: objectType.trim(),
          message: comment,
          website: website,
          turnstileToken: turnstileEl ? turnstileEl.value : "",
        }),
      });
      var data = await res.json();
      if (data.ok) {
        msg.textContent = "Спасибо! Мастер свяжется в рабочее время.";
        msg.classList.add("ok");
        form.reset();
        if (window.turnstile) window.turnstile.reset();
        if (window.ym) ym(112788163, "reachGoal", "quiz_lead");
        btn.textContent = "Отправлено";
      } else {
        msg.textContent = "Не удалось отправить. Позвоните +7 993 466-05-55";
        msg.classList.add("err");
        btn.disabled = false;
        btn.textContent = orig;
      }
    } catch (err) {
      msg.textContent = "Ошибка сети. Позвоните +7 993 466-05-55";
      msg.classList.add("err");
      btn.disabled = false;
      btn.textContent = orig;
    }
  }

  renderIntro();
})();
