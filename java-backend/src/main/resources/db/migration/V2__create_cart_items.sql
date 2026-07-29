CREATE TABLE cart_items (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    product_id VARCHAR(128) NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    product_image_url VARCHAR(1024),
    unit_price DECIMAL(19, 2) NOT NULL,
    quantity INTEGER NOT NULL,
    selected BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_cart_items_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uk_cart_items_user_product UNIQUE (user_id, product_id),
    CONSTRAINT ck_cart_items_quantity_positive CHECK (quantity >= 1),
    CONSTRAINT ck_cart_items_unit_price_non_negative CHECK (unit_price >= 0)
);

CREATE INDEX idx_cart_items_user_created_at
    ON cart_items(user_id, created_at);
