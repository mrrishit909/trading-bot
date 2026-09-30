/* ==========================================================================
   MOMENTUM GEOMETRY: the Trading Robot intro field
   --------------------------------------------------------------------------
   Algorithmic philosophy (method borrowed from the algorithmic-art skill):

   Capital is matter in motion. Every particle is a small unit of the account,
   and the shape it joins is never decoration; it is the account itself: the
   wordmark at rest, the allocation bent into a ring, the holdings in orbit
   around a golden core of idle cash, the equity history folded into a
   surface, the 2,000-stock universe spun into a galaxy whose arms are sectors
   and whose core is momentum.

   Two tempos govern the drift. Each particle breathes on a fast period and a
   slow one (five and twenty, the robot's own moving averages), so the field
   never stills and never repeats: the quiet signature of a crossover engine.

   Change is a rebalance. When the field re-forms, particles leave on staggered
   delays and travel curved, eased paths the way orders fill: not all at once,
   never in a straight line, always arriving.

   Nothing is random without a seed. The backdrop sky is seeded by the trading
   day, so each session has its own stars that stay put across reloads; forms
   are seeded by the data, so the same account always draws the same geometry.
   ========================================================================== */
(function () {
  "use strict";
  const D = document, H = D.documentElement, W = window;
  const RM = H.classList.contains("rm");
  const FINE = !RM && !!(W.matchMedia && matchMedia("(hover: hover) and (pointer: fine)").matches);
  if (FINE) H.classList.add("finepointer");
  const $ = (q, r) => (r || D).querySelector(q);
  const $$ = (q, r) => Array.from((r || D).querySelectorAll(q));

  let DATA = {};
  try { DATA = JSON.parse($("#boot-data").textContent) || {}; } catch (e) { DATA = {}; }
  let EXTRAS = null, UNI = null, FIELD = null;

  // ------------------------------------------------------------------ utils
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const lerp = (a, b, t) => a + (b - a) * t;
  const num = (v) => (typeof v === "number" && isFinite(v) ? v : null);
  const pad2 = (n) => String(n).padStart(2, "0");
  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function hashStr(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
  function gauss(r) { let u = 0; while (!u) u = r(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(6.283185307 * r()); }
  function hex(c) { const n = parseInt(c.slice(1), 16); return [(n >> 16 & 255) / 255, (n >> 8 & 255) / 255, (n & 255) / 255]; }
  function mixc(a, b, t) { return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]; }

  const fmt = {
    money(v, dec) {
      if (num(v) === null) return "—";
      dec = dec === undefined ? 2 : dec;
      return (v < 0 ? "−$" : "$") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
    },
    signMoney(v, dec) {
      if (num(v) === null) return "—";
      dec = dec === undefined ? 2 : dec;
      return (v >= 0 ? "+$" : "−$") + Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
    },
    pct(v, dec) { if (num(v) === null) return "—"; dec = dec === undefined ? 2 : dec; return (v >= 0 ? "+" : "−") + Math.abs(v).toFixed(dec) + "%"; },
    int(v) { return num(v) === null ? "—" : Math.round(v).toLocaleString("en-US"); },
    kmoney(v, dec) { return num(v) === null ? "—" : (v < 0 ? "−$" : "$") + (Math.abs(v) / 1000).toFixed(dec) + "k"; },
  };
  const cls = (v) => (num(v) === null ? "" : v >= 0 ? "up" : "down");
  const plural = (n, one, many) => n + " " + (n === 1 ? one : many);

  function h(tag, props) {
    const e = D.createElement(tag);
    if (props) for (const k in props) {
      const v = props[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "text") e.textContent = v;
      else e.setAttribute(k, v);
    }
    for (let i = 2; i < arguments.length; i++) {
      const c = arguments[i];
      if (c === null || c === undefined || c === false) continue;
      if (Array.isArray(c)) c.forEach((x) => x != null && e.append(x.nodeType ? x : D.createTextNode(String(x))));
      else e.append(c.nodeType ? c : D.createTextNode(String(c)));
    }
    return e;
  }
  function sv(tag, attrs) {
    const e = D.createElementNS("http://www.w3.org/2000/svg", tag);
    if (attrs) for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }
  const ARROW = () => {
    const s = sv("svg", { viewBox: "0 0 14 14", fill: "none", stroke: "currentColor", "stroke-width": "1.3", class: "arr" });
    s.append(sv("path", { d: "M4 10 10 4M5 4h5v5" }));
    return s;
  };

  // count-up: eases from the element's last value to the new one
  function tween(el, to, paint, dur) {
    if (!el) return;
    const from = num(el._v) === null ? 0 : el._v;
    el._v = to;
    if (RM || num(to) === null) { paint(el, to); return; }
    const t0 = performance.now(); dur = dur || 1800;
    (function step(now) {
      const k = Math.min(1, (now - t0) / dur), e = k === 1 ? 1 : 1 - Math.pow(2, -10 * k);
      paint(el, from + (to - from) * e);
      if (k < 1) requestAnimationFrame(step);
    })(t0);
  }
  const paintMoney = (el, v) => { el.textContent = fmt.money(v); };
  const paintSigned = (el, v) => { el.textContent = fmt.signMoney(v); };
  const paintInt = (el, v) => { el.textContent = fmt.int(v); };

  // ---------------------------------------------------------------- palette
  const C = {
    bone: hex("#ece8e1"), white: hex("#ffffff"), gold: hex("#f3d484"), gold2: hex("#d4af37"),
    sky: hex("#38bdf8"), ice: hex("#7dd3fc"), up: hex("#34d399"), upDim: hex("#1d6b52"),
    down: hex("#f87171"), downDim: hex("#7a3434"), steel: hex("#7486ad"), violet: hex("#a5b4fc"),
    pink: hex("#f9a8d4"), warm: hex("#fde68a"),
    risk: ["#6b5220", "#9c7a2c", "#caa33e", "#f3d484"].map(hex),   // dataviz-validated ordinal ramp
  };

  /* ======================================================================
     THE FIELD: one WebGL point cloud that morphs between data-built forms
     ====================================================================== */
  function createField(canvas) {
    let gl = null;
    try {
      gl = canvas.getContext("webgl", { antialias: false, alpha: false, depth: false, stencil: false,
        premultipliedAlpha: false, powerPreference: "high-performance" });
    } catch (e) { gl = null; }
    if (!gl) return null;

    const small = Math.min(innerWidth, innerHeight) < 640 || innerWidth < 760;
    const N = small ? 12000 : 26000, NB = Math.round(N * 0.38), NC = N - NB;
    const FOV = 45 * Math.PI / 180, MORPH = RM ? 1 : 2400;

    const VS = `
      attribute vec3 aFrom, aTo, aCF, aCT; attribute vec4 aMisc; attribute vec2 aSG;
      uniform mat4 uP, uV; uniform vec3 uOff; uniform vec2 uMouse, uWaveC;
      uniform float uT, uM, uPR, uFade, uBack, uPush, uAsp, uFocus, uWaveT;
      varying vec3 vC; varying float vA, vK;
      float ease(float t) { return t < .5 ? 4.*t*t*t : 1. - pow(-2.*t + 2., 3.) / 2.; }
      void main() {
        float s = aSG.x, grp = aSG.y;
        float t = ease(clamp((uM - s * .35) / .65, 0., 1.));
        vec3 p = mix(aFrom, aTo, t);
        float b = sin(3.14159265 * t) * .35;
        p += b * vec3(sin(s * 43.1 + uT * .7), cos(s * 17.3 + uT * .6), sin(s * 29.7 - uT * .5));
        /* two tempos: periods of 5 and 20 seconds, the robot's own averages */
        p += .014 * vec3(sin(uT * 1.2566 + s * 50.), cos(uT * .31416 + s * 80.), sin(uT * 1.2566 + s * 30.));
        vec4 mv = uV * vec4(p, 1.);
        mv.xyz += uOff * (1. - grp);
        vec4 c = uP * mv;
        vec2 ndc = c.xy / max(c.w, 1e-3);
        vec2 dm = (ndc - uMouse) * vec2(uAsp, 1.); float md = length(dm);
        float push = uPush * smoothstep(.3, 0., md) * (1. - grp);
        vec2 wv = (ndc - uWaveC) * vec2(uAsp, 1.); float wd = length(wv);
        float wave = uWaveT < 2.4 ? exp(-pow((wd - uWaveT * 1.15) * 5.5, 2.)) * (1. - uWaveT / 2.4) * .16 : 0.;
        vec2 shift = dm / max(md, 1e-4) * push * .1 + wv / max(wd, 1e-4) * wave;
        c.xy += shift / vec2(uAsp, 1.) * c.w;
        float k = mix(aMisc.z, aMisc.w, step(.5, t));
        float sz = mix(aMisc.x, aMisc.y, t);
        float foc = (k > .5 && abs(k - 1. - uFocus) < .5) ? 1.45 : 1.;
        gl_Position = mv.z > -.15 ? vec4(2., 2., 2., 1.) : c;
        gl_PointSize = clamp(sz * foc * uPR * 7. / -mv.z, 1., 180.);
        vC = mix(aCF, aCT, t) * (foc > 1. ? 1.35 : 1.);
        float tw = .72 + .28 * sin(uT * (1.3 + s * 2.) + s * 100.);
        vA = uFade * mix(1., uBack, grp) * mix(tw, 1., step(.5, k));
        vK = k;
      }`;
    const FS = `
      precision mediump float;
      varying vec3 vC; varying float vA, vK;
      void main() {
        vec2 q = gl_PointCoord * 2. - 1.; float r2 = dot(q, q);
        if (r2 > 1.) discard;
        if (vK > .5) {                     /* a lit sphere: planets, the sun, held stocks */
          vec3 n = vec3(q.x, -q.y, sqrt(1. - r2));
          float dif = max(dot(n, normalize(vec3(-.45, .55, .7))), 0.);
          float rim = pow(1. - n.z, 3.);
          vec3 col = vC * (.12 + .9 * dif) + vec3(pow(dif, 28.) * .45) + vC * rim * .9;
          gl_FragColor = vec4(col, vA * smoothstep(1., .82, r2));
        } else {                            /* a star: soft gaussian glow */
          float g = exp(-r2 * 3.6);
          gl_FragColor = vec4(vC * g * 1.3, vA * g);
        }
      }`;
    const LVS = `attribute vec3 aP; uniform mat4 uP, uV; uniform vec3 uOff;
      void main() { vec4 mv = uV * vec4(aP, 1.); mv.xyz += uOff; gl_Position = uP * mv; }`;
    const LFS = `precision mediump float; uniform float uA; void main() { gl_FragColor = vec4(.95, .83, .52, uA); }`;

    function shader(type, src) {
      const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    }
    function program(vs, fs) {
      const p = gl.createProgram();
      gl.attachShader(p, shader(gl.VERTEX_SHADER, vs)); gl.attachShader(p, shader(gl.FRAGMENT_SHADER, fs));
      gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
      return p;
    }
    const P = program(VS, FS), PL = program(LVS, LFS);
    const A = {}, U = {};
    ["aFrom", "aTo", "aCF", "aCT", "aMisc", "aSG"].forEach((n) => { A[n] = gl.getAttribLocation(P, n); });
    ["uP", "uV", "uOff", "uMouse", "uWaveC", "uT", "uM", "uPR", "uFade", "uBack", "uPush", "uAsp", "uFocus", "uWaveT"]
      .forEach((n) => { U[n] = gl.getUniformLocation(P, n); });
    const LU = { uP: gl.getUniformLocation(PL, "uP"), uV: gl.getUniformLocation(PL, "uV"),
      uOff: gl.getUniformLocation(PL, "uOff"), uA: gl.getUniformLocation(PL, "uA") };
    const LA = gl.getAttribLocation(PL, "aP");

    const from = new Float32Array(N * 3), to = new Float32Array(N * 3);
    const cf = new Float32Array(N * 3), ct = new Float32Array(N * 3);
    const misc = new Float32Array(N * 4), sg = new Float32Array(N * 2);
    const bufs = {};
    function mkbuf(name, arr, size) {
      const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, arr, gl.DYNAMIC_DRAW);
      bufs[name] = { b, arr, size };
    }
    const lineBuf = gl.createBuffer(); let lineCount = 0;

    // -- seeds + the backdrop sky (seeded by the trading day, static) --
    const day = String(DATA.now || new Date().toISOString()).slice(0, 10);
    const rs = rng(hashStr("seeds" + day)), rb = rng(hashStr("sky" + day));
    for (let i = 0; i < N; i++) { sg[i * 2] = rs(); sg[i * 2 + 1] = i < NC ? 0 : 1; }
    const skyPal = [[C.white, .5], [C.warm, .14], [C.gold, .08], [C.ice, .12], [C.violet, .1], [C.pink, .06]];
    for (let i = NC; i < N; i++) {
      const j = i * 3, k = i * 4, band = rb() < .62;
      const x = (rb() - .5) * 30;
      from[j] = to[j] = x;
      from[j + 1] = to[j + 1] = band ? x * .2 + gauss(rb) * 1.15 - .5 : (rb() - .5) * 20;
      from[j + 2] = to[j + 2] = -4 - rb() * 13;
      let q = rb(), c = C.white;
      for (const [cc, w] of skyPal) { if ((q -= w) <= 0) { c = cc; break; } }
      const br = .25 + Math.pow(rb(), 2.2) * .9;
      cf[j] = ct[j] = c[0] * br; cf[j + 1] = ct[j + 1] = c[1] * br; cf[j + 2] = ct[j + 2] = c[2] * br;
      const sz = .8 + Math.pow(rb(), 4) * 2.4;
      misc[k] = misc[k + 1] = sz; misc[k + 2] = misc[k + 3] = 0;
    }
    // content starts as a collapsed point: the big bang forms the wordmark
    const r0 = rng(3);
    for (let i = 0; i < NC; i++) {
      const j = i * 3, k = i * 4;
      from[j] = to[j] = gauss(r0) * .04; from[j + 1] = to[j + 1] = gauss(r0) * .04; from[j + 2] = to[j + 2] = gauss(r0) * .04;
      cf[j] = ct[j] = 1; cf[j + 1] = ct[j + 1] = .92; cf[j + 2] = ct[j + 2] = .75;
      misc[k] = misc[k + 1] = .6; misc[k + 2] = misc[k + 3] = 0;
    }
    mkbuf("aFrom", from, 3); mkbuf("aTo", to, 3); mkbuf("aCF", cf, 3); mkbuf("aCT", ct, 3);
    mkbuf("aMisc", misc, 4); mkbuf("aSG", sg, 2);

    function upload() {
      for (const n of ["aFrom", "aTo", "aCF", "aCT", "aMisc"]) {
        const { b, arr, size } = bufs[n];
        gl.bindBuffer(gl.ARRAY_BUFFER, b);
        gl.bufferSubData(gl.ARRAY_BUFFER, 0, arr.subarray(0, NC * size));
      }
    }
    const setC = (j, c, br) => { ct[j] = c[0] * br; ct[j + 1] = c[1] * br; ct[j + 2] = c[2] * br; };
    const put = (i, x, y, z, c, br, size, kind) => {
      const j = i * 3, k = i * 4;
      to[j] = x; to[j + 1] = y; to[j + 2] = z; setC(j, c, br); misc[k + 1] = size; misc[k + 3] = kind;
    };

    // -- camera / viewport --
    let cssW = innerWidth, cssH = innerHeight, PR = 1, ASP = cssW / cssH;
    let PROJ = persp(FOV, ASP, .1, 80), VIEW = ident();
    function resize() {
      cssW = innerWidth; cssH = innerHeight; ASP = cssW / cssH;
      PR = Math.min(W.devicePixelRatio || 1, cssW > 1800 ? 1.5 : 2);
      canvas.width = Math.round(cssW * PR); canvas.height = Math.round(cssH * PR);
      gl.viewport(0, 0, canvas.width, canvas.height);
      PROJ = persp(FOV, ASP, .1, 80);
      if (RM) draw(performance.now());
    }
    const narrow = () => cssW / cssH < .95 || cssW < 640;
    const SP = {
      wordmark: { dist: 6.2, tilt: 0, spin: 0, osc: .05, push: .9, back: 1, off: () => [0, 0, 0] },
      sphere: { dist: 6.7, tilt: .3, spin: .09, push: .3, back: .75, off: () => [0, narrow() ? -.1 : -.2, 0] },
      ring: { dist: 7.2, tilt: 1.12, spin: .1, push: .3, back: .6, off: () => (narrow() ? [0, -1.1, 0] : [2.45, -.35, 0]) },
      manifold: { dist: 6.7, tilt: .5, spin: 0, osc: .38, push: .3, back: .6, off: () => [0, -.3, 0] },
      galaxy: { dist: 7.1, tilt: 1.02, spin: .03, push: .2, back: .65, off: () => [0, -.3, 0] },
      vortex: { dist: 6.9, tilt: .3, spin: .5, push: .3, back: .6, off: () => (narrow() ? [0, -.7, 0] : [2.3, -.2, 0]) },
      dust: { dist: 7.4, tilt: .2, spin: .02, push: .2, back: .5, off: () => [0, 0, 0] },
    };
    const cam = { dist: 6.2, tilt: 0, yaw: 0, off: [0, 0, 0], push: .9, back: 1, fade: 1 };
    let fadeTarget = 1;

    // -- generators: each writes the content particles' targets --
    let planets = [], stars = null, anchors = [], textPts = null, textKey = "";
    const GEN = {};

    function sampleText() {
      const nar = narrow(), key = cssW + "x" + cssH + nar + (fontsOK ? 1 : 0);
      if (textPts && key === textKey) return textPts;
      const lines = nar ? ["TRADING", "ROBOT"] : ["TRADING ROBOT"];
      const cw = 1600, fs = nar ? 240 : 150, lh = fs * 1.1;
      const cv = D.createElement("canvas"); cv.width = cw; cv.height = Math.ceil(lh * lines.length + fs * .6);
      const x2 = cv.getContext("2d", { willReadFrequently: true });
      x2.fillStyle = "#fff"; x2.textBaseline = "middle";
      x2.font = "200 " + fs + "px Geist, 'Helvetica Neue', Arial, sans-serif";
      const sp = fs * .14;
      lines.forEach((ln, li) => {
        const ch = Array.from(ln); let w = 0;
        ch.forEach((c, i) => { w += x2.measureText(c).width + (i < ch.length - 1 ? sp : 0); });
        let x = (cw - w) / 2; const y = cv.height / 2 + (li - (lines.length - 1) / 2) * lh;
        ch.forEach((c) => { x2.fillText(c, x, y); x += x2.measureText(c).width + sp; });
      });
      const img = x2.getImageData(0, 0, cw, cv.height).data, pts = [];
      let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
      for (let y = 0; y < cv.height; y += 2) for (let x = 0; x < cw; x += 2) {
        if (img[(y * cw + x) * 4 + 3] > 110) { pts.push(x, y); if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      }
      const visH = 2 * SP.wordmark.dist * Math.tan(FOV / 2), visW = visH * ASP;
      const scale = (visW * (nar ? .84 : .64)) / Math.max(1, x1 - x0);
      // centre where the HTML wordmark sits (42% down the area under the 64px bar)
      const cy = 64 + .42 * (cssH - 64), worldY = (1 - 2 * cy / cssH) * visH / 2;
      const mx = (x0 + x1) / 2, my = (y0 + y1) / 2, out = new Float32Array(pts.length);
      for (let i = 0; i < pts.length; i += 2) { out[i] = (pts[i] - mx) * scale; out[i + 1] = -(pts[i + 1] - my) * scale + worldY; }
      textPts = { pts: out, n: out.length / 2, scale, cy: worldY }; textKey = key;
      return textPts;
    }

    GEN.wordmark = () => {
      const T = sampleText(), r = rng(7), nText = Math.floor(NC * .8);
      for (let i = 0; i < NC; i++) {
        if (i < nText && T.n) {
          const q = Math.floor(r() * T.n) * 2, g = r();
          put(i, T.pts[q] + (r() - .5) * T.scale * 2.4, T.pts[q + 1] + (r() - .5) * T.scale * 2.4, (r() - .5) * .14,
            g < .8 ? C.bone : g < .93 ? C.gold : C.white, .7 + r() * .5, 1.6 + r() * 1.5, 0);
        } else {
          put(i, gauss(r) * 2.8, gauss(r) * .9 + T.cy, gauss(r) * 1.3 - .6, r() < .5 ? C.bone : C.ice, .1 + r() * .22, .8 + r() * .9, 0);
        }
      }
      lineCount = 0;
    };

    GEN.sphere = () => {
      const hs = (FD.holdings || []).slice().sort((a, b) => (b.value || 0) - (a.value || 0)).slice(0, 60);
      const sl = FD.sleeve || [], r = rng(11), R = 1.55;
      const maxV = Math.max(1, ...hs.map((p) => Math.abs(p.value || 0)), ...sl.map((p) => p.value || 0));
      planets = []; let idx = 0;
      const K = hs.length, lines = [];
      hs.forEach((p, q) => {
        const y = 1 - (q + .5) / K * 2, rad = Math.sqrt(Math.max(0, 1 - y * y)), th = q * 2.399963 + .7;
        const pr = R * (1.03 + (q % 3) * .06);
        const x = Math.cos(th) * rad * pr, z = Math.sin(th) * rad * pr, yy = y * pr;
        const size = 8 + 30 * Math.sqrt(Math.abs(p.value || 0) / maxV);
        const pl = num(p.plpc) || 0, mag = clamp(Math.abs(pl) / 6, .2, 1);
        const col = Math.abs(pl) < .15 ? C.bone : pl > 0 ? mixc(C.upDim, C.up, mag) : mixc(C.downDim, C.down, mag);
        put(idx, x, yy, z, col, 1, size, 1 + idx);
        planets.push({ i: idx, sym: p.sym, x, y: yy, z, size, p });
        lines.push(0, 0, 0, x, yy, z);
        idx++;
      });
      if (sl.length) {
        const size = 14 + 30 * Math.sqrt((sl[0].value || 0) / maxV);
        put(idx, 0, 0, 0, C.gold, 1, size, 1 + idx);
        planets.push({ i: idx, sym: "SPY", sleeve: true, x: 0, y: 0, z: 0, size, p: sl[0] });
        idx++;
      }
      const rest = NC - idx, nShell = Math.floor(rest * .8);
      for (let q = 0; q < rest; q++) {
        const i = idx + q;
        if (q < nShell) {
          const y = 1 - (q + .5) / nShell * 2, rad = Math.sqrt(1 - y * y), th = q * 2.399963, rr = R * (1 + gauss(r) * .006);
          put(i, Math.cos(th) * rad * rr, y * rr, Math.sin(th) * rad * rr, C.bone, .3 + r() * .6, 1 + r() * .9, 0);
        } else {
          const u = Math.cbrt(r()) * .95, th = r() * 6.2832, ph = Math.acos(2 * r() - 1);
          put(i, u * Math.sin(ph) * Math.cos(th), u * Math.cos(ph), u * Math.sin(ph) * Math.sin(th),
            r() < .6 ? C.gold : C.sky, .07 + r() * .18, 1.2 + r() * 1.4, 0);
        }
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, lineBuf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(lines), gl.DYNAMIC_DRAW);
      lineCount = lines.length / 3;
    };

    GEN.ring = () => {
      const a = FD.alloc || {}, r = rng(21), R = 1.75, tube = .2, gap = .045;
      const segs = [["cash", 0], ["sleeve", 1], ["stocks", 2], ["crypto", 3]].map(([key, ci]) => ({ v: Math.max(0, a[key] || 0), c: C.risk[ci] }));
      const tot = segs.reduce((s, x) => s + x.v, 0) || 1; let acc = 0;
      segs.forEach((s) => { s.a0 = acc / tot * 6.2832; acc += s.v; s.a1 = acc / tot * 6.2832; });
      const live = segs.filter((s) => s.v > 0);
      for (let i = 0; i < NC; i++) {
        if (r() < .9 && live.length) {
          let th = r() * 6.2832;
          const s = live.find((x) => th >= x.a0 && th < x.a1) || live[live.length - 1];
          th = s.a1 - s.a0 > gap * 2 ? clamp(th, s.a0 + gap / 2, s.a1 - gap / 2) : (s.a0 + s.a1) / 2;
          const ph = r() * 6.2832, rad = tube * Math.sqrt(r());
          put(i, (R + rad * Math.cos(ph)) * Math.cos(th), rad * Math.sin(ph), (R + rad * Math.cos(ph)) * Math.sin(th),
            s.c, .5 + r() * .55, 1.1 + r() * 1.2, 0);
        } else {
          const th = r() * 6.2832, rr = R * .62 + gauss(r) * .02;
          put(i, Math.cos(th) * rr, gauss(r) * .015, Math.sin(th) * rr, C.gold, .12 + r() * .14, .9 + r() * .6, 0);
        }
      }
      lineCount = 0;
    };

    GEN.manifold = () => {
      const s = FD.series || [], base = num(FD.baseline), r = rng(31);
      let vals = s.map((p) => p[1]);
      if (vals.length < 2) vals = [100, 100.4, 100.1, 100.9, 100.6, 101.2];
      let lo = Math.min(...vals), hi = Math.max(...vals);
      if (base !== null) { lo = Math.min(lo, base); hi = Math.max(hi, base); }
      const span = (hi - lo) || 1, norm = (v) => ((v - lo) / span * 2 - 1) * .95;
      const f = (u) => { const x = u * (vals.length - 1), i = Math.floor(x), t = x - i; const a = vals[i], b = vals[Math.min(i + 1, vals.length - 1)]; return a + (b - a) * t; };
      for (let i = 0; i < NC; i++) {
        const u = r(), v = r(), lane = v * 2 - 1, al = Math.abs(lane), ev = f(u);
        const y = norm(ev) * (1 - .5 * Math.pow(al, 1.5)) + .07 * Math.sin(6.2832 * (u * 3 + v * 1.5)) * al - .15;
        const above = base === null || ev >= base, br = al < .035 ? 1.25 : (1 - al) * .8 + .12;
        put(i, (u - .5) * 6.2, y, lane * 1.05, above ? C.gold : C.sky, br, 1 + (1 - al) * 1.4, 0);
      }
      lineCount = 0;
    };

    GEN.galaxy = () => {
      const rows = UNI && UNI.rows && UNI.rows.length ? UNI.rows : null, r = rng(41), NSEC = 14, wedge = 6.2832 / NSEC;
      let items;
      if (rows) {
        const sc = rows.map((rw) => ({ rw, s: num(rw[2]) !== null ? rw[2] : num(rw[3]) !== null ? rw[3] : 0 }));
        sc.sort((a, b) => b.s - a.s);
        items = sc.map((o, q) => ({ rw: o.rw, sec: o.rw[1], p: sc.length > 1 ? q / (sc.length - 1) : 0 }));
      } else {
        items = []; for (let q = 0; q < 2000; q++) items.push({ rw: null, sec: Math.floor(r() * 12), p: r() });
      }
      const S = Math.min(items.length, NC - 600);
      stars = { n: S, pos: new Float32Array(S * 3), rows: [] };
      for (let q = 0; q < S; q++) {
        const it = items[q], rad = .32 + 2.85 * Math.pow(it.p, .85);
        const th = it.sec * wedge + rad * 1.55 + (r() - .5) * wedge * .5;
        const x = Math.cos(th) * rad, z = Math.sin(th) * rad, y = gauss(r) * .045 * (1 + rad * .35);
        const fl = it.rw ? it.rw[7] : 0, upT = it.rw ? it.rw[6] : r() < .3;
        let c = C.steel, br = 1, size = 2.8, kind = 0;
        if (fl & 1) { c = C.up; br = 1; size = 7; kind = 501; }
        else if (fl & 2) { c = C.gold; br = 1.25; size = 7.5; }
        else if (fl & 4) { c = C.sky; br = 1.1; size = 4.6; }
        else if (upT) { c = C.bone; br = 1; size = 3.4; }
        put(q, x, y, z, c, br, size, kind);
        stars.pos[q * 3] = x; stars.pos[q * 3 + 1] = y; stars.pos[q * 3 + 2] = z;
        stars.rows.push(it.rw);
      }
      for (let i = S; i < NC; i++) {
        if (r() < .14) {
          const rad = Math.abs(gauss(r)) * .34, th = r() * 6.2832;
          put(i, Math.cos(th) * rad, gauss(r) * .11, Math.sin(th) * rad, C.warm, .35 + r() * .4, 1.4 + r() * 1.2, 0);
        } else {
          const sec = Math.floor(r() * NSEC), rad = .3 + 3.1 * Math.pow(r(), 1.1);
          const th = sec * wedge + rad * 1.55 + gauss(r) * wedge * .2;
          put(i, Math.cos(th) * rad, gauss(r) * .06, Math.sin(th) * rad, mixc(C.violet, C.warm, r()), .2 + r() * .35, 1.2 + r() * 1.1, 0);
        }
      }
      anchors = [];
      for (let s = 0; s < NSEC; s++) { const rad = 3.5, th = s * wedge + rad * 1.55; anchors.push([Math.cos(th) * rad, 0, Math.sin(th) * rad]); }
      lineCount = 0;
    };

    GEN.vortex = () => {
      const r = rng(51);
      for (let i = 0; i < NC; i++) {
        const u = Math.pow(r(), .9), y = 1.7 - 3.3 * u, rad = 2.3 * Math.pow(1 - u, 1.7) + .05 + gauss(r) * .02;
        const th = r() * 6.2832 + u * 9;
        put(i, Math.cos(th) * rad, y, Math.sin(th) * rad, mixc(C.bone, C.gold, Math.pow(u, 1.4)), .25 + r() * .6, 1 + u * 1.8, 0);
      }
      lineCount = 0;
    };

    GEN.dust = () => {
      const r = rng(61);
      for (let i = 0; i < NC; i++) {
        const rad = 1.2 + Math.pow(r(), .5) * 4.2, th = r() * 6.2832, ph = Math.acos(2 * r() - 1);
        put(i, rad * Math.sin(ph) * Math.cos(th), rad * Math.cos(ph) * .45, rad * Math.sin(ph) * Math.sin(th) - 1,
          r() < .7 ? C.bone : C.gold, .1 + r() * .25, .8 + r() * .8, 0);
      }
      lineCount = 0;
    };

    // -- morph machinery --
    let FD = DATA, state = "none", morphT0 = -1e9, fontsOK = false;
    const t0 = performance.now();
    const timeAt = (now) => (RM ? 0 : (now - t0) / 1000);
    const morphAt = (now) => (RM ? 1 : clamp((now - morphT0) / MORPH, 0, 1));
    function freeze(now) {
      const m = morphAt(now), T = timeAt(now);
      for (let i = 0; i < NC; i++) {
        const s = sg[i * 2]; let t = clamp((m - s * .35) / .65, 0, 1);
        t = t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        const b = Math.sin(Math.PI * t) * .35, j = i * 3, k = i * 4;
        from[j] = lerp(from[j], to[j], t) + b * Math.sin(s * 43.1 + T * .7);
        from[j + 1] = lerp(from[j + 1], to[j + 1], t) + b * Math.cos(s * 17.3 + T * .6);
        from[j + 2] = lerp(from[j + 2], to[j + 2], t) + b * Math.sin(s * 29.7 - T * .5);
        cf[j] = lerp(cf[j], ct[j], t); cf[j + 1] = lerp(cf[j + 1], ct[j + 1], t); cf[j + 2] = lerp(cf[j + 2], ct[j + 2], t);
        misc[k] = lerp(misc[k], misc[k + 1], t); misc[k + 2] = t < .5 ? misc[k + 2] : misc[k + 3];
      }
    }
    function setState(name, force) {
      if (!GEN[name] || (name === state && !force)) return;
      const now = performance.now();
      freeze(now); GEN[name](); upload();
      morphT0 = now; state = name;
      if (RM) draw(now);
      api.onState && api.onState(name);
    }

    // -- render loop --
    let raf = 0, running = false, last = performance.now(), fpsN = 0, fpsT = 0, fps = 0;
    const mouse = { x: 0, y: 0, sx: 0, sy: 0, ndcX: 9, ndcY: 9 };
    let focus = -10, waveT0 = -1e9, waveC = [9, 9], yawOsc = 0;
    function draw(now) {
      const dt = Math.min(.05, Math.max(0, (now - last) / 1000)); last = now;
      const T = timeAt(now), m = morphAt(now), sp = SP[state] || SP.dust;
      const k = RM ? 1 : 1 - Math.pow(.02, dt);
      cam.dist = lerp(cam.dist, sp.dist, k); cam.tilt = lerp(cam.tilt, sp.tilt, k);
      const off = sp.off();
      cam.off = [lerp(cam.off[0], off[0], k), lerp(cam.off[1], off[1], k), lerp(cam.off[2], off[2], k)];
      cam.push = lerp(cam.push, RM ? 0 : sp.push, k); cam.back = lerp(cam.back, sp.back, k);
      cam.fade = lerp(cam.fade, fadeTarget, RM ? 1 : 1 - Math.pow(.1, dt));
      if (!RM) cam.yaw += sp.spin * dt;
      yawOsc = lerp(yawOsc, sp.osc ? Math.sin(T * .15) * sp.osc : 0, k);
      mouse.sx = lerp(mouse.sx, mouse.x, RM ? 0 : 1 - Math.pow(.05, dt));
      mouse.sy = lerp(mouse.sy, mouse.y, RM ? 0 : 1 - Math.pow(.05, dt));
      VIEW = mul(mul(tr(0, 0, -cam.dist), rx(cam.tilt + mouse.sy * .09)), ry(cam.yaw + yawOsc + mouse.sx * .16));

      gl.clearColor(8 / 255, 8 / 255, 8 / 255, 1); gl.clear(gl.COLOR_BUFFER_BIT);
      gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
      gl.useProgram(P);
      for (const n in bufs) {
        const { b, size } = bufs[n]; gl.bindBuffer(gl.ARRAY_BUFFER, b);
        gl.enableVertexAttribArray(A[n]); gl.vertexAttribPointer(A[n], size, gl.FLOAT, false, 0, 0);
      }
      gl.uniformMatrix4fv(U.uP, false, PROJ); gl.uniformMatrix4fv(U.uV, false, VIEW);
      gl.uniform3fv(U.uOff, cam.off); gl.uniform2f(U.uMouse, mouse.ndcX, mouse.ndcY);
      gl.uniform2f(U.uWaveC, waveC[0], waveC[1]); gl.uniform1f(U.uWaveT, RM ? 9 : (now - waveT0) / 1000);
      gl.uniform1f(U.uT, T); gl.uniform1f(U.uM, m); gl.uniform1f(U.uPR, PR); gl.uniform1f(U.uFade, cam.fade);
      gl.uniform1f(U.uBack, cam.back); gl.uniform1f(U.uPush, cam.push); gl.uniform1f(U.uAsp, ASP);
      gl.uniform1f(U.uFocus, focus);
      gl.drawArrays(gl.POINTS, 0, N);
      for (const n in bufs) gl.disableVertexAttribArray(A[n]);

      if (lineCount && state === "sphere") {
        gl.useProgram(PL);
        gl.bindBuffer(gl.ARRAY_BUFFER, lineBuf); gl.enableVertexAttribArray(LA);
        gl.vertexAttribPointer(LA, 3, gl.FLOAT, false, 0, 0);
        gl.uniformMatrix4fv(LU.uP, false, PROJ); gl.uniformMatrix4fv(LU.uV, false, VIEW);
        gl.uniform3fv(LU.uOff, cam.off); gl.uniform1f(LU.uA, .16 * clamp((m - .6) / .4, 0, 1) * cam.fade);
        gl.drawArrays(gl.LINES, 0, lineCount);
        gl.disableVertexAttribArray(LA);
      }
      fpsN++; if (now - fpsT > 1000) { fps = Math.round(fpsN * 1000 / (now - fpsT)); fpsN = 0; fpsT = now; }
      api.onFrame && api.onFrame(api, now);
    }
    function loop(now) { raf = 0; if (!running) return; draw(now); raf = requestAnimationFrame(loop); }
    function start() { if (running || RM) { if (RM) draw(performance.now()); return; } running = true; last = performance.now(); raf = requestAnimationFrame(loop); }
    function stop() { running = false; if (raf) cancelAnimationFrame(raf); raf = 0; }

    function project(x, y, z) {
      const v = VIEW;
      let X = v[0] * x + v[4] * y + v[8] * z + v[12], Y = v[1] * x + v[5] * y + v[9] * z + v[13], Z = v[2] * x + v[6] * y + v[10] * z + v[14];
      X += cam.off[0]; Y += cam.off[1]; Z += cam.off[2];
      if (Z > -.15) return null;
      const w = -Z;
      return { x: (PROJ[0] * X / w * .5 + .5) * cssW, y: (1 - (PROJ[5] * Y / w * .5 + .5)) * cssH, z: w };
    }

    const api = {
      N, NC, get state() { return state; }, get fps() { return fps; }, get planets() { return planets; },
      get stars() { return stars; }, get anchors() { return anchors; },
      morph: () => morphAt(performance.now()),
      pointSize: (size, depth) => size * 7 / depth,
      setState, start, stop, resize, project, draw: () => draw(performance.now()),
      setData(d) { FD = d; },
      setDim(v) { fadeTarget = clamp(v, 0, 1); if (RM) draw(performance.now()); },
      setFocus(i) { focus = i; },
      mouse(cx, cy) {
        mouse.x = (cx / cssW) * 2 - 1; mouse.y = (cy / cssH) * 2 - 1;
        mouse.ndcX = (cx / cssW) * 2 - 1; mouse.ndcY = 1 - (cy / cssH) * 2;
      },
      mouseOut() { mouse.ndcX = 9; mouse.ndcY = 9; },
      wave(cx, cy) { waveC = [(cx / cssW) * 2 - 1, 1 - (cy / cssH) * 2]; waveT0 = performance.now(); },
      fontsReady() { fontsOK = true; textKey = ""; },
      onFrame: null, onState: null,
    };
    canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); stop(); H.classList.remove("fieldon"); H.classList.add("nofield"); });
    resize();
    return api;
  }

  // column-major 4x4 helpers
  function ident() { return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]); }
  function persp(fovy, asp, n, f) { const t = 1 / Math.tan(fovy / 2), nf = 1 / (n - f); return new Float32Array([t / asp, 0, 0, 0, 0, t, 0, 0, 0, 0, (f + n) * nf, -1, 0, 0, 2 * f * n * nf, 0]); }
  function mul(a, b) { const o = new Float32Array(16); for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) { let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k]; o[c * 4 + r] = s; } return o; }
  function rx(t) { const c = Math.cos(t), s = Math.sin(t); return new Float32Array([1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]); }
  function ry(t) { const c = Math.cos(t), s = Math.sin(t); return new Float32Array([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]); }
  function tr(x, y, z) { return new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]); }

  /* ======================================================================
     PAGE CONTENT
     ====================================================================== */
  const R = () => DATA.rules || {};
  const stocksHeld = () => (DATA.holdings || []).filter((p) => p.kind === "stock");
  const coinsHeld = () => (DATA.holdings || []).filter((p) => p.kind === "crypto");

  function bindText() {
    const map = {
      profile: (DATA.profile || "Paper account").toUpperCase(),
      runs: fmt.int(DATA.runs), universe: fmt.int(R().universe),
      particles: FIELD ? fmt.int(FIELD.N) : "0",
    };
    $$("[data-b]").forEach((el) => { const k = el.getAttribute("data-b"); if (k in map) el.textContent = map[k]; });
    if (num(R().universe)) $("#t4").textContent = fmt.int(R().universe) + " stocks. One galaxy.";
    $("#yr").textContent = String(new Date().getFullYear());
  }

  function renderLive() {
    const m = DATA.market, dot = $("#mktDot"), txt = $("#mktTxt");
    if (m) {
      dot.className = m.open ? "open" : "";
      const nx = new Date(m.open ? m.next_close : m.next_open);
      const when = isNaN(nx) ? "" : nx.toLocaleString(undefined, { weekday: "short", hour: "numeric", minute: "2-digit" });
      txt.textContent = m.open ? "Market open · closes " + when : "Market closed · opens " + when;
    } else { txt.textContent = "Market status unavailable"; }
    $("#runTxt").textContent = (DATA.next_run || "").toUpperCase();
    // the first screen shows live numbers straight away (the full ledger is section 01)
    const eq = num(DATA.equity), day = eq !== null && num(DATA.last_equity) !== null ? eq - DATA.last_equity : null;
    tween($("#hEq"), eq, paintMoney, 1600);
    const hd = $("#hDay"); hd.className = cls(day); hd.textContent = day === null ? "" : fmt.signMoney(day) + " today";
    $("#hPos").textContent = plural(stocksHeld().length, "stock", "stocks") + " · " + plural(coinsHeld().length, "coin", "coins") + ((DATA.sleeve || []).length ? " · SPY sleeve" : "");
    $("#liveDot").className = "live-dot" + (m && m.open ? " open" : "");
    if (m && m.open) { $("#liveDot").style.background = "var(--up)"; $("#liveDot").style.boxShadow = "0 0 8px var(--up)"; }
  }

  // ---- 01 account ----
  function renderAccount() {
    const eq = num(DATA.equity), last = num(DATA.last_equity), base = num(DATA.baseline);
    const day = eq !== null && last !== null ? eq - last : null;
    const since = eq !== null && base ? eq - base : null;
    const openPl = (DATA.holdings || []).concat(DATA.sleeve || []).reduce((s, p) => s + (p.pl || 0), 0);
    const cash = num(DATA.cash), inv = eq !== null && cash !== null ? eq - cash : null;

    const eqEl = $("#eqNum");
    if (!eqEl.firstChild || !eqEl.querySelector(".cents")) { eqEl.textContent = ""; eqEl.append(h("span", { class: "whole" }), h("span", { class: "cents" })); }
    tween(eqEl, eq, (el, v) => {
      const s = fmt.money(v), dot = s.lastIndexOf(".");
      el.firstChild.textContent = s.slice(0, dot); el.lastChild.textContent = s.slice(dot);
    }, 2200);
    const sub = $("#eqSub"); sub.textContent = "";
    sub.append(h("span", { class: cls(day) }, fmt.signMoney(day)), " today · ",
      h("span", { class: cls(since) }, since !== null ? fmt.pct(since / base * 100) : "—"), " since the start (" + fmt.money(base) + ")");

    const kt = $("#kToday"); kt.className = "v " + cls(day); tween(kt, day, paintSigned);
    const ks = $("#kSince"); ks.className = "v " + cls(since); tween(ks, since, paintSigned);
    $("#kSinceS").textContent = since !== null ? fmt.pct(since / base * 100) + " on " + fmt.money(base, 0) : "—";
    const ko = $("#kOpen"); ko.className = "v " + cls(openPl); tween(ko, openPl, paintSigned);
    tween($("#kInv"), inv, paintMoney);
    $("#kInvS").textContent = inv !== null && eq ? Math.round(inv / eq * 100) + "% of the account is working" : "—";
    const kp = $("#kPos"); kp.textContent = stocksHeld().length + " / " + (R().max_held || "—");
    $("#kPosS").textContent = plural(coinsHeld().length, "coin", "coins") + ((DATA.sleeve || []).length ? " · SPY sleeve" : "");
    tween($("#kFills"), DATA.fills_today, paintInt, 1200);
    $("#kRun").textContent = DATA.next_run || "";

    // allocation: ordinal risk ramp, 2px gaps, legend + direct labels (dataviz)
    const a = DATA.alloc || {}, segs = [
      { k: "cash", n: "Cash", v: a.cash, c: "var(--risk1)" }, { k: "sleeve", n: "SPY sleeve", v: a.sleeve, c: "var(--risk2)" },
      { k: "stocks", n: "Stocks", v: a.stocks, c: "var(--risk3)" }, { k: "crypto", n: "Crypto", v: a.crypto, c: "var(--risk4)" }];
    const tot = segs.reduce((s, x) => s + Math.max(0, x.v || 0), 0) || 1;
    const bar = $("#allocBar"), leg = $("#allocLegend");
    bar.textContent = ""; leg.textContent = "";
    $("#allocTot").textContent = fmt.money(tot, 0) + " total";
    segs.forEach((s, i) => {
      const share = Math.max(0, s.v || 0) / tot;
      if (share > 0) {
        const seg = h("i", { style: "background:" + s.c + ";--d:" + (i * .12) + "s", "data-w": (share * 100).toFixed(3),
          tabindex: "0", "aria-label": s.n + " " + fmt.money(s.v, 0) + ", " + (share * 100).toFixed(1) + "%" });
        seg._tip = [s.n, fmt.money(s.v), (share * 100).toFixed(1) + "% of the account"];
        bar.append(seg);
      }
      leg.append(h("div", { class: "row" }, h("span", { class: "sw", style: "background:" + s.c }),
        h("div", null, h("div", { class: "nm" }, s.n), h("div", { class: "vl" }, fmt.money(s.v, 0), h("span", { class: "pc" }, (share * 100).toFixed(1) + "%")))));
    });
    bar.setAttribute("aria-label", segs.map((s) => s.n + " " + fmt.money(s.v, 0)).join(", "));
    const al = bar.closest(".alloc");
    const grow = () => $$("i", bar).forEach((i) => { i.style.width = "calc(" + i.getAttribute("data-w") + "% - 2px)"; });
    if (al.classList.contains("in") || RM) grow(); else al.addEventListener("reveal", grow, { once: true });
  }

  // ---- 02 holdings ----
  function renderHoldings() {
    const all = (DATA.sleeve || []).concat((DATA.holdings || []).slice().sort((a, b) => (b.value || 0) - (a.value || 0)));
    const grid = $("#hgrid"); grid.textContent = "";
    const total = all.reduce((s, p) => s + (p.value || 0), 0);
    tween($("#orbitBig"), total, paintMoney, 1600);
    const sl = (DATA.sleeve || [])[0];
    $("#orbitSub").textContent = plural(stocksHeld().length, "stock", "stocks") + " · " + plural(coinsHeld().length, "coin", "coins") + (sl ? " · SPY sleeve " + fmt.money(sl.value, 0) : "");
    all.forEach((p, i) => {
      const kind = p.kind === "sleeve" ? "Sleeve" : p.kind === "crypto" ? "Crypto" : "Stock";
      const href = p.kind === "crypto" ? "/crypto" : "/holdings";
      const cv = h("canvas", { "aria-hidden": "true" });
      const card = h("a", { class: "hcard brk spot" + (p.kind === "sleeve" ? " sleeve" : ""), href, "data-reveal": "", "data-cur": "OPEN", "data-sym": p.sym },
        h("span", { class: "glow" }),
        h("div", { class: "pv" }, cv, h("span", { class: "chip" }, kind + " " + pad2(i), h("b", null, p.sym))),
        h("div", { class: "meta" },
          h("div", null, h("div", { class: "sec-n" }, p.sector || ""), h("div", { class: "sym" }, p.sym)),
          h("div", null, h("div", { class: "pl " + cls(p.plpc) }, fmt.pct(p.plpc)), h("div", { class: "val" }, fmt.money(p.value, 0) + " · " + fmt.signMoney(p.pl, 0))),
          ARROW()));
      card._p = p; card._cv = cv;
      grid.append(card);
    });
    stagger(grid); observeReveals(grid);
    $$(".hcard", grid).forEach((c) => c.addEventListener("reveal", () => { c._shown = true; drawSpark(c); }, { once: true }));
  }

  // refresh without rebuilding: card numbers, the orbit total, planet data for labels/tooltips
  function updateHoldings() {
    const bySym = {};
    (DATA.holdings || []).concat(DATA.sleeve || []).forEach((p) => { bySym[p.sym] = p; });
    $$(".hcard").forEach((c) => {
      const p = bySym[c.getAttribute("data-sym")]; if (!p) return;
      c._p = p;
      const pl = $(".pl", c); pl.className = "pl " + cls(p.plpc); pl.textContent = fmt.pct(p.plpc);
      $(".val", c).textContent = fmt.money(p.value, 0) + " · " + fmt.signMoney(p.pl, 0);
    });
    const all = (DATA.sleeve || []).concat(DATA.holdings || []);
    tween($("#orbitBig"), all.reduce((s, p) => s + (p.value || 0), 0), paintMoney, 1200);
    const sl = (DATA.sleeve || [])[0];
    $("#orbitSub").textContent = plural(stocksHeld().length, "stock", "stocks") + " · " + plural(coinsHeld().length, "coin", "coins") + (sl ? " · SPY sleeve " + fmt.money(sl.value, 0) : "");
    if (FIELD) {
      FIELD.planets.forEach((pl) => { if (bySym[pl.sym]) pl.p = bySym[pl.sym]; });
      plabelEls.forEach((el, i) => {
        const pl = FIELD.planets[i]; if (!pl) return;
        const pc = el.lastChild; pc.className = "p " + cls(pl.p.plpc); pc.textContent = pl.sleeve ? "sleeve" : fmt.pct(pl.p.plpc, 1);
      });
    }
  }

  function drawSpark(card) {
    const vals = EXTRAS && EXTRAS.spark && EXTRAS.spark[card._p.sym];
    if (!vals || vals.length < 2 || !card._shown) return;
    const cv = card._cv, rect = cv.getBoundingClientRect(), dpr = Math.min(2, W.devicePixelRatio || 1);
    if (!rect.width) return;
    cv.width = Math.round(rect.width * dpr); cv.height = Math.round(rect.height * dpr);
    const x = cv.getContext("2d"); x.setTransform(dpr, 0, 0, dpr, 0, 0);
    const w = rect.width, hh = rect.height, pl = 10, pr = 14, pt = 34, pb = 12;
    let lo = Math.min(...vals), hi = Math.max(...vals); const sp = (hi - lo) || hi * .01 || 1; lo -= sp * .08; hi += sp * .08;
    const pts = vals.map((v, i) => [pl + i * (w - pl - pr) / (vals.length - 1), pt + (hi - v) * (hh - pt - pb) / (hi - lo)]);
    const upCol = (card._p.plpc || 0) >= 0 ? "#34d399" : "#f87171", accent = card._p.kind === "sleeve" ? "#f3d484" : upCol;
    const t0 = performance.now(), dur = RM ? 0 : 1300;
    (function paint(now) {
      const k = dur ? Math.min(1, (now - t0) / dur) : 1, e = 1 - Math.pow(1 - k, 3);
      const n = Math.max(2, Math.ceil(e * (pts.length - 1)) + 1), end = pts[n - 1];
      x.clearRect(0, 0, w, hh);
      const g = x.createLinearGradient(0, pt, 0, hh); g.addColorStop(0, "rgba(243,212,132,.10)"); g.addColorStop(1, "rgba(243,212,132,0)");
      x.beginPath(); x.moveTo(pts[0][0], hh - pb); for (let i = 0; i < n; i++) x.lineTo(pts[i][0], pts[i][1]); x.lineTo(end[0], hh - pb); x.closePath();
      x.fillStyle = g; x.fill();
      const split = Math.floor((pts.length - 1) * .85);
      x.lineWidth = 2; x.lineJoin = "round"; x.lineCap = "round";
      x.beginPath(); for (let i = 0; i < Math.min(n, split + 1); i++) i ? x.lineTo(pts[i][0], pts[i][1]) : x.moveTo(pts[i][0], pts[i][1]);
      x.strokeStyle = "rgba(236,232,225,.5)"; x.stroke();
      if (n > split + 1) {
        x.beginPath(); x.moveTo(pts[split][0], pts[split][1]); for (let i = split + 1; i < n; i++) x.lineTo(pts[i][0], pts[i][1]);
        x.strokeStyle = accent; x.stroke();
      }
      x.beginPath(); x.arc(end[0], end[1], 4, 0, 6.2832); x.fillStyle = accent; x.fill();
      x.lineWidth = 2; x.strokeStyle = "#09090a"; x.stroke();
      if (k < 1) requestAnimationFrame(paint);
    })(t0);
  }

  // ---- 03 curve ----
  function niceTicks(lo, hi, n) {
    const raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / mag;
    const step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag, out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
    return { ticks: out, step };
  }
  function renderChart() {
    const s = DATA.series || [], box = $("#plot"), stats = $("#chartStats");
    box.textContent = ""; stats.textContent = "";
    if (s.length < 2) { box.append(h("div", { class: "label" }, "Need a few more robot runs to draw the line.")); return; }
    const vals = s.map((p) => p[1]), base = num(DATA.baseline), n = vals.length;
    const Wd = 1000, Ht = 300, pl = 62, pr = 14, pt = 14, pb = 30;
    let lo = Math.min(...vals), hi = Math.max(...vals);
    if (base !== null) { lo = Math.min(lo, base); hi = Math.max(hi, base); }
    const padv = (hi - lo) * .12 || hi * .002; lo -= padv; hi += padv;
    const { ticks, step } = niceTicks(lo, hi, 4);
    const dec = step >= 1000 ? 0 : step >= 100 ? 1 : 2;
    const X = (i) => pl + i * (Wd - pl - pr) / (n - 1), Y = (v) => pt + (hi - v) * (Ht - pt - pb) / (hi - lo);
    const d = vals.map((v, i) => (i ? "L" : "M") + X(i).toFixed(1) + "," + Y(v).toFixed(1)).join("");
    const svg = sv("svg", { viewBox: "0 0 " + Wd + " " + Ht, role: "img", "aria-label": "Account value over time, from " + fmt.money(vals[0]) + " to " + fmt.money(vals[n - 1]) });
    const defs = sv("defs"), grad = sv("linearGradient", { id: "areaG", x1: "0", x2: "0", y1: "0", y2: "1" });
    grad.append(sv("stop", { offset: "0", "stop-color": "#f3d484", "stop-opacity": ".13" }), sv("stop", { offset: "1", "stop-color": "#f3d484", "stop-opacity": "0" }));
    defs.append(grad); svg.append(defs);
    const g = sv("g", { class: "grid" });
    ticks.forEach((v) => {
      if (v < lo || v > hi) return;
      g.append(sv("line", { x1: pl, x2: Wd - pr, y1: Y(v), y2: Y(v) }));
      const t = sv("text", { x: pl - 10, y: Y(v) + 3.5, "text-anchor": "end", class: "tick" }); t.textContent = fmt.kmoney(v, dec); g.append(t);
    });
    const times = s.map((p) => new Date(p[0] * 1000));
    [0, .33, .66, 1].forEach((f) => {
      const i = Math.round(f * (n - 1)), t = sv("text", { x: X(i), y: Ht - 8, "text-anchor": f === 0 ? "start" : f === 1 ? "end" : "middle", class: "tick" });
      t.textContent = times[i].toLocaleDateString(undefined, { month: "short", day: "numeric" }); g.append(t);
    });
    svg.append(g);
    svg.append(sv("path", { class: "area", d: d + "L" + X(n - 1).toFixed(1) + "," + (Ht - pb) + "L" + pl + "," + (Ht - pb) + "Z", fill: "url(#areaG)" }));
    if (base !== null) {
      svg.append(sv("line", { class: "base", x1: pl, x2: Wd - pr, y1: Y(base), y2: Y(base) }));
      const bt = sv("text", { x: Wd - pr, y: Y(base) - 6, "text-anchor": "end", class: "tick" }); bt.textContent = "START " + fmt.money(base, 0); svg.append(bt);
    }
    svg.append(sv("path", { class: "ln", d, stroke: "#f3d484", pathLength: "1" }));
    const ex = X(n - 1), ey = Y(vals[n - 1]);
    svg.append(sv("circle", { class: "halo", cx: ex, cy: ey, r: 4, fill: "#f3d484" }));
    svg.append(sv("circle", { class: "enddot", cx: ex, cy: ey, r: 4.5, fill: "#f3d484", stroke: "#0c0c0d", "stroke-width": 2 }));
    const xh = sv("line", { class: "xh", x1: 0, x2: 0, y1: pt, y2: Ht - pb }), hd = sv("circle", { r: 4.5, fill: "#f3d484", stroke: "#0c0c0d", "stroke-width": 2, opacity: 0 });
    svg.append(xh, hd);
    const tip = h("div", { class: "tip" });
    box.append(svg, tip);
    box.setAttribute("tabindex", "0");
    box.setAttribute("aria-label", "Account value chart. Use left and right arrow keys to move through time.");

    let cur = n - 1;
    function show(i) {
      cur = clamp(i, 0, n - 1);
      const px = X(cur), py = Y(vals[cur]), r = svg.getBoundingClientRect(), sx = r.width / Wd;
      xh.setAttribute("x1", px); xh.setAttribute("x2", px); xh.style.opacity = 1;
      hd.setAttribute("cx", px); hd.setAttribute("cy", py); hd.setAttribute("opacity", 1);
      tip.textContent = "";
      const dv = base !== null ? vals[cur] - base : null;
      tip.append(h("b", null, fmt.money(vals[cur])),
        h("span", null, h("i", { class: "key" }), times[cur].toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) +
          (dv !== null ? " · " + fmt.signMoney(dv) + " vs start" : "")));
      tip.style.left = clamp(px * sx, 70, r.width - 70) + "px"; tip.style.top = py * sx + "px"; tip.style.opacity = 1;
    }
    function hide() { xh.style.opacity = 0; hd.setAttribute("opacity", 0); tip.style.opacity = 0; }
    box.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect(), sx = (e.clientX - r.left) / r.width * Wd;
      show(Math.round((sx - pl) / (Wd - pl - pr) * (n - 1)));
    });
    box.addEventListener("pointerleave", hide);
    box.addEventListener("blur", hide);
    box.addEventListener("keydown", (e) => {
      const stepN = e.shiftKey ? 10 : 1;
      if (e.key === "ArrowLeft") { show(cur - stepN); e.preventDefault(); }
      else if (e.key === "ArrowRight") { show(cur + stepN); e.preventDefault(); }
      else if (e.key === "Home") { show(0); e.preventDefault(); } else if (e.key === "End") { show(n - 1); e.preventDefault(); }
    });

    const st = (k, v, c) => h("div", null, k, h("b", { class: c || "" }, v));
    stats.append(st("Start", fmt.money(base, 0)), st("Low", fmt.money(Math.min(...vals), 0)), st("High", fmt.money(Math.max(...vals), 0)),
      st("Now", fmt.money(vals[n - 1], 0), cls(base !== null ? vals[n - 1] - base : null)), st("Runs", fmt.int(DATA.runs)));

    // table twin (dataviz: every chart has a table view): last value of each day
    const byDay = new Map();
    s.forEach((p) => byDay.set(new Date(p[0] * 1000).toISOString().slice(0, 10), p[1]));
    const tb = h("table", { class: "sr" }, h("caption", null, "Account value at the end of each day"),
      h("tr", null, h("th", null, "Day"), h("th", null, "Value")),
      Array.from(byDay).map(([dday, v]) => h("tr", null, h("td", null, dday), h("td", null, fmt.money(v)))));
    box.append(tb);

    const wrap = box.closest(".chart");
    const drawIn = () => box.classList.add("in");
    if (RM || wrap.classList.contains("in")) drawIn(); else wrap.addEventListener("reveal", drawIn, { once: true });
  }

  // ---- 04 universe ----
  function renderUniverse() {
    const heldN = stocksHeld().length;
    if (!UNI || !UNI.rows) {
      $("#uWatch").textContent = fmt.int(R().universe); $("#uHeld").textContent = String(heldN);
      $("#uShort").textContent = fmt.int(R().shortlist);
      return;
    }
    tween($("#uWatch"), UNI.rows.length, paintInt); tween($("#uUp"), UNI.n_up, paintInt);
    tween($("#uCross"), UNI.n_cross, paintInt); tween($("#uShort"), (UNI.shortlist || []).length, paintInt);
    tween($("#uHeld"), heldN, paintInt);
    $("#uStatus").textContent = "Live scan · " + fmt.int(UNI.rows.length) + " stars placed · " + new Date().toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
    const fs = $("#fUp"); if (fs) tween(fs, UNI.n_up, paintInt);
  }

  // ---- 05 machine ----
  function renderMachine() {
    const r = R(), held = stocksHeld().length, box = $("#funnel"), acts = $("#acts");
    box.textContent = ""; acts.textContent = "";
    const steps = [
      [fmt.int(r.universe), "Stocks scanned", "every 30 min while the market is open", null],
      [UNI ? fmt.int(UNI.n_up) : "—", "Trending up", "5-day average above the 20-day", "fUp"],
      [fmt.int(r.shortlist), "Shortlist", "strongest momentum, not overbought", null],
      [String(Math.max(0, (r.max_held || 0) - held)), "Open slots", "of " + (r.max_held || "—") + " · " + held + " held now", null],
      [fmt.int(DATA.fills_today), "Trades today", "filled orders, every robot", null],
    ];
    steps.forEach((s, i) => {
      if (i) box.append(h("div", { class: "farrow", "aria-hidden": "true" }, "→"));
      box.append(h("div", { class: "fstep brk", "data-reveal": "" }, h("div", { class: "label" }, s[1]), h("div", { class: "v", id: s[3] }, s[0]), h("div", { class: "s" }, s[2])));
    });
    const money0 = (v) => fmt.money(v, 0);
    const list = [
      ["Act I", "Scan", "Score every stock", "Momentum = 60% of the 3-month gain + 40% of the 6-month gain. The strongest risers score highest.",
        [fmt.int(r.universe) + " stocks, every run", "must be up over the last quarter", "skipped if RSI is above " + r.rsi]],
      ["Act II", "Gate", "Is it safe to buy today?", "Three whole-market checks can pause all buying for the day. Holdings are kept either way.",
        ["SPY 3-month return above " + r.trend_min + "%", "SPY daily swing under " + r.max_mkt_atr + "%", r.news ? "morning news not “risk-off”" : "news filter off"]],
      ["Act III", "Filter", "Pick from the top", "The best " + r.shortlist + " are checked one by one, strongest first.",
        ["no bad overnight news", "not sold in the last " + r.cooldown + " days", "max " + r.sector_cap + " stocks per sector"]],
      ["Act IV", "Size", "How much to spend", money0(r.per_buy) + " per buy, bent by volatility so every position carries similar risk.",
        ["calm stock: up to " + money0(r.per_buy * r.vol_max), "wild stock: down to " + money0(r.per_buy * r.vol_min), "max " + r.max_held + " stocks, " + money0(r.max_per_stock) + " each"]],
      ["Act V", "Exit", "Five ways out", "Checked on every holding, every run. The first rule that matches wins.",
        ["stop-loss at 4–" + r.stop + "%", "trailing stop " + r.trail + "% (only in profit)", "3-month trend breaks −" + r.mom_break + "%", "bad news, or the averages flip down"]],
    ];
    if (r.sleeve) list.push(["Act VI", "Park", "Idle cash goes to work", "Cash above " + money0(r.sleeve_buffer) + " is parked in SPY, and steps back to cash when the market turns.",
      ["sold first to fund stock buys", "only trades when $2,000+ off target", "logged apart from the stock score"]]);
    list.forEach((a, i) => acts.append(h("div", { class: "act brk spot", "data-reveal": "", "data-cur": a[1].toUpperCase() },
      h("span", { class: "glow" }), h("span", { class: "edge" }),
      h("div", { class: "top" }, h("span", { class: "n" }, a[0].toUpperCase() + " · " + pad2(i + 1)), h("span", { class: "t" }, a[1].toUpperCase())),
      h("h3", null, a[2]), h("p", null, a[3]), h("ul", null, a[4].map((x) => h("li", null, x))))));
    stagger(box); stagger(acts); observeReveals(box); observeReveals(acts);
  }

  // ---- 06 scoreboard ----
  function renderScores() {
    const box = $("#score"); box.textContent = "";
    const sc = ((EXTRAS && EXTRAS.scores) || []).slice();
    if (!sc.length) { box.append(h("div", { class: "label", "data-reveal": "" }, EXTRAS ? "No completed trades to grade yet." : "Grading real trades…")); observeReveals(box); return; }
    const order = ["sma_scan_v1", "crypto_sma_v1", "spy_sleeve_v1", "options_long_v1"];
    sc.sort((a, b) => (order.indexOf(a.key) + 1 || 99) - (order.indexOf(b.key) + 1 || 99));
    const maxAbs = Math.max(2, ...sc.filter((x) => x.n).map((x) => Math.abs(x.avg || 0)));
    sc.forEach((s, i) => {
      const d = (i * .08) + "s";
      const note = s.n ? s.n + " completed · " + (s.open || 0) + " open" : "too new to grade · " + (s.open || 0) + " open";
      const row = h("div", { class: "srow brk", "data-reveal": "" }, h("div", { class: "nm" }, s.name, h("small", null, note)));
      if (!s.n) {
        row.append(h("div", { class: "c", style: "grid-column:2 / -1" }, h("div", { class: "label" }, "Waiting for its first completed round trip")));
      } else {
        const vs = num(s.spy) !== null && num(s.avg) !== null ? s.avg - s.spy : null;
        const wm = h("i", { style: "--d:" + d + ";background:var(--gold)" });
        row.append(
          h("div", { class: "c" }, h("div", { class: "label" }, "Win rate"), h("div", { class: "v" }, fmt.int(s.win) + "%"), h("div", { class: "meter" }, wm)),
          h("div", { class: "c" }, h("div", { class: "label" }, "Avg / trade"), h("div", { class: "v " + cls(s.avg) }, fmt.pct(s.avg))),
          h("div", { class: "c" }, h("div", { class: "label" }, "Realised"), h("div", { class: "v " + cls(s.pnl) }, fmt.signMoney(s.pnl, 0))),
          h("div", { class: "c" }, h("div", { class: "label" }, "vs SPY"), h("div", { class: "v " + cls(vs) }, vs === null ? "—" : (vs >= 0 ? "Beat by " : "Lost by ") + Math.abs(vs).toFixed(2) + "%")));
        const w = Math.abs(s.avg || 0) / maxAbs * 48, pos = (s.avg || 0) >= 0;
        const bar = h("i", { class: pos ? "pos" : "neg", style: "--d:" + d });
        const lbl = h("span", { class: "lbl", style: pos ? "left:calc(50% + " + w + "% + 8px)" : "right:calc(50% + " + w + "% + 8px)" }, fmt.pct(s.avg));
        row.append(h("div", { class: "c divc" }, h("div", { class: "label" }, "Avg per trade, centred on zero"), h("div", { class: "div-bar", role: "img", "aria-label": s.name + " average per trade " + fmt.pct(s.avg) }, h("span", { class: "zero" }), bar, lbl)));
        row.addEventListener("reveal", () => { wm.style.width = (s.win || 0) + "%"; bar.style.width = w + "%"; }, { once: true });
      }
      box.append(row);
    });
    stagger(box); observeReveals(box);
  }

  // ---- 07 log ----
  function renderLog() {
    const nw = DATA.news, read = nw && nw.read ? nw.read : null;
    const rd = $("#newsRead"); rd.textContent = "";
    const col = read === "risk_off" ? "var(--down)" : read === "risk_on" ? "var(--up)" : "var(--gold)";
    rd.append(h("span", { class: "live-dot", style: "width:9px;height:9px;margin:0;background:" + col + ";box-shadow:0 0 10px " + col }),
      read ? read.replace("_", " ") : "No scan yet");
    $("#newsWhy").textContent = nw ? nw.reason || "" : "The news scan runs about 8:45am ET on trading days.";
    $("#newsDate").textContent = nw ? (nw.today ? "Today" : nw.date || "") : "";
    const ls = DATA.lesson;
    $("#lessonDate").textContent = ls ? ls.head.split(" · ")[0] : "";
    $("#lessonTxt").textContent = ls ? ls.text : "No self-review yet: the first one runs tonight.";
    const ml = $("#mlChips"); ml.textContent = "";
    (DATA.ml_picks || []).forEach((s) => ml.append(h("span", null, s)));
    if (!(DATA.ml_picks || []).length) ml.append(h("span", null, "no picks yet"));

    renderTape();
  }
  let tapeKey = "";
  function renderTape() {
    const dec = DATA.decisions || [];
    const key = dec.length ? dec.length + "|" + dec[0].t + "|" + dec[0].sym + "|" + dec[0].act : "none";
    if (key === tapeKey) return;            // unchanged: don't restart the marquee
    tapeKey = key;
    const tape = $("#tape"); tape.textContent = "";
    if (!dec.length) return;
    const mk = (list) => list.map((d) => h("div", { class: "tk" }, h("span", { class: "b " + d.act }, d.act), h("span", { class: "s" }, d.sym),
      h("span", { class: "t" }, d.t.slice(5) + " · " + d.who), h("span", { class: "w" }, d.why)));
    const a = dec.filter((_, i) => i % 2 === 0), b = dec.filter((_, i) => i % 2 === 1);
    [a, b].forEach((list, i) => {
      if (!list.length) return;
      const tr = h("div", { class: "track" + (i ? " rev" : "") }, mk(list), mk(list));
      tr.lastChild && Array.from(tr.children).slice(list.length).forEach((c) => c.setAttribute("aria-hidden", "true"));
      tape.append(tr);
    });
  }

  // ---- 08 enter ----
  function glyph(kind) {
    const s = sv("svg", { viewBox: "0 0 100 60", fill: "none", stroke: "#f3d484", "stroke-width": "1.4", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" });
    const P = (d, extra) => { const p = sv("path", Object.assign({ d, class: "draw", pathLength: "1" }, extra || {})); s.append(p); };
    const dim = { stroke: "rgba(255,255,255,.35)" };
    switch (kind) {
      case "overview": P("M0 50 L14 42 L26 46 L40 28 L54 34 L68 16 L82 22 L100 6"); P("M0 58 H100", dim); break;
      case "holdings": P("M50 30 m-24 0 a24 24 0 1 0 48 0 a24 24 0 1 0 -48 0", dim); P("M50 30 m-5 0 a5 5 0 1 0 10 0 a5 5 0 1 0 -10 0");
        P("M74 30 m-3 0 a3 3 0 1 0 6 0 a3 3 0 1 0 -6 0"); P("M33 13 m-2 0 a2 2 0 1 0 4 0 a2 2 0 1 0 -4 0"); break;
      case "crypto": P("M50 4 L74 17 L74 43 L50 56 L26 43 L26 17 Z"); P("M50 16 L62 23 L62 37 L50 44 L38 37 L38 23 Z", dim); break;
      case "decisions": P("M4 30 H40"); P("M40 30 L62 12 H96"); P("M40 30 L62 48 H96", dim); break;
      case "trades": P("M28 54 V8 M18 18 L28 8 L38 18"); P("M72 6 V52 M62 42 L72 52 L82 42", dim); break;
      case "scoreboard": P("M12 58 V40 M32 58 V22 M52 58 V32 M72 58 V10 M92 58 V28"); P("M0 58 H100", dim); break;
      case "universe": { let d = ""; for (let i = 0; i <= 120; i++) { const t = i / 120 * 12.5, r = 1.8 * t; d += (i ? "L" : "M") + (50 + Math.cos(t) * r * 1.7).toFixed(1) + " " + (30 + Math.sin(t) * r).toFixed(1); } P(d); break; }
      case "news": P("M10 10 H90"); P("M10 24 H90 M10 38 H72 M10 52 H50", dim); break;
      case "research": P("M40 28 m-18 0 a18 18 0 1 0 36 0 a18 18 0 1 0 -36 0"); P("M53 41 L72 58"); P("M30 28 H50", dim); break;
      default: P("M8 30 H92 M78 16 L92 30 L78 44");
    }
    return s;
  }
  function renderEnter() {
    const box = $("#enter"); box.textContent = "";
    const pages = [
      ["/overview", "overview", "Overview", "Account value, the chart, today's picks"],
      ["/holdings", "holdings", "Holdings", "Every stock position, with profit and loss"],
      ["/crypto", "crypto", "Crypto", "The 24/7 coin sleeve"],
      ["/decisions", "decisions", "Decisions", "Every BUY, SELL and WAIT, with the reason"],
      ["/trades", "trades", "Trades", "Every order: filled, blocked or skipped"],
      ["/scoreboard", "scoreboard", "Scoreboard", "Real results vs the S&P 500"],
      ["/universe", "universe", "Universe", "All " + fmt.int(R().universe) + " stocks and their signals"],
      ["/news", "news", "News", "The pre-market read, day by day"],
      ["/research", "research", "Research", "The robot's nightly self-review"],
    ];
    pages.forEach((p, i) => box.append(h("a", { class: "ecard brk spot", href: p[0], "data-reveal": "", "data-cur": "OPEN" },
      h("span", { class: "glow" }), h("div", { class: "pv" }, glyph(p[1])),
      h("div", { class: "ft" }, h("div", null, h("div", { class: "ey" }, "Page " + pad2(i + 1)), h("div", { class: "nm" }, p[2]), h("div", { class: "ds" }, p[3])), ARROW()))));
    (DATA.others || []).forEach((o) => box.append(h("a", { class: "ecard brk spot", href: o.url, "data-reveal": "", "data-cur": "SWITCH" },
      h("span", { class: "glow" }), h("div", { class: "pv" }, glyph("other")),
      h("div", { class: "ft" }, h("div", null, h("div", { class: "ey" }, "Other account"), h("div", { class: "nm" }, o.label), h("div", { class: "ds" }, "Its own robot, its own field")), ARROW()))));
    stagger(box); observeReveals(box);
  }

  /* ======================================================================
     MOTION SYSTEM
     ====================================================================== */
  let revealIO = null;
  function stagger(box) { Array.from(box.children).forEach((c, i) => c.style.setProperty("--d", Math.min(i, 12) * .07 + "s")); }
  function observeReveals(root) {
    $$("[data-reveal],[data-wipe]", root).forEach((el) => { if (!el._obs && !el.classList.contains("in")) { el._obs = 1; revealIO.observe(el); } });
  }
  function setupReveals() {
    revealIO = new IntersectionObserver((es) => es.forEach((e) => {
      if (!e.isIntersecting) return;
      e.target.classList.add("in"); revealIO.unobserve(e.target);
      e.target.dispatchEvent(new CustomEvent("reveal"));
    }), { threshold: .12, rootMargin: "0px 0px -6% 0px" });
    $$("[data-stagger]").forEach(stagger);
    // titles: word masks
    $$("[data-split]").forEach((t) => {
      const words = t.textContent.trim().split(/\s+/); t.textContent = "";
      words.forEach((w, i) => { const s = h("span", null, w); s.style.setProperty("--d", (i * .07) + "s"); t.append(h("span", { class: "w" }, s), i < words.length - 1 ? " " : ""); });
      t.setAttribute("data-reveal-title", ""); revealIO.observe(t);
    });
    // kickers: typewriter
    $$("[data-type]").forEach((k) => {
      const full = k.getAttribute("data-type"), m = full.split(" / ");
      const n = h("span", { class: "n" }), txt = h("span", { class: "txt" }), caret = h("span", { class: "caret" });
      k.append(n, txt, caret);
      const type = () => {
        if (RM) { n.textContent = m[0]; txt.textContent = " / " + m.slice(1).join(" / "); return; }
        const s = m[0] + " / " + m.slice(1).join(" / "); let i = 0;
        (function tick() { i++; n.textContent = s.slice(0, Math.min(i, m[0].length)); txt.textContent = s.slice(m[0].length, i); if (i < s.length) setTimeout(tick, 26); })();
      };
      k.addEventListener("reveal", type, { once: true }); k.setAttribute("data-reveal-k", ""); revealIO.observe(k);
    });
    observeReveals(D);
  }

  // which section is centred: drives the field, the nav dots and the chime
  let active = "hero", manualState = null;
  function setupSections() {
    const secs = $$("#hero, main > .sec");
    const nav = $$(".dots a");
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) activate(e.target); }), { rootMargin: "-48% 0px -48% 0px" });
    secs.forEach((s) => io.observe(s));
    function activate(sec) {
      if (active === sec.id) return;
      active = sec.id;
      const idx = sec.id === "hero" ? 0 : +sec.id.slice(1);
      nav.forEach((a) => a.classList.toggle("on", +a.getAttribute("data-i") === idx));
      const st = idx === 0 ? (manualState || "wordmark") : sec.getAttribute("data-field");
      if (FIELD) { FIELD.setState(st); FIELD.setDim(parseFloat(sec.getAttribute("data-dim")) || .5); }
      const co = $("#coords"); if (co && co.firstChild) co.firstChild.textContent = "FIELD " + pad2(idx) + " · " + st.toUpperCase();
      Sound.chime(idx);
      if (idx === 4 && !UNI) loadUniverse();
    }
  }

  function setupHero() {
    const hero = $("#hero"), inner = $("#heroIn"), prog = $(".progress i");
    let ticking = false;
    function onScroll() {
      if (ticking) return; ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        const y = W.scrollY, vh = innerHeight, p = clamp(y / (vh * .8), 0, 1);
        if (!RM) {
          inner.style.opacity = String(1 - p * 1.05);
          inner.style.transform = "translateY(" + (-p * 70) + "px) scale(" + (1 - p * .04) + ")";
          inner.style.filter = p > .01 ? "blur(" + (p * 6).toFixed(2) + "px)" : "";
        }
        const max = D.documentElement.scrollHeight - vh;
        prog.style.transform = "scaleX(" + (max > 0 ? y / max : 0) + ")";
      });
    }
    addEventListener("scroll", onScroll, { passive: true }); onScroll();
    // tap anywhere on the hero: a shockwave through the field, then the reveal
    hero.addEventListener("click", (e) => {
      if (e.target.closest("a,button,input,.seg")) return;
      if (FIELD) FIELD.wave(e.clientX, e.clientY);
      Sound.chime(1);
      setTimeout(() => go("s1"), RM ? 0 : 380);
    });
    $("#cue").addEventListener("click", (e) => { e.stopPropagation(); if (FIELD) FIELD.wave(innerWidth / 2, innerHeight * .8); go("s1"); });
    $$(".seg button").forEach((b) => b.addEventListener("click", (e) => {
      e.stopPropagation();
      manualState = b.getAttribute("data-state");
      $$(".seg button").forEach((x) => x.classList.toggle("on", x === b));
      if (manualState === "galaxy" && !UNI) loadUniverse();
      if (FIELD && active === "hero") FIELD.setState(manualState);
    }));
    // shooting stars
    if (!RM) setInterval(() => {
      if (active !== "hero" || D.hidden) return;
      const s = h("div", { class: "streak" }), a = 28 + Math.random() * 22, len = 260 + Math.random() * 280;
      s.style.left = (10 + Math.random() * 70) + "%"; s.style.top = (8 + Math.random() * 35) + "%";
      s.style.setProperty("--a", a + "deg");
      s.style.setProperty("--dx", Math.cos(a * Math.PI / 180) * len + "px"); s.style.setProperty("--dy", Math.sin(a * Math.PI / 180) * len + "px");
      inner.append(s); requestAnimationFrame(() => s.classList.add("go"));
      setTimeout(() => s.remove(), 1500);
    }, 4200);
  }

  function go(id) {
    const el = D.getElementById(id); if (!el) return;
    el.scrollIntoView({ behavior: RM ? "auto" : "smooth", block: "start" });
  }

  // ---- labels + hover for the orbit and the galaxy ----
  const stageVis = { orbit: false, uni: false };
  function setupStages() {
    const io = new IntersectionObserver((es) => es.forEach((e) => {
      if (e.target.id === "orbitStage") stageVis.orbit = e.isIntersecting; else stageVis.uni = e.isIntersecting;
    }), { threshold: 0 });
    io.observe($("#orbitStage")); io.observe($("#uniStage"));
  }
  let plabelEls = [], slabelEls = [];
  function buildLabels() {
    const box = $("#plabels"); box.textContent = ""; plabelEls = [];
    if (!FIELD) return;
    FIELD.planets.forEach((p) => {
      const el = h("div", { class: "plabel" }, p.sym, h("span", { class: "p " + cls(p.p.plpc) }, p.sleeve ? "sleeve" : fmt.pct(p.p.plpc, 1)));
      box.append(el); plabelEls.push(el);
    });
  }
  function buildSectorLabels() {
    const box = $("#slabels"); box.textContent = ""; slabelEls = [];
    const names = (UNI && UNI.sectors) || [];
    names.forEach((n) => { const el = h("div", { class: "slabel" }, n === "Information Technology" ? "Tech" : n); box.append(el); slabelEls.push(el); });
  }
  let hoverI = -1;
  function onFrame(F) {
    const st = F.state, ready = F.morph() > .88;
    // planet labels
    if (st === "sphere" && stageVis.orbit && ready) {
      if (plabelEls.length !== F.planets.length) buildLabels();
      const rect = $("#orbitStage").getBoundingClientRect();
      F.planets.forEach((p, i) => {
        const q = F.project(p.x, p.y, p.z), el = plabelEls[i]; if (!el) return;
        if (!q) { el.classList.remove("show"); return; }
        const rad = F.pointSize(p.size, q.z) / 2;
        el.style.transform = "translate(" + (q.x - rect.left + rad + 6).toFixed(1) + "px," + (q.y - rect.top - 6).toFixed(1) + "px)";
        el.classList.add("show"); el.classList.toggle("focus", i === hoverI);
      });
    } else if (plabelEls.length && plabelEls[0].classList.contains("show")) plabelEls.forEach((el) => el.classList.remove("show"));
    // sector labels on the galaxy rim
    if (st === "galaxy" && stageVis.uni && ready && UNI) {
      if (slabelEls.length !== F.anchors.length) buildSectorLabels();
      const rect = $("#uniStage").getBoundingClientRect();
      F.anchors.forEach((a, i) => {
        const q = F.project(a[0], a[1], a[2]), el = slabelEls[i]; if (!el) return;
        if (!q) { el.classList.remove("show"); return; }
        el.style.transform = "translate(-50%,-50%) translate(" + (q.x - rect.left).toFixed(1) + "px," + (q.y - rect.top).toFixed(1) + "px)";
        el.classList.add("show");
      });
    } else if (slabelEls.length && slabelEls[0].classList.contains("show")) slabelEls.forEach((el) => el.classList.remove("show"));
    if (!RM && F.fps) { const c = $("#fps"); if (c && active === "hero" && (F._fpsShown !== F.fps)) { F._fpsShown = F.fps; c.textContent = fmt.int(F.N) + " PARTICLES · " + F.fps + " FPS"; } }
  }

  const tipEl = () => $("#stip");
  function showTip(x, y, parts) {
    const t = tipEl(); t.textContent = "";
    parts.forEach((p) => t.append(p));
    const w = t.offsetWidth || 180, hgt = t.offsetHeight || 80;
    t.style.transform = "translate(" + clamp(x + 18, 8, innerWidth - w - 8) + "px," + clamp(y + 18, 70, innerHeight - hgt - 50) + "px)";
    t.style.opacity = 1;
  }
  function hideTip() { tipEl().style.opacity = 0; }
  function setupHover() {
    let px = -1, py = -1, pending = false;
    addEventListener("pointermove", (e) => {
      if (FIELD) FIELD.mouse(e.clientX, e.clientY);
      px = e.clientX; py = e.clientY;
      if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; hover(px, py, e.target); }); }
    }, { passive: true });
    H.addEventListener("pointerleave", () => { if (FIELD) FIELD.mouseOut(); hideTip(); });
    // allocation bar segments share the fixed tooltip
    $("#allocBar").addEventListener("pointermove", (e) => {
      const t = e.target.closest("i"); if (!t || !t._tip) return;
      showTip(e.clientX, e.clientY, [h("b", null, t._tip[1]), h("span", { class: "s" }, t._tip[0] + " · " + t._tip[2])]);
    });
    $("#allocBar").addEventListener("pointerleave", hideTip);
    // a card in the grid lights up its planet
    $("#hgrid").addEventListener("pointerover", (e) => {
      const c = e.target.closest(".hcard"); if (!c || !FIELD) return;
      const i = FIELD.planets.findIndex((p) => p.sym === c.getAttribute("data-sym"));
      hoverI = i; FIELD.setFocus(i >= 0 ? FIELD.planets[i].i : -10);
    });
    $("#hgrid").addEventListener("pointerleave", () => { hoverI = -1; if (FIELD) FIELD.setFocus(-10); });
  }
  function hover(x, y, target) {
    if (!FIELD || (target && target.closest && target.closest("#allocBar"))) return;
    const st = FIELD.state;
    if (st === "sphere" && stageVis.orbit && FIELD.morph() > .9) {
      let best = -1, bd = 1e9;
      FIELD.planets.forEach((p, i) => {
        const q = FIELD.project(p.x, p.y, p.z); if (!q) return;
        const d = Math.hypot(q.x - x, q.y - y), rad = FIELD.pointSize(p.size, q.z) / 2 + 8;
        if (d < rad && d < bd) { bd = d; best = i; }
      });
      hoverI = best; FIELD.setFocus(best >= 0 ? FIELD.planets[best].i : -10);
      if (best >= 0) {
        const p = FIELD.planets[best].p;
        showTip(x, y, [h("b", null, p.sym), h("span", { class: "s" }, p.sector || ""),
          h("div", { class: "row" }, "Value", h("b", null, fmt.money(p.value))),
          h("div", { class: "row" }, "Profit", h("b", { class: cls(p.pl) }, fmt.signMoney(p.pl) + " (" + fmt.pct(p.plpc) + ")")),
          h("div", { class: "row" }, "Bought at", h("b", null, fmt.money(p.entry)))]);
      } else hideTip();
      return;
    }
    if (st === "galaxy" && stageVis.uni && FIELD.morph() > .9 && FIELD.stars && UNI) {
      const S = FIELD.stars; let best = -1, bd = 16;
      for (let i = 0; i < S.n; i++) {
        const q = FIELD.project(S.pos[i * 3], S.pos[i * 3 + 1], S.pos[i * 3 + 2]); if (!q) continue;
        const d = Math.hypot(q.x - x, q.y - y); if (d < bd) { bd = d; best = i; }
      }
      const rw = best >= 0 ? S.rows[best] : null;
      if (rw) {
        const tags = [(rw[7] & 1) && "held", (rw[7] & 2) && "shortlist", (rw[7] & 4) && "fresh crossover"].filter(Boolean).join(" · ");
        showTip(x, y, [h("b", null, rw[0]), h("span", { class: "s" }, (UNI.sectors[rw[1]] || "") + (tags ? " · " + tags : "")),
          h("div", { class: "row" }, "3-month", h("b", { class: cls(rw[2]) }, fmt.pct(rw[2], 1))),
          h("div", { class: "row" }, "6-month", h("b", { class: cls(rw[3]) }, fmt.pct(rw[3], 1))),
          h("div", { class: "row" }, "RSI · swing", h("b", null, (rw[4] === null ? "—" : rw[4]) + " · " + (rw[5] === null ? "—" : rw[5] + "%"))),
          h("div", { class: "row" }, "Trend", h("b", { class: rw[6] ? "up" : "down" }, rw[6] ? "▲ up" : "▼ down"))]);
      } else hideTip();
      return;
    }
    hoverI = -1; FIELD.setFocus(-10); hideTip();
  }

  // ---- spotlight + 3D tilt on cards ----
  function setupCards() {
    D.addEventListener("pointermove", (e) => {
      const c = e.target.closest && e.target.closest(".spot"); if (!c) return;
      const r = c.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
      c.style.setProperty("--mx", mx + "px"); c.style.setProperty("--my", my + "px");
      if (FINE && c.matches(".hcard,.ecard") && c.classList.contains("in")) {
        c.style.transition = "transform .25s var(--ease), border-color .4s";
        c.style.transform = "perspective(900px) rotateX(" + ((.5 - my / r.height) * 7).toFixed(2) + "deg) rotateY(" + ((mx / r.width - .5) * 9).toFixed(2) + "deg)";
      }
    }, { passive: true });
    D.addEventListener("pointerout", (e) => {
      const c = e.target.closest && e.target.closest(".hcard,.ecard");
      if (c && !c.contains(e.relatedTarget)) { c.style.transform = ""; }
    });
  }

  // ---- custom cursor ----
  function setupCursor() {
    if (!FINE) return;
    const dot = $(".cur-dot"), ring = $(".cur-ring"), lbl = $(".cur-ring .lbl");
    let x = -100, y = -100, rxp = -100, ryp = -100;
    addEventListener("pointermove", (e) => { x = e.clientX; y = e.clientY; dot.style.transform = "translate(" + x + "px," + y + "px)"; }, { passive: true });
    (function loop() { rxp += (x - rxp) * .2; ryp += (y - ryp) * .2; ring.style.transform = "translate(" + rxp.toFixed(1) + "px," + ryp.toFixed(1) + "px)"; requestAnimationFrame(loop); })();
    D.addEventListener("pointerover", (e) => {
      const t = e.target.closest && e.target.closest("a,button,[data-cur],.plot");
      if (t) { ring.classList.add("hot"); lbl.textContent = t.getAttribute("data-cur") || (t.classList.contains("plot") ? "READ" : t.tagName === "A" ? "OPEN" : ""); }
      else ring.classList.remove("hot");
    });
    H.addEventListener("pointerleave", () => { dot.style.opacity = 0; ring.style.opacity = 0; });
    H.addEventListener("pointerenter", () => { dot.style.opacity = ""; ring.style.opacity = ""; });
  }

  // ---- auto tour ----
  function setupTour() {
    const btn = $("#tourBtn"), order = ["hero", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"];
    let timer = 0, on = false, ownScroll = 0;
    function step() {
      const i = order.indexOf(active), nx = order[i + 1];
      if (!nx) { stopTour(); return; }
      ownScroll = performance.now(); go(nx);
      timer = setTimeout(step, 7500);
    }
    function startTour() { on = true; btn.classList.add("on"); btn.setAttribute("aria-pressed", "true"); step(); }
    function stopTour() { on = false; clearTimeout(timer); btn.classList.remove("on"); btn.setAttribute("aria-pressed", "false"); }
    btn.addEventListener("click", (e) => { e.stopPropagation(); on ? stopTour() : startTour(); });
    addEventListener("keydown", (e) => {
      if (e.target.closest && e.target.closest("input,textarea")) return;
      if ((e.key === "t" || e.key === "T") && !e.metaKey && !e.ctrlKey && !e.altKey) { on ? stopTour() : startTour(); return; }
      if (on && !["Shift", "Meta", "Control", "Alt"].includes(e.key)) stopTour();
    });
    const userStop = () => { if (on && performance.now() - ownScroll > 900) stopTour(); };
    addEventListener("wheel", userStop, { passive: true }); addEventListener("touchstart", userStop, { passive: true });
  }

  // ---- sound: an ambient drone + a chime per section (off until clicked) ----
  const Sound = {
    ctx: null, master: null, on: false,
    init() {
      const AC = W.AudioContext || W.webkitAudioContext; if (!AC) return false;
      const c = this.ctx = new AC(), m = this.master = c.createGain(); m.gain.value = 0; m.connect(c.destination);
      const f = c.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = 520; f.Q.value = .6; f.connect(m);
      [[55, "sine", .22], [82.41, "sine", .12], [110.3, "triangle", .045], [164.8, "sine", .03]].forEach(([fr, ty, g]) => {
        const o = c.createOscillator(), gg = c.createGain(); o.type = ty; o.frequency.value = fr; gg.gain.value = g; o.connect(gg); gg.connect(f); o.start();
      });
      const l = c.createOscillator(), lg = c.createGain(); l.frequency.value = .05; lg.gain.value = 240; l.connect(lg); lg.connect(f.frequency); l.start();
      this.delay = c.createDelay(); this.delay.delayTime.value = .38; const fb = c.createGain(); fb.gain.value = .35;
      this.delay.connect(fb); fb.connect(this.delay); this.delay.connect(m);
      return true;
    },
    toggle() {
      if (!this.ctx && !this.init()) return;
      this.on = !this.on;
      if (this.on) this.ctx.resume();
      this.master.gain.setTargetAtTime(this.on ? .5 : 0, this.ctx.currentTime, .6);
      const b = $("#soundBtn"); b.classList.toggle("on", this.on); b.setAttribute("aria-pressed", String(this.on));
      $("#soundTxt").textContent = this.on ? "Sound on" : "Sound off";
    },
    chime(i) {
      if (!this.on || !this.ctx) return;
      const c = this.ctx, t = c.currentTime, notes = [440, 523.25, 587.33, 659.25, 783.99, 880, 1046.5, 1174.66, 1318.5];
      const o = c.createOscillator(), g = c.createGain(); o.type = "sine"; o.frequency.value = notes[i % notes.length];
      g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(.14, t + .02); g.gain.exponentialRampToValueAtTime(.0001, t + 2.4);
      o.connect(g); g.connect(this.master); g.connect(this.delay); o.start(t); o.stop(t + 2.5);
    },
  };

  // ---- boot sequence (once per session) then the hero entrance ----
  function boot(done) {
    if (!H.classList.contains("boot")) { done(); return; }
    const box = $("#boot"), lines = $$(".ln", box), meter = $(".meter i", box), pct = $(".pct .n", box);
    let finished = false; const t0 = performance.now(), DUR = 1900;
    lines.forEach((l, i) => setTimeout(() => l.classList.add("on"), 120 + i * 260));
    (function tick(now) {
      if (finished) return;
      const k = Math.min(1, (now - t0) / DUR);
      meter.style.transform = "scaleX(" + k + ")"; pct.textContent = String(Math.round(k * 100)).padStart(3, "0");
      if (k < 1) requestAnimationFrame(tick); else finish();
    })(t0);
    function finish() {
      if (finished) return; finished = true;
      lines.forEach((l) => l.classList.add("on")); meter.style.transform = "scaleX(1)"; pct.textContent = "100";
      box.classList.add("out");
      try { sessionStorage.setItem("tr-boot", "1"); } catch (e) {}
      setTimeout(() => { H.classList.remove("boot"); }, 900);
      setTimeout(done, 150);
    }
    const skip = () => { finish(); removeEventListener("keydown", skip); };
    box.addEventListener("click", skip); addEventListener("keydown", skip, { once: true });
  }

  function enter() {
    H.classList.add("enter");
    if (FIELD) {
      const sec = D.getElementById(active);
      FIELD.setDim(sec ? parseFloat(sec.getAttribute("data-dim")) || .5 : 1);
      const fontGate = D.fonts && D.fonts.load ? Promise.race([D.fonts.load("200 100px Geist"), new Promise((r) => setTimeout(r, 1500))]) : Promise.resolve();
      fontGate.then(() => {
        FIELD.fontsReady();
        const st = active === "hero" ? (manualState || "wordmark") : (sec && sec.getAttribute("data-field")) || "wordmark";
        FIELD.setState(st, true);
        setTimeout(() => H.classList.add("fieldon"), RM ? 0 : 1700);
      });
    } else H.classList.add("nofield");
  }

  // ---- data feeds ----
  function getJSON(url) { return fetch(url, { cache: "no-store" }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }); }
  let uniLoading = false;
  function loadUniverse() {
    if (uniLoading || UNI) return; uniLoading = true;
    $("#uStatus").textContent = "Placeholder stars · scanning " + fmt.int(R().universe) + " stocks (first load can take ~20s)";
    getJSON("/api/universe").then((u) => {
      uniLoading = false;
      if (u.error || !u.rows) { $("#uStatus").textContent = "Live scan unavailable · showing placeholder stars"; return; }
      UNI = u; renderUniverse(); buildSectorLabels();
      if (FIELD && FIELD.state === "galaxy") FIELD.setState("galaxy", true);
    }).catch(() => { uniLoading = false; $("#uStatus").textContent = "Live scan unavailable · showing placeholder stars"; });
  }
  function loadExtras() {
    getJSON("/api/extras").then((x) => {
      if (x.error) return;
      EXTRAS = x; renderScores(); $$(".hcard").forEach(drawSpark);
    }).catch(() => { const b = $("#score"); b.textContent = ""; b.append(h("div", { class: "label" }, "Trade grading unavailable right now.")); });
  }
  function refresh() {
    if (D.hidden) return;
    getJSON("/api/intro").then((d) => {
      if (d.error) return;
      const oldSyms = (DATA.holdings || []).map((p) => p.sym).join();
      DATA = d; if (FIELD) FIELD.setData(DATA);
      renderLive(); renderAccount(); renderLog(); renderUniverse();
      if ((d.holdings || []).map((p) => p.sym).join() !== oldSyms) {
        renderHoldings(); if (FIELD && FIELD.state === "sphere") { FIELD.setState("sphere", true); buildLabels(); }
      } else updateHoldings();
    }).catch(() => {});
  }

  /* ======================================================================
     MAIN
     ====================================================================== */
  function main() {
    H.classList.add("fx");
    if (DATA.error) { const e = $("#err"); e.textContent = "Live data unavailable: " + DATA.error; e.style.display = "block"; }
    try { FIELD = createField($("#field")); } catch (e) { console.warn("[intro] field disabled:", e); FIELD = null; }
    if (FIELD) { FIELD.setData(DATA); FIELD.onFrame = onFrame; FIELD.start(); } else H.classList.add("nofield");
    bindText();
    setupReveals();
    renderLive(); renderAccount(); renderHoldings(); renderChart(); renderUniverse(); renderMachine(); renderScores(); renderLog(); renderEnter();
    observeReveals(D);
    setupSections(); setupHero(); setupStages(); setupHover(); setupCards(); setupCursor(); setupTour();
    $("#soundBtn").addEventListener("click", (e) => { e.stopPropagation(); Sound.toggle(); });
    D.addEventListener("visibilitychange", () => { if (!FIELD) return; if (D.hidden) FIELD.stop(); else FIELD.start(); });
    let rt = 0;
    addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => {
      if (FIELD) { FIELD.resize(); if (FIELD.state === "wordmark") FIELD.setState("wordmark", true); }
      $$(".hcard").forEach(drawSpark);
    }, 180); });
    boot(enter);
    loadExtras(); setTimeout(loadUniverse, 1200);
    setInterval(refresh, 60000); setInterval(loadExtras, 300000);
    if (/[?&]debug\b/.test(location.search)) W.__tr = { field: FIELD, go, hover, stageVis, refresh, data: () => DATA, uni: () => UNI };
    W.__introOK = true;
  }
  try { main(); } catch (e) { H.classList.remove("fx", "boot", "finepointer"); console.error("[intro]", e); }
})();
