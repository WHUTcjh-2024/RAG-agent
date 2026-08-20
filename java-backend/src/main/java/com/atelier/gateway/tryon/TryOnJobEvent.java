package com.atelier.gateway.tryon;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "virtual_try_on_job_events")
public class TryOnJobEvent {
    @Id
    private UUID id;

    @Column(name = "job_id", nullable = false)
    private UUID jobId;

    @Column(name = "from_status", length = 16)
    @Enumerated(EnumType.STRING)
    private TryOnStatus fromStatus;

    @Column(name = "to_status", nullable = false, length = 16)
    @Enumerated(EnumType.STRING)
    private TryOnStatus toStatus;

    @Column(nullable = false, length = 64)
    private String reason;

    @Column(name = "attempt_count", nullable = false)
    private int attemptCount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected TryOnJobEvent() {
    }

    public static TryOnJobEvent create(
        TryOnJob job,
        TryOnStatus fromStatus,
        String reason
    ) {
        TryOnJobEvent event = new TryOnJobEvent();
        event.id = UUID.randomUUID();
        event.jobId = job.getId();
        event.fromStatus = fromStatus;
        event.toStatus = job.getStatus();
        event.reason = reason;
        event.attemptCount = job.getAttemptCount();
        event.createdAt = Instant.now();
        return event;
    }

    public UUID getJobId() { return jobId; }
    public TryOnStatus getFromStatus() { return fromStatus; }
    public TryOnStatus getToStatus() { return toStatus; }
    public String getReason() { return reason; }
    public int getAttemptCount() { return attemptCount; }
    public Instant getCreatedAt() { return createdAt; }
}
