#!/bin/bash
# Start / stop / check the robot's background schedule.
#
#   ./service.sh start          turn the schedule ON (robot every 30 min, AI 2x/weekday)
#   ./service.sh stop           turn it OFF
#   ./service.sh status         is it running? when did it last run? is lid-closed mode on?
#   ./service.sh logs           watch the robot's log live (Ctrl+C to stop watching)
#   ./service.sh ai-logs        watch the AI advisor's log live
#   ./service.sh lid-closed-on  keep running with the lid CLOSED (asks for your Mac password)
#   ./service.sh lid-closed-off go back to normal (sleeps when you close the lid)

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
        echo "== lid-closed mode =="
        if pmset -g | grep -q "SleepDisabled.*1"; then
            echo "  ON  - the Mac stays awake with the lid closed. Keep it plugged in!"
        else
            echo "  OFF - closing the lid puts it to sleep and the robot pauses."
        fi
        echo
        echo "== last robot run =="
        tail -n 20 "$HOME/trading-robot/logs/robot.log" 2>/dev/null || echo "  (no log yet)"
        ;;
    logs)    tail -f "$HOME/trading-robot/logs/robot.log" ;;
    ai-logs) tail -f "$HOME/trading-robot/logs/ai.log" ;;
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
        echo "usage: ./service.sh {start|stop|status|logs|ai-logs|lid-closed-on|lid-closed-off}"
        ;;
esac
