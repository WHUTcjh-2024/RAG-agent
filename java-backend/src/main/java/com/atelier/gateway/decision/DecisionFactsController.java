package com.atelier.gateway.decision;

import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.security.JwtTokenService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
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
public class DecisionFactsController {
    private final BodyProfileRepository profileRepository;
    private final ProductSkuFactRepository productFactRepository;
    private final JwtTokenService tokenService;
    private final String internalToken;

    public DecisionFactsController(
        BodyProfileRepository profileRepository,
        ProductSkuFactRepository productFactRepository,
        JwtTokenService tokenService,
        @Value("${agent.internal-token:}") String internalToken
    ) {
        this.profileRepository = profileRepository;
        this.productFactRepository = productFactRepository;
        this.tokenService = tokenService;
        this.internalToken = internalToken;
    }

    @PutMapping("/api/profile/body")
    public Mono<BodyProfileView> updateProfile(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @RequestBody UpdateBodyProfileRequest request
    ) {
        return Mono.fromCallable(() -> {
            UUID userId = userId(authorization);
            if (request.chestCm() == null || request.chestCm().compareTo(BigDecimal.ZERO) <= 0) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "胸围必须为正数");
            }
            BodyProfile profile = profileRepository.save(BodyProfile.update(userId, request.chestCm()));
            return new BodyProfileView(profile.getChestCm(), profile.getUpdatedAt());
        }).subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/internal/agent/decision-facts")
    public Mono<DecisionFactsResponse> decisionFacts(
        @RequestHeader(name = "X-Agent-Internal-Token", required = false) String suppliedToken,
        @RequestParam("trusted_user_id") UUID trustedUserId,
        @RequestParam("product_id") String productId
    ) {
        return Mono.fromCallable(() -> {
            if (internalToken.isBlank() || !internalToken.equals(suppliedToken)) {
                throw new ApiException(HttpStatus.FORBIDDEN, "Internal agent credential is invalid");
            }
            BodyProfile profile = profileRepository.findById(trustedUserId).orElse(null);
            ProductSkuFact product = productFactRepository.findById(productId).orElse(null);
            Instant observedAt = product != null ? product.getUpdatedAt() : Instant.now();
            Map<String, Object> profileValues = new LinkedHashMap<>();
            if (profile != null && profile.getChestCm() != null) profileValues.put("chest_cm", profile.getChestCm());
            Map<String, Object> measurementValues = new LinkedHashMap<>();
            Map<String, Object> priceValues = new LinkedHashMap<>();
            Map<String, Object> inventoryValues = new LinkedHashMap<>();
            Map<String, Object> returnValues = new LinkedHashMap<>();
            if (product != null) {
                if (product.getChestCm() != null) measurementValues.put("chest_cm", product.getChestCm());
                if (product.getSize() != null) measurementValues.put("size", product.getSize());
                if (product.getPrice() != null) priceValues.put("amount", product.getPrice());
                if (product.getInStock() != null) inventoryValues.put("in_stock", product.getInStock());
                if (product.getReturnPolicy() != null) returnValues.put("summary", product.getReturnPolicy());
            }
            return new DecisionFactsResponse(
                trustedUserId.toString(), productId, product == null ? null : product.getSkuId(),
                profileValues, measurementValues, priceValues, inventoryValues, returnValues,
                product == null ? null : product.getVersion(), observedAt
            );
        }).subscribeOn(Schedulers.boundedElastic());
    }

    private UUID userId(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "请先登录");
        }
        try {
            return tokenService.parseUserId(authorization.substring("Bearer ".length()).trim());
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "请先登录");
        }
    }

    public record UpdateBodyProfileRequest(BigDecimal chestCm) { }
    public record BodyProfileView(BigDecimal chestCm, Instant updatedAt) { }
    public record DecisionFactsResponse(
        String user_id, String product_id, String sku_id,
        Map<String, Object> profile, Map<String, Object> sku_measurements,
        Map<String, Object> price, Map<String, Object> inventory,
        Map<String, Object> return_policy, String version, Instant observed_at
    ) { }
}
