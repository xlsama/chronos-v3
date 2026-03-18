#!/bin/bash
set -e

echo "[start] Starting SSH daemon..."
/usr/sbin/sshd

# Configure PostgreSQL for trust auth on local connections
PG_HBA=$(find /etc/postgresql -name pg_hba.conf | head -1)
if [ -n "$PG_HBA" ]; then
    sed -i 's/peer$/trust/' "$PG_HBA"
    sed -i 's/scram-sha-256$/trust/' "$PG_HBA"
    sed -i 's/md5$/trust/' "$PG_HBA"
fi

echo "[start] Starting PostgreSQL..."
pg_ctlcluster 15 main start

echo "[start] Waiting for PostgreSQL to be ready..."
for i in $(seq 1 30); do
    if su - postgres -c "pg_isready" > /dev/null 2>&1; then
        echo "[start] PostgreSQL is ready"
        break
    fi
    sleep 1
done

# Initialize database if not exists
echo "[start] Initializing inventory database..."
if ! su - postgres -c "psql -lqt" | grep -q inventory; then
    su - postgres -c "psql -f /opt/inventory-api/init.sql"
    echo "[start] Database initialized"
else
    echo "[start] Database already exists"
fi

echo "[start] Starting Flask inventory-api..."
/opt/inventory-api/venv/bin/python /opt/inventory-api/app.py &

# Keep container alive even if Flask is killed
tail -f /dev/null
