CREATE TABLE wardrobe_versions (
    user_id UUID PRIMARY KEY,
    version BIGINT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_wardrobe_version_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE wardrobe_items (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    source_product_id VARCHAR(128),
    name VARCHAR(128) NOT NULL,
    category VARCHAR(64) NOT NULL,
    color VARCHAR(64),
    image_url VARCHAR(500),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_wardrobe_item_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_wardrobe_items_user ON wardrobe_items(user_id, category);

CREATE TABLE wardrobe_feedback_events (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    task_id VARCHAR(100),
    plan_ref VARCHAR(100),
    item_ref VARCHAR(128),
    outcome VARCHAR(32) NOT NULL,
    fit_feedback VARCHAR(32),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_wardrobe_feedback_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_wardrobe_feedback_user_created
    ON wardrobe_feedback_events(user_id, created_at);
