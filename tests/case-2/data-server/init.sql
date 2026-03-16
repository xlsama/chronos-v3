CREATE DATABASE inventory;

\c inventory;

CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    price DECIMAL(10, 2) NOT NULL
);

CREATE TABLE stock (
    product_id INTEGER PRIMARY KEY REFERENCES products(id),
    quantity INTEGER NOT NULL DEFAULT 0
);

INSERT INTO products (name, price) VALUES
    ('无线蓝牙耳机', 299.00),
    ('机械键盘', 599.00),
    ('USB-C 扩展坞', 199.00);

INSERT INTO stock (product_id, quantity) VALUES
    (1, 150),
    (2, 80),
    (3, 200);
