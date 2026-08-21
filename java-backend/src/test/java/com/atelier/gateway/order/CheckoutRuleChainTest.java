package com.atelier.gateway.order;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;

import com.atelier.gateway.cart.CartItem;
import com.atelier.gateway.catalog.CatalogProductSnapshot;
import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.decision.ProductSkuFact;
import com.atelier.gateway.decision.ProductSkuFactRepository;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class CheckoutRuleChainTest {
    @Mock
    private ProductSkuFactRepository productSkuFactRepository;

    @Test
    void reportsPriceChangeWithoutBlockingSnapshotRefresh() {
        given(productSkuFactRepository.findAllById(any())).willReturn(List.of());
        CheckoutRuleChain chain = new CheckoutRuleChain(productSkuFactRepository);

        CheckoutRuleChain.CheckoutValidationResult result = chain.validate(List.of(snapshot(
            "sku-price", new BigDecimal("129.99"), new BigDecimal("149.99")
        )));

        assertThat(result.hasPriceChanges()).isTrue();
        assertThat(result.changedPriceSnapshots()).hasSize(1);
        result.requireAllowed();
    }

    @Test
    void rejectsProductMarkedOutOfStockByDecisionFacts() {
        ProductSkuFact fact = ProductSkuFact.create(
            "sku-stock", "sku-stock", "M", new BigDecimal("96.0"),
            new BigDecimal("129.99"), false, "7 days", "v1"
        );
        given(productSkuFactRepository.findAllById(any())).willReturn(List.of(fact));
        CheckoutRuleChain chain = new CheckoutRuleChain(productSkuFactRepository);

        CheckoutRuleChain.CheckoutValidationResult result = chain.validate(List.of(snapshot(
            "sku-stock", new BigDecimal("129.99"), new BigDecimal("129.99")
        )));

        assertThatThrownBy(result::requireAllowed)
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("Product is out of stock");
    }

    private CheckoutCatalogSnapshot snapshot(String productId, BigDecimal cartPrice, BigDecimal catalogPrice) {
        CartItem cartItem = CartItem.create(
            UUID.randomUUID(), productId, "Wool Coat", "/media/coat.png", cartPrice, 1, true
        );
        CatalogProductSnapshot catalogSnapshot = new CatalogProductSnapshot(
            productId, "Wool Coat", "/media/coat.png", catalogPrice
        );
        return new CheckoutCatalogSnapshot(cartItem, catalogSnapshot);
    }
}
