package com.atelier.gateway.cart;

import com.atelier.gateway.cart.CartResponses.CartItemView;
import com.atelier.gateway.cart.CartResponses.CartView;
import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.security.JwtTokenService;
import com.atelier.gateway.user.UserRepository;
import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CartService {
    private final CartItemRepository cartItemRepository;
    private final UserRepository userRepository;
    private final JwtTokenService jwtTokenService;

    public CartService(
        CartItemRepository cartItemRepository,
        UserRepository userRepository,
        JwtTokenService jwtTokenService
    ) {
        this.cartItemRepository = cartItemRepository;
        this.userRepository = userRepository;
        this.jwtTokenService = jwtTokenService;
    }

    @Transactional
    public CartItemView addItem(String authorizationHeader, AddCartItemRequest request) {
        UUID userId = currentUserId(authorizationHeader);
        String productId = requireText(request.productId(), "Product id is required");
        String productName = requireText(request.productName(), "Product name is required");
        BigDecimal unitPrice = requireUnitPrice(request.unitPrice());
        int quantity = requireQuantity(request.quantity());
        Boolean selected = request.selected();

        CartItem item = cartItemRepository.findByUserIdAndProductId(userId, productId)
            .map(existing -> {
                existing.addQuantity(quantity, productName, normalizedImageUrl(request.productImageUrl()), unitPrice, selected);
                return existing;
            })
            .orElseGet(() -> CartItem.create(
                userId,
                productId,
                productName,
                normalizedImageUrl(request.productImageUrl()),
                unitPrice,
                quantity,
                selected == null || selected
            ));

        return CartItemView.from(cartItemRepository.save(item));
    }

    @Transactional(readOnly = true)
    public CartView currentCart(String authorizationHeader) {
        UUID userId = currentUserId(authorizationHeader);
        return new CartView(cartItemRepository.findByUserIdOrderByCreatedAtAsc(userId).stream()
            .map(CartItemView::from)
            .toList());
    }

    @Transactional
    public CartItemView updateItem(String authorizationHeader, UUID itemId, UpdateCartItemRequest request) {
        UUID userId = currentUserId(authorizationHeader);
        if (request.quantity() == null && request.selected() == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "No cart item changes provided");
        }
        Integer quantity = request.quantity();
        if (quantity != null) {
            requireQuantity(quantity);
        }

        CartItem item = cartItemRepository.findByIdAndUserId(itemId, userId)
            .orElseThrow(this::cartItemNotFound);
        item.update(quantity, request.selected());
        return CartItemView.from(cartItemRepository.save(item));
    }

    @Transactional
    public void deleteItem(String authorizationHeader, UUID itemId) {
        UUID userId = currentUserId(authorizationHeader);
        CartItem item = cartItemRepository.findByIdAndUserId(itemId, userId)
            .orElseThrow(this::cartItemNotFound);
        cartItemRepository.delete(item);
    }

    @Transactional
    public void clearCart(String authorizationHeader) {
        UUID userId = currentUserId(authorizationHeader);
        cartItemRepository.deleteByUserId(userId);
    }

    private UUID currentUserId(String authorizationHeader) {
        if (authorizationHeader == null || !authorizationHeader.startsWith("Bearer ")) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Login required");
        }
        String token = authorizationHeader.substring("Bearer ".length()).trim();
        UUID userId;
        try {
            userId = jwtTokenService.parseUserId(token);
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Login required");
        }
        if (!userRepository.existsById(userId)) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "Login required");
        }
        return userId;
    }

    private String requireText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, message);
        }
        return value.trim();
    }

    private String normalizedImageUrl(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    private BigDecimal requireUnitPrice(BigDecimal unitPrice) {
        if (unitPrice == null || unitPrice.compareTo(BigDecimal.ZERO) < 0) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Unit price must be at least 0");
        }
        return unitPrice;
    }

    private int requireQuantity(Integer quantity) {
        if (quantity == null || quantity < 1) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Quantity must be at least 1");
        }
        return quantity;
    }

    private ApiException cartItemNotFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "Cart item not found");
    }
}
