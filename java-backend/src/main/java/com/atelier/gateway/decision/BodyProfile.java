package com.atelier.gateway.decision;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "body_profiles")
public class BodyProfile {
    @Id
    @Column(name = "user_id")
    private UUID userId;

    @Column(name = "chest_cm", precision = 6, scale = 2)
    private BigDecimal chestCm;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected BodyProfile() {
    }

    public static BodyProfile update(UUID userId, BigDecimal chestCm) {
        BodyProfile profile = new BodyProfile();
        profile.userId = userId;
        profile.chestCm = chestCm;
        profile.updatedAt = Instant.now();
        return profile;
    }

    public UUID getUserId() { return userId; }
    public BigDecimal getChestCm() { return chestCm; }
    public Instant getUpdatedAt() { return updatedAt; }
}
