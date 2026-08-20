package com.atelier.gateway.cart;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class AgentCartActionCommitTest {
    @Test
    void reconciliationDetectsCartDeletionAfterAnAgentCommit() {
        UUID userId = UUID.randomUUID();
        CartItem item = CartItem.create(
            userId, "dress-1", "Cerise Dress", "/media/dress.jpg", new BigDecimal("199.00"), 1, true
        );
        AgentCartActionCommit commit = AgentCartActionCommit.create(
            "action-1", userId, "task-1", "dress-1", item.getId(), new BigDecimal("199.00"), 1, "{}"
        );

        commit.reconcile(item);
        assertThat(commit.getReconciliationStatus()).isEqualTo(CartActionReconciliationStatus.MATCHED);

        commit.reconcile(null);
        assertThat(commit.getReconciliationStatus()).isEqualTo(CartActionReconciliationStatus.CART_ITEM_MISSING);
        assertThat(commit.getReconciliationMessage()).isEqualTo("购物车商品已不存在。");
    }
}
