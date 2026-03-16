import logging
import psycopg2
from flask import Flask, jsonify

app = Flask(__name__)

DB_CONFIG = {
    "dbname": "inventory",
    "user": "postgres",
    "host": "localhost",
    "port": 5432,
}
LOG_FILE = "/var/log/inventory-api/app.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def get_db():
    return psycopg2.connect(**DB_CONFIG)


@app.route("/api/health")
def health():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        return jsonify({"status": "ok", "service": "inventory-api", "db": "connected"})
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "error", "service": "inventory-api", "db": str(e)}), 503


@app.route("/api/inventory/<int:product_id>")
def get_inventory(product_id):
    logger.info(f"Querying inventory for product {product_id}")
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT p.id, p.name, p.price, s.quantity
            FROM products p
            JOIN stock s ON s.product_id = p.id
            WHERE p.id = %s
        """, (product_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if row is None:
            logger.warning(f"Product {product_id} not found")
            return jsonify({"error": "Product not found"}), 404

        result = {
            "product_id": row[0],
            "name": row[1],
            "price": float(row[2]),
            "quantity": row[3],
        }
        logger.info(f"Returning inventory for product {product_id}: {result}")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Database error for product {product_id}: {e}")
        return jsonify({"error": "Database error", "detail": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
