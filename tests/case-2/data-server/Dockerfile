FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    postgresql \
    postgresql-client \
    python3 \
    python3-venv \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# SSH setup
RUN mkdir -p /run/sshd && \
    echo 'root:testpassword' | chpasswd && \
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config

# Python venv + dependencies
RUN python3 -m venv /opt/inventory-api/venv
COPY requirements.txt /opt/inventory-api/requirements.txt
RUN /opt/inventory-api/venv/bin/pip install --no-cache-dir -r /opt/inventory-api/requirements.txt

# App files
COPY app.py /opt/inventory-api/app.py
COPY init.sql /opt/inventory-api/init.sql

# Log directory
RUN mkdir -p /var/log/inventory-api

# Entry script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 22 5432 8080

CMD ["/start.sh"]
