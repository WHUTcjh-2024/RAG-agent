package com.atelier.gateway.order;

import java.io.Serializable;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

public final class OrderResponses {
    private OrderResponses() {
    }

    public record OrderListView(List<OrderSummaryView> orders) implements Serializable {
    }

    public record OrderSummaryView(
        UUID id,
        OrderStatus status,
        BigDecimal totalAmount,
        Instant createdAt,
        Instant updatedAt
    ) implements Serializable {
        public static OrderSummaryView from(Order order) {
            return new OrderSummaryView(
                order.getId(),
                order.getStatus(),
                order.getTotalAmount(),
                order.getCreatedAt(),
                order.getUpdatedAt()
            );
        }
    }

    public record OrderDetailView(
        UUID id,
        OrderStatus status,
        BigDecimal totalAmount,
        List<OrderItemView> items,
        Instant createdAt,
        Instant updatedAt
    ) {
        public static OrderDetailView from(Order order, List<OrderItem> items) {
            return new OrderDetailView(
                order.getId(),
                order.getStatus(),
                order.getTotalAmount(),
                items.stream().map(OrderItemView::from).toList(),
                order.getCreatedAt(),
                order.getUpdatedAt()
            );
        }
    }

    public record OrderItemView(
        UUID id,
        String productId,
        String productName,
        String productImageUrl,
        BigDecimal unitPrice,
        int quantity,
        BigDecimal subtotal,
        Instant createdAt
    ) {
        public static OrderItemView from(OrderItem item) {
            return new OrderItemView(
                item.getId(),
                item.getProductId(),
                item.getProductName(),
                item.getProductImageUrl(),
                item.getUnitPrice(),
                item.getQuantity(),
                item.getSubtotal(),
                item.getCreatedAt()
            );
        }
    }
}
