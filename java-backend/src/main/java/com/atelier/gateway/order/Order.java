package com.atelier.gateway.order;

import com.atelier.gateway.common.ApiException;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.HttpStatus;

@Entity
@Table(name = "orders")
public class Order {
    @Id
    private UUID id;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    @Column(name = "idempotency_key", nullable = false, length = 128)
    private String idempotencyKey;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 32)
    private OrderStatus status;

    @Column(name = "total_amount", nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected Order() {
    }

    public static Order create(UUID userId, String idempotencyKey, BigDecimal totalAmount) {
        Instant now = Instant.now();
        Order order = new Order();
        order.id = UUID.randomUUID();
        order.userId = userId;
        order.idempotencyKey = idempotencyKey;
        order.status = OrderStatus.PENDING_PAYMENT;
        order.totalAmount = totalAmount;
        order.createdAt = now;
        order.updatedAt = now;
        return order;
    }

    public void cancel() {
        if (status != OrderStatus.PENDING_PAYMENT) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Order cannot be cancelled");
        }
        status = OrderStatus.CANCELLED;
        updatedAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }

    public UUID getUserId() {
        return userId;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
