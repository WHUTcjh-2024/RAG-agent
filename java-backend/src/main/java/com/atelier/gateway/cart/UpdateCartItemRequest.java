package com.atelier.gateway.cart;

public record UpdateCartItemRequest(
    Integer quantity,
    Boolean selected
) {
}
