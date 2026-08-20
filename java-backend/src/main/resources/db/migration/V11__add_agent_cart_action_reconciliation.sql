ALTER TABLE agent_cart_action_commits
    ADD COLUMN task_id VARCHAR(100) NOT NULL DEFAULT 'legacy';

ALTER TABLE agent_cart_action_commits
    ADD COLUMN expected_unit_price DECIMAL(19, 2);

ALTER TABLE agent_cart_action_commits
    ADD COLUMN requested_quantity INTEGER NOT NULL DEFAULT 1;

ALTER TABLE agent_cart_action_commits
    ADD COLUMN rule_decision_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE agent_cart_action_commits
    ADD COLUMN reconciliation_status VARCHAR(32) NOT NULL DEFAULT 'PENDING';

ALTER TABLE agent_cart_action_commits
    ADD COLUMN reconciliation_message VARCHAR(500);

ALTER TABLE agent_cart_action_commits
    ADD COLUMN reconciled_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE agent_cart_action_commits
    ADD CONSTRAINT ck_agent_cart_action_requested_quantity
    CHECK (requested_quantity >= 1);

CREATE INDEX idx_agent_cart_action_reconciliation
    ON agent_cart_action_commits(reconciled_at, created_at);
