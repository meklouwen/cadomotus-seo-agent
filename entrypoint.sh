#!/bin/bash

echo "=== Cadomotus SEO Agent ==="
echo "Mode: ${MODE:-watch}"
echo "Token path: ${GOOGLE_TOKEN_PATH:-/data/token.json}"

# Zorg dat /data directory bestaat
mkdir -p /data

case "${MODE}" in
    report)
        echo "Eenmalig rapport genereren..."
        exec python agent.py --weekly-report
        ;;
    auth)
        echo "Google OAuth2 authenticatie..."
        exec python agent.py --auth
        ;;
    watch)
        echo "Reply watcher starten..."
        exec python agent.py --watch-replies
        ;;
    full)
        echo "Reply watcher + cron starten..."

        # Start de reply watcher op de achtergrond
        python agent.py --watch-replies &
        WATCHER_PID=$!

        # Start de cron scheduler op de achtergrond
        python -c "
import schedule, time, subprocess

def run_report():
    print('=== Cron: wekelijks rapport starten ===', flush=True)
    subprocess.run(['python', 'agent.py', '--weekly-report'])

schedule.every().friday.at('07:00').do(run_report)
print('Cron gestart: wekelijks rapport elke vrijdag 07:00', flush=True)

while True:
    schedule.run_pending()
    time.sleep(60)
" &
        CRON_PID=$!

        # Wacht op beide processen — herstart niet bij crash
        trap "kill $WATCHER_PID $CRON_PID 2>/dev/null" EXIT TERM INT
        wait $WATCHER_PID $CRON_PID
        ;;
    *)
        echo "Onbekende mode: ${MODE}. Standaard: watch mode."
        exec python agent.py --watch-replies
        ;;
esac
