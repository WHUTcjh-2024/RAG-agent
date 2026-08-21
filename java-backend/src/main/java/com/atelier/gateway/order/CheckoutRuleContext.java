package com.atelier.gateway.order;

import com.atelier.gateway.decision.ProductSkuFact;

record CheckoutRuleContext(CheckoutCatalogSnapshot catalogSnapshot, ProductSkuFact productFact) {
}
