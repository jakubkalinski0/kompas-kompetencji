// Kompas Kompetencji – „Profil ocen cząstkowych” (ekran wyniku). SVG rysuje serwer (app/radar.py), tu tylko zachowanie:
//   najechanie na wycinek albo pozycję listy – oś, punkty i numer wyróżnione, reszta przygaszona, dymek z wartościami;
//   kliknięcie / Enter – wybór kryterium i szczegóły pod wykresem (wjeżdżają z kierunku ruchu);
//   strzałki na liście – poprzednie / następne kryterium; legenda – najechanie wyróżnia warstwę, kliknięcie ją chowa.
// Wycinek „tu jesteś” obraca się najkrótszym łukiem (przejście CSS – przerywalne).
(function () {
  "use strict";

  function init(root) {
    var svg = root.querySelector(".radar-svg");
    if (!svg) return;
    var fig = root.querySelector(".radar-figure");
    var side = root.querySelector(".radar-side");
    var detailsWrap = root.querySelector(".radar-details");
    var tip = root.querySelector(".radar-tip");
    var items = Array.prototype.slice.call(root.querySelectorAll(".ri"));
    var details = Array.prototype.slice.call(root.querySelectorAll(".crit-detail"));
    var turners = [svg.querySelector(".r-focus")].filter(Boolean);
    var n = items.length, step = 360 / n;
    var selected = parseInt(root.getAttribute("data-select"), 10) || 0, hot = null, rot = selected * step, tipFor = null;

    function marks(i) { return svg.querySelectorAll('[data-axis="' + i + '"]'); }
    function each(list, fn) { Array.prototype.forEach.call(list, fn); }

    function turnTo(i) {                          // najkrótszy łuk: kąt rośnie bez ograniczeń, więc CSS nie kręci „dookoła”
      var target = i * step, cur = ((rot % 360) + 360) % 360;
      var d = ((target - cur + 540) % 360) - 180;
      rot += d;
      turners.forEach(function (el) { el.style.setProperty("--rot", rot + "deg"); });
    }

    function setHot(i) {
      if (i === hot) return;
      if (hot !== null) each(marks(hot), function (el) { el.classList.remove("is-hot"); });
      hot = i;
      svg.classList.toggle("has-hot", i !== null);
      items.forEach(function (b, k) { b.classList.toggle("is-hot", k === i); });
      if (i !== null) each(marks(i), function (el) { el.classList.add("is-hot"); });
      turnTo(i === null ? selected : i);
      if (i === null) hideTip(); else showTip(i);
    }

    function select(i, fromKey) {
      if (i < 0 || i >= n) return;
      var prev = selected;
      selected = i;
      each(svg.querySelectorAll(".is-sel"), function (el) { el.classList.remove("is-sel"); });
      each(marks(i), function (el) { el.classList.add("is-sel"); });
      items.forEach(function (b, k) { b.setAttribute("aria-pressed", k === i ? "true" : "false"); });
      details.forEach(function (d, k) {
        var on = k === i;
        if (on && d.hidden) {
          d.hidden = false;
          d.style.setProperty("--from", (i > prev ? 1 : -1) * 14 + "px");
          d.classList.remove("is-entering");
          void d.offsetWidth;
          d.classList.add("is-entering");
        } else if (!on) d.hidden = true;
      });
      if (hot === null) turnTo(i);
      if (fromKey) items[i].focus();
    }

    function anchor(i) {                          // punkt decyzji, a gdy go brak – sugestii, a gdy i jej brak – numer osi
      var el = svg.querySelector('.r-dp[data-axis="' + i + '"]') || svg.querySelector('.r-sp[data-axis="' + i + '"]') ||
               svg.querySelector('.r-lab[data-axis="' + i + '"] rect');
      var b = el.getBoundingClientRect();
      return { x: b.left + b.width / 2, y: b.top + b.height / 2 };
    }

    function line(cls, text) { var p = document.createElement("p"); p.className = cls; p.textContent = text; return p; }

    function showTip(i) {
      var b = items[i], ds = b.dataset;
      if (tipFor !== i) {
        tip.textContent = "";
        var head = line("tip-name", "");
        var no = document.createElement("span"); no.className = "tip-no"; no.textContent = ds.no;
        head.appendChild(no); head.appendChild(document.createTextNode(ds.name));
        tip.appendChild(head);
        tip.appendChild(line("tip-dec" + (ds.alert ? " alert" : ""), ds.dec ? ds.dec + " pkt · " + ds.decLabel : "brak decyzji"));
        var sugText = ds.sug ? "sugestia " + ds.sug + " pkt" + (ds.dec && ds.sug !== ds.dec ? " – decyzja inna" : "") : "brak sugestii";
        tip.appendChild(line("tip-sug", sugText));
        if (i !== selected) tip.appendChild(line("tip-hint", "kliknij, aby zobaczyć szczegóły"));
        tipFor = i;
      }
      var a = anchor(i), f = fig.getBoundingClientRect(), svgBox = svg.getBoundingClientRect();
      var sideBox = side ? side.getBoundingClientRect() : null;
      var detBox = detailsWrap ? detailsWrap.getBoundingClientRect() : null;
      var bar = document.querySelector(".topbar");
      var w = tip.offsetWidth, h = tip.offsetHeight;
      var cx = svgBox.left + svgBox.width / 2, cy = svgBox.top + svgBox.height / 2;

      var sideRight = !!(sideBox && sideBox.width > 0 && sideBox.left >= f.right - 4);
      var sideBelow = !!(sideBox && sideBox.height > 0 && !sideRight && sideBox.top >= f.bottom - 4);

      var minLeft = 8;
      var maxLeft = (sideRight ? Math.min(window.innerWidth - 8, sideBox.left - 12) : window.innerWidth - 8) - w;
      if (maxLeft < minLeft) maxLeft = minLeft;

      var minTop = (bar ? Math.round(bar.getBoundingClientRect().bottom) + 8 : 70);
      var bottomCeil = window.innerHeight - 8;
      if (sideBelow) bottomCeil = Math.min(bottomCeil, sideBox.top - 12);
      else if (detBox && detBox.top - minTop >= h + 24) bottomCeil = Math.min(bottomCeil, detBox.top - 8);
      var maxTop = bottomCeil - h;
      if (maxTop < minTop) maxTop = minTop;

      function clamp(x, y) {
        return {
          left: Math.max(minLeft, Math.min(x, maxLeft)),
          top: Math.max(minTop, Math.min(y, maxTop))
        };
      }
      function coversAnchor(pos) {
        return a.x >= pos.left - 8 && a.x <= pos.left + w + 8 && a.y >= pos.top - 8 && a.y <= pos.top + h + 8;
      }

      // Kolejność kandydatów: na zewnątrz punktu (ale bez wchodzenia w .radar-side), potem góra/dół lub druga strona.
      var candidates = [];
      if (Math.abs(a.x - cx) < 16) {
        if (a.y <= cy) candidates.push([a.x - w / 2, a.y - h - 18], [a.x - w - 18, a.y - h / 2], [a.x + 18, a.y - h / 2]);
        else candidates.push([a.x - w - 18, a.y - h / 2], [a.x - w / 2, a.y + 18], [a.x - w / 2, a.y - h - 18]);
      } else if (a.x < cx) {
        candidates.push([a.x - w - 18, a.y - h / 2], [a.x - w / 2, a.y - h - 18], [a.x - w / 2, a.y + 18], [a.x + 18, a.y - h / 2]);
      } else {
        // Prawa połowa wykresu: jeśli po prawej jest tabela kryteriów, od razu kieruj dymek na lewo/górę/dół od punktu.
        if (!sideRight && a.x + 18 + w <= maxLeft + w) candidates.push([a.x + 18, a.y - h / 2]);
        candidates.push([a.x - w - 18, a.y - h / 2], [a.x - w / 2, a.y - h - 18], [a.x - w / 2, a.y + 18]);
      }

      var chosen = null;
      for (var c = 0; c < candidates.length; c++) {
        var rawX = candidates[c][0], rawY = candidates[c][1];
        var p = clamp(rawX, rawY);
        var shifted = Math.abs(p.left - rawX) > 24 || Math.abs(p.top - rawY) > 24;
        if (!coversAnchor(p) && !shifted) { chosen = p; break; }
        if (!chosen && !coversAnchor(p)) chosen = p;
      }
      if (!chosen) chosen = clamp(candidates[0][0], candidates[0][1]);
      var left = chosen.left, top = chosen.top;
      var t = "translate(" + Math.round(left - f.left) + "px," + Math.round(top - f.top) + "px)";
      if (!tip.classList.contains("is-on")) {          // pierwsze pokazanie: na miejscu, bez przelotu z rogu
        tip.style.transition = "none";
        tip.style.transform = t;
        void tip.offsetWidth;
        tip.style.transition = "";
        tip.classList.add("is-on");
      } else tip.style.transform = t;                 // kolejne: dymek płynie za wyborem
    }
    function hideTip() { tip.classList.remove("is-on"); tipFor = null; }

    // wykres: wycinki osi łapią najechanie i kliknięcie
    svg.addEventListener("pointerover", function (e) {
      var h = e.target.closest(".r-hit");
      if (h) setHot(parseInt(h.getAttribute("data-axis"), 10));
    });
    svg.addEventListener("pointerleave", function () { setHot(null); });
    svg.addEventListener("click", function (e) {
      var h = e.target.closest(".r-hit");
      if (h) { select(parseInt(h.getAttribute("data-axis"), 10)); tipFor = null; if (hot !== null) showTip(hot); }
    });

    // lista: to samo z klawiatury i myszy
    items.forEach(function (b, i) {
      b.addEventListener("pointerenter", function () { setHot(i); });
      b.addEventListener("pointerleave", function () { setHot(null); });
      b.addEventListener("focus", function () { setHot(i); });
      b.addEventListener("blur", function () { setHot(null); });
      b.addEventListener("click", function () { select(i); tipFor = null; if (hot !== null) showTip(hot); });
      b.addEventListener("keydown", function (e) {
        var k = e.key, j = null;
        if (k === "ArrowDown" || k === "ArrowRight") j = (i + 1) % n;
        else if (k === "ArrowUp" || k === "ArrowLeft") j = (i - 1 + n) % n;
        else if (k === "Home") j = 0;
        else if (k === "End") j = n - 1;
        if (j !== null) { e.preventDefault(); select(j, true); }
      });
    });

    // legenda: najechanie wyróżnia warstwę, kliknięcie ją chowa (co najmniej jedna zostaje widoczna)
    Array.prototype.forEach.call(root.querySelectorAll(".lg[data-layer]"), function (btn) {
      var layer = btn.getAttribute("data-layer"), other = layer === "dec" ? "sug" : "dec";
      btn.addEventListener("pointerenter", function () { svg.classList.add("solo-" + layer); });
      btn.addEventListener("pointerleave", function () { svg.classList.remove("solo-" + layer); });
      btn.addEventListener("click", function () {
        var on = btn.getAttribute("aria-pressed") !== "false";
        if (on && svg.classList.contains("hide-" + other)) return;
        btn.setAttribute("aria-pressed", on ? "false" : "true");
        svg.classList.toggle("hide-" + layer, on);
      });
    });

    window.addEventListener("scroll", function () { if (hot !== null) showTip(hot); }, { passive: true });
    select(selected);
  }

  function boot() { document.querySelectorAll("[data-radar]").forEach(init); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
