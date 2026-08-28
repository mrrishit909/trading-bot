#!/bin/bash
# Start / stop / check the robot's background schedule.
#
#   ./service.sh start     turn the schedule ON (robot every 30 min, AI 2x/weekday)
#   ./service.sh stop      turn it OFF
#   ./service.sh status    is it running? when did it last run?
#   ./service.sh logs      watch the robot's log live (Ctrl+C to stop watching)
#   ./service.sh ai-logs   watch the AI advisor's log live

UID_NUM=$(id -u)
LA="$HOME/Library/LaunchAgents"
ROBOT="$LA/com.trading-robot.robot.plist"
AI="$LA/com.trading-robot.ai.plist"

load() {
    launchctl bootstrap "gui/$UID_NUM" "$1" 2>/dev/null || launchctl load -w "$1"
}
unload() {
    launchctl bootout "gui/$UID_NUM" "$1" 2>/dev/null || launchctl unload "$1"
}

case "$1" in
    start)
        mkdir -p "$HOME/trading-robot/logs"
        load "$ROBOT"; load "$AI"
        echo "Schedule ON. Robot runs every 30 min; AI advisor 2x on weekdays."
        echo "Your Mac must be awake for it to run. Check with: ./service.sh status"
        ;;
    stop)
        unload "$ROBOT"; unload "$AI"
        echo "Schedule OFF. The robot will not run again until you ./service.sh start"
        ;;
    status)
        echo "== scheduled jobs =="
        launchctl list | grep trading-robot || echo "  (none loaded — run ./service.sh start)"
        echo
        echo "== last robot run =="
        tail -n 20 "$HOME/trading-robot/logs/robot.log" 2>/dev/null || echo "  (no log yet)"
        ;;
    logs)    tail -f "$HOME/trading-robot/logs/robot.log" ;;
    ai-logs) tail -f "$HOME/trading-robot/logs/ai.log" ;;
    *)
        echo "usage: ./service.sh {start|stop|status|logs|ai-logs}"
        ;;
esac
