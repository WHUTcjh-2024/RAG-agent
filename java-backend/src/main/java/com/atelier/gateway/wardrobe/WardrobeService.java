package com.atelier.gateway.wardrobe;

import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.security.JwtTokenService;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WardrobeService {
    private static final Set<String> OUTCOMES = Set.of("ADOPTED", "PURCHASED", "KEPT", "RETURNED");
    private static final Set<String> FIT_FEEDBACK = Set.of("TOO_SMALL", "TOO_LARGE", "GOOD_FIT");

    private final WardrobeItemRepository itemRepository;
    private final WardrobeVersionRepository versionRepository;
    private final WardrobeFeedbackEventRepository feedbackRepository;
    private final JwtTokenService tokenService;

    public WardrobeService(
        WardrobeItemRepository itemRepository,
        WardrobeVersionRepository versionRepository,
        WardrobeFeedbackEventRepository feedbackRepository,
        JwtTokenService tokenService
    ) {
        this.itemRepository = itemRepository;
        this.versionRepository = versionRepository;
        this.feedbackRepository = feedbackRepository;
        this.tokenService = tokenService;
    }

    @Transactional(readOnly = true)
    public SnapshotView current(String authorization) {
        return snapshot(currentUserId(authorization));
    }

    @Transactional
    public SnapshotView add(String authorization, ItemInput input) {
        UUID userId = currentUserId(authorization);
        validate(input);
        itemRepository.save(WardrobeItem.create(userId, input));
        advanceVersion(userId);
        return snapshot(userId);
    }

    @Transactional
    public SnapshotView update(String authorization, UUID itemId, ItemInput input) {
        UUID userId = currentUserId(authorization);
        validate(input);
        WardrobeItem item = itemRepository.findByIdAndUserId(itemId, userId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Wardrobe item was not found"));
        item.update(input);
        advanceVersion(userId);
        return snapshot(userId);
    }

    @Transactional
    public void delete(String authorization, UUID itemId) {
        UUID userId = currentUserId(authorization);
        WardrobeItem item = itemRepository.findByIdAndUserId(itemId, userId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Wardrobe item was not found"));
        itemRepository.delete(item);
        advanceVersion(userId);
    }

    @Transactional
    public void recordFeedback(String authorization, FeedbackInput input) {
        UUID userId = currentUserId(authorization);
        validate(input);
        feedbackRepository.save(WardrobeFeedbackEvent.create(userId, input));
    }

    @Transactional(readOnly = true)
    public SnapshotView internalSnapshot(UUID userId) {
        return snapshot(userId);
    }

    private SnapshotView snapshot(UUID userId) {
        long version = versionRepository.findById(userId).map(WardrobeVersion::getVersion).orElse(0L);
        List<ItemView> items = itemRepository.findAllByUserIdOrderByCreatedAtAsc(userId).stream()
            .map(item -> new ItemView(
                item.getId().toString(), item.getSourceProductId(), item.getName(), item.getCategory(),
                item.getColor(), item.getImageUrl(), item.getUpdatedAt()
            ))
            .toList();
        return new SnapshotView(version, items, Instant.now());
    }

    private void advanceVersion(UUID userId) {
        WardrobeVersion version = versionRepository.findById(userId)
            .orElseGet(() -> WardrobeVersion.initial(userId));
        version.advance();
        versionRepository.save(version);
    }

    private UUID currentUserId(String authorization) {
        if (authorization == null || !authorization.startsWith("Bearer ")) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Please sign in first");
        }
        try {
            return tokenService.parseUserId(authorization.substring("Bearer ".length()).trim());
        } catch (IllegalArgumentException error) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Please sign in first");
        }
    }

    private static void validate(ItemInput input) {
        if (input == null || blank(input.name()) || blank(input.category())) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Wardrobe item name and category are required");
        }
        if (input.name().length() > 128 || input.category().length() > 64
            || tooLong(input.color(), 64) || tooLong(input.imageUrl(), 500)
            || tooLong(input.sourceProductId(), 128)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Wardrobe item contains an oversized field");
        }
    }

    private static void validate(FeedbackInput input) {
        if (input == null || !OUTCOMES.contains(normalize(input.outcome()))
            || (input.fitFeedback() != null && !input.fitFeedback().isBlank()
                && !FIT_FEEDBACK.contains(normalize(input.fitFeedback())))) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Feedback outcome is invalid");
        }
        if (tooLong(input.taskId(), 100) || tooLong(input.planRef(), 100) || tooLong(input.itemRef(), 128)) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Feedback reference is oversized");
        }
    }

    private static String normalize(String value) {
        return value == null ? "" : value.trim().toUpperCase(Locale.ROOT);
    }

    private static boolean blank(String value) { return value == null || value.isBlank(); }
    private static boolean tooLong(String value, int maximum) { return value != null && value.length() > maximum; }

    public record ItemInput(String sourceProductId, String name, String category, String color, String imageUrl) { }
    public record FeedbackInput(String taskId, String planRef, String itemRef, String outcome, String fitFeedback) { }
    public record ItemView(String id, String sourceProductId, String name, String category, String color, String imageUrl, Instant updatedAt) { }
    public record SnapshotView(long version, List<ItemView> items, Instant observedAt) { }
}
