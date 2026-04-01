-- 目标数据库：聚合后的分析报表数据
-- 表初始为空，由 ETL 脚本填充

CREATE TABLE IF NOT EXISTS daily_sales_summary (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_date DATE NOT NULL,
    region VARCHAR(20) NOT NULL,
    category VARCHAR(50) NOT NULL,
    order_count INT NOT NULL,
    total_quantity INT NOT NULL,
    total_revenue DECIMAL(12,2) NOT NULL,
    etl_loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_date_region_cat (order_date, region, category)
);
