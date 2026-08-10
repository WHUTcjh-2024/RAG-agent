package com.atelier.gateway.catalog;

public interface CatalogProductGateway {
    CatalogProductSnapshot fetch(String productId);
}
