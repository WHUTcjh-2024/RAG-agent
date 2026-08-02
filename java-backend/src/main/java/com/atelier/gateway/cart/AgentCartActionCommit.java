package com.atelier.gateway.cart;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "agent_cart_action_commits")
public class AgentCartActionCommit {
    @Id
    @Column(name = "action_id", length = 64)
    private String actionId;
    @Column(name = "user_id", nullable = false)
    private UUID userId;
    @Column(name = "product_id", nullable = false, length = 128)
    private String productId;
    @Column(name = "cart_item_id")
    private UUID cartItemId;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected AgentCartActionCommit() { }

    public static AgentCartActionCommit create(String actionId, UUID userId, String productId, UUID cartItemId) {
        AgentCartActionCommit commit = new AgentCartActionCommit();
        commit.actionId = actionId;
        commit.userId = userId;
        commit.productId = productId;
        commit.cartItemId = cartItemId;
        commit.createdAt = Instant.now();
        return commit;
    }

    public UUID getUserId() { return userId; }
    public UUID getCartItemId() { return cartItemId; }
}
