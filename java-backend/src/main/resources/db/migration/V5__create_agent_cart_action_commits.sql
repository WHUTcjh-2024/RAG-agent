CREATE TABLE agent_cart_action_commits (
    action_id VARCHAR(64) PRIMARY KEY,
    user_id UUID NOT NULL,
    product_id VARCHAR(128) NOT NULL,
    cart_item_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_agent_cart_action_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_agent_cart_action_item FOREIGN KEY (cart_item_id) REFERENCES cart_items(id) ON DELETE RESTRICT
);

CREATE INDEX idx_agent_cart_action_user_created
    ON agent_cart_action_commits(user_id, created_at);
