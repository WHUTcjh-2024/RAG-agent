package com.atelier.gateway.wardrobe;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "wardrobe_items")
public class WardrobeItem {
    @Id
    private UUID id;
    @Column(name = "user_id", nullable = false)
    private UUID userId;
    @Column(name = "source_product_id", length = 128)
    private String sourceProductId;
    @Column(name = "name", nullable = false, length = 128)
    private String name;
    @Column(name = "category", nullable = false, length = 64)
    private String category;
    @Column(name = "color", length = 64)
    private String color;
    @Column(name = "image_url", length = 500)
    private String imageUrl;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected WardrobeItem() { }

    public static WardrobeItem create(UUID userId, WardrobeService.ItemInput input) {
        WardrobeItem item = new WardrobeItem();
        item.id = UUID.randomUUID();
        item.userId = userId;
        item.apply(input);
        item.createdAt = Instant.now();
        item.updatedAt = item.createdAt;
        return item;
    }

    public void update(WardrobeService.ItemInput input) {
        apply(input);
        updatedAt = Instant.now();
    }

    private void apply(WardrobeService.ItemInput input) {
        sourceProductId = input.sourceProductId();
        name = input.name();
        category = input.category();
        color = input.color();
        imageUrl = input.imageUrl();
    }

    public UUID getId() { return id; }
    public UUID getUserId() { return userId; }
    public String getSourceProductId() { return sourceProductId; }
    public String getName() { return name; }
    public String getCategory() { return category; }
    public String getColor() { return color; }
    public String getImageUrl() { return imageUrl; }
    public Instant getUpdatedAt() { return updatedAt; }
}
