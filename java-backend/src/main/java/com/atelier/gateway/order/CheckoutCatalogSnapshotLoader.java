package com.atelier.gateway.order;

import com.atelier.gateway.cart.CartItem;
import com.atelier.gateway.catalog.CatalogProductGateway;
import com.atelier.gateway.catalog.CatalogProductSnapshot;
import com.atelier.gateway.common.ApiException;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;

/** Loads authoritative catalog snapshots concurrently before a checkout commits. */
@Service
public class CheckoutCatalogSnapshotLoader {
    private final CatalogProductGateway catalogProductGateway;
    private final Executor executor;

    public CheckoutCatalogSnapshotLoader(
        CatalogProductGateway catalogProductGateway,
        @Qualifier("checkoutCatalogExecutor") Executor executor
    ) {
        this.catalogProductGateway = catalogProductGateway;
        this.executor = executor;
    }

    public List<CheckoutCatalogSnapshot> load(List<CartItem> cartItems) {
        List<CompletableFuture<CheckoutCatalogSnapshot>> futures = cartItems.stream()
            .map(item -> CompletableFuture.supplyAsync(() -> snapshotFor(item), executor))
            .toList();
        try {
            return futures.stream().map(CompletableFuture::join).toList();
        } catch (CompletionException exception) {
            if (exception.getCause() instanceof ApiException apiException) {
                throw apiException;
            }
            throw new ApiException(HttpStatus.BAD_GATEWAY, "Catalog is unavailable");
        }
    }

    private CheckoutCatalogSnapshot snapshotFor(CartItem item) {
        CatalogProductSnapshot snapshot = Objects.requireNonNull(
            catalogProductGateway.fetch(item.getProductId()),
            "Catalog snapshot must not be null"
        );
        return new CheckoutCatalogSnapshot(item, snapshot);
    }
}
