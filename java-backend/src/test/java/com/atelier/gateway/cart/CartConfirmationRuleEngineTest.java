package com.atelier.gateway.cart;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.atelier.gateway.catalog.CatalogProductSnapshot;
import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.decision.ProductSkuFact;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class CartConfirmationRuleEngineTest {
    private final CartConfirmationRuleEngine engine = new CartConfirmationRuleEngine();

    @Test
    void rejectsAnOutOfStockBusinessFactAndKeepsItsDecisionAuditable() {
        ProductSkuFact stockFact = ProductSkuFact.create(
            "dress-1", "dress-1", "M", new BigDecimal("88"), new BigDecimal("199.00"), false,
            "7 days", "catalog-v1"
        );

        CartConfirmationRuleEngine.RuleDecision decision = engine.evaluate(
            action("dress-1", "199.00", 1),
            new CatalogProductSnapshot("dress-1", "Cerise Dress", "/media/dress.jpg", new BigDecimal("199.00")),
            stockFact
        );

        assertThat(decision.allowed()).isFalse();
        assertThat(decision.toAuditJson()).contains("cart_confirmation/v1", "inventory_fact", "FAIL");
        assertThatThrownBy(decision::requireAllowed)
            .isInstanceOf(ApiException.class)
            .hasMessage("商品当前无库存。");
    }

    @Test
    void allowsAnActionWhenTheCatalogPriceMatchesAndNoInventoryFactExists() {
        CartConfirmationRuleEngine.RuleDecision decision = engine.evaluate(
            action("dress-1", "199.00", 1),
            new CatalogProductSnapshot("dress-1", "Cerise Dress", "/media/dress.jpg", new BigDecimal("199.00")),
            null
        );

        assertThat(decision.allowed()).isTrue();
        assertThat(decision.toAuditJson()).contains("inventory_fact", "SKIPPED");
    }

    private AgentActionTokenService.AgentCartAction action(String productId, String price, int quantity) {
        return new AgentActionTokenService.AgentCartAction(
            "action-" + UUID.randomUUID(),
            "task-1",
            UUID.randomUUID().toString(),
            productId,
            "Cerise Dress",
            "/media/dress.jpg",
            price,
            quantity,
            Instant.now().plusSeconds(600).getEpochSecond()
        );
    }
}
