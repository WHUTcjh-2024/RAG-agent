package com.atelier.gateway.cart;

import java.math.BigDecimal;

public record AddCartItemRequest(
    String productId,
    String productName,
    String productImageUrl,
    BigDecimal unitPrice,
    Integer quantity,
    Boolean selected
) {
}
