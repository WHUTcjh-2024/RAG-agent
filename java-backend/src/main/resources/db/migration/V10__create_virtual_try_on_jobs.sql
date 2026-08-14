CREATE TABLE virtual_try_on_jobs (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    product_id VARCHAR(100) NOT NULL,
    category VARCHAR(64) NOT NULL,
    body_profile_json TEXT NOT NULL,
    status VARCHAR(16) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    attempt_count INTEGER NOT NULL,
    output_key VARCHAR(255),
    failure_code VARCHAR(64),
    saved BOOLEAN NOT NULL DEFAULT FALSE,
    feedback_json TEXT,
    available_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_virtual_try_on_jobs_user
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT uq_virtual_try_on_jobs_user_idempotency
        UNIQUE (user_id, idempotency_key),
    CONSTRAINT chk_virtual_try_on_jobs_status
        CHECK (status IN ('QUEUED', 'PROCESSING', 'SUCCEEDED', 'FAILED'))
);

CREATE INDEX idx_virtual_try_on_jobs_queue
    ON virtual_try_on_jobs(status, available_at, created_at);

CREATE INDEX idx_virtual_try_on_jobs_user_created
    ON virtual_try_on_jobs(user_id, created_at DESC);
