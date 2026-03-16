FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-server \
    nginx \
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
RUN python3 -m venv /opt/order-api/venv
COPY requirements.txt /opt/order-api/requirements.txt
RUN /opt/order-api/venv/bin/pip install --no-cache-dir -r /opt/order-api/requirements.txt

# App files
COPY app.py /opt/order-api/app.py
COPY nginx.conf /etc/nginx/sites-available/default

# Log and data directories
RUN mkdir -p /var/log/order-api /var/lib/order-api

# Entry script
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 22 80 5000

CMD ["/start.sh"]
