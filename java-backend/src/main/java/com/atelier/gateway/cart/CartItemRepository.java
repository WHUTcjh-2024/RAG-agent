package com.atelier.gateway.cart;

import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CartItemRepository extends JpaRepository<CartItem, UUID> {
    List<CartItem> findByUserIdOrderByCreatedAtAsc(UUID userId);

    List<CartItem> findByUserIdAndSelectedTrueOrderByCreatedAtAsc(UUID userId);

    Optional<CartItem> findByUserIdAndProductId(UUID userId, String productId);

    Optional<CartItem> findByIdAndUserId(UUID id, UUID userId);

    long deleteByUserId(UUID userId);
}
