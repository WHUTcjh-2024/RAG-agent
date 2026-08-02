package com.atelier.gateway.wardrobe;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface WardrobeItemRepository extends JpaRepository<WardrobeItem, UUID> {
    List<WardrobeItem> findAllByUserIdOrderByCreatedAtAsc(UUID userId);
    Optional<WardrobeItem> findByIdAndUserId(UUID id, UUID userId);
}
