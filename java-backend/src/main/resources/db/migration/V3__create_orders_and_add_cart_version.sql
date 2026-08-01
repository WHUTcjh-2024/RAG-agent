ALTER TABLE cart_items ADD COLUMN version BIGINT NOT NULL DEFAULT 0;

CREATE TABLE orders (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount DECIMAL(19, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_orders_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uk_orders_user_idempotency UNIQUE (user_id, idempotency_key),
    CONSTRAINT ck_orders_total_non_negative CHECK (total_amount >= 0)
);

CREATE TABLE order_items (
    id UUID PRIMARY KEY,
    order_id UUID NOT NULL,
    product_id VARCHAR(128) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    product_image_url VARCHAR(1024),
    unit_price DECIMAL(19, 2) NOT NULL,
    quantity INTEGER NOT NULL,
    subtotal DECIMAL(19, 2) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_order_items_order FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    CONSTRAINT ck_order_items_quantity_positive CHECK (quantity >= 1),
    CONSTRAINT ck_order_items_price_non_negative CHECK (unit_price >= 0),
    CONSTRAINT ck_order_items_subtotal_non_negative CHECK (subtotal >= 0)
);

CREATE INDEX idx_orders_user_created_at ON orders(user_id, created_at);
CREATE INDEX idx_order_items_order_created_at ON order_items(order_id, created_at);
