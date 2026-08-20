package com.atelier.gateway.tryon;

import com.atelier.gateway.common.ApiException;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.RejectedExecutionException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Component;
import org.springframework.context.annotation.Profile;

@Component
@Profile("!local")
public class TryOnWorker {
    private static final Logger LOGGER = LoggerFactory.getLogger(TryOnWorker.class);

    private final TryOnService tryOnService;
    private final TryOnInferenceClient inferenceClient;
    private final ThreadPoolTaskExecutor executor;
    private final TryOnProperties properties;
    private final TryOnQueue queue;

    public TryOnWorker(
        TryOnService tryOnService,
        TryOnInferenceClient inferenceClient,
        @Qualifier("tryOnExecutor") ThreadPoolTaskExecutor executor,
        TryOnProperties properties,
        TryOnQueue queue
    ) {
        this.tryOnService = tryOnService;
        this.inferenceClient = inferenceClient;
        this.executor = executor;
        this.properties = properties;
        this.queue = queue;
    }

    @Scheduled(fixedDelayString = "${tryon.poll-interval-ms:200}", initialDelayString = "${tryon.poll-interval-ms:200}")
    public void dispatchReadyJobs() {
        try {
            dispatch(queue.read(dispatchCapacity()));
        } catch (RuntimeException exception) {
            LOGGER.error("try-on queue read failed", exception);
        }
    }

    @Scheduled(fixedDelayString = "${tryon.poll-interval-ms:200}", initialDelayString = "${tryon.poll-interval-ms:200}")
    public void requeueReadyJobs() {
        try {
            for (UUID jobId : tryOnService.readyJobIds(properties.queueCapacity())) {
                queue.publish(jobId);
            }
        } catch (RuntimeException exception) {
            LOGGER.error("try-on queue reconciliation failed", exception);
        }
    }

    @Scheduled(fixedDelayString = "${tryon.recovery-interval-ms:30000}")
    public void recoverStalledJobs() {
        try {
            List<UUID> recovered = tryOnService.recoverStalled(Instant.now().minus(properties.processingLease()));
            recovered.forEach(jobId -> {
                queue.release(jobId);
                queue.publish(jobId);
            });
            dispatch(queue.reclaimStale(properties.processingLease(), dispatchCapacity()));
            if (!recovered.isEmpty()) {
                LOGGER.warn("recovered stalled try-on jobs count={}", recovered.size());
            }
        } catch (RuntimeException exception) {
            LOGGER.error("try-on recovery failed", exception);
        }
    }

    @Scheduled(fixedDelayString = "${tryon.expiry-interval-ms:60000}")
    public void expireDueJobs() {
        try {
            List<UUID> expired = tryOnService.expireDueJobs(properties.queueCapacity());
            if (!expired.isEmpty()) {
                LOGGER.info("expired try-on jobs count={}", expired.size());
            }
        } catch (RuntimeException exception) {
            LOGGER.error("try-on expiry sweep failed", exception);
        }
    }

    private void dispatch(List<TryOnQueue.QueueMessage> messages) {
        for (TryOnQueue.QueueMessage message : messages) {
            try {
                executor.execute(() -> process(message));
            } catch (RejectedExecutionException exception) {
                LOGGER.debug("try-on executor saturated; queue message remains pending jobId={}", message.jobId());
                return;
            }
        }
    }

    private int dispatchCapacity() {
        int active = executor.getActiveCount();
        int queued = executor.getThreadPoolExecutor().getQueue().size();
        return Math.max(0, properties.workerCount() + properties.queueCapacity() - active - queued);
    }

    private void process(TryOnQueue.QueueMessage message) {
        UUID jobId = message.jobId();
        TryOnJob job = tryOnService.claim(jobId);
        if (job == null) {
            completeQueueMessage(message);
            return;
        }
        try {
            byte[] image = inferenceClient.render(job);
            if (tryOnService.succeed(jobId, image)) {
                LOGGER.info("try-on job succeeded jobId={} attempt={}", jobId, job.getAttemptCount());
            } else {
                LOGGER.info("try-on job expired before result persistence jobId={}", jobId);
            }
        } catch (TryOnInferenceClient.RetryableTryOnException exception) {
            completeRetryableFailure(job, exception.getCode(), exception);
        } catch (ApiException exception) {
            completeRejectedFailure(jobId, exception);
        } catch (RuntimeException exception) {
            completeRetryableFailure(job, "INTERNAL_ERROR", exception);
        } finally {
            completeQueueMessage(message);
        }
    }

    private void completeQueueMessage(TryOnQueue.QueueMessage message) {
        try {
            queue.acknowledge(message);
            queue.release(message.jobId());
        } catch (RuntimeException exception) {
            LOGGER.warn("try-on queue acknowledgement failed jobId={}", message.jobId(), exception);
        }
    }

    private void completeRetryableFailure(TryOnJob job, String code, RuntimeException exception) {
        try {
            if (job.getAttemptCount() < tryOnService.maxAttempts()) {
                tryOnService.retry(job.getId());
                LOGGER.warn(
                    "try-on job scheduled for retry jobId={} attempt={} code={}",
                    job.getId(),
                    job.getAttemptCount(),
                    code
                );
                return;
            }
            tryOnService.fail(job.getId(), code);
            LOGGER.warn("try-on job failed jobId={} code={}", job.getId(), code, exception);
        } catch (ApiException stateChanged) {
            LOGGER.info("try-on job failure ignored because state changed jobId={}", job.getId());
        }
    }

    private void completeRejectedFailure(UUID jobId, ApiException exception) {
        try {
            tryOnService.fail(jobId, "PROVIDER_REJECTED");
            LOGGER.warn("try-on job rejected jobId={} status={}", jobId, exception.getStatus());
        } catch (ApiException stateChanged) {
            LOGGER.info("try-on job rejection ignored because state changed jobId={}", jobId);
        }
    }
}
