package com.atelier.gateway.order;

import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.decision.ProductSkuFact;
import com.atelier.gateway.decision.ProductSkuFactRepository;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.function.Function;
import java.util.stream.Collectors;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/**
 * Checkout responsibility chain. Every selected cart item is verified against
 * the authoritative catalog snapshot before an order can be created.
 */
@Component
public class CheckoutRuleChain {
    private final ProductSkuFactRepository productSkuFactRepository;
    private final List<CheckoutRule> rules;

    public CheckoutRuleChain(ProductSkuFactRepository productSkuFactRepository) {
        this.productSkuFactRepository = productSkuFactRepository;
        this.rules = List.of(
            this::catalogProductMatches,
            this::catalogPriceMatches,
            this::inventoryIsAvailable
        );
    }

    public CheckoutValidationResult validate(List<CheckoutCatalogSnapshot> snapshots) {
        Map<String, ProductSkuFact> facts = productSkuFactRepository.findAllById(
            snapshots.stream().map(snapshot -> snapshot.cartItem().getProductId()).toList()
        ).stream().collect(Collectors.toMap(ProductSkuFact::getProductId, Function.identity()));

        List<CheckoutRuleViolation> violations = snapshots.stream()
            .flatMap(snapshot -> violationsFor(new CheckoutRuleContext(
                snapshot,
                facts.get(snapshot.cartItem().getProductId())
            )).stream())
            .toList();
        return new CheckoutValidationResult(violations);
    }

    private List<CheckoutRuleViolation> violationsFor(CheckoutRuleContext context) {
        return rules.stream().map(rule -> rule.validate(context)).flatMap(Optional::stream).toList();
    }

    private Optional<CheckoutRuleViolation> catalogProductMatches(CheckoutRuleContext context) {
        CheckoutCatalogSnapshot snapshot = context.catalogSnapshot();
        if (snapshot.cartItem().getProductId().equals(snapshot.snapshot().productId())) {
            return Optional.empty();
        }
        return Optional.of(new CheckoutRuleViolation(
            CheckoutRuleCode.PRODUCT_CHANGED,
            "Product is no longer available",
            snapshot
        ));
    }

    private Optional<CheckoutRuleViolation> catalogPriceMatches(CheckoutRuleContext context) {
        CheckoutCatalogSnapshot snapshot = context.catalogSnapshot();
        BigDecimal cartPrice = snapshot.cartItem().getUnitPrice();
        if (cartPrice.compareTo(snapshot.snapshot().unitPrice()) == 0) {
            return Optional.empty();
        }
        return Optional.of(new CheckoutRuleViolation(
            CheckoutRuleCode.PRICE_CHANGED,
            "Cart price changed",
            snapshot
        ));
    }

    private Optional<CheckoutRuleViolation> inventoryIsAvailable(CheckoutRuleContext context) {
        ProductSkuFact fact = context.productFact();
        if (fact == null || fact.getInStock() == null || fact.getInStock()) {
            return Optional.empty();
        }
        return Optional.of(new CheckoutRuleViolation(
            CheckoutRuleCode.OUT_OF_STOCK,
            "Product is out of stock",
            context.catalogSnapshot()
        ));
    }

    public record CheckoutValidationResult(List<CheckoutRuleViolation> violations) {
        public boolean hasPriceChanges() {
            return violations.stream().anyMatch(violation -> violation.code() == CheckoutRuleCode.PRICE_CHANGED);
        }

        public List<CheckoutCatalogSnapshot> changedPriceSnapshots() {
            return violations.stream()
                .filter(violation -> violation.code() == CheckoutRuleCode.PRICE_CHANGED)
                .map(CheckoutRuleViolation::catalogSnapshot)
                .toList();
        }

        public void requireAllowed() {
            violations.stream()
                .filter(violation -> violation.code() != CheckoutRuleCode.PRICE_CHANGED)
                .findFirst()
                .ifPresent(violation -> {
                    throw new ApiException(HttpStatus.CONFLICT, violation.message());
                });
        }
    }
}
