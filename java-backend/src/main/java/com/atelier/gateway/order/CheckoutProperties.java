package com.atelier.gateway.order;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "checkout")
public record CheckoutProperties(int catalogParallelism) {
    public CheckoutProperties {
        if (catalogParallelism < 1 || catalogParallelism > 16) {
            throw new IllegalArgumentException("checkout.catalog-parallelism must be between 1 and 16");
        }
    }
}
