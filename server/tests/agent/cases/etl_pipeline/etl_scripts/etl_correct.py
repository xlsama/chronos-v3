"""正确的 ETL 管道：source -> staging -> target。

Step 1: 从 source 提取 completed 订单，JOIN products，写入 staging
Step 2: 从 staging 按 (order_date, region, category) 聚合，写入 target
"""

import logging

import aiomysql

log = logging.getLogger(__name__)


async def run_correct_etl(
    source_config: dict,
    staging_config: dict,
    target_config: dict,
) -> dict:
    """运行正确的 ETL 流程，返回统计信息。"""
    stats = {}

    source_pool = await aiomysql.create_pool(**source_config, minsize=1, maxsize=2, autocommit=True)
    staging_pool = await aiomysql.create_pool(
        **staging_config, minsize=1, maxsize=2, autocommit=False
    )
    target_pool = await aiomysql.create_pool(
        **target_config, minsize=1, maxsize=2, autocommit=False
    )

    try:
        # ── Step 1: source -> staging ──
        log.info("[ETL-correct] Step 1: Extracting completed orders from source...")

        async with source_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT o.id, o.order_no, o.customer_id, o.product_id,
                           p.name AS product_name, p.category,
                           o.quantity, o.unit_price, o.total_amount,
                           o.order_date, o.region
                    FROM orders o
                    JOIN products p ON o.product_id = p.id
                    WHERE o.status = 'completed'
                """)
                rows = await cur.fetchall()
                stats["source_completed"] = len(rows)
                log.info(f"[ETL-correct] Extracted {len(rows)} completed orders from source")

        async with staging_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("TRUNCATE TABLE clean_orders")
                for row in rows:
                    await cur.execute(
                        """
                        INSERT INTO clean_orders
                        (source_order_id, order_no, customer_id, product_id,
                         product_name, category, quantity, unit_price,
                         total_amount, order_date, region)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            row["id"],
                            row["order_no"],
                            row["customer_id"],
                            row["product_id"],
                            row["product_name"],
                            row["category"],
                            row["quantity"],
                            row["unit_price"],
                            row["total_amount"],
                            row["order_date"],
                            row["region"],
                        ),
                    )
                await conn.commit()
                stats["staging_loaded"] = len(rows)
                log.info(f"[ETL-correct] Loaded {len(rows)} rows to staging")

        # ── Step 2: staging -> target ──
        log.info("[ETL-correct] Step 2: Aggregating from staging to target...")

        async with staging_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("""
                    SELECT order_date, region, category,
                           COUNT(*) AS order_count,
                           SUM(quantity) AS total_quantity,
                           SUM(total_amount) AS total_revenue
                    FROM clean_orders
                    GROUP BY order_date, region, category
                """)
                agg_rows = await cur.fetchall()

        async with target_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("TRUNCATE TABLE daily_sales_summary")
                for row in agg_rows:
                    await cur.execute(
                        """
                        INSERT INTO daily_sales_summary
                        (order_date, region, category, order_count,
                         total_quantity, total_revenue)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            row["order_date"],
                            row["region"],
                            row["category"],
                            row["order_count"],
                            row["total_quantity"],
                            row["total_revenue"],
                        ),
                    )
                await conn.commit()
                stats["target_aggregated_rows"] = len(agg_rows)
                log.info(f"[ETL-correct] Loaded {len(agg_rows)} aggregated rows to target")

    finally:
        source_pool.close()
        await source_pool.wait_closed()
        staging_pool.close()
        await staging_pool.wait_closed()
        target_pool.close()
        await target_pool.wait_closed()

    log.info(f"[ETL-correct] Done. Stats: {stats}")
    return stats
