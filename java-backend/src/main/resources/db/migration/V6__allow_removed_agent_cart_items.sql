ALTER TABLE agent_cart_action_commits
    DROP CONSTRAINT fk_agent_cart_action_item;

ALTER TABLE agent_cart_action_commits
    ALTER COLUMN cart_item_id DROP NOT NULL;

ALTER TABLE agent_cart_action_commits
    ADD CONSTRAINT fk_agent_cart_action_item
        FOREIGN KEY (cart_item_id) REFERENCES cart_items(id) ON DELETE SET NULL;
