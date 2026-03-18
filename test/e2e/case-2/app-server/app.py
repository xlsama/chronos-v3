import logging
import sqlite3
import os
from flask import Flask, jsonify

import requests

app = Flask(__name__)

DB_PATH = "/var/lib/order-api/orders.db"
INVENTORY_API = os.environ.get("INVENTORY_API_URL", "http://data-server:8080")
LOG_FILE = "/var/log/order-api/app.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending'
        )
    """)
    # Seed some orders
    cursor = conn.execute("SELECT COUNT(*) FROM orders")
    if cursor.fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO orders (product_id, quantity, status) VALUES (?, ?, ?)",
            [
                (1, 2, "pending"),
                (2, 1, "confirmed"),
                (3, 5, "pending"),
            ],
        )
        conn.commit()
    conn.close()


init_db()


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "service": "order-api"})


@app.route("/api/orders")
def get_orders():
    logger.info("Fetching orders list")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    orders = conn.execute("SELECT * FROM orders").fetchall()
    conn.close()

    results = []
    for order in orders:
        order_dict = dict(order)
        # Call inventory API for each order's product
        try:
            resp = requests.get(
                f"{INVENTORY_API}/api/inventory/{order['product_id']}",
                timeout=5,
            )
            resp.raise_for_status()
            order_dict["inventory"] = resp.json()
            logger.info(
                f"Inventory check OK for product {order['product_id']}"
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"Failed to connect to inventory service for product "
                f"{order['product_id']}: {e}"
            )
            return jsonify({
                "error": "Inventory service unavailable",
                "detail": f"Cannot connect to {INVENTORY_API}",
            }), 500
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Inventory API error for product {order['product_id']}: {e}"
            )
            return jsonify({
                "error": "Inventory service error",
                "detail": str(e),
            }), 500

        results.append(order_dict)

    logger.info(f"Returning {len(results)} orders")
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
