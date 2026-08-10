package com.atelier.gateway.catalog;

import java.math.BigDecimal;

/** Immutable, server-derived product data persisted with cart and order items. */
public record CatalogProductSnapshot(
    String productId,
    String productName,
    String productImageUrl,
    BigDecimal unitPrice
) {
}
