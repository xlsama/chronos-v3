-- 源数据库：原始交易订单数据
-- 200 条订单，其中 20 条 cancelled，180 条 completed
-- 5 个产品，4 个区域，60 天日期范围

CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(50) NOT NULL,
    price DECIMAL(10,2) NOT NULL
);

INSERT INTO products (id, name, category, price) VALUES
(1, 'Widget A', 'electronics', 29.99),
(2, 'Widget B', 'electronics', 49.99),
(3, 'Gadget X', 'accessories', 19.99),
(4, 'Gadget Y', 'accessories', 39.99),
(5, 'Tool Z', 'tools', 59.99);

CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_no VARCHAR(32) NOT NULL,
    customer_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    total_amount DECIMAL(10,2) NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    region VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 生成 200 条订单数据
DELIMITER //
CREATE PROCEDURE generate_orders()
BEGIN
    DECLARE i INT DEFAULT 1;
    DECLARE v_product_id INT;
    DECLARE v_unit_price DECIMAL(10,2);
    DECLARE v_quantity INT;
    DECLARE v_status VARCHAR(20);
    DECLARE v_region VARCHAR(20);

    WHILE i <= 200 DO
        SET v_product_id = (i MOD 5) + 1;
        SET v_quantity = (i MOD 3) + 1;
        SET v_status = CASE WHEN i MOD 10 = 0 THEN 'cancelled' ELSE 'completed' END;
        SET v_region = CASE (i MOD 4)
            WHEN 0 THEN 'north'
            WHEN 1 THEN 'south'
            WHEN 2 THEN 'east'
            ELSE 'west'
        END;
        SET v_unit_price = CASE v_product_id
            WHEN 1 THEN 29.99
            WHEN 2 THEN 49.99
            WHEN 3 THEN 19.99
            WHEN 4 THEN 39.99
            ELSE 59.99
        END;

        INSERT INTO orders (order_no, customer_id, product_id, quantity, unit_price, total_amount, order_date, status, region)
        VALUES (
            CONCAT('ORD-', LPAD(i, 6, '0')),
            (i MOD 50) + 1,
            v_product_id,
            v_quantity,
            v_unit_price,
            v_quantity * v_unit_price,
            DATE_ADD('2026-01-01', INTERVAL (i MOD 60) DAY),
            v_status,
            v_region
        );
        SET i = i + 1;
    END WHILE;
END //
DELIMITER ;

CALL generate_orders();
DROP PROCEDURE generate_orders;
