package com.atelier.gateway.cart;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
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
    @Column(name = "task_id", nullable = false, length = 100)
    private String taskId;
    @Column(name = "expected_unit_price", precision = 19, scale = 2)
    private BigDecimal expectedUnitPrice;
    @Column(name = "requested_quantity", nullable = false)
    private int requestedQuantity;
    @Column(name = "rule_decision_json", nullable = false, columnDefinition = "TEXT")
    private String ruleDecisionJson;
    @Enumerated(EnumType.STRING)
    @Column(name = "reconciliation_status", nullable = false, length = 32)
    private CartActionReconciliationStatus reconciliationStatus;
    @Column(name = "reconciliation_message", length = 500)
    private String reconciliationMessage;
    @Column(name = "reconciled_at")
    private Instant reconciledAt;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected AgentCartActionCommit() { }

    public static AgentCartActionCommit create(
        String actionId,
        UUID userId,
        String taskId,
        String productId,
        UUID cartItemId,
        BigDecimal expectedUnitPrice,
        int requestedQuantity,
        String ruleDecisionJson
    ) {
        AgentCartActionCommit commit = new AgentCartActionCommit();
        commit.actionId = actionId;
        commit.userId = userId;
        commit.taskId = taskId;
        commit.productId = productId;
        commit.cartItemId = cartItemId;
        commit.expectedUnitPrice = expectedUnitPrice;
        commit.requestedQuantity = requestedQuantity;
        commit.ruleDecisionJson = ruleDecisionJson;
        commit.reconciliationStatus = CartActionReconciliationStatus.PENDING;
        commit.createdAt = Instant.now();
        return commit;
    }

    public void reconcile(CartItem item) {
        if (item == null) {
            updateReconciliation(CartActionReconciliationStatus.CART_ITEM_MISSING, "购物车商品已不存在。");
        } else if (!userId.equals(item.getUserId()) || !productId.equals(item.getProductId())) {
            updateReconciliation(CartActionReconciliationStatus.CART_ITEM_MISMATCH, "购物车商品与确认动作不一致。");
        } else if (expectedUnitPrice != null && expectedUnitPrice.compareTo(item.getUnitPrice()) != 0) {
            updateReconciliation(CartActionReconciliationStatus.PRICE_CHANGED, "购物车价格与确认价格不一致。");
        } else if (item.getQuantity() < requestedQuantity) {
            updateReconciliation(CartActionReconciliationStatus.QUANTITY_REDUCED, "购物车商品数量低于确认数量。");
        } else {
            updateReconciliation(CartActionReconciliationStatus.MATCHED, "确认动作与购物车状态一致。");
        }
    }

    private void updateReconciliation(CartActionReconciliationStatus status, String message) {
        reconciliationStatus = status;
        reconciliationMessage = message;
        reconciledAt = Instant.now();
    }

    public String getActionId() { return actionId; }
    public UUID getUserId() { return userId; }
    public String getTaskId() { return taskId; }
    public String getProductId() { return productId; }
    public UUID getCartItemId() { return cartItemId; }
    public BigDecimal getExpectedUnitPrice() { return expectedUnitPrice; }
    public int getRequestedQuantity() { return requestedQuantity; }
    public String getRuleDecisionJson() { return ruleDecisionJson; }
    public CartActionReconciliationStatus getReconciliationStatus() { return reconciliationStatus; }
    public String getReconciliationMessage() { return reconciliationMessage; }
    public Instant getReconciledAt() { return reconciledAt; }
}
