"""
Publishes a static snapshot of the dashboard (main account) to GitHub Pages,
so other people can see it without any Alpaca/Anthropic key ever leaving
this machine -- the public site is plain files, no backend, nothing to hack.

Run by hand:
    ./venv/bin/python publish_dashboard.py
Scheduled: wired into the robot's own LaunchAgent cadence (every ~30 min),
so the public site is never more stale than the live one normally is.
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser("~/trading-bot-live-site")
BASE = "/trading-bot-live"
REPO = "trading-bot-live"
PUBLISH_SH = os.path.expanduser("~/projects-site/publish.sh")

sys.path.insert(0, HERE)
import dashboard  # noqa: E402  (connects to Alpaca with the real keys -- server-side, local only)

# only one profile in the map kills the "switch account" localhost link --
# meaningless (and broken) on a public site
dashboard.profiles.PROFILES = {dashboard.PROFILE_NAME: dashboard.PROFILE}

ROUTE_NAMES = [r.lstrip("/") for r, _ in dashboard.NAV]
STATIC_NAMES = ["static/intro.js", "static/fx.js"]
_LINK_RE = re.compile(
    r'(href|src)="/(' + "|".join(re.escape(n) for n in sorted(ROUTE_NAMES + STATIC_NAMES, key=len, reverse=True)) + r')(["?])'
)


def _rewrite_link(m):
    attr, name, tail = m.group(1), m.group(2), m.group(3)
    if name in STATIC_NAMES:
        return f'{attr}="{BASE}/{name}{tail}'
    return f'{attr}="{BASE}/{name}/' + ("?" if tail == "?" else '"')


def rewrite(text):
    text = _LINK_RE.sub(_rewrite_link, text)
    text = text.replace('href="/"', f'href="{BASE}/"')
    text = text.replace("auto-refreshes every 60s", "snapshot, republished every ~30 min")
    return text


def write(rel_path, content, mode="w"):
    full = os.path.join(OUT, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, mode, encoding=None if "b" in mode else "utf-8") as fh:
        fh.write(content)


def main():
    if os.path.isdir(OUT):
        for name in os.listdir(OUT):
            if name == ".git":
                continue
            p = os.path.join(OUT, name)
            shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    else:
        os.makedirs(OUT)

    write("index.html", rewrite(dashboard.page_intro()))

    for route, fn in dashboard.ROUTES.items():
        body = fn({})
        page = dashboard.shell(route, dashboard.TITLES[route], body)
        write(route.lstrip("/") + "/index.html", rewrite(page))

    intro_js = open(os.path.join(HERE, "web", "intro.js")).read()
    for ep in dashboard.API:
        intro_js = intro_js.replace(f'"{ep}"', f'"{BASE}{ep}"')
    write("static/intro.js", intro_js)
    shutil.copy(os.path.join(HERE, "web", "fx.js"), os.path.join(OUT, "static", "fx.js"))

    for ep, fn in dashboard.API.items():
        try:
            payload = fn()
        except Exception as e:
            payload = {"error": str(e)}
        write(ep.lstrip("/"), json.dumps(payload))

    write(".nojekyll", "")

    subprocess.run(["git", "init", "-q"], cwd=OUT, check=True)
    subprocess.run(["git", "add", "-A"], cwd=OUT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=OUT).returncode == 0:
        print("No changes since last publish.")
        return
    subprocess.run(["git", "commit", "-q", "-m", "Snapshot update"], cwd=OUT, check=True)
    subprocess.run(
        [PUBLISH_SH, OUT, REPO, "Live read-only snapshot of the trading bot dashboard (auto-updated)", "pages"],
        check=True,
    )
    print(f"Published: https://mrrishit909.github.io/{REPO}/")


if __name__ == "__main__":
    main()
