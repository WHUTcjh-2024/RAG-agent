package com.atelier.gateway.health;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class HealthController {
    @GetMapping("/health")
    public Mono<HealthStatus> health() {
        return Mono.just(new HealthStatus("ok", "java-backend"));
    }

    public record HealthStatus(
        String status,
        String service
    ) {
    }
}
