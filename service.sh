#!/bin/bash
# Start / stop / check the whole trading robot — BOTH accounts + BOTH websites.
#
#   ./service.sh start          turn EVERYTHING on
#   ./service.sh stop           turn EVERYTHING off
#   ./service.sh restart        stop everything, then start it again
#   ./service.sh status         what's running? last run? lid-closed mode?
#   ./service.sh logs           watch the main ($100k) robot log live
#   ./service.sh sprint-logs    watch the $500 sprint robot log live
#   ./service.sh ai-logs        watch the AI advisor log live
#   ./service.sh web-logs       watch the websites' log live
#   ./service.sh research-now   run today's daily review right now (costs ~$0.09)
#   ./service.sh research-logs  watch the daily-review log live
#   ./service.sh news-now      run the pre-market news scan right now
#   ./service.sh news-logs     watch the news-scan log live
#   ./service.sh publish-now   push a fresh public snapshot to GitHub Pages right now
#   ./service.sh web            (re)start ONLY the websites
#   ./service.sh web-stop       stop ONLY the websites
#   ./service.sh lid-closed-on  keep running with the lid CLOSED (asks for your Mac password)
#   ./service.sh lid-closed-off go back to normal
#
# Two accounts:
#   main       ~$100k  · stocks + options + crypto + AI  · dashboard :8777
#   sprint500  ~$500   · stocks + crypto only            · dashboard :8778

# where this script lives — works no matter where the project folder is moved
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
UID_NUM=$(id -u)
LA="$HOME/Library/LaunchAgents"
ROBOT="$LA/com.trading-robot.robot.plist"
AI="$LA/com.trading-robot.ai.plist"
SPRINT="$LA/com.trading-robot.sprint500.plist"
RESEARCH="$LA/com.trading-robot.research.plist"
NEWS="$LA/com.trading-robot.news.plist"
ML="$LA/com.trading-robot.ml.plist"
PY="$HERE/venv/bin/python"
WEB_LOG="$HERE/logs/dashboard.log"

load()   { launchctl bootstrap "gui/$UID_NUM" "$1" 2>/dev/null || launchctl load -w "$1"; }
unload() { launchctl bootout   "gui/$UID_NUM" "$1" 2>/dev/null || launchctl unload   "$1"; }

WEB_MATCH="[d]ashboard\.py"

web_start() {
    mkdir -p "$HERE/logs"
    pkill -f "dashboard.py" 2>/dev/null
    sleep 1
    cd "$HERE"
    # main account dashboard on :8777
    nohup "$PY" dashboard.py </dev/null >"$WEB_LOG" 2>&1 &
    disown 2>/dev/null || true
    # $500 sprint dashboard on :8778
    ROBOT_PROFILE=sprint500 nohup "$PY" dashboard.py </dev/null >>"$WEB_LOG" 2>&1 &
    disown 2>/dev/null || true
    cd - >/dev/null
    sleep 2
    ok8777=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8777/" 2>/dev/null)
    ok8778=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8778/" 2>/dev/null)
    printf '  main   (100k account):  http://localhost:8777   [%s]\n' "$ok8777"
    printf '  sprint (500 account):   http://localhost:8778   [%s]\n' "$ok8778"
}
web_stop() {
    pkill -f "dashboard.py" 2>/dev/null && echo "Websites OFF." || echo "Websites were not running."
}

case "$1" in
    start)
        mkdir -p "$HERE/logs"
        load "$ROBOT"; load "$AI"; load "$SPRINT"; load "$RESEARCH"; load "$NEWS"; load "$ML"
        echo "Schedules ON:"
        echo "  main     — every 30 min (stocks+crypto), AI 2x/weekday"
        echo "  sprint   — every 15 min (stocks+crypto, \$500 account)"
        echo "  news     — once a day at 08:45, reads overnight news -> news/YYYY-MM-DD.json"
        echo "  research — once a day at 17:20, writes research/YYYY-MM-DD.md"
        web_start
        echo "Your Mac must be awake for the schedules to run. Check: ./service.sh status"
        ;;
    stop)
        unload "$ROBOT"; unload "$AI"; unload "$SPRINT"; unload "$RESEARCH"; unload "$NEWS"; unload "$ML"
        echo "Schedules OFF. Nothing runs until ./service.sh start"
        web_stop
        ;;
    research-now)
        echo "Running the daily review now (costs a few cents)..."
        cd "$HERE" && "$PY" daily_review.py
        ;;
    research-logs)
        tail -f "$HERE/logs/research.log"
        ;;
    news-now)
        echo "Running the pre-market news scan now (--force, costs a few cents)..."
        cd "$HERE" && "$PY" news_scan.py --force
        ;;
    reconcile)
        cd "$HERE" && "$PY" reconcile.py "${@:2}" && "$PY" reconcile.py --profile sprint500 "${@:2}"
        ;;
    publish-now)
        echo "Publishing a fresh snapshot to https://mrrishit909.github.io/trading-bot-live/ ..."
        cd "$HERE" && "$PY" publish_dashboard.py
        ;;
    restart)
        "$0" stop; echo; sleep 1; "$0" start
        ;;
    web|web-start|web-restart)
        web_start
        ;;
    web-stop)
        web_stop
        ;;
    status)
        echo "== scheduled jobs =="
        launchctl list | grep trading-robot || echo "  (none loaded — run ./service.sh start)"
        echo
        echo "== websites =="
        if pgrep -f "$WEB_MATCH" >/dev/null; then
            echo "  running (pids $(pgrep -f "$WEB_MATCH" | tr '\n' ' '))"
            echo "  main:   http://localhost:8777  [$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8777/ 2>/dev/null)]"
            echo "  sprint: http://localhost:8778  [$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8778/ 2>/dev/null)]"
        else
            echo "  OFF - run ./service.sh web"
        fi
        echo
        echo "== lid-closed mode =="
        if pmset -g | grep -q "SleepDisabled.*1"; then
            echo "  ON  - the Mac stays awake with the lid closed. Keep it plugged in!"
        else
            echo "  OFF - closing the lid puts it to sleep and the robot pauses."
        fi
        echo
        echo "== last main run =="
        tail -n 12 "$HERE/logs/robot.log" 2>/dev/null || echo "  (no log yet)"
        echo
        echo "== last sprint run =="
        tail -n 12 "$HERE/logs/sprint500.log" 2>/dev/null || echo "  (no log yet)"
        echo
        echo "== latest pre-market news read =="
        ls -t "$HERE/news"/20*.json 2>/dev/null | head -1 | xargs -I{} "$PY" -c "import json,sys; d=json.load(open(sys.argv[1])); print(f\"  {d['date']}: market {d['market']['read']} - {d['market']['reason'][:80]}\")" || echo "  (none yet)"
        echo
        echo "== latest daily review =="
        ls -t "$HERE/research"/20*.md 2>/dev/null | head -1 | xargs -I{} basename {} || echo "  (none yet)"
        echo
        echo "== public snapshot =="
        echo "  https://mrrishit909.github.io/trading-bot-live/  [$(curl -s -o /dev/null -w '%{http_code}' https://mrrishit909.github.io/trading-bot-live/ 2>/dev/null)]"
        ;;
    logs)          tail -f "$HERE/logs/robot.log" ;;
    sprint-logs)   tail -f "$HERE/logs/sprint500.log" ;;
    ai-logs)       tail -f "$HERE/logs/ai.log" ;;
    news-logs)     tail -f "$HERE/logs/news.log" ;;
    web-logs)      tail -f "$WEB_LOG" ;;
    lid-closed-on)
        echo "This keeps your Mac awake even with the lid closed."
        echo "IMPORTANT: keep the laptop PLUGGED IN and somewhere with airflow"
        echo "(not zipped in a bag) so it doesn't overheat or drain."
        echo
        sudo pmset -a disablesleep 1 && echo "Done. Lid-closed mode is ON. Undo with: ./service.sh lid-closed-off"
        ;;
    lid-closed-off)
        sudo pmset -a disablesleep 0 && echo "Back to normal - the Mac will sleep when you close the lid."
        ;;
    *)
        echo "usage: ./service.sh {start|stop|restart|status|web|web-stop|research-now|research-logs|news-now|news-logs|publish-now|reconcile|logs|sprint-logs|ai-logs|web-logs|lid-closed-on|lid-closed-off}"
        ;;
esac
