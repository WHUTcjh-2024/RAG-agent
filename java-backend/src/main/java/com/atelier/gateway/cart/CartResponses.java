package com.atelier.gateway.cart;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class CartResponses {
    private CartResponses() {
    }

    public record CartView(List<CartItemView> items) {
    }

    public record CartItemView(
        UUID id,
        String productId,
        String productName,
        String productImageUrl,
        BigDecimal unitPrice,
        int quantity,
        boolean selected,
        Instant createdAt,
        Instant updatedAt
    ) {
        public static CartItemView from(CartItem item) {
            return new CartItemView(
                item.getId(),
                item.getProductId(),
                item.getProductName(),
                item.getProductImageUrl(),
                item.getUnitPrice(),
                item.getQuantity(),
                item.isSelected(),
                item.getCreatedAt(),
                item.getUpdatedAt()
            );
        }
    }
}
