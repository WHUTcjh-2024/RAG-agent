package com.atelier.gateway.order;

import com.atelier.gateway.order.OrderResponses.OrderListView;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Service;

@Service
public class OrderListCache {
    private static final String CACHE_NAME = "orderLists";

    private final CacheManager cacheManager;

    public OrderListCache(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public Optional<OrderListView> get(UUID userId) {
        try {
            Cache.ValueWrapper value = cache().get(userId);
            return value == null ? Optional.empty() : Optional.of((OrderListView) value.get());
        } catch (RuntimeException ex) {
            return Optional.empty();
        }
    }

    public void put(UUID userId, OrderListView orders) {
        try {
            cache().put(userId, orders);
        } catch (RuntimeException ignored) {
            // A cache outage must not prevent order reads from using PostgreSQL.
        }
    }

    public void evict(UUID userId) {
        try {
            cache().evict(userId);
        } catch (RuntimeException ignored) {
            // A cache outage must not prevent order writes from committing.
        }
    }

    private Cache cache() {
        return Objects.requireNonNull(cacheManager.getCache(CACHE_NAME));
    }
}
