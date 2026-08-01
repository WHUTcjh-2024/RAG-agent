package com.atelier.gateway.wardrobe;

import com.atelier.gateway.common.ApiException;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping
public class WardrobeController {
    private final WardrobeService wardrobeService;
    private final String internalToken;

    public WardrobeController(WardrobeService wardrobeService, @Value("${agent.internal-token:}") String internalToken) {
        this.wardrobeService = wardrobeService;
        this.internalToken = internalToken;
    }

    @GetMapping("/api/wardrobe")
    public Mono<WardrobeService.SnapshotView> current(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization
    ) {
        return Mono.fromCallable(() -> wardrobeService.current(authorization)).subscribeOn(Schedulers.boundedElastic());
    }

    @PostMapping("/api/wardrobe/items")
    public Mono<WardrobeService.SnapshotView> add(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @RequestBody WardrobeService.ItemInput input
    ) {
        return Mono.fromCallable(() -> wardrobeService.add(authorization, input)).subscribeOn(Schedulers.boundedElastic());
    }

    @PutMapping("/api/wardrobe/items/{itemId}")
    public Mono<WardrobeService.SnapshotView> update(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID itemId,
        @RequestBody WardrobeService.ItemInput input
    ) {
        return Mono.fromCallable(() -> wardrobeService.update(authorization, itemId, input)).subscribeOn(Schedulers.boundedElastic());
    }

    @DeleteMapping("/api/wardrobe/items/{itemId}")
    public Mono<ResponseEntity<Void>> delete(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID itemId
    ) {
        return Mono.fromCallable(() -> {
            wardrobeService.delete(authorization, itemId);
            return ResponseEntity.noContent().<Void>build();
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @PostMapping("/api/wardrobe/feedback")
    public Mono<ResponseEntity<Void>> feedback(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @RequestBody WardrobeService.FeedbackInput input
    ) {
        return Mono.fromCallable(() -> {
            wardrobeService.recordFeedback(authorization, input);
            return ResponseEntity.noContent().<Void>build();
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/internal/agent/wardrobe")
    public Mono<WardrobeService.SnapshotView> internalSnapshot(
        @RequestHeader(name = "X-Agent-Internal-Token", required = false) String suppliedToken,
        @RequestParam("trusted_user_id") UUID trustedUserId
    ) {
        return Mono.fromCallable(() -> {
            if (internalToken.isBlank() || !internalToken.equals(suppliedToken)) {
                throw new ApiException(HttpStatus.FORBIDDEN, "Internal agent credential is invalid");
            }
            return wardrobeService.internalSnapshot(trustedUserId);
        }).subscribeOn(Schedulers.boundedElastic());
    }
}
