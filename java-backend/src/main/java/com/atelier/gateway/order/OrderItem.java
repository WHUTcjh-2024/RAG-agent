package com.atelier.gateway.order;

import com.atelier.gateway.cart.CartItem;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "order_items")
public class OrderItem {
    @Id
    private UUID id;

    @Column(name = "order_id", nullable = false)
    private UUID orderId;

    @Column(name = "product_id", nullable = false, length = 128)
    private String productId;

    @Column(name = "product_name", nullable = false, length = 255)
    private String productName;

    @Column(name = "product_image_url", length = 1024)
    private String productImageUrl;

    @Column(name = "unit_price", nullable = false, precision = 19, scale = 2)
    private BigDecimal unitPrice;

    @Column(nullable = false)
    private int quantity;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal subtotal;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected OrderItem() {
    }

    public static OrderItem fromCartItem(UUID orderId, CartItem cartItem) {
        OrderItem item = new OrderItem();
        item.id = UUID.randomUUID();
        item.orderId = orderId;
        item.productId = cartItem.getProductId();
        item.productName = cartItem.getProductName();
        item.productImageUrl = cartItem.getProductImageUrl();
        item.unitPrice = cartItem.getUnitPrice();
        item.quantity = cartItem.getQuantity();
        item.subtotal = item.unitPrice.multiply(BigDecimal.valueOf(item.quantity));
        item.createdAt = Instant.now();
        return item;
    }

    public UUID getId() {
        return id;
    }

    public UUID getOrderId() {
        return orderId;
    }

    public String getProductId() {
        return productId;
    }

    public String getProductName() {
        return productName;
    }

    public String getProductImageUrl() {
        return productImageUrl;
    }

    public BigDecimal getUnitPrice() {
        return unitPrice;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getSubtotal() {
        return subtotal;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
