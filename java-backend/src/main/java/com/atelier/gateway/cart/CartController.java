package com.atelier.gateway.cart;

import com.atelier.gateway.cart.CartResponses.CartItemView;
import com.atelier.gateway.cart.CartResponses.CartView;
import java.util.UUID;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/cart")
public class CartController {
    private final CartService cartService;

    public CartController(CartService cartService) {
        this.cartService = cartService;
    }

    @PostMapping("/items")
    public Mono<CartItemView> addItem(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @RequestBody AddCartItemRequest request
    ) {
        return Mono.fromCallable(() -> cartService.addItem(authorization, request))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping
    public Mono<CartView> currentCart(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization
    ) {
        return Mono.fromCallable(() -> cartService.currentCart(authorization))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @PatchMapping("/items/{itemId}")
    public Mono<CartItemView> updateItem(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID itemId,
        @RequestBody UpdateCartItemRequest request
    ) {
        return Mono.fromCallable(() -> cartService.updateItem(authorization, itemId, request))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @DeleteMapping("/items/{itemId}")
    public Mono<ResponseEntity<Void>> deleteItem(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization,
        @PathVariable UUID itemId
    ) {
        return Mono.fromCallable(() -> {
                cartService.deleteItem(authorization, itemId);
                return ResponseEntity.noContent().<Void>build();
            })
            .subscribeOn(Schedulers.boundedElastic());
    }

    @DeleteMapping
    public Mono<ResponseEntity<Void>> clearCart(
        @RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization
    ) {
        return Mono.fromCallable(() -> {
                cartService.clearCart(authorization);
                return ResponseEntity.noContent().<Void>build();
            })
            .subscribeOn(Schedulers.boundedElastic());
    }
}
