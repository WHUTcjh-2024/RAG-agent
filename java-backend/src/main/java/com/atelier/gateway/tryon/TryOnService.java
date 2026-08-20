package com.atelier.gateway.tryon;

import com.atelier.gateway.catalog.CatalogProductGateway;
import com.atelier.gateway.catalog.CatalogProductSnapshot;
import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.security.JwtTokenService;
import com.atelier.gateway.user.UserRepository;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class TryOnService {
    private final TryOnJobRepository jobRepository;
    private final TryOnJobEventRepository jobEventRepository;
    private final CatalogProductGateway catalogProductGateway;
    private final JwtTokenService jwtTokenService;
    private final UserRepository userRepository;
    private final ObjectMapper objectMapper;
    private final TryOnProperties properties;
    private final TryOnResultStore resultStore;
    private final TryOnRateLimiter rateLimiter;
    private final TryOnResultSigner resultSigner;
    private final TryOnQueue queue;

    public TryOnService(
        TryOnJobRepository jobRepository,
        TryOnJobEventRepository jobEventRepository,
        CatalogProductGateway catalogProductGateway,
        JwtTokenService jwtTokenService,
        UserRepository userRepository,
        ObjectMapper objectMapper,
        TryOnProperties properties,
        TryOnResultStore resultStore,
        TryOnRateLimiter rateLimiter,
        TryOnResultSigner resultSigner,
        TryOnQueue queue
    ) {
        this.jobRepository = jobRepository;
        this.jobEventRepository = jobEventRepository;
        this.catalogProductGateway = catalogProductGateway;
        this.jwtTokenService = jwtTokenService;
        this.userRepository = userRepository;
        this.objectMapper = objectMapper;
        this.properties = properties;
        this.resultStore = resultStore;
        this.rateLimiter = rateLimiter;
        this.resultSigner = resultSigner;
        this.queue = queue;
    }

    @Transactional
    public CreateResult create(String authorization, String idempotencyKey, TryOnRequest input) {
        UUID userId = currentUserId(authorization);
        String key = validateIdempotencyKey(idempotencyKey);
        if (input == null || input.product_id() == null || input.product_id().isBlank() || input.body_profile() == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Try-on request is invalid");
        }
        TryOnRequest.BodyProfile bodyProfile = input.body_profile().normalized();
        bodyProfile.validate();

        TryOnJob existing = jobRepository.findByUserIdAndIdempotencyKey(userId, key).orElse(null);
        if (existing != null) {
            return new CreateResult(existing, false);
        }
        rateLimiter.check(userId);
        CatalogProductSnapshot product = catalogProductGateway.fetch(input.product_id().trim());
        TryOnJob job = TryOnJob.create(
            userId,
            product.productId(),
            inferCategory(product.productName()),
            serialize(bodyProfile),
            key,
            properties.resultTtl()
        );
        try {
            TryOnJob created = jobRepository.saveAndFlush(job);
            recordTransition(created, null, "CREATED");
            enqueueAfterCommit(created.getId());
            return new CreateResult(created, true);
        } catch (DataIntegrityViolationException exception) {
            return new CreateResult(jobRepository.findByUserIdAndIdempotencyKey(userId, key)
                .orElseThrow(() -> exception), false);
        }
    }

    @Transactional(readOnly = true)
    public TryOnJob get(String authorization, UUID jobId) {
        UUID userId = currentUserId(authorization);
        return jobRepository.findByIdAndUserId(jobId, userId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Try-on job was not found"));
    }

    @Transactional(readOnly = true)
    public List<TryOnJob> list(String authorization, int limit) {
        return jobRepository.findTop50ByUserIdOrderByCreatedAtDesc(currentUserId(authorization)).stream()
            .limit(limit)
            .toList();
    }

    @Transactional
    public TryOnJob save(String authorization, UUID jobId, boolean saved) {
        TryOnJob job = get(authorization, jobId);
        job.save(saved, saved ? properties.savedResultTtl() : properties.resultTtl());
        resultStore.extend(jobId, saved ? properties.savedResultTtl() : properties.resultTtl());
        return job;
    }

    @Transactional
    public TryOnJob feedback(String authorization, UUID jobId, TryOnRequest.FeedbackRequest input) {
        if (input == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Try-on feedback is invalid");
        }
        TryOnRequest.FeedbackRequest feedback = input.normalized();
        feedback.validate();
        TryOnJob job = get(authorization, jobId);
        job.feedback(serialize(feedback));
        return job;
    }

    @Transactional
    public void delete(String authorization, UUID jobId) {
        TryOnJob job = get(authorization, jobId);
        resultStore.delete(job.getId());
        queue.release(job.getId());
        jobRepository.delete(job);
    }

    @Transactional(readOnly = true)
    public byte[] result(UUID jobId, long expires, String signature) {
        TryOnJob job = jobRepository.findById(jobId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Try-on result was not found"));
        if (job.getStatus() != TryOnStatus.SUCCEEDED || !resultSigner.verify(job, expires, signature)) {
            throw new ApiException(HttpStatus.NOT_FOUND, "Try-on result was not found");
        }
        return resultStore.get(jobId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Try-on result was not found"));
    }

    @Transactional
    public TryOnJob claim(UUID jobId) {
        TryOnJob job = jobRepository.findByIdForUpdate(jobId).orElse(null);
        if (job == null || job.getStatus() != TryOnStatus.QUEUED || job.getAvailableAt().isAfter(Instant.now())) {
            return null;
        }
        if (!job.getExpiresAt().isAfter(Instant.now())) {
            expire(job);
            return null;
        }
        TryOnStatus previous = job.getStatus();
        job.claim();
        recordTransition(job, previous, "CLAIMED");
        return job;
    }

    @Transactional
    public boolean succeed(UUID jobId, byte[] image) {
        TryOnJob job = requiredForUpdate(jobId, TryOnStatus.PROCESSING);
        if (!job.getExpiresAt().isAfter(Instant.now())) {
            expire(job);
            return false;
        }
        resultStore.put(jobId, image, Duration.between(Instant.now(), job.getExpiresAt()));
        TryOnStatus previous = job.getStatus();
        job.succeed("redis:fitme:tryon:result:" + jobId);
        recordTransition(job, previous, "RENDER_SUCCEEDED");
        return true;
    }

    @Transactional
    public void retry(UUID jobId) {
        TryOnJob job = requiredForUpdate(jobId, TryOnStatus.PROCESSING);
        TryOnStatus previous = job.getStatus();
        job.retryAt(Instant.now().plus(backoff(job.getAttemptCount())));
        recordTransition(job, previous, "RETRY_SCHEDULED");
    }

    @Transactional
    public void fail(UUID jobId, String failureCode) {
        TryOnJob job = requiredForUpdate(jobId, TryOnStatus.PROCESSING);
        TryOnStatus previous = job.getStatus();
        job.fail(failureCode);
        recordTransition(job, previous, failureCode);
    }

    @Transactional(readOnly = true)
    public List<UUID> readyJobIds(int limit) {
        return jobRepository.findReadyJobIds(Instant.now(), limit);
    }

    @Transactional
    public List<UUID> recoverStalled(Instant stalledBefore) {
        List<UUID> recovered = new java.util.ArrayList<>();
        for (UUID jobId : jobRepository.findStalledJobIds(stalledBefore, properties.workerCount() * 2)) {
            TryOnJob job = jobRepository.findByIdForUpdate(jobId).orElse(null);
            if (job == null || job.getStatus() != TryOnStatus.PROCESSING) {
                continue;
            }
            TryOnStatus previous = job.getStatus();
            if (job.getAttemptCount() < properties.maxAttempts()) {
                job.retryAt(Instant.now());
                recordTransition(job, previous, "WORKER_RECOVERED");
            } else {
                job.fail("WORKER_LEASE_EXPIRED");
                recordTransition(job, previous, "WORKER_LEASE_EXPIRED");
            }
            recovered.add(jobId);
        }
        return recovered;
    }

    public int maxAttempts() { return properties.maxAttempts(); }

    public String resultUrl(TryOnJob job) {
        return resultSigner.url(job);
    }

    @Transactional(readOnly = true)
    public List<TryOnJobEvent> events(String authorization, UUID jobId) {
        get(authorization, jobId);
        return jobEventRepository.findByJobIdOrderByCreatedAtAsc(jobId);
    }

    @Transactional
    public List<UUID> expireDueJobs(int limit) {
        List<UUID> expired = new java.util.ArrayList<>();
        for (UUID jobId : jobRepository.findExpiredJobIds(Instant.now(), limit)) {
            TryOnJob job = jobRepository.findByIdForUpdate(jobId).orElse(null);
            if (job == null || job.getStatus() == TryOnStatus.EXPIRED || job.getExpiresAt().isAfter(Instant.now())) {
                continue;
            }
            expire(job);
            expired.add(jobId);
        }
        return expired;
    }

    public record CreateResult(TryOnJob job, boolean created) { }

    public JsonNode bodyProfile(TryOnJob job) {
        try {
            return objectMapper.readTree(job.getBodyProfileJson());
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Stored body profile is invalid", exception);
        }
    }

    private TryOnJob requiredForUpdate(UUID jobId, TryOnStatus status) {
        TryOnJob job = jobRepository.findByIdForUpdate(jobId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Try-on job was not found"));
        if (job.getStatus() != status) {
            throw new ApiException(HttpStatus.CONFLICT, "Try-on job state changed");
        }
        return job;
    }

    private void expire(TryOnJob job) {
        TryOnStatus previous = job.getStatus();
        job.expire();
        resultStore.delete(job.getId());
        queue.release(job.getId());
        recordTransition(job, previous, "RESULT_EXPIRED");
    }

    private void recordTransition(TryOnJob job, TryOnStatus previous, String reason) {
        jobEventRepository.save(TryOnJobEvent.create(job, previous, reason));
    }

    private UUID currentUserId(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Please sign in first");
        }
        UUID userId;
        try {
            userId = jwtTokenService.parseUserId(authorization.substring("Bearer ".length()).trim());
        } catch (IllegalArgumentException exception) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Please sign in first");
        }
        if (!userRepository.existsById(userId)) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Please sign in first");
        }
        return userId;
    }

    private static String validateIdempotencyKey(String value) {
        if (value == null || !value.trim().matches("^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Idempotency-Key must contain 8 to 128 safe characters");
        }
        return value.trim();
    }

    private String serialize(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Cannot serialize try-on payload", exception);
        }
    }

    private static Duration backoff(int attempt) {
        int exponent = Math.min(Math.max(attempt - 1, 0), 5);
        return Duration.ofSeconds(1L << exponent);
    }

    private void enqueueAfterCommit(UUID jobId) {
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                try {
                    queue.publish(jobId);
                } catch (RuntimeException ignored) {
                    // The reconciler republishes QUEUED jobs; a committed request must stay idempotent.
                }
            }
        });
    }

    private static String inferCategory(String productName) {
        String value = productName == null ? "" : productName.toLowerCase();
        if (value.contains("dress")) return "dress";
        if (value.contains("skirt")) return "skirt";
        if (value.contains("shoe") || value.contains("boot") || value.contains("sneaker")) return "shoes";
        if (value.contains("coat") || value.contains("jacket") || value.contains("blazer")) return "outerwear";
        if (value.contains("pants") || value.contains("jean") || value.contains("trouser")) return "bottom";
        return "apparel";
    }
}
