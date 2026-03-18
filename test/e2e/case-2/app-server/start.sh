#!/bin/bash
set -e

echo "[start] Starting SSH daemon..."
/usr/sbin/sshd

echo "[start] Starting Flask order-api..."
/opt/order-api/venv/bin/python /opt/order-api/app.py &

echo "[start] Waiting for order-api to be ready..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:5000/api/health > /dev/null 2>&1; then
        echo "[start] order-api is ready"
        break
    fi
    sleep 1
done

echo "[start] Starting Nginx..."
exec nginx -g "daemon off;"
