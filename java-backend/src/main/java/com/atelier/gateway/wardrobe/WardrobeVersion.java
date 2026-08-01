package com.atelier.gateway.wardrobe;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "wardrobe_versions")
public class WardrobeVersion {
    @Id
    @Column(name = "user_id")
    private UUID userId;
    @Column(name = "version", nullable = false)
    private long version;
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    protected WardrobeVersion() { }

    public static WardrobeVersion initial(UUID userId) {
        WardrobeVersion value = new WardrobeVersion();
        value.userId = userId;
        value.version = 0;
        value.updatedAt = Instant.now();
        return value;
    }

    public void advance() {
        version++;
        updatedAt = Instant.now();
    }

    public long getVersion() { return version; }
}
