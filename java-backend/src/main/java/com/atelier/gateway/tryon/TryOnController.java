package com.atelier.gateway.tryon;

import com.atelier.gateway.common.ApiException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/try-on")
public class TryOnController {
    private final TryOnService tryOnService;
    private final ObjectMapper objectMapper;

    public TryOnController(TryOnService tryOnService, ObjectMapper objectMapper) {
        this.tryOnService = tryOnService;
        this.objectMapper = objectMapper;
    }

    @PostMapping("/jobs")
    public Mono<ResponseEntity<JobView>> create(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey,
        @RequestBody TryOnRequest input
    ) {
        return Mono.fromCallable(() -> {
            TryOnService.CreateResult result = tryOnService.create(authorization, idempotencyKey, input);
            ResponseEntity.BodyBuilder response = ResponseEntity.status(result.created() ? HttpStatus.ACCEPTED : HttpStatus.OK);
            if (result.created()) {
                response.header(HttpHeaders.RETRY_AFTER, "2");
            }
            return response.body(view(result.job()));
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/jobs")
    public Mono<Map<String, List<JobView>>> list(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @RequestParam(defaultValue = "12") int limit
    ) {
        return Mono.fromCallable(() -> {
            if (limit < 1 || limit > 50) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "limit must be between 1 and 50");
            }
            return Map.of("items", tryOnService.list(authorization, limit).stream().map(this::view).toList());
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/jobs/{jobId}")
    public Mono<JobView> get(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID jobId
    ) {
        return Mono.fromCallable(() -> view(tryOnService.get(authorization, jobId))).subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/jobs/{jobId}/events")
    public Mono<Map<String, List<StateEventView>>> events(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID jobId
    ) {
        return Mono.fromCallable(() -> Map.of(
            "items",
            tryOnService.events(authorization, jobId).stream().map(this::eventView).toList()
        )).subscribeOn(Schedulers.boundedElastic());
    }

    @PostMapping("/jobs/{jobId}/save")
    public Mono<JobView> save(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID jobId,
        @RequestBody TryOnRequest.SaveRequest input
    ) {
        return Mono.fromCallable(() -> {
            if (input == null) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "Try-on save request is invalid");
            }
            return view(tryOnService.save(authorization, jobId, input.saved()));
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @PostMapping("/jobs/{jobId}/feedback")
    public Mono<JobView> feedback(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID jobId,
        @RequestBody TryOnRequest.FeedbackRequest input
    ) {
        return Mono.fromCallable(() -> view(tryOnService.feedback(authorization, jobId, input))).subscribeOn(Schedulers.boundedElastic());
    }

    @DeleteMapping("/jobs/{jobId}")
    public Mono<ResponseEntity<Void>> delete(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID jobId
    ) {
        return Mono.fromCallable(() -> {
            tryOnService.delete(authorization, jobId);
            return ResponseEntity.noContent().<Void>build();
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @PostMapping("/jobs/{jobId}/share")
    public Mono<Map<String, String>> share(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID jobId
    ) {
        return Mono.fromCallable(() -> Map.of("url", tryOnService.resultUrl(tryOnService.get(authorization, jobId))))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/jobs/{jobId}/result")
    public Mono<ResponseEntity<byte[]>> result(
        @PathVariable UUID jobId,
        @RequestParam long expires,
        @RequestParam String signature
    ) {
        return Mono.fromCallable(() -> ResponseEntity.ok()
            .contentType(MediaType.IMAGE_JPEG)
            .header(HttpHeaders.CACHE_CONTROL, "private, no-store")
            .header("X-Content-Type-Options", "nosniff")
            .header("Referrer-Policy", "no-referrer")
            .header("X-AI-Generated", "synthetic-virtual-model")
            .body(tryOnService.result(jobId, expires, signature)))
            .subscribeOn(Schedulers.boundedElastic());
    }

    private JobView view(TryOnJob job) {
        return new JobView(
            job.getId(), job.getProductId(), job.getCategory(), job.getStatus(), job.getCreatedAt(),
            job.getUpdatedAt(), job.getExpiresAt(), queued(job) ? 2 : null, job.getAttemptCount(),
            new ModelView("SYNTHETIC_ADULT", parse(job.getBodyProfileJson()), false),
            job.getStatus() == TryOnStatus.SUCCEEDED ? new ResultView(tryOnService.resultUrl(job)) : null,
            job.getStatus() == TryOnStatus.FAILED || job.getStatus() == TryOnStatus.EXPIRED
                ? Map.of("code", job.getFailureCode()) : null,
            job.isSaved(), parseNullable(job.getFeedbackJson())
        );
    }

    private static boolean queued(TryOnJob job) {
        return job.getStatus() == TryOnStatus.QUEUED || job.getStatus() == TryOnStatus.PROCESSING;
    }

    private JsonNode parse(String value) {
        try {
            return objectMapper.readTree(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException("Stored try-on payload is invalid", exception);
        }
    }

    private JsonNode parseNullable(String value) { return value == null ? null : parse(value); }

    private StateEventView eventView(TryOnJobEvent event) {
        return new StateEventView(
            event.getFromStatus(),
            event.getToStatus(),
            event.getReason(),
            event.getAttemptCount(),
            event.getCreatedAt()
        );
    }

    public record JobView(
        UUID id, String product_id, String category, TryOnStatus status, Instant created_at, Instant updated_at,
        Instant expires_at, Integer retry_after_seconds, int attempt_count, ModelView model, ResultView result,
        Map<String, String> failure, boolean saved, JsonNode feedback
    ) { }
    public record ModelView(String kind, JsonNode body_profile, boolean uses_person_photo) { }
    public record ResultView(String url) { }
    public record StateEventView(
        TryOnStatus from_status,
        TryOnStatus to_status,
        String reason,
        int attempt_count,
        Instant created_at
    ) { }
}
