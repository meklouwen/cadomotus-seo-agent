FROM python:3.12-slim

# Nederlandse tijdzone zodat `schedule.every().friday.at("07:00")` en datetime.now()
# uitkomen op CET/CEST — anders draait het rapport op UTC (07:00 UTC = 09:00 NL in zomer).
ENV TZ=Europe/Amsterdam \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Deps eerst voor build-cache hit.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Non-root user voor defence-in-depth. /data moet schrijfbaar zijn voor token-refresh
# en report-archief, dus we chownen het naar deze user.
RUN useradd --create-home --shell /bin/bash app \
    && mkdir -p /data /app/logs \
    && chown -R app:app /data /app

COPY --chown=app:app . .

USER app

VOLUME /data
EXPOSE 8080

# Easypanel/Docker kan zelf restart-policy regelen; de healthcheck geeft de container
# orchestrator een betrouwbaar signaal dat de health-HTTP nog antwoordt.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8080/ || exit 1

CMD ["python", "-u", "main.py"]
