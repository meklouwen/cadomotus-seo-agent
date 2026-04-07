#!/bin/bash

echo "=== Cadomotus SEO Agent ==="
echo "Mode: ${MODE:-watch}"
echo "Token path: ${GOOGLE_TOKEN_PATH:-/data/token.json}"

# Zorg dat /data directory bestaat
mkdir -p /data

# Start health check server (Easypanel vereist een open poort)
python healthcheck.py &
HEALTH_PID=$!

case "${MODE}" in
    report)
        echo "Eenmalig rapport genereren..."
        python agent.py --weekly-report
        ;;
    auth)
        echo "Google OAuth2 authenticatie..."
        python agent.py --auth
        # Blijf draaien na auth zodat container niet stopt
        echo "Auth voltooid. Container blijft draaien voor health check."
        wait $HEALTH_PID
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

        # Wacht op alle processen
        trap "kill $WATCHER_PID $CRON_PID $HEALTH_PID 2>/dev/null" EXIT TERM INT
        wait $WATCHER_PID $CRON_PID
        ;;
    *)
        echo "Onbekende mode: ${MODE}. Standaard: watch mode."
        python agent.py --watch-replies &
        wait $!
        ;;
esac
