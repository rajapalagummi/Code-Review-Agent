-- sample_buggy.sql
-- Intentionally problematic SQL for demo purposes

-- Query 1: Missing WHERE on UPDATE
UPDATE users
SET status = 'inactive';

-- Query 2: SELECT * with no filtering
SELECT * FROM orders
JOIN customers ON orders.customer_id = customers.id
JOIN products ON orders.product_id = products.id;

-- Query 3: Non-SARGable WHERE clause
SELECT * FROM transactions
WHERE YEAR(created_at) = 2024
AND MONTH(created_at) = 6;

-- Query 4: Deeply nested subqueries
SELECT *
FROM users
WHERE id IN (
    SELECT user_id FROM orders
    WHERE product_id IN (
        SELECT id FROM products
        WHERE category_id IN (
            SELECT id FROM categories
            WHERE name = 'Electronics'
        )
    )
);

-- Query 5: CROSS JOIN
SELECT *
FROM products
CROSS JOIN warehouses;

-- Query 6: DELETE without WHERE
DELETE FROM audit_logs;

-- Query 7: String comparison on numeric column
SELECT * FROM accounts
WHERE account_id = '12345';
