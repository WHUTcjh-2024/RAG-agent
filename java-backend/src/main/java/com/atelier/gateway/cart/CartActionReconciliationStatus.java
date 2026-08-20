package com.atelier.gateway.cart;

public enum CartActionReconciliationStatus {
    PENDING,
    MATCHED,
    CART_ITEM_MISSING,
    CART_ITEM_MISMATCH,
    PRICE_CHANGED,
    QUANTITY_REDUCED
}
