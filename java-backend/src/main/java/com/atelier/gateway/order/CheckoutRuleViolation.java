package com.atelier.gateway.order;

enum CheckoutRuleCode {
    PRODUCT_CHANGED,
    PRICE_CHANGED,
    OUT_OF_STOCK
}

record CheckoutRuleViolation(
    CheckoutRuleCode code,
    String message,
    CheckoutCatalogSnapshot catalogSnapshot
) {
}
