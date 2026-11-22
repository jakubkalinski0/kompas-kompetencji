// Kompas Kompetencji – tło „pole magnetyczne” (Canvas 2D, bez bibliotek).
// Warstwy:
//   1) ziarno papieru – rzadkie plamki, które jadą razem z treścią;
//   2) warstwice wolno dryfującego pola, drukowane rastrem stochastycznym jak mapa topograficzna
//      (co piąta grubsza – jak warstwica zasadnicza); maska gęstości sprawia, że w jednych miejscach są pełne,
//      w innych rozsypują się w kropki;
//   3) rzadkie ultramarynowe „szczyty” – raster tam, gdzie pole jest najwyżej.
// Kursor jest biegunem: podnosi pole, więc warstwice układają się wokół niego w pierścienie (z opóźnieniem
// sprężyny) – to ten sam punkt, który wskazuje igła kompasu z art.js. Przewijanie: pole jedzie wolniej niż treść
// (głębia), w głębi strony warstwice gęstnieją, a szybki ruch na chwilę zakłóca rzędy jak sygnał.
// Koszt: pole liczone na rzadkiej siatce (co 2 komórki) i interpolowane; najwyżej 30 kl./s i tylko kilka sekund
// po ostatniej interakcji; zegar pola stoi, gdy nic się nie dzieje (bez skoku po powrocie), w ukrytej karcie nic.
// Dotyk: bez bieguna, tylko przewijanie. prefers-reduced-motion: jedna statyczna klatka.
(function () {
  "use strict";
  if (!window.HTMLCanvasElement || !window.Uint32Array) return;
  function mm(q) { return !!(window.matchMedia && window.matchMedia(q).matches); }
  var reduce = mm("(prefers-reduced-motion: reduce)");
  var hover = mm("(hover: hover) and (pointer: fine)");

  /* ---------------------------------------------------------------- szum wartości 128×128 (stałe ziarno: to samo pole na każdej stronie) */
  var NS = 128, NM = NS - 1, NT = new Float32Array(NS * NS);
  (function () {
    var s = 20261121;
    for (var i = 0; i < NT.length; i++) {
      s = (s + 0x6d2b79f5) | 0;
      var t = Math.imul(s ^ (s >>> 15), 1 | s);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      NT[i] = ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    }
  })();
  function noise(x, y) {
    var xi = Math.floor(x), yi = Math.floor(y), xf = x - xi, yf = y - yi;
    var u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    var x0 = xi & NM, y0 = (yi & NM) * NS, x1 = (x0 + 1) & NM, y1 = (((yi + 1) & NM)) * NS;
    var a = NT[y0 + x0], b = NT[y0 + x1], c = NT[y1 + x0], d = NT[y1 + x1];
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  }
  function rgb(name, fb) {
    var m = /#([0-9a-f]{6})/i.exec(getComputedStyle(document.documentElement).getPropertyValue(name) || "");
    var n = m ? parseInt(m[1], 16) : fb;
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function pack(c, a) { return ((a << 24) | (c[2] << 16) | (c[1] << 8) | c[0]) >>> 0; } // RGBA little-endian

  // komórka pola = 4 px CSS; płótno ma 2×2 podpiksele na komórkę, żeby kropka rastra mogła mieć 1, 2 albo 4 podpiksele
  // (modulacja wielkości punktu jak w druku: środek warstwicy grubszy, brzegi drobniejsze)
  var wrap, cv, ctx, img, buf, dpr = 1, cell = 4, gw = 0, gh = 0, W2 = 0, S = 2, cw = 0, ch = 0, C, M, P, thrA, thrB;
  var COL = {};
  var ptr = { x: 0, y: 0, tx: 0, ty: 0, k: 0, tk: 0 }; // biegun: pozycja wygładzona, docelowa, siła
  var scr = { y: window.scrollY, amp: 0 };
  var clock = 0, raf = 0, lastDraw = 0, lastTick = 0, awakeUntil = 0;
  var frameGap = 33, cost = 0;                     // 30 kl./s; gdy klatka jest droga (duży ekran, słaby komputer) – 20 kl./s

  function setup() {
    wrap = document.createElement("div");
    wrap.className = "field-wrap";
    wrap.setAttribute("aria-hidden", "true");
    cv = document.createElement("canvas");
    wrap.appendChild(cv);
    document.body.insertBefore(wrap, document.body.firstChild);
    ctx = cv.getContext("2d");
    if (!ctx) return false;
    var ink = rgb("--ink", 0x181712), blue = rgb("--blue-art", 0x2f2dd9);
    // tło ma być rzadkie i ciche (czytają z niego kadry): jaśniejsze kropki niż w pierwszej wersji
    COL = { line: pack(ink, 46), index: pack(ink, 64), grain: pack(ink, 32), blue: pack(blue, 84) };
    try { // ciągłość między stronami: zegar pola i ostatni biegun
      var saved = JSON.parse(sessionStorage.getItem("kk-field") || "null");
      if (saved) {
        clock = +saved.c || 0;
        if (hover && saved.k > 0.05) { ptr.x = ptr.tx = saved.x; ptr.y = ptr.ty = saved.y; ptr.k = saved.k; ptr.tk = 1; }
      }
    } catch (e) { /* bez sessionStorage pole startuje od zera */ }
    document.documentElement.classList.add("has-field");
    resize();
    return true;
  }

  function resize() {
    dpr = window.devicePixelRatio || 1;
    cell = 2 * Math.max(1, Math.round(2 * dpr)); // ≈ 4 px CSS, parzysta liczba pikseli urządzenia (podpiksel = cell / 2)
    gw = Math.ceil(window.innerWidth * dpr / cell);
    gh = Math.ceil(window.innerHeight * dpr / cell);
    if (!gw || !gh) return;
    W2 = gw * 2;
    cv.width = W2;
    cv.height = gh * 2;
    cv.style.width = (gw * cell / dpr) + "px";
    cv.style.height = (gh * cell / dpr) + "px";
    img = ctx.createImageData(W2, gh * 2);
    buf = new Uint32Array(img.data.buffer);
    cw = Math.ceil(gw / S) + 3;
    ch = Math.ceil(gh / S) + 3;
    C = new Float32Array(cw * ch);
    M = new Float32Array(cw * ch);
    P = new Float32Array(cw * ch);
    thrA = new Float32Array(gw * gh);
    thrB = new Float32Array(gw * gh);
    for (var j = 0, q = 0; j < gh; j++) for (var i = 0; i < gw; i++, q++) {
      // interleaved gradient noise: ziarno stochastyczne, stabilne między klatkami (bez migotania)
      var a = 52.9829189 * ((0.06711056 * i + 0.00583715 * j) % 1);
      var b = 52.9829189 * ((0.06711056 * (j + 23) + 0.00583715 * (i + 61)) % 1);
      thrA[q] = a - Math.floor(a);
      thrB[q] = b - Math.floor(b);
    }
  }

  function draw() {
    if (!buf) return;
    var t = clock, cssCell = cell / dpr, step = S * cssCell, sy = window.scrollY;
    var maxScroll = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    var L = 5 + 2 * Math.min(1, sy / maxScroll);    // kilka warstwic na ekran; w głębi strony nieco więcej
    var par = sy * 0.3;                              // pole jedzie wolniej niż treść
    var pk = ptr.k * 0.14, px = ptr.x, py = ptr.y, sig2 = 2 * 140 * 140, reach2 = 9 * 140 * 140, lens2 = 2 * 230 * 230;

    // 1) rzadka siatka: wartość pola (z biegunem), maska gęstości i „soczewka” wokół kursora; węzeł i ↔ x CSS = (i - 1) · step
    for (var j = 0; j < ch; j++) {
      var Y = (j - 1) * step, y = (Y + par) / 600;
      for (var i = 0; i < cw; i++) {
        var X = (i - 1) * step, x = X / 600;
        var wx = noise(x * 0.8 + 17.3 + t * 0.006, y * 0.8 - t * 0.004) - 0.5;
        var wy = noise(x * 0.8 - 9.1 - t * 0.005, y * 0.8 + 31.7 + t * 0.003) - 0.5;
        var v = noise(x + wx * 1.2 + t * 0.010, y + wy * 1.2 - t * 0.007) * 0.7 +
                noise(x * 2.2 - t * 0.008 + 50.5, y * 2.2 + wx + 50.5) * 0.3;
        var k = j * cw + i, lens = 0;
        if (pk > 0.002) {
          var dx = X - px, dy = Y - py, d2 = dx * dx + dy * dy;
          if (d2 < reach2) v += pk * Math.exp(-d2 / sig2);
          if (d2 < 4 * lens2) lens = ptr.k * Math.exp(-d2 / lens2);
        }
        C[k] = v;
        M[k] = noise(x * 0.33 + 80 - t * 0.003, y * 0.33 + 80);
        P[k] = lens;
      }
    }

    // 2) komórki: warstwica, gdy odległość od najbliższego poziomu (w komórkach) jest mniejsza niż pół grubości.
    //    Kropka: 1, 2 albo 4 podpiksele zależnie od natężenia; położenie pojedynczej kropki losowe w komórce (raster stochastyczny).
    buf.fill(0);
    var off = Math.floor(sy * dpr / cell);           // ziarno jedzie razem z treścią
    var amp = scr.amp, ph = t * 9, col = COL, W = W2;
    for (var fj = 0, q = 0; fj < gh; fj++) {
      var shift = amp > 0.15 ? amp * Math.sin(fj * 0.23 + ph) : 0; // zakłócenie rzędów przy szybkim przewijaniu
      var gy = (fj + 0.5) / S + 1, y0 = gy | 0, fy = gy - y0, r0 = y0 * cw, r1 = r0 + cw, row = 2 * fj * W;
      for (var fi = 0; fi < gw; fi++, q++) {
        var gx = (fi + 0.5 + shift) / S + 1;
        if (gx < 0) gx = 0; else if (gx > cw - 2) gx = cw - 2;
        var x0 = gx | 0, fx = gx - x0;
        var c00 = C[r0 + x0], c10 = C[r0 + x0 + 1], c01 = C[r1 + x0], c11 = C[r1 + x0 + 1];
        var top = c00 + (c10 - c00) * fx, bot = c01 + (c11 - c01) * fx;
        var v2 = top + (bot - top) * fy;
        var m = M[r0 + x0] + (M[r1 + x0 + 1] - M[r0 + x0]) * 0.5 * (fx + fy);
        var dens = m < 0.34 ? 0.34 : (m > 0.66 ? 0.72 : 0.34 + 0.38 * (m - 0.34) / 0.32); // mało linii, ale każda czytelna jako kropkowana
        var lens = P[r0 + x0];
        if (lens > 0.01) dens = dens + (0.6 - dens) * lens * 0.6; // przy kursorze warstwice nieco gęstnieją
        var b = row + 2 * fi, color = 0, size = 0;
        // pochodna interpolacji dwuliniowej → przyrost poziomu na komórkę
        var gX = ((c10 - c00) * (1 - fy) + (c11 - c01) * fy) * L / S;
        var gY = (bot - top) * L / S;
        var g = Math.sqrt(gX * gX + gY * gY);
        if (g > 0.0008 && g < 0.5) {
          var c = v2 * L, lvl = Math.floor(c + 0.5), dist = Math.abs(c - lvl) / g;
          var index = lvl % 5 === 0, half = index ? 0.8 : 0.6;
          if (dist < half) {
            var it = (1 - dist / half) * dens;
            if (it > thrA[q]) { color = index ? col.index : col.line; size = 1; }
          }
        }
        if (!color && v2 > 0.78) {                   // ultramarynowe szczyty: rzadkie i lekkie
          var pv = (v2 - 0.78) * 8;
          pv = (pv > 1 ? 1 : pv) * 0.35 * dens;
          if (pv > thrB[q] * 0.6) { color = col.blue; size = 1; }
        }
        if (!color) {                                // ziarno papieru
          var h = Math.imul(fi * 374761393 + (fj + off) * 668265263, 1274126177);
          h = (h ^ (h >>> 13)) >>> 0;
          if (h % 1000 > 998) { color = col.grain; size = 1; }
        }
        if (color) {
          if (size === 4) { buf[b] = buf[b + 1] = buf[b + W] = buf[b + W + 1] = color; }
          else if (size === 2) { buf[b] = buf[b + W + 1] = color; }
          else { var s = (thrB[q] * 4) | 0; buf[b + (s & 1) + (s >> 1) * W] = color; }
        }
      }
    }
    ctx.putImageData(img, 0, 0);
  }

  function tick(now) {
    raf = 0;
    var dt = lastTick ? Math.min(0.05, (now - lastTick) / 1000) : 1 / 60;
    lastTick = now;
    clock += dt;                                     // zegar pola biegnie tylko, gdy pole żyje
    var e = 1 - Math.pow(0.0025, dt);                // sprężyste dociąganie bieguna, niezależne od kl./s
    ptr.x += (ptr.tx - ptr.x) * e;
    ptr.y += (ptr.ty - ptr.y) * e;
    ptr.k += (ptr.tk - ptr.k) * (1 - Math.pow(0.02, dt));
    scr.amp *= Math.pow(0.03, dt);
    var settling = Math.abs(ptr.tx - ptr.x) > 0.5 || Math.abs(ptr.ty - ptr.y) > 0.5 || Math.abs(ptr.tk - ptr.k) > 0.01 || scr.amp > 0.15;
    if (now - lastDraw >= frameGap) {
      lastDraw = now;
      var a = performance.now();
      draw();
      cost = cost * 0.8 + (performance.now() - a) * 0.2;
      frameGap = cost > 9 ? 50 : 33;
    }
    if (now < awakeUntil || settling) raf = requestAnimationFrame(tick);
    else lastTick = 0;
  }
  function wake(ms) {
    awakeUntil = Math.max(awakeUntil, performance.now() + ms);
    if (!raf && !document.hidden) raf = requestAnimationFrame(tick);
  }

  function init() {
    if (!document.body || !setup()) return;
    draw();
    var resizeQueued = false;
    window.addEventListener("resize", function () {
      if (resizeQueued) return;
      resizeQueued = true;
      requestAnimationFrame(function () { resizeQueued = false; resize(); draw(); });
    });
    if (reduce) return;                              // bez ruchu: jedna klatka, przerysowana tylko przy zmianie rozmiaru
    if (hover) {
      document.addEventListener("pointermove", function (ev) {
        if (ev.pointerType && ev.pointerType !== "mouse" && ev.pointerType !== "pen") return;
        if (ptr.k < 0.02) { ptr.x = ev.clientX; ptr.y = ev.clientY; } // biegun pojawia się tam, gdzie kursor
        ptr.tx = ev.clientX;
        ptr.ty = ev.clientY;
        ptr.tk = 1;
        wake(3500);
      }, { passive: true });
      document.documentElement.addEventListener("pointerleave", function () { ptr.tk = 0; wake(1500); });
    }
    window.addEventListener("scroll", function () {
      var y = window.scrollY, dy = Math.abs(y - scr.y);
      scr.y = y;
      if (dy > 30) scr.amp = Math.min(1.5, scr.amp + dy * 0.006); // tylko szybkie przewijanie, lekko
      wake(2500);
    }, { passive: true });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) wake(1500); });
    window.addEventListener("pagehide", function () {
      try { sessionStorage.setItem("kk-field", JSON.stringify({ c: clock, x: ptr.x, y: ptr.y, k: ptr.k })); } catch (e) { /* trudno */ }
    });
    wake(5000);                                      // po wejściu pole chwilę dryfuje, potem zastyga
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
