FROM python:3.12-slim

WORKDIR /app

# Dependencies installeren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code kopiëren
COPY . .

# Data volume voor Google token persistence
VOLUME /data

# Health check poort voor Easypanel
EXPOSE 8080

# Entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
