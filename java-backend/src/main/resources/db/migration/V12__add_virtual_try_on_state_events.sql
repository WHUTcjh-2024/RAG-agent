ALTER TABLE virtual_try_on_jobs
    DROP CONSTRAINT chk_virtual_try_on_jobs_status;

ALTER TABLE virtual_try_on_jobs
    ADD CONSTRAINT chk_virtual_try_on_jobs_status
    CHECK (status IN ('QUEUED', 'PROCESSING', 'SUCCEEDED', 'FAILED', 'EXPIRED'));

CREATE TABLE virtual_try_on_job_events (
    id UUID PRIMARY KEY,
    job_id UUID NOT NULL,
    from_status VARCHAR(16),
    to_status VARCHAR(16) NOT NULL,
    reason VARCHAR(64) NOT NULL,
    attempt_count INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_virtual_try_on_job_events_job
        FOREIGN KEY (job_id) REFERENCES virtual_try_on_jobs(id) ON DELETE CASCADE
);

CREATE INDEX idx_virtual_try_on_job_events_job_created
    ON virtual_try_on_job_events(job_id, created_at);
