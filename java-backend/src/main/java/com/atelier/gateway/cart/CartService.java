package com.atelier.gateway.cart;

import com.atelier.gateway.cart.CartResponses.CartItemView;
import com.atelier.gateway.cart.CartResponses.CartView;
import com.atelier.gateway.catalog.CatalogProductGateway;
import com.atelier.gateway.catalog.CatalogProductSnapshot;
import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.security.JwtTokenService;
import com.atelier.gateway.user.UserRepository;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CartService {
    private final CartItemRepository cartItemRepository;
    private final UserRepository userRepository;
    private final JwtTokenService jwtTokenService;
    private final AgentActionTokenService actionTokenService;
    private final AgentCartActionCommitRepository actionCommitRepository;
    private final CatalogProductGateway catalogProductGateway;

    public CartService(
        CartItemRepository cartItemRepository,
        UserRepository userRepository,
        JwtTokenService jwtTokenService,
        AgentActionTokenService actionTokenService,
        AgentCartActionCommitRepository actionCommitRepository,
        CatalogProductGateway catalogProductGateway
    ) {
        this.cartItemRepository = cartItemRepository;
        this.userRepository = userRepository;
        this.jwtTokenService = jwtTokenService;
        this.actionTokenService = actionTokenService;
        this.actionCommitRepository = actionCommitRepository;
        this.catalogProductGateway = catalogProductGateway;
    }

    @Transactional
    public CartItemView addItem(String authorizationHeader, AddCartItemRequest request) {
        UUID userId = currentUserId(authorizationHeader);
        return CartItemView.from(addItem(userId, request));
    }

    @Transactional
    public CartItemView confirmAgentAction(
        String authorizationHeader, AgentCartConfirmationRequest request
    ) {
        UUID userId = currentUserId(authorizationHeader);
        AgentActionTokenService.AgentCartAction action = actionTokenService.verify(request.confirmationToken());
        if (!userId.toString().equals(action.user_id())) {
            throw new ApiException(HttpStatus.FORBIDDEN, "Agent confirmation does not belong to this user");
        }
        AgentCartActionCommit prior = actionCommitRepository.findById(action.action_id()).orElse(null);
        if (prior != null) {
            if (!prior.getUserId().equals(userId)) {
                throw new ApiException(HttpStatus.FORBIDDEN, "Agent confirmation does not belong to this user");
            }
            if (prior.getCartItemId() == null) {
                throw new ApiException(HttpStatus.CONFLICT, "Confirmed cart item is no longer available");
            }
            CartItem priorItem = cartItemRepository.findById(prior.getCartItemId())
                .orElseThrow(() -> new ApiException(HttpStatus.CONFLICT, "Confirmed cart item is no longer available"));
            return CartItemView.from(priorItem);
        }
        CatalogProductSnapshot snapshot = catalogProductGateway.fetch(action.product_id());
        if (snapshot.unitPrice().compareTo(expectedPrice(action.expected_price())) != 0) {
            throw new ApiException(HttpStatus.CONFLICT, "Product price changed; request a new confirmation");
        }
        CartItem item = addItem(userId, snapshot, requireQuantity(action.quantity()));
        actionCommitRepository.save(AgentCartActionCommit.create(
            action.action_id(), userId, action.product_id(), item.getId()
        ));
        return CartItemView.from(item);
    }

    private CartItem addItem(UUID userId, AddCartItemRequest request) {
        String productId = requireText(request.productId(), "Product id is required");
        int quantity = requireQuantity(request.quantity());
        return addItem(userId, catalogProductGateway.fetch(productId), quantity);
    }

    private CartItem addItem(UUID userId, CatalogProductSnapshot snapshot, int quantity) {
        String productId = snapshot.productId();
        String productName = snapshot.productName();
        String productImageUrl = normalizedImageUrl(snapshot.productImageUrl());

        CartItem item = cartItemRepository.findByUserIdAndProductId(userId, productId)
            .map(existing -> {
                existing.addQuantity(quantity, productName, productImageUrl, snapshot.unitPrice(), true);
                return existing;
            })
            .orElseGet(() -> CartItem.create(
                userId,
                productId,
                productName,
                productImageUrl,
                snapshot.unitPrice(),
                quantity,
                true
            ));

        return cartItemRepository.save(item);
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

    private int requireQuantity(Integer quantity) {
        if (quantity == null || quantity < 1) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Quantity must be at least 1");
        }
        return quantity;
    }

    private java.math.BigDecimal expectedPrice(String value) {
        if (value == null || value.isBlank()) {
            throw new ApiException(HttpStatus.CONFLICT, "Agent confirmation is invalid or expired");
        }
        try {
            return new java.math.BigDecimal(value);
        } catch (NumberFormatException exception) {
            throw new ApiException(HttpStatus.CONFLICT, "Agent confirmation is invalid or expired");
        }
    }

    private ApiException cartItemNotFound() {
        return new ApiException(HttpStatus.NOT_FOUND, "Cart item not found");
    }
}
