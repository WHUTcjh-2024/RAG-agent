package com.atelier.gateway.tryon;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.atelier.gateway.common.ApiException;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class TryOnJobTest {
    @Test
    void transitionsThroughRetryAndSuccessWithoutDuplicateClaims() {
        TryOnJob job = TryOnJob.create(
            UUID.randomUUID(), "dress-1", "dress", "{}", "try-on-key-0001", Duration.ofHours(24)
        );

        assertThat(job.getStatus()).isEqualTo(TryOnStatus.QUEUED);
        assertThat(job.getAttemptCount()).isZero();

        job.claim();
        assertThat(job.getStatus()).isEqualTo(TryOnStatus.PROCESSING);
        assertThat(job.getAttemptCount()).isEqualTo(1);

        job.retryAt(Instant.now().plusSeconds(1));
        job.claim();
        job.succeed("redis:fitme:tryon:result:job-1");

        assertThat(job.getStatus()).isEqualTo(TryOnStatus.SUCCEEDED);
        assertThat(job.getAttemptCount()).isEqualTo(2);
        assertThat(job.getOutputKey()).isEqualTo("redis:fitme:tryon:result:job-1");
        assertThatThrownBy(job::claim).isInstanceOf(ApiException.class);
    }

    @Test
    void resultCannotBeSavedBeforeItSucceeds() {
        TryOnJob job = TryOnJob.create(
            UUID.randomUUID(), "dress-1", "dress", "{}", "try-on-key-0001", Duration.ofHours(24)
        );

        assertThatThrownBy(() -> job.save(true, Duration.ofDays(7))).isInstanceOf(ApiException.class);
    }
}
