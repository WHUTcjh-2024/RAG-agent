package com.atelier.gateway.order;

import com.atelier.gateway.order.OrderResponses.OrderDetailView;
import com.atelier.gateway.order.OrderResponses.OrderListView;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @PostMapping
    public Mono<OrderDetailView> createOrder(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey
    ) {
        return Mono.fromCallable(() -> orderService.createOrder(authorization, idempotencyKey))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping
    public Mono<OrderListView> currentOrders(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization
    ) {
        return Mono.fromCallable(() -> orderService.currentOrders(authorization))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/{orderId}")
    public Mono<OrderDetailView> orderDetail(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID orderId
    ) {
        return Mono.fromCallable(() -> orderService.orderDetail(authorization, orderId))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @PostMapping("/{orderId}/cancel")
    public Mono<OrderDetailView> cancelOrder(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID orderId
    ) {
        return Mono.fromCallable(() -> orderService.cancelOrder(authorization, orderId))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
