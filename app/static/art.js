// Kompas Kompetencji – reaktywny kompas na <canvas> (bez bibliotek):
//   [data-art]  – ditherowany kompas (tarcza w antycznym mosiądzu --blue-art, rozrzucone kwadraciki w Oxbloodzie --blue):
//                 igła na sprężynie szuka kursora albo elementu z fokusem klawiatury, bloki odsuwają się o jedno pole siatki.
//                 Bez kursora igła wraca na północ. Na stronie błędu (data-art="lost") igła nie ma północy.
//   [data-mark] – miniaturowy znak w nagłówku (22×22 px): ta sama sprężyna, obrót po najechaniu, ciągłość w sessionStorage.
// Rysujemy tylko, gdy coś się rusza; poza ekranem i w ukrytej karcie nic nie liczymy.
// Przy prefers-reduced-motion: reduce – jedna statyczna klatka, bez nasłuchiwania kursora.
(function () {
  "use strict";

  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ================================================================ glify stron świata (N/E/S/W na tarczy kompasu) */
  var CARDINALS = {
    N: "#...#|#...#|##..#|#.#.#|#..##|#...#|#...#",
    E: "#####|#....|#....|####.|#....|#....|#####",
    S: ".####|#....|#....|.###.|....#|....#|####.",
    W: "#...#|#...#|#...#|#.#.#|#.#.#|#.#.#|.#.#."
  };

  function glyph(ch) {
    var src = CARDINALS[ch];
    if (!src) return null;
    var rows = src.split("|"), px = [];
    rows.forEach(function (r, y) { for (var x = 0; x < r.length; x++) if (r.charAt(x) === "#") px.push([x, y]); });
    return { w: rows[0].length, px: px };
  }

  /* ================================================================ ditherowany kompas */
  function hexToRgb(v, fallback) {
    var m = /#([0-9a-f]{6})/i.exec(v || "");
    if (!m) return fallback;
    var n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function pack(c) { return ((255 << 24) | (c[2] << 16) | (c[1] << 8) | c[0]) >>> 0; } // RGBA little-endian

  function mulberry(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
      var t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function wrapAngle(a) { while (a > Math.PI) a -= 2 * Math.PI; while (a < -Math.PI) a += 2 * Math.PI; return a; }

  var pointer = null;   // ostatnia pozycja kursora (clientX/Y) albo środek elementu z fokusem (wtedy kb: true)
  var arts = [];

  // Igła: tłumiona sprężyna (ζ ≈ 0,5) – lekko „pływa” jak prawdziwa igła magnetyczna. Wspólna dla grafiki i znaku.
  function spring(o, target, dt) {
    var diff = wrapAngle(target - o.theta);
    o.omega += (26 * diff - 5.2 * o.omega) * dt;
    o.theta = wrapAngle(o.theta + o.omega * dt);
    return Math.abs(diff) > 0.002 || Math.abs(o.omega) > 0.002;
  }
  // Kierunek igły z osi (x, y) w px ekranu; w promieniu dead wokół osi igła stoi.
  function aim(o, x, y, dead) {
    if (o.mode === "lost") { // strona błędu: igła nie ma północy
      o.wander += 0.016;
      return o.theta + Math.sin(o.wander * 1.7) * 1.4 + Math.sin(o.wander * 0.43) * 2.2;
    }
    if (!pointer) return 0;
    var px = pointer.x - x, py = pointer.y - y;
    if (px * px + py * py < dead * dead) return o.theta;
    return Math.atan2(px, -py);
  }

  function Art(el) {
    var css = getComputedStyle(document.documentElement);
    this.el = el;
    this.mode = el.getAttribute("data-art") || "compass";
    this.cfg = { cx: parseFloat(el.dataset.cx || "0.5"), cy: parseFloat(el.dataset.cy || "0.5"), r: parseFloat(el.dataset.r || "0.42"),
                 seed: parseInt(el.dataset.seed || "7", 10), blocks: el.dataset.blocks !== "0",
                 keepLeft: parseFloat(el.dataset.keepLeft || "0") }; // część szerokości od lewej bez bloków (tam stoi tekst)
    this.col = {
      ink: pack(hexToRgb(css.getPropertyValue("--blue-art"), [124, 92, 30])),
      block: pack(hexToRgb(css.getPropertyValue("--blue"), [92, 16, 34])),
      paper: pack(hexToRgb(css.getPropertyValue("--paper"), [244, 241, 234])),
      moss: pack(hexToRgb(css.getPropertyValue("--moss"), [242, 234, 215]))
    };
    this.canvas = document.createElement("canvas");
    this.canvas.setAttribute("aria-hidden", "true");
    el.appendChild(this.canvas);
    this.ctx = this.canvas.getContext("2d");
    this.theta = reduce ? 0 : -2.35;  // na starcie igła odchylona – przy wejściu „szuka” północy
    this.omega = 0;
    this.visible = true;
    this.blocks = [];
    this.raf = 0;
    this.last = 0;
    this.wander = 0;
    this.resize();
    var self = this;
    if (window.ResizeObserver) new ResizeObserver(function () { self.resize(); }).observe(el);
    if (window.IntersectionObserver) new IntersectionObserver(function (es) {
      self.visible = es[0].isIntersecting;
      if (self.visible) self.kick();
    }).observe(el);
    if (!reduce && this.cfg.blocks) this.scheduleHop();
  }

  Art.prototype.resize = function () {
    var rect = this.el.getBoundingClientRect();
    if (rect.width < 4 || rect.height < 4) return;
    var dpr = window.devicePixelRatio || 1, cell = Math.max(2, Math.round(3 * dpr)); // komórka ≈ 3 px CSS, całkowita w pikselach urządzenia
    var gw = Math.floor(rect.width * dpr / cell), gh = Math.floor(rect.height * dpr / cell);
    if (gw === this.gw && gh === this.gh) return;
    this.gw = gw; this.gh = gh; this.cell = cell; this.dpr = dpr;
    this.canvas.width = gw; this.canvas.height = gh;
    this.canvas.style.width = (gw * cell / dpr) + "px";
    this.canvas.style.height = (gh * cell / dpr) + "px";
    this.img = this.ctx.createImageData(gw, gh);
    this.frame = new Uint32Array(this.img.data.buffer);
    this.base = new Uint32Array(gw * gh);
    this.thr = new Float32Array(gw * gh);
    for (var j = 0; j < gh; j++) for (var i = 0; i < gw; i++) {
      // interleaved gradient noise – ziarno jak w rastrze stochastycznym, stabilne między klatkami (bez migotania)
      var t = 52.9829189 * ((0.06711056 * i + 0.00583715 * j) % 1);
      this.thr[j * gw + i] = t - Math.floor(t);
    }
    this.cx = this.cfg.cx * gw;
    this.cy = this.cfg.cy * gh;
    this.R = this.cfg.r * gh;
    this.buildStatic();
    this.buildBlocks();
    this.draw();
  };

  // Gęstość „tuszu” 0..1 dla nieruchomej części: obrys, pierścień z podziałką, wklęsła tarcza, róża wiatrów, litery N/E/S/W.
  Art.prototype.buildStatic = function () {
    var gw = this.gw, gh = this.gh, R = this.R, cx = this.cx, cy = this.cy, dens = new Float32Array(gw * gh);
    var DEG = 180 / Math.PI, lx = -0.62, ly = -0.78; // światło z lewej góry
    for (var j = 0; j < gh; j++) for (var i = 0; i < gw; i++) {
      var dx = (i + 0.5 - cx) / R, dy = (j + 0.5 - cy) / R, r = Math.sqrt(dx * dx + dy * dy), d = 0;
      if (r > 1.035) { dens[j * gw + i] = 0; continue; }
      var a = Math.atan2(dx, -dy), deg = (a * DEG + 360) % 360, cellDeg = DEG / Math.max(1, r * R);
      var toward = r > 0 ? (dx * lx + dy * ly) / r : 0;
      if (r >= 1.0) d = 1;
      else if (r >= 0.86) {
        d = 0.5 + 0.34 * toward;                          // wypukły pierścień: ciemniej po stronie cienia
        var n5 = deg % 5, n30 = deg % 30;
        n5 = Math.min(n5, 5 - n5); n30 = Math.min(n30, 30 - n30);
        if (r > 0.885 && r < 0.97 && n5 < 0.55 * cellDeg) d = 0;
        if (r > 0.875 && r < 0.985 && n30 < 1.05 * cellDeg) d = 0;
      } else {
        var k = r / 0.86;
        d = 0.05 + 0.42 * k * k * k * Math.max(0, toward);  // wklęsła tarcza: ściana od strony światła w cieniu
        if (r > 0.84) d = 0.92;                           // krawędź tarczy
        // róża wiatrów: 4 główne i 4 pośrednie ramiona, każde z jasną i ciemną połową
        var main = ((deg % 90) + 90) % 90, off = main > 45 ? main - 90 : main;
        var mid = (((deg - 45) % 90) + 90) % 90, off2 = mid > 45 ? mid - 90 : mid;
        var e1 = 0.1 + 0.54 * Math.max(0, 1 - Math.abs(off) / 22);
        var e2 = 0.08 + 0.3 * Math.max(0, 1 - Math.abs(off2) / 22);
        if (r < e1) d = off >= 0 ? 0.5 : 0.14;           // róża jaśniejsza niż igła – igła ma dominować
        else if (r < e2) d = off2 >= 0 ? 0.34 : 0.08;
        if (dx + dy > -0.86 && dx + dy < -0.68 && r < 0.8) d *= 0.25; // refleks na szkle
      }
      dens[j * gw + i] = d;
    }
    // litery stron świata – z jasną obwódką, żeby czytały się na rastrze
    var scale = R > 80 ? 2 : 1, self = this;
    [["N", 0, -0.755], ["E", 0.755, 0], ["S", 0, 0.755], ["W", -0.755, 0]].forEach(function (L) {
      var g = glyph(L[0]), gx = Math.round(cx + L[1] * R - g.w * scale / 2), gy = Math.round(cy + L[2] * R - 3.5 * scale);
      for (var y = -1; y <= 7 * scale; y++) for (var x = -1; x <= g.w * scale; x++) self.setD(dens, gx + x, gy + y, 0);
      g.px.forEach(function (p) {
        for (var sy = 0; sy < scale; sy++) for (var sx = 0; sx < scale; sx++) self.setD(dens, gx + p[0] * scale + sx, gy + p[1] * scale + sy, 1);
      });
    });
    for (var q = 0; q < gw * gh; q++) this.base[q] = dens[q] > this.thr[q] ? this.col.ink : 0;
  };
  Art.prototype.setD = function (dens, x, y, v) { if (x >= 0 && y >= 0 && x < this.gw && y < this.gh) dens[y * this.gw + x] = v; };

  // Piksele-bloki na wspólnej siatce: kaskada schodkami + pojedyncze kwadraciki wokół tarczy (Oxblood, trawertyn, pergamin).
  Art.prototype.buildBlocks = function () {
    this.blocks = [];
    if (!this.cfg.blocks) return;
    var rnd = mulberry(this.cfg.seed), B = Math.max(4, Math.round(this.R * 0.12)), Rb = this.R / B, list = [], seen = {};
    var minBi = (this.cfg.keepLeft * this.gw - this.cx) / B, maxBj = (this.gh - this.cy) / B;
    this.B = B;
    function add(bi, bj) {
      var key = bi + ":" + bj;
      if (seen[key] || bi < minBi || bj > maxBj) return;
      seen[key] = 1;
      var k = rnd();
      list.push({ bi: bi, bj: bj, kind: k < 0.74 ? 0 : (k < 0.93 ? 1 : 2), ox: 0, oy: 0, vx: 0, vy: 0, tx: 0, ty: 0 });
    }
    var x = Math.round(Rb * 0.35), y = Math.round(-Rb * 1.3);
    for (var s = 0; s < 22; s++) {               // kaskada z prawej góry w dół
      if (rnd() > 0.22) add(x, y);
      if (rnd() < 0.28) add(x + 1, y);
      if (rnd() < 0.12) add(x - 2, y + 1);
      y += 1;
      if (rnd() < 0.5) x += 1;
    }
    x = Math.round(-Rb * 1.25); y = Math.round(Rb * 0.25);
    for (s = 0; s < 9; s++) {                    // druga, krótsza – z lewej dołem
      if (rnd() > 0.3) add(x, y);
      x += 1; if (rnd() < 0.55) y += 1;
    }
    for (s = 0; s < 10; s++) {                   // pojedyncze piksele wokół tarczy
      var ang = rnd() * Math.PI * 2, rad = Rb * (1.08 + rnd() * 0.6);
      add(Math.round(Math.sin(ang) * rad), Math.round(-Math.cos(ang) * rad));
    }
    this.blocks = list;
  };

  Art.prototype.kick = function () {
    if (reduce || this.raf || !this.visible || document.hidden) return;
    var self = this;
    this.last = 0;
    this.raf = requestAnimationFrame(function (t) { self.step(t); });
  };

  Art.prototype.scheduleHop = function () { // co kilka sekund jeden blok przeskakuje o pole i wraca
    var self = this;
    setTimeout(function () {
      if (self.visible && !document.hidden && self.blocks.length) {
        var b = self.blocks[Math.floor(Math.random() * self.blocks.length)];
        b.hop = 1; b.hx = Math.random() < 0.5 ? (Math.random() < 0.5 ? -1 : 1) : 0; b.hy = b.hx ? 0 : (Math.random() < 0.5 ? -1 : 1);
        setTimeout(function () { b.hop = 0; self.kick(); }, 520);
        self.kick();
      }
      self.scheduleHop();
    }, 3200 + Math.random() * 3600);
  };

  Art.prototype.target = function () {
    var b = this.canvas.getBoundingClientRect(), k = b.width / this.gw;
    return aim(this, b.left + this.cx * k, b.top + this.cy * k, this.R * k * 0.12); // kursor nad osią: zostań
  };

  Art.prototype.step = function (t) {
    this.raf = 0;
    if (!this.frame) return;
    var dt = this.last ? Math.min(0.034, (t - this.last) / 1000) : 1 / 60;
    this.last = t;
    var active = spring(this, this.target(), dt) || this.mode === "lost";
    // bloki: odsuwają się od kursora o jedno pole siatki
    var b = this.canvas.getBoundingClientRect(), k = b.width / this.gw, B = this.B;
    for (var i = 0; i < this.blocks.length; i++) {
      var bl = this.blocks[i], tx = 0, ty = 0;
      if (pointer && this.mode !== "lost") {
        var bx = b.left + (this.cx + (bl.bi + 0.5) * B) * k, by = b.top + (this.cy + (bl.bj + 0.5) * B) * k;
        var dx = bx - pointer.x, dy = by - pointer.y, d = Math.sqrt(dx * dx + dy * dy), reach = B * k * 2.4;
        if (d < reach && d > 0.01) {
          if (Math.abs(dx) > Math.abs(dy)) tx = dx > 0 ? B : -B; else ty = dy > 0 ? B : -B;
        }
      }
      if (bl.hop) { tx += bl.hx * B; ty += bl.hy * B; }
      bl.vx += (240 * (tx - bl.ox) - 22 * bl.vx) * dt;
      bl.vy += (240 * (ty - bl.oy) - 22 * bl.vy) * dt;
      bl.ox += bl.vx * dt;
      bl.oy += bl.vy * dt;
      if (Math.abs(tx - bl.ox) > 0.05 || Math.abs(ty - bl.oy) > 0.05 || Math.abs(bl.vx) > 0.05 || Math.abs(bl.vy) > 0.05) active = true;
    }
    this.draw();
    if (active) this.kick();
  };

  Art.prototype.draw = function () {
    if (!this.frame) return;
    var gw = this.gw, gh = this.gh, R = this.R, cx = this.cx, cy = this.cy, f = this.frame, thr = this.thr, ink = this.col.ink;
    f.set(this.base);
    // igła: północ pełna (z fazowaną połową), południe obrysem; cień przesunięty w prawo w dół
    var s = Math.sin(this.theta), c = Math.cos(this.theta), Ln = 0.72, W = 0.125, cellR = 1 / R;
    var rad = Math.ceil((Ln + 0.12) * R), i0 = Math.max(0, Math.floor(cx - rad)), i1 = Math.min(gw - 1, Math.ceil(cx + rad));
    var j0 = Math.max(0, Math.floor(cy - rad)), j1 = Math.min(gh - 1, Math.ceil(cy + rad));
    function needle(u, v) {
      var au = Math.abs(u);
      if (au > Ln) return -1;
      var half = W * (1 - au / Ln), av = Math.abs(v);
      if (av > half) return -1;
      if (Math.abs(u) < 0.8 * cellR) return 1;
      if (u > 0) return v < 0 ? 1 : 0.82;
      return (half - av < 1.4 * cellR || au > Ln - 2 * cellR) ? 1 : 0.06;
    }
    for (var j = j0; j <= j1; j++) for (var i = i0; i <= i1; i++) {
      var q = j * gw + i, dx = (i + 0.5 - cx) / R, dy = (j + 0.5 - cy) / R, r = Math.sqrt(dx * dx + dy * dy);
      if (r < 0.052) { f[q] = 0; continue; }                 // oś: jasny kapturek
      if (r < 0.074) { f[q] = ink; continue; }
      var d = needle(dx * s - dy * c, dx * c + dy * s);
      if (d >= 0) { f[q] = d > thr[q] ? ink : 0; continue; }
      var sx = dx - 0.04, sy = dy - 0.055;
      if (needle(sx * s - sy * c, sx * c + sy * s) >= 0 && 0.5 > thr[q]) f[q] = ink;
    }
    // bloki – pozycje zaokrąglone do komórki: ruch skokowy, „pikselowy”
    var B = this.B, cols = [this.col.block, this.col.paper, this.col.moss];
    for (var n = 0; n < this.blocks.length; n++) {
      var bl = this.blocks[n], x0 = Math.round(cx + bl.bi * B + bl.ox), y0 = Math.round(cy + bl.bj * B + bl.oy), col = cols[bl.kind];
      for (var y = Math.max(0, y0); y < Math.min(gh, y0 + B); y++)
        for (var x = Math.max(0, x0); x < Math.min(gw, x0 + B); x++) f[y * gw + x] = col;
    }
    this.ctx.putImageData(this.img, 0, 0);
  };

  /* ================================================================ znak w nagłówku */
  // Miniaturowy kompas: pierścień z północą w Oxbloodzie i igła na tej samej sprężynie.
  var MARK_KEY = "kk-mark", mark = null;

  function Mark(el, saved) {
    var css = getComputedStyle(document.documentElement);
    this.el = el;
    this.mode = document.querySelector('[data-art="lost"]') ? "lost" : "compass";
    this.col = [0, pack(hexToRgb(css.getPropertyValue("--ink"), [28, 23, 22])),   // 0 pusto · 1 atrament · 2 Oxblood · 3 trawertyn
                pack(hexToRgb(css.getPropertyValue("--blue"), [92, 16, 34])),
                pack(hexToRgb(css.getPropertyValue("--paper"), [244, 241, 234]))];
    this.canvas = document.createElement("canvas");
    this.ctx = this.canvas.getContext("2d");
    this.theta = reduce ? 0 : (saved ? saved.t : -2.35);
    this.omega = reduce || !saved ? 0 : saved.w;
    this.visible = true;
    this.wander = 0; this.raf = 0; this.last = 0; this.n = 0;
    el.appendChild(this.canvas);
    this.resize();
    el.classList.add("mark-live");
    var self = this;
    if (window.ResizeObserver) new ResizeObserver(function () { self.resize(); }).observe(el);
    if (!reduce) (el.closest("a") || el).addEventListener("pointerenter", function () {
      if (self.omega < 20) self.omega += 38;
      self.kick();
    });
  }

  Mark.prototype.resize = function () {
    var n = Math.round(this.el.getBoundingClientRect().width);
    if (n < 8 || n === this.n) return;
    this.n = n;
    this.canvas.width = this.canvas.height = n;
    this.img = this.ctx.createImageData(n, n);
    this.frame = new Uint32Array(this.img.data.buffer);
    this.base = new Uint32Array(n * n);
    var R = n / 2, cr = 1 / R;
    for (var j = 0; j < n; j++) for (var i = 0; i < n; i++) {
      var dx = (i + 0.5 - R) / R, dy = (j + 0.5 - R) / R, r = Math.sqrt(dx * dx + dy * dy);
      if (r <= 1 && r > 1 - 1.5 * cr) this.base[j * n + i] = this.col[dy < 0 && Math.abs(dx) < 0.6 * cr ? 2 : 1];
    }
    this.draw();
  };

  Mark.prototype.draw = function () {
    if (!this.frame) return;
    var n = this.n, R = n / 2, cr = 1 / R, f = this.frame, col = this.col, Ln = 0.8, W = 0.26;
    var s = Math.sin(this.theta), c = Math.cos(this.theta);
    f.set(this.base);
    for (var j = 0; j < n; j++) for (var i = 0; i < n; i++) {
      var dx = (i + 0.5 - R) / R, dy = (j + 0.5 - R) / R, r = Math.sqrt(dx * dx + dy * dy), v = 0;
      var u = dx * s - dy * c, w = Math.abs(dx * c + dy * s), au = Math.abs(u), half = W * (1 - au / Ln);
      if (au <= Ln && w <= half) v = u > 0 ? 2 : ((half - w < 1.1 * cr || au > Ln - 1.6 * cr) ? 1 : 3);
      if (r < 0.9 * cr) v = 3; else if (r < 1.7 * cr) v = 1;
      if (v) f[j * n + i] = col[v];
    }
    this.ctx.putImageData(this.img, 0, 0);
  };

  Mark.prototype.kick = Art.prototype.kick;

  Mark.prototype.step = function (t) {
    this.raf = 0;
    var dt = this.last ? Math.min(0.034, (t - this.last) / 1000) : 1 / 60;
    this.last = t;
    var b = this.canvas.getBoundingClientRect();
    var active = spring(this, aim(this, b.left + b.width / 2, b.top + b.height / 2, b.width * 0.15), dt) || this.mode === "lost";
    this.draw();
    if (active) this.kick();
  };

  /* ================================================================ start */
  function kickAll() { for (var i = 0; i < arts.length; i++) arts[i].kick(); }

  function init() {
    var saved = null;
    try { saved = JSON.parse(sessionStorage.getItem(MARK_KEY) || "null"); } catch (e) { /* bez sessionStorage znak startuje od nowa */ }
    if (saved && !(Date.now() - saved.at < 15000)) saved = null;
    if (saved && saved.x != null && !reduce) pointer = { x: saved.x, y: saved.y };
    document.querySelectorAll("[data-art]").forEach(function (el) {
      try { arts.push(new Art(el)); } catch (e) { /* grafika jest ozdobą – błąd nie może zatrzymać strony */ }
    });
    var mk = document.querySelector("[data-mark]");
    if (mk) try { mark = new Mark(mk, saved); arts.push(mark); } catch (e) { /* zostaje SVG */ }
    if (reduce || !arts.length) return;
    document.addEventListener("pointermove", function (e) { pointer = { x: e.clientX, y: e.clientY }; kickAll(); }, { passive: true });
    document.documentElement.addEventListener("pointerleave", function () { pointer = null; kickAll(); });
    document.addEventListener("focusin", function (e) {
      if (!e.target || !e.target.getBoundingClientRect || !e.target.matches(":focus-visible")) return;
      var b = e.target.getBoundingClientRect();
      pointer = { x: b.left + b.width / 2, y: b.top + b.height / 2, kb: true };
      kickAll();
    });
    document.addEventListener("visibilitychange", kickAll);
    window.addEventListener("pagehide", function () {
      if (!mark) return;
      var p = pointer && !pointer.kb ? pointer : null;
      try { sessionStorage.setItem(MARK_KEY, JSON.stringify({ t: mark.theta, w: mark.omega, x: p && p.x, y: p && p.y, at: Date.now() })); } catch (e) { /* trudno */ }
    });
    kickAll();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
