-- 清洗数据库：存储经过 ETL 清洗转换后的订单数据
-- 表初始为空，由 ETL 脚本填充

CREATE TABLE IF NOT EXISTS clean_orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    source_order_id INT NOT NULL,
    order_no VARCHAR(32) NOT NULL,
    customer_id INT NOT NULL,
    product_id INT NOT NULL,
    product_name VARCHAR(100),
    category VARCHAR(50),
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    order_date DATE NOT NULL,
    region VARCHAR(20) NOT NULL,
    etl_loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
