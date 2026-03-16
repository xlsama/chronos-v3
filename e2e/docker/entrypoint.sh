#!/bin/bash
set -e

# Simulate disk alert: create a 200MB debug log file
dd if=/dev/zero of=/var/log/app-debug.log bs=1M count=200 2>/dev/null

# Simulate error logs
cat > /var/log/app-error.log <<'LOG'
[2026-03-16 08:01:12] ERROR  Failed to connect to database: connection refused
[2026-03-16 08:01:13] ERROR  Retry 1/3 failed for db connection
[2026-03-16 08:01:14] ERROR  Retry 2/3 failed for db connection
[2026-03-16 08:05:30] WARN   Disk usage exceeded 80% on /var/log
[2026-03-16 08:10:00] ERROR  Application health check failed
LOG

# nginx is installed but NOT started (simulates a stopped service)

# Start SSH daemon in foreground
exec /usr/sbin/sshd -D
