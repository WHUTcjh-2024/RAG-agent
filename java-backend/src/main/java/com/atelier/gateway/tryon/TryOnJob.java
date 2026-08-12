package com.atelier.gateway.tryon;

import com.atelier.gateway.common.ApiException;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.HttpStatus;

@Entity
@Table(name = "virtual_try_on_jobs")
public class TryOnJob {
    @Id
    private UUID id;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    @Column(name = "product_id", nullable = false, length = 100)
    private String productId;

    @Column(nullable = false, length = 64)
    private String category;

    @Column(name = "body_profile_json", nullable = false, columnDefinition = "TEXT")
    private String bodyProfileJson;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 16)
    private TryOnStatus status;

    @Column(name = "idempotency_key", nullable = false, length = 128)
    private String idempotencyKey;

    @Column(name = "attempt_count", nullable = false)
    private int attemptCount;

    @Column(name = "output_key", length = 255)
    private String outputKey;

    @Column(name = "failure_code", length = 64)
    private String failureCode;

    @Column(nullable = false)
    private boolean saved;

    @Column(name = "feedback_json", columnDefinition = "TEXT")
    private String feedbackJson;

    @Column(name = "available_at", nullable = false)
    private Instant availableAt;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Column(name = "expires_at", nullable = false)
    private Instant expiresAt;

    protected TryOnJob() {
    }

    public static TryOnJob create(
        UUID userId,
        String productId,
        String category,
        String bodyProfileJson,
        String idempotencyKey,
        Duration resultTtl
    ) {
        Instant now = Instant.now();
        TryOnJob job = new TryOnJob();
        job.id = UUID.randomUUID();
        job.userId = userId;
        job.productId = productId;
        job.category = category;
        job.bodyProfileJson = bodyProfileJson;
        job.status = TryOnStatus.QUEUED;
        job.idempotencyKey = idempotencyKey;
        job.attemptCount = 0;
        job.availableAt = now;
        job.createdAt = now;
        job.updatedAt = now;
        job.expiresAt = now.plus(resultTtl);
        return job;
    }

    public void claim() {
        transition(TryOnStatus.QUEUED, TryOnStatus.PROCESSING);
        attemptCount++;
        availableAt = Instant.now();
    }

    public void succeed(String resultKey) {
        transition(TryOnStatus.PROCESSING, TryOnStatus.SUCCEEDED);
        outputKey = resultKey;
        failureCode = null;
    }

    public void retryAt(Instant nextAvailableAt) {
        transition(TryOnStatus.PROCESSING, TryOnStatus.QUEUED);
        availableAt = nextAvailableAt;
    }

    public void fail(String code) {
        transition(TryOnStatus.PROCESSING, TryOnStatus.FAILED);
        failureCode = code;
    }

    public void save(boolean value, Duration ttl) {
        if (status != TryOnStatus.SUCCEEDED) {
            throw new ApiException(HttpStatus.CONFLICT, "Try-on result is not ready");
        }
        saved = value;
        expiresAt = Instant.now().plus(ttl);
        updatedAt = Instant.now();
    }

    public void feedback(String value) {
        if (status != TryOnStatus.SUCCEEDED) {
            throw new ApiException(HttpStatus.CONFLICT, "Try-on result is not ready");
        }
        feedbackJson = value;
        updatedAt = Instant.now();
    }

    private void transition(TryOnStatus expected, TryOnStatus target) {
        if (status != expected) {
            throw new ApiException(HttpStatus.CONFLICT, "Invalid try-on job state transition");
        }
        status = target;
        updatedAt = Instant.now();
    }

    public UUID getId() { return id; }
    public UUID getUserId() { return userId; }
    public String getProductId() { return productId; }
    public String getCategory() { return category; }
    public String getBodyProfileJson() { return bodyProfileJson; }
    public TryOnStatus getStatus() { return status; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public int getAttemptCount() { return attemptCount; }
    public String getOutputKey() { return outputKey; }
    public String getFailureCode() { return failureCode; }
    public boolean isSaved() { return saved; }
    public String getFeedbackJson() { return feedbackJson; }
    public Instant getAvailableAt() { return availableAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
    public Instant getExpiresAt() { return expiresAt; }
}
