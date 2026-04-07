#!/bin/bash
set -e

echo "=== Cadomotus SEO Agent ==="
echo "Mode: ${MODE:-watch}"

# Check of Google token bestaat
if [ ! -f /data/token.json ]; then
    echo "WAARSCHUWING: Geen Google token gevonden op /data/token.json"
    echo "Voer eerst de auth flow uit: docker exec <container> python agent.py --auth"
fi

case "${MODE}" in
    report)
        echo "Eenmalig rapport genereren..."
        python agent.py --weekly-report
        ;;
    auth)
        echo "Google OAuth2 authenticatie..."
        python agent.py --auth
        ;;
    watch)
        echo "Reply watcher starten..."
        python agent.py --watch-replies
        ;;
    full)
        echo "Reply watcher + cron starten..."
        # Start de reply watcher op de achtergrond
        python agent.py --watch-replies &
        WATCHER_PID=$!

        # Start een simpele cron loop voor het wekelijkse rapport
        python -c "
import schedule, time, subprocess, os

def run_report():
    print('=== Cron: wekelijks rapport starten ===')
    subprocess.run(['python', 'agent.py', '--weekly-report'])

# Parse REPORT_CRON env var (standaard: vrijdag 07:00)
# Simpele implementatie: elke vrijdag om 07:00
schedule.every().friday.at('07:00').do(run_report)

print(f'Cron gestart: wekelijks rapport elke vrijdag 07:00')
while True:
    schedule.run_pending()
    time.sleep(60)
" &
        CRON_PID=$!

        # Wacht op beide processen
        trap "kill $WATCHER_PID $CRON_PID 2>/dev/null" EXIT
        wait -n $WATCHER_PID $CRON_PID
        ;;
    *)
        echo "Onbekende mode: ${MODE}"
        echo "Gebruik: MODE=watch|report|auth|full"
        exit 1
        ;;
esac
