"""错误的 ETL 管道：重跑 source -> staging 时不过滤 cancelled 订单，且不重跑聚合。

Bug 1: 从 source 提取时缺少 WHERE status='completed'，导致 staging 包含已取消订单
Bug 2: 不重跑 staging -> target 聚合，target 仍为旧数据

结果: staging(200) vs target.SUM(order_count)(180) 不一致
"""

import logging

import aiomysql

log = logging.getLogger(__name__)


async def run_buggy_etl(
    source_config: dict,
    staging_config: dict,
    target_config: dict,
) -> dict:
    """运行错误的 ETL 流程，制造数据不一致。"""
    stats = {}

    source_pool = await aiomysql.create_pool(**source_config, minsize=1, maxsize=2, autocommit=True)
    staging_pool = await aiomysql.create_pool(
        **staging_config, minsize=1, maxsize=2, autocommit=False
    )

    try:
        # ── BUG: 从 source 提取时不过滤 cancelled 订单 ──
        log.info("[ETL-buggy] Extracting ALL orders from source (BUG: no status filter)...")

        async with source_pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # BUG: 缺少 WHERE o.status = 'completed'
                await cur.execute("""
                    SELECT o.id, o.order_no, o.customer_id, o.product_id,
                           p.name AS product_name, p.category,
                           o.quantity, o.unit_price, o.total_amount,
                           o.order_date, o.region
                    FROM orders o
                    JOIN products p ON o.product_id = p.id
                """)
                rows = await cur.fetchall()
                stats["source_extracted"] = len(rows)
                log.info(f"[ETL-buggy] Extracted {len(rows)} orders (includes cancelled!)")

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
                log.info(f"[ETL-buggy] Loaded {len(rows)} rows to staging (should be 180, got 200)")

        # BUG: 不重跑 staging -> target 聚合
        # target.daily_sales_summary 仍然基于之前正确 ETL 的 180 条数据
        log.info("[ETL-buggy] SKIPPED target aggregation (BUG: stale target data)")
        stats["target_updated"] = False

    finally:
        source_pool.close()
        await source_pool.wait_closed()
        staging_pool.close()
        await staging_pool.wait_closed()

    log.info(f"[ETL-buggy] Done. Stats: {stats}")
    return stats
