package com.atelier.gateway.cart;

public record AddCartItemRequest(
    String productId,
    Integer quantity
) {
}
