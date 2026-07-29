package com.atelier.gateway.cart;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(
    name = "cart_items",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_cart_items_user_product",
        columnNames = {"user_id", "product_id"}
    )
)
public class CartItem {
    @Id
    private UUID id;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

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

    @Column(nullable = false)
    private boolean selected;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected CartItem() {
    }

    public static CartItem create(
        UUID userId,
        String productId,
        String productName,
        String productImageUrl,
        BigDecimal unitPrice,
        int quantity,
        boolean selected
    ) {
        Instant now = Instant.now();
        CartItem item = new CartItem();
        item.id = UUID.randomUUID();
        item.userId = userId;
        item.productId = productId;
        item.productName = productName;
        item.productImageUrl = productImageUrl;
        item.unitPrice = unitPrice;
        item.quantity = quantity;
        item.selected = selected;
        item.createdAt = now;
        item.updatedAt = now;
        return item;
    }

    public void addQuantity(
        int addedQuantity,
        String productName,
        String productImageUrl,
        BigDecimal unitPrice,
        Boolean selected
    ) {
        this.quantity += addedQuantity;
        this.productName = productName;
        this.productImageUrl = productImageUrl;
        this.unitPrice = unitPrice;
        if (selected != null) {
            this.selected = selected;
        }
        this.updatedAt = Instant.now();
    }

    public void update(Integer quantity, Boolean selected) {
        if (quantity != null) {
            this.quantity = quantity;
        }
        if (selected != null) {
            this.selected = selected;
        }
        this.updatedAt = Instant.now();
    }

    public UUID getId() {
        return id;
    }

    public UUID getUserId() {
        return userId;
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

    public boolean isSelected() {
        return selected;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }
}
