/* Shared motion for the dashboard's data pages (the intro page has its own).
   - content eases in on the FIRST visit to a page this session (the 60s auto-refresh
     reloads the page, and replaying the entrance every minute would be noise)
   - money / count values roll up to their number
   - a soft spotlight follows the pointer across cards and panels
   Page-to-page cross-fades come from CSS view transitions in shell(). */
(function () {
  "use strict";
  var D = document, H = D.documentElement;
  var rm = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;

  D.addEventListener("pointermove", function (e) {
    var c = e.target.closest && e.target.closest(".stat,.card,.panel");
    if (!c) return;
    var r = c.getBoundingClientRect();
    c.style.setProperty("--mx", (e.clientX - r.left) + "px");
    c.style.setProperty("--my", (e.clientY - r.top) + "px");
  }, { passive: true });

  var key = "tr-seen:" + location.pathname + location.search, first = true;
  try { first = !sessionStorage.getItem(key); sessionStorage.setItem(key, "1"); } catch (e) { first = true; }
  if (rm || !first || !("IntersectionObserver" in window)) return;

  var els = [].slice.call(D.querySelectorAll("main .page-head, main .sec, main .cards > *, main > .panel, main .empty, main > p"));
  if (!els.length) return;
  H.classList.add("fx");
  els.forEach(function (el) { el.classList.add("fx-in"); });
  [].slice.call(D.querySelectorAll("main .cards")).forEach(function (row) {
    [].slice.call(row.children).forEach(function (c, i) { c.style.setProperty("--d", Math.min(i, 10) * 0.06 + "s"); });
  });

  function count(root) {
    var list = [].slice.call(root.querySelectorAll(".s-val"));
    list.forEach(function (el) {
      if (el.children.length) return;                       // only plain "$1,234.56" / "12" / "+0.73%" values
      var m = el.textContent.match(/^([^0-9]*)([0-9][0-9,]*\.?[0-9]*)(.*)$/);
      if (!m) return;
      var pre = m[1], raw = m[2], suf = m[3], dec = (raw.split(".")[1] || "").length;
      var to = parseFloat(raw.replace(/,/g, ""));
      if (!isFinite(to)) return;
      var t0 = performance.now(), dur = 1400;
      (function step(now) {
        var k = Math.min(1, (now - t0) / dur), e = k === 1 ? 1 : 1 - Math.pow(2, -10 * k);
        el.textContent = pre + (to * e).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) + suf;
        if (k < 1) requestAnimationFrame(step);
      })(t0);
    });
  }

  var io = new IntersectionObserver(function (es) {
    es.forEach(function (e) {
      if (!e.isIntersecting) return;
      e.target.classList.add("in"); io.unobserve(e.target); count(e.target);
    });
  }, { threshold: 0 });            // any pixel on screen: tall tables must never wait
  els.forEach(function (el) { io.observe(el); });
  // failsafe: nothing stays hidden, whatever happens
  setTimeout(function () { els.forEach(function (el) { el.classList.add("in"); }); }, 1500);
})();
