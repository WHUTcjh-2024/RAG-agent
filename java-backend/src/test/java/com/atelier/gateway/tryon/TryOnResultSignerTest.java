package com.atelier.gateway.tryon;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.time.Duration;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class TryOnResultSignerTest {
    private final TryOnProperties properties = new TryOnProperties(
        "http://127.0.0.1:18000", "internal-token", 2, 8, 3, 10,
        Duration.ofMinutes(10), Duration.ofHours(24), Duration.ofDays(7),
        Duration.ofSeconds(90), Duration.ofMinutes(2), "result-url-signing-secret"
    );

    @Test
    void signedResultUrlIsShortLivedAndBoundToTheJobOutput() {
        TryOnJob job = TryOnJob.create(
            UUID.randomUUID(), "dress-1", "dress", "{}", "try-on-key-0001", Duration.ofHours(24)
        );
        job.claim();
        job.succeed("redis:fitme:tryon:result:job-1");
        TryOnResultSigner signer = new TryOnResultSigner(properties);

        URI uri = URI.create("http://localhost" + signer.url(job));
        String[] parameters = uri.getQuery().split("&");
        long expires = Long.parseLong(parameters[0].substring("expires=".length()));
        String signature = parameters[1].substring("signature=".length());

        assertThat(signer.verify(job, expires, signature)).isTrue();
        assertThat(signer.verify(job, expires + 1, signature)).isFalse();
    }
}
