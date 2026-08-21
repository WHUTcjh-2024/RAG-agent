package com.atelier.gateway.order;

import com.atelier.gateway.cart.CartItem;
import com.atelier.gateway.catalog.CatalogProductSnapshot;

record CheckoutCatalogSnapshot(CartItem cartItem, CatalogProductSnapshot snapshot) {
}
