// Kompas Kompetencji – drobne zachowania UI (bez frameworka; htmx robi resztę).
// Ruch tylko z celem (pokazuje, co się zmieniło), < 300 ms, ease-out; przy prefers-reduced-motion: reduce – bez animacji.
(function () {
  "use strict";

  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Nawigacja: stała u góry, trzy stany w html[data-nav] (wygląd w app.css).
  //   top – y ≤ 8 px; compact – przewijanie w dół; full – przewijanie w górę o ≥ 72 px albo fokus w pasku.
  // Histereza: liczymy drogę w jednym kierunku (dół 24 px, góra 72 px), więc drgania kółka nie przełączają stanu.
  (function () {
    var root = document.documentElement, bar = document.querySelector(".topbar");
    if (!bar) return;
    var last = window.scrollY, run = 0, state = root.getAttribute("data-nav") || "top", queued = false;
    function set(s) { if (s !== state) { state = s; root.setAttribute("data-nav", s); } }
    function update() {
      queued = false;
      var y = window.scrollY, dy = y - last;
      last = y;
      if (y <= 8) { run = 0; set("top"); return; }
      run = (dy > 0) === (run > 0) ? run + dy : dy;
      if (state === "top" || run > 24) set("compact");
      else if (run < -72) set("full");
    }
    window.addEventListener("scroll", function () { if (!queued) { queued = true; requestAnimationFrame(update); } }, { passive: true });
    bar.addEventListener("focusin", function () { if (state === "compact") set("full"); });
    if (window.scrollY > 8) set("compact"); // powrót do strony w środku (bfcache, odświeżenie)
  })();

  function restart(el, cls) { // ponowne odpalenie animacji CSS
    el.classList.remove(cls);
    void el.offsetWidth;
    el.classList.add(cls);
  }

  // Klik w odnośnik [n] w odpowiedzi asystenta → rozwiń cytat, przewiń do niego i na chwilę podświetl.
  document.addEventListener("click", function (ev) {
    var ref = ev.target.closest(".cite-ref");
    if (!ref) return;
    var li = document.getElementById(ref.dataset.cite);
    if (!li) return;
    ev.preventDefault();
    var det = li.querySelector("details");
    if (det) det.open = true;
    li.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" });
    restart(li, "cite-flash");
  });

  // Przykładowe pytania do asystenta (data-form wskazuje formularz; domyślnie panel boczny).
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-question]");
    if (!b) return;
    var form = document.getElementById(b.dataset.form || "assist-form");
    if (!form) return;
    form.querySelector("textarea").value = b.dataset.question;
    form.requestSubmit();
  });

  // Rozmowa z asystentem formalnym: Enter wysyła (Shift+Enter – nowa linia).
  document.addEventListener("keydown", function (ev) {
    var ta = ev.target;
    if (ev.key !== "Enter" || ev.shiftKey || ev.isComposing || !ta.matches || !ta.matches("textarea[data-submit-enter]")) return;
    ev.preventDefault();
    if (ta.value.trim() && ta.form) ta.form.requestSubmit();
  });

  // Rozmowa zostaje przy przejściu między krokami oceny: kontener [data-persist] zapisuje się w sessionStorage
  // (tylko ta karta przeglądarki; czyszczone przy „Zmień rolę”). Kolejne pytanie wysyła ukryte pola historii.
  var PERSIST_MAX = 12;
  function store(key, val) { try { if (val === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, val); } catch (e) { /* tryb prywatny */ } }
  function load(key) { try { return sessionStorage.getItem(key); } catch (e) { return null; } }
  function syncClear(box) {
    var has = !!box.querySelector(".answer");
    document.querySelectorAll('[data-assist-clear="' + box.id + '"]').forEach(function (b) { b.hidden = !has; });
    box.classList.toggle("has-answers", has);
  }
  function persist(box) {
    var answers = box.querySelectorAll(".answer");
    // panel boczny: najnowsze na górze; pełny widok: najnowsze na dole – usuwamy najstarsze ponad limit
    var newestFirst = box.dataset.persist === "kk-assist-side";
    for (var i = PERSIST_MAX; i < answers.length; i++) {
      var old = answers[newestFirst ? i : answers.length - 1 - i];
      if (old) old.remove();
    }
    var html = Array.prototype.map.call(box.querySelectorAll(".answer"), function (a) { return a.outerHTML; }).join("");
    store(box.dataset.persist, html || null);
    syncClear(box);
  }
  document.querySelectorAll("[data-persist]").forEach(function (box) {
    var html = load(box.dataset.persist);
    if (html) {
      box.insertAdjacentHTML("beforeend", html);
      if (window.htmx) window.htmx.process(box);
    }
    syncClear(box);
  });
  document.addEventListener("htmx:afterSwap", function (ev) {
    var box = ev.detail && ev.detail.target;
    if (!box || !box.dataset || !box.dataset.persist) return;
    persist(box);
    if (box.id === "chat-log") { // pełny widok: pokaż początek nowej odpowiedzi
      var last = box.querySelector(".answer:last-of-type");
      if (last) last.scrollIntoView({ block: "start", behavior: reduceMotion ? "auto" : "smooth" });
    }
  });
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-assist-clear]");
    if (!b) return;
    var box = document.getElementById(b.dataset.assistClear);
    if (!box) return;
    box.querySelectorAll(".answer, .assist-hint").forEach(function (a) { a.remove(); });
    persist(box);
    var form = b.form;
    if (form) { var ta = form.querySelector("textarea"); if (ta) ta.focus(); }
  });
  document.addEventListener("submit", function (ev) {
    if (ev.target.matches && ev.target.matches("form[data-logout]")) {
      store("kk-assist-side", null);
      store("kk-assist-page", null);
    }
  });

  // Zakładki: Asystent formalny / Asystent rozmowy.
  document.addEventListener("click", function (ev) {
    var tab = ev.target.closest("[data-tab]");
    if (!tab) return;
    tab.parentElement.querySelectorAll("[data-tab]").forEach(function (t) {
      var on = t === tab;
      t.setAttribute("aria-selected", on ? "true" : "false");
      var panel = document.getElementById(t.dataset.tab);
      if (panel) panel.hidden = !on;
    });
  });

  // Panel asystenta na węższych ekranach (wysuwany).
  document.addEventListener("click", function (ev) {
    if (ev.target.closest("[data-assist-toggle]")) document.body.classList.toggle("assist-open");
  });

  // „Brak podstaw do oceny” wyszarza opisy zachowań wskaźnika (serwer i tak pomija poziom).
  function syncNoBasis(box) {
    var fs = box.closest("fieldset.indicator");
    if (fs) fs.classList.toggle("is-nobasis", box.checked);
  }
  document.addEventListener("change", function (ev) {
    if (ev.target.matches("input[data-nobasis]")) syncNoBasis(ev.target);
  });

  // Asystent oceny zachowań: „Zaznacz” przenosi propozycję AI do formularza wskaźników (przełożony może ją zmienić).
  // Ukryte pole ai::<wskaźnik> zapisuje, co zaproponowało AI; zaznaczony poziom to wybór przełożonego.
  function applyProposal(li) {
    var form = document.getElementById("ratings");
    if (!form || !li) return null;
    var iid = li.dataset.baiInd, level = li.dataset.baiLevel, evidence = li.dataset.baiEvidence;
    var radio = form.querySelector('input[name="lvl::' + iid + '"][value="' + level + '"]');
    if (!radio) return null;
    var nb = form.querySelector('input[name="nb::' + iid + '"]');
    if (nb && nb.checked) { nb.checked = false; syncNoBasis(nb); }
    radio.checked = true;
    var hidden = form.querySelector('input[name="ai::' + iid + '"]');
    if (hidden) hidden.value = level;
    var fs = radio.closest("fieldset");
    fs.querySelectorAll(".level.ai-pick").forEach(function (l) {
      l.classList.remove("ai-pick");
      var n = l.querySelector(".ai-note");
      if (n) n.remove();
    });
    var label = radio.closest(".level");
    label.classList.add("ai-pick");
    var name = label.querySelector(".lvl-name");
    if (name && !name.querySelector(".ai-note")) {
      var tag = document.createElement("small");
      tag.className = "ai-note";
      tag.textContent = "propozycja AI";
      name.appendChild(tag);
    }
    var ta = form.querySelector('textarea[name="sdr::' + iid + '"]');
    if (ta && !ta.value.trim() && evidence) {
      ta.value = "Z opisu przełożonego: „" + evidence + "”";
      var det = ta.closest("details");
      if (det) det.open = true;
    }
    li.classList.add("is-applied");
    var b = li.querySelector("[data-bai-apply]");
    if (b) { b.textContent = "Zaznaczono"; b.disabled = true; }
    return radio;
  }
  document.addEventListener("click", function (ev) {
    var one = ev.target.closest("[data-bai-apply]"), all = ev.target.closest("[data-bai-apply-all]");
    if (!one && !all) return;
    var items = one ? [one.closest("[data-bai-ind]")]
      : Array.prototype.slice.call(document.querySelectorAll("#behavior-ai-out [data-bai-ind]"));
    var last = null;
    items.forEach(function (li) { var r = applyProposal(li); if (r) last = r; });
    if (!last) return;
    last.dispatchEvent(new Event("change", { bubbles: true })); // htmx: zapis ocen i przeliczenie Kompasu poziomu
    if (all) { all.disabled = true; all.textContent = "Zaznaczono propozycje"; }
    var target = document.getElementById("ind-" + items[0].dataset.baiInd.replace(/\./g, "-"));
    if (one && target) target.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
  });

  // Kryteria dodatkowe: najwyżej 3 (§ 5 ust. 2 rozp. 2016) – blokada w przeglądarce, serwer sprawdza ponownie.
  function syncLimit() {
    var boxes = document.querySelectorAll("input[name=additional]");
    if (!boxes.length) return;
    var max = parseInt(document.querySelector("[data-max-additional]").dataset.maxAdditional, 10);
    var n = Array.prototype.filter.call(boxes, function (b) { return b.checked; }).length;
    boxes.forEach(function (b) { b.disabled = !b.checked && n >= max; });
    var c = document.getElementById("additional-count");
    if (c) c.textContent = n + " z " + max;
  }
  document.addEventListener("change", function (ev) {
    if (ev.target.matches("input[name=additional]")) syncLimit();
  });

  // Propozycja AI → „Zaznacz” zaznacza kryterium na liście (z limitem 3) i pokazuje je na chwilę.
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-check-criterion]");
    if (!b) return;
    var box = document.querySelector('input[name=additional][value="' + b.dataset.checkCriterion + '"]');
    if (!box) return;
    if (!box.checked && box.disabled) { b.textContent = "Najwyżej 3 kryteria (§ 5 ust. 2)"; return; }
    box.checked = true;
    syncLimit();
    b.textContent = "Zaznaczono";
    var row = box.closest(".crit-row");
    if (row) { row.scrollIntoView({ block: "nearest", behavior: reduceMotion ? "auto" : "smooth" }); restart(row, "cite-flash"); }
  });

  // Zwykłe formularze (pełne przeładowanie strony): stan „w toku” na klikniętym przycisku i blokada podwójnego wysłania.
  // Przycisku nie wyłączamy – wtedy przeglądarka nie wysłałaby jego name/value (np. wybór arkusza B/C).
  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (f.hasAttribute("hx-post") || f.hasAttribute("hx-get")) return; // htmx sam obsługuje stan
    if (f.dataset.submitting === "1") { ev.preventDefault(); return; }
    f.dataset.submitting = "1";
    var b = ev.submitter;
    if (b && b.classList) { b.classList.add("is-busy"); b.setAttribute("aria-busy", "true"); }
  });
  window.addEventListener("pageshow", function () { // powrót z bfcache: odblokuj formularze
    document.querySelectorAll("form[data-submitting]").forEach(function (f) { delete f.dataset.submitting; });
    document.querySelectorAll(".is-busy").forEach(function (b) { b.classList.remove("is-busy"); b.removeAttribute("aria-busy"); });
  });

  // Kompas poziomu na żywo: po każdej zmianie ocen wskaźników ramka „sugestia” przelatuje do nowego przycisku,
  // średnia przelicza się krótkim licznikiem, a wzór na chwilę się podświetla – widać przyczynę i skutek.
  function fmt(v) { return v.toFixed(2).replace(".", ","); }

  function countTo(el, from, to, ms) {
    var finalText = el.textContent; // dokładnie to, co policzył serwer (ROUND_HALF_UP)
    var t0 = performance.now();
    function step(now) {
      var k = Math.min(1, (now - t0) / ms);
      var e = 1 - Math.pow(1 - k, 3); // ease-out
      el.textContent = k < 1 ? fmt(from + (to - from) * e) : finalText;
      if (k < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  function flyMarker(fromRect, toEl) {
    var to = toEl.getBoundingClientRect();
    if (!to.width) return;
    var g = document.createElement("div");
    g.className = "sug-ghost";
    g.style.left = to.left + "px";
    g.style.top = to.top + "px";
    g.style.width = to.width + "px";
    g.style.height = to.height + "px";
    g.style.transform = "translate(" + (fromRect.left - to.left) + "px," + (fromRect.top - to.top) + "px) scaleX(" + (fromRect.width / to.width) + ")";
    document.body.appendChild(g);
    toEl.classList.add("sug-arriving");
    requestAnimationFrame(function () { requestAnimationFrame(function () { g.style.transform = "none"; }); });
    setTimeout(function () { g.remove(); toEl.classList.remove("sug-arriving"); }, 230);
  }

  var compassBefore = null;
  document.addEventListener("htmx:beforeSwap", function (ev) {
    var t = ev.detail.target;
    if (!t || t.id !== "compass") return;
    var sug = t.querySelector(".pt.suggested");
    compassBefore = { rect: sug ? sug.getBoundingClientRect() : null, avg: parseFloat(t.dataset.average), points: t.dataset.suggested };
  });
  document.addEventListener("htmx:afterSettle", function () {
    var c = document.getElementById("compass");
    var prev = compassBefore;
    compassBefore = null;
    if (!c || !prev || reduceMotion) return;
    var newAvg = parseFloat(c.dataset.average);
    if (c.dataset.suggested === prev.points && newAvg === prev.avg) return;
    var b = c.querySelector(".formula b");
    if (b) restart(b, "is-updated");
    var avgEl = c.querySelector(".formula .avg");
    if (avgEl && !isNaN(prev.avg) && !isNaN(newAvg)) countTo(avgEl, prev.avg, newAvg, 260);
    var sug = c.querySelector(".pt.suggested");
    if (sug && prev.rect && c.dataset.suggested !== prev.points) flyMarker(prev.rect, sug);
  });

  // Kalendarz daty w stylu Roman Pilaster (progressive enhancement dla każdego <input type="date">).
  (function () {
    var MONTHS = ["styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec", "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień"];
    var MONTHS_SHORT = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"];
    var DAYS = ["pon", "wto", "śro", "czw", "pią", "sob", "nie"];
    var ICON_SVG = '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.35" aria-hidden="true">'
      + '<rect x="1.75" y="3" width="12.5" height="11.25"/>'
      + '<path d="M1.75 6.5h12.5M5 1.5v2.75M11 1.5v2.75"/>'
      + '<rect x="4.5" y="8.75" width="2" height="2" fill="currentColor" stroke="none"/>'
      + '<rect x="7" y="8.75" width="2" height="2" fill="currentColor" stroke="none"/>'
      + '<rect x="9.5" y="8.75" width="2" height="2" fill="currentColor" stroke="none"/>'
      + '<rect x="4.5" y="11.25" width="2" height="2" fill="currentColor" stroke="none"/>'
      + '</svg>';

    function pad(n) { return n < 10 ? "0" + n : String(n); }
    function toISO(y, m, d) { return y + "-" + pad(m + 1) + "-" + pad(d); }
    function parseISO(s) {
      var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((s || "").trim());
      if (!m) return null;
      var y = +m[1], mo = +m[2] - 1, d = +m[3];
      var dt = new Date(y, mo, d);
      return dt.getFullYear() === y && dt.getMonth() === mo && dt.getDate() === d ? { y: y, m: mo, d: d } : null;
    }
    function parseUserDate(s) {
      s = (s || "").trim();
      if (!s) return "";
      var iso = parseISO(s);
      if (iso) return toISO(iso.y, iso.m, iso.d);
      var m = /^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})$/.exec(s);
      if (!m) return null;
      var d = +m[1], mo = +m[2] - 1, y = +m[3];
      var dt = new Date(y, mo, d);
      return dt.getFullYear() === y && dt.getMonth() === mo && dt.getDate() === d ? toISO(y, mo, d) : null;
    }
    function fmtPL(iso) {
      var p = parseISO(iso);
      return p ? pad(p.d) + "." + pad(p.m + 1) + "." + p.y : "";
    }
    function todayISO() {
      var t = new Date();
      return toISO(t.getFullYear(), t.getMonth(), t.getDate());
    }

    var pop = null, active = null, viewYear = 2026, viewMonth = 0, mode = "days";

    function ensurePop() {
      if (pop) return pop;
      pop = document.createElement("div");
      pop.className = "dp-pop";
      pop.setAttribute("role", "dialog");
      pop.setAttribute("aria-modal", "false");
      pop.setAttribute("aria-label", "Wybierz datę");
      pop.hidden = true;
      pop.addEventListener("mousedown", function (ev) { ev.stopPropagation(); });
      document.body.appendChild(pop);
      return pop;
    }

    function positionPop() {
      if (!pop || pop.hidden || !active) return;
      var r = active.wrap.getBoundingClientRect();
      var pw = pop.offsetWidth || 292, ph = pop.offsetHeight || 318;
      var left = Math.min(Math.max(8, r.left), window.innerWidth - pw - 8);
      var below = window.innerHeight - r.bottom;
      var top = (below >= ph + 8 || below >= r.top) ? (r.bottom + 4) : Math.max(8, r.top - ph - 4);
      pop.style.left = Math.round(left) + "px";
      pop.style.top = Math.round(top) + "px";
    }

    function closePop(restoreFocus) {
      if (!pop || pop.hidden) return;
      pop.hidden = true;
      if (active) {
        active.btn.setAttribute("aria-expanded", "false");
        if (restoreFocus) active.btn.focus();
      }
      active = null;
    }

    function selectISO(iso) {
      if (!active) return;
      active.setValue(iso, true);
      closePop(true);
    }

    function renderPop() {
      if (!pop || !active) return;
      var sel = active.native.value;
      var min = active.native.min || "";
      var max = active.native.max || "";
      var today = todayISO();

      var html = '<div class="dp-head">'
        + '<button type="button" class="dp-nav" data-dp-prev aria-label="' + (mode === "months" ? "Poprzedni rok" : "Poprzedni miesiąc") + '">↢</button>'
        + '<button type="button" class="dp-title" data-dp-mode aria-label="Zmień miesiąc lub rok">'
        + (mode === "months" ? String(viewYear) : MONTHS[viewMonth] + " " + viewYear)
        + '</button>'
        + '<button type="button" class="dp-nav" data-dp-next aria-label="' + (mode === "months" ? "Następny rok" : "Następny miesiąc") + '">↣</button>'
        + '</div>';

      if (mode === "months") {
        html += '<div class="dp-months">';
        var selP = parseISO(sel);
        for (var m = 0; m < 12; m++) {
          var isSelM = selP && selP.y === viewYear && selP.m === m;
          html += '<button type="button" class="dp-month' + (isSelM ? " is-selected" : "") + '" data-dp-m="' + m + '">' + MONTHS_SHORT[m] + '</button>';
        }
        html += '</div>';
      } else {
        html += '<div class="dp-dow">' + DAYS.map(function (d) { return '<span>' + d + '</span>'; }).join("") + '</div>';
        html += '<div class="dp-grid" role="grid">';
        var firstDow = (new Date(viewYear, viewMonth, 1).getDay() + 6) % 7; // 0 = pon
        var startDate = new Date(viewYear, viewMonth, 1 - firstDow);
        for (var i = 0; i < 42; i++) {
          var cur = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate() + i);
          var iso = toISO(cur.getFullYear(), cur.getMonth(), cur.getDate());
          var cls = "dp-day";
          if (cur.getMonth() !== viewMonth) cls += " is-out";
          if (iso === today) cls += " is-today";
          if (iso === sel) cls += " is-selected";
          var dis = (min && iso < min) || (max && iso > max);
          html += '<button type="button" class="' + cls + '" data-dp-iso="' + iso + '"'
            + (iso === sel ? ' aria-pressed="true"' : '')
            + (dis ? ' disabled' : '') + '>' + cur.getDate() + '</button>';
        }
        html += '</div>';
      }

      html += '<div class="dp-foot">'
        + '<button type="button" class="dp-clear" data-dp-clear>Wyczyść</button>'
        + '<button type="button" class="dp-today" data-dp-today>Dzisiaj</button>'
        + '</div>';

      pop.innerHTML = html;
      positionPop();
    }

    function openPop(inst) {
      ensurePop();
      if (active === inst && !pop.hidden) { closePop(false); return; }
      if (active) active.btn.setAttribute("aria-expanded", "false");
      active = inst;
      var p = parseISO(inst.native.value) || parseISO(todayISO());
      viewYear = p.y;
      viewMonth = p.m;
      mode = "days";
      pop.hidden = false;
      inst.btn.setAttribute("aria-expanded", "true");
      renderPop();
    }

    document.addEventListener("click", function (ev) {
      if (!pop || pop.hidden) return;
      var t = ev.target;
      if (pop.contains(t)) {
        if (t.closest("[data-dp-prev]")) {
          if (mode === "months") viewYear--; else { viewMonth--; if (viewMonth < 0) { viewMonth = 11; viewYear--; } }
          renderPop(); return;
        }
        if (t.closest("[data-dp-next]")) {
          if (mode === "months") viewYear++; else { viewMonth++; if (viewMonth > 11) { viewMonth = 0; viewYear++; } }
          renderPop(); return;
        }
        if (t.closest("[data-dp-mode]")) {
          mode = mode === "months" ? "days" : "months";
          renderPop(); return;
        }
        var mBtn = t.closest("[data-dp-m]");
        if (mBtn) {
          viewMonth = parseInt(mBtn.dataset.dpM, 10);
          mode = "days";
          renderPop(); return;
        }
        var dBtn = t.closest("[data-dp-iso]");
        if (dBtn && !dBtn.disabled) { selectISO(dBtn.dataset.dpIso); return; }
        if (t.closest("[data-dp-clear]")) { selectISO(""); return; }
        if (t.closest("[data-dp-today]")) { selectISO(todayISO()); return; }
        return;
      }
      if (active && active.wrap.contains(t)) return;
      closePop(false);
    });

    document.addEventListener("keydown", function (ev) {
      if (!pop || pop.hidden) return;
      if (ev.key === "Escape") { ev.preventDefault(); closePop(true); }
    });
    window.addEventListener("scroll", positionPop, true);
    window.addEventListener("resize", positionPop);

    function enhanceDate(native) {
      if (native.dataset.dpReady === "1") return;
      native.dataset.dpReady = "1";

      var wrap = document.createElement("span");
      wrap.className = "dp-wrap";

      var disp = document.createElement("input");
      disp.type = "text";
      disp.className = "dp-input";
      disp.placeholder = "dd.mm.rrrr";
      disp.autocomplete = "off";
      disp.inputMode = "numeric";
      disp.maxLength = 10;
      if (native.required) { disp.required = true; native.required = false; }
      if (native.disabled) disp.disabled = true;

      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dp-btn";
      btn.setAttribute("aria-label", "Otwórz kalendarz");
      btn.setAttribute("aria-haspopup", "dialog");
      btn.setAttribute("aria-expanded", "false");
      btn.innerHTML = ICON_SVG;
      if (native.disabled) btn.disabled = true;

      native.parentNode.insertBefore(wrap, native);
      wrap.appendChild(disp);
      wrap.appendChild(btn);
      wrap.appendChild(native);
      native.classList.add("dp-native");
      native.tabIndex = -1;
      native.setAttribute("aria-hidden", "true");

      function syncFromNative() {
        disp.value = fmtPL(native.value);
        disp.setCustomValidity("");
      }

      function setValue(iso, emit) {
        native.value = iso || "";
        disp.value = fmtPL(iso);
        disp.setCustomValidity("");
        if (emit) {
          native.dispatchEvent(new Event("input", { bubbles: true }));
          native.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }

      function commitText() {
        var res = parseUserDate(disp.value);
        if (res === null) {
          disp.setCustomValidity("Wpisz datę w formacie dd.mm.rrrr");
          return false;
        }
        if (res && ((native.min && res < native.min) || (native.max && res > native.max))) {
          disp.setCustomValidity("Data poza dopuszczalnym zakresem");
          return false;
        }
        setValue(res, native.value !== res);
        return true;
      }

      function selectParentOption() {
        var opt = wrap.closest(".option-row");
        var r = opt && opt.querySelector('input[type="radio"]');
        if (r && !r.checked) r.checked = true;
      }

      var inst = { native: native, disp: disp, btn: btn, wrap: wrap, setValue: setValue };
      syncFromNative();

      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        selectParentOption();
        openPop(inst);
      });
      disp.addEventListener("click", function () {
        selectParentOption();
        if (!pop || pop.hidden || active !== inst) openPop(inst);
      });
      disp.addEventListener("keydown", function (ev) {
        if (ev.key === "ArrowDown" || ev.key === "F4") { ev.preventDefault(); openPop(inst); }
      });
      disp.addEventListener("input", function () {
        disp.setCustomValidity("");
        var res = parseUserDate(disp.value);
        if (res !== null) native.value = res;
      });
      disp.addEventListener("blur", commitText);

      var form = native.form;
      if (form) {
        form.addEventListener("submit", function (ev) {
          if (!commitText()) { ev.preventDefault(); disp.reportValidity(); }
        }, true);
        form.addEventListener("reset", function () { setTimeout(syncFromNative, 0); });
      }
    }

    function initDates(root) {
      (root || document).querySelectorAll('input[type="date"]').forEach(enhanceDate);
    }
    document.addEventListener("DOMContentLoaded", function () { initDates(document); });
    document.addEventListener("htmx:afterSwap", function (ev) { initDates(ev.target); });
  })();

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("input[data-nobasis]").forEach(syncNoBasis);
    syncLimit();
  });
})();
