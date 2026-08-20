package com.atelier.gateway.cart;

import com.atelier.gateway.catalog.CatalogProductSnapshot;
import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.decision.ProductSkuFact;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/**
 * Versioned, deterministic gate for an Agent-originated cart action.
 *
 * <p>The Agent may propose an action, but it cannot decide price, stock or
 * quantity rules. This engine keeps those checks in the Java transaction domain
 * and returns an auditable result that is persisted with the action commit.</p>
 */
@Component
public class CartConfirmationRuleEngine {
    private static final String VERSION = "cart_confirmation/v1";
    private static final int MAX_AGENT_QUANTITY = 10;

    public RuleDecision evaluate(
        AgentActionTokenService.AgentCartAction action,
        CatalogProductSnapshot snapshot,
        ProductSkuFact inventoryFact
    ) {
        List<RuleCheck> checks = new ArrayList<>();
        checks.add(productMatches(action, snapshot));
        checks.add(priceMatches(action, snapshot));
        checks.add(quantityAllowed(action.quantity()));
        checks.add(inventoryAvailable(inventoryFact));
        return new RuleDecision(VERSION, List.copyOf(checks));
    }

    private RuleCheck productMatches(
        AgentActionTokenService.AgentCartAction action,
        CatalogProductSnapshot snapshot
    ) {
        boolean matches = action.product_id() != null && action.product_id().equals(snapshot.productId());
        return new RuleCheck(
            "catalog_product_match",
            matches ? RuleStatus.PASS : RuleStatus.FAIL,
            matches ? "商品编号与服务端目录一致。" : "商品编号与服务端目录不一致。"
        );
    }

    private RuleCheck priceMatches(
        AgentActionTokenService.AgentCartAction action,
        CatalogProductSnapshot snapshot
    ) {
        BigDecimal expectedPrice;
        try {
            expectedPrice = new BigDecimal(action.expected_price());
        } catch (RuntimeException exception) {
            return new RuleCheck("price_snapshot", RuleStatus.FAIL, "确认价格无效或已过期。");
        }
        boolean matches = snapshot.unitPrice().compareTo(expectedPrice) == 0;
        return new RuleCheck(
            "price_snapshot",
            matches ? RuleStatus.PASS : RuleStatus.FAIL,
            matches ? "服务端价格未变化。" : "Product price changed; request a new confirmation"
        );
    }

    private RuleCheck quantityAllowed(Integer quantity) {
        boolean allowed = quantity != null && quantity >= 1 && quantity <= MAX_AGENT_QUANTITY;
        return new RuleCheck(
            "quantity_limit",
            allowed ? RuleStatus.PASS : RuleStatus.FAIL,
            allowed ? "商品数量符合自动加购限制。" : "商品数量不符合自动加购限制。"
        );
    }

    private RuleCheck inventoryAvailable(ProductSkuFact fact) {
        if (fact == null || fact.getInStock() == null) {
            return new RuleCheck("inventory_fact", RuleStatus.SKIPPED, "暂无可验证库存事实。");
        }
        return new RuleCheck(
            "inventory_fact",
            fact.getInStock() ? RuleStatus.PASS : RuleStatus.FAIL,
            fact.getInStock() ? "商品库存可用。" : "商品当前无库存。"
        );
    }

    public enum RuleStatus {
        PASS,
        FAIL,
        SKIPPED
    }

    public record RuleCheck(String code, RuleStatus status, String message) { }

    public record RuleDecision(String version, List<RuleCheck> checks) {
        public boolean allowed() {
            return checks.stream().noneMatch(check -> check.status() == RuleStatus.FAIL);
        }

        public void requireAllowed() {
            checks.stream()
                .filter(check -> check.status() == RuleStatus.FAIL)
                .findFirst()
                .ifPresent(check -> {
                    throw new ApiException(HttpStatus.CONFLICT, check.message());
                });
        }

        public String toAuditJson() {
            String serializedChecks = checks.stream()
                .map(check -> "{\"code\":\"%s\",\"status\":\"%s\",\"message\":\"%s\"}"
                    .formatted(escape(check.code()), check.status(), escape(check.message())))
                .reduce((left, right) -> left + "," + right)
                .orElse("");
            return "{\"version\":\"%s\",\"allowed\":%s,\"checks\":[%s]}"
                .formatted(escape(version), allowed(), serializedChecks);
        }

        private static String escape(String value) {
            return value.replace("\\", "\\\\").replace("\"", "\\\"");
        }
    }
}
