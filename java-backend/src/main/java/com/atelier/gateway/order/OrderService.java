package com.atelier.gateway.order;

import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.cart.CartItem;
import com.atelier.gateway.cart.CartItemRepository;
import com.atelier.gateway.order.OrderResponses.OrderDetailView;
import com.atelier.gateway.order.OrderResponses.OrderListView;
import com.atelier.gateway.order.OrderResponses.OrderSummaryView;
import com.atelier.gateway.security.JwtTokenService;
import com.atelier.gateway.user.UserRepository;
import java.math.BigDecimal;
import java.util.List;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final CartItemRepository cartItemRepository;
    private final OrderRepository orderRepository;
    private final OrderItemRepository orderItemRepository;
    private final UserRepository userRepository;
    private final JwtTokenService jwtTokenService;
    private final OrderListCache orderListCache;

    public OrderService(
        CartItemRepository cartItemRepository,
        OrderRepository orderRepository,
        OrderItemRepository orderItemRepository,
        UserRepository userRepository,
        JwtTokenService jwtTokenService,
        OrderListCache orderListCache
    ) {
        this.cartItemRepository = cartItemRepository;
        this.orderRepository = orderRepository;
        this.orderItemRepository = orderItemRepository;
        this.userRepository = userRepository;
        this.jwtTokenService = jwtTokenService;
        this.orderListCache = orderListCache;
    }

    @Transactional
    public OrderDetailView createOrder(String authorizationHeader, String idempotencyKey) {
        UUID userId = currentUserId(authorizationHeader);
        String key = requireIdempotencyKey(idempotencyKey);
        userRepository.findByIdForUpdate(userId).orElseThrow(this::loginRequired);

        return orderRepository.findByUserIdAndIdempotencyKey(userId, key)
            .map(this::detailView)
            .orElseGet(() -> createNewOrder(userId, key));
    }

    @Transactional(readOnly = true)
    public OrderListView currentOrders(String authorizationHeader) {
        UUID userId = currentUserId(authorizationHeader);
        return orderListCache.get(userId).orElseGet(() -> {
            OrderListView orders = new OrderListView(orderRepository.findByUserIdOrderByCreatedAtDesc(userId).stream()
                .map(OrderSummaryView::from)
                .toList());
            orderListCache.put(userId, orders);
            return orders;
        });
    }

    @Transactional(readOnly = true)
    public OrderDetailView orderDetail(String authorizationHeader, UUID orderId) {
        UUID userId = currentUserId(authorizationHeader);
        return detailView(orderForUser(orderId, userId));
    }

    @Transactional
    public OrderDetailView cancelOrder(String authorizationHeader, UUID orderId) {
        UUID userId = currentUserId(authorizationHeader);
        Order order = orderForUser(orderId, userId);
        order.cancel();
        OrderDetailView detail = detailView(orderRepository.save(order));
        orderListCache.evict(userId);
        return detail;
    }

    private OrderDetailView createNewOrder(UUID userId, String idempotencyKey) {
        List<CartItem> selectedItems = cartItemRepository.findByUserIdAndSelectedTrueOrderByCreatedAtAsc(userId);
        if (selectedItems.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "No selected cart items");
        }

        BigDecimal totalAmount = selectedItems.stream()
            .map(item -> item.getUnitPrice().multiply(BigDecimal.valueOf(item.getQuantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);
        Order order = orderRepository.save(Order.create(userId, idempotencyKey, totalAmount));
        List<OrderItem> orderItems = selectedItems.stream()
            .map(item -> OrderItem.fromCartItem(order.getId(), item))
            .toList();
        orderItemRepository.saveAll(orderItems);
        cartItemRepository.deleteAll(selectedItems);
        orderListCache.evict(userId);
        return OrderDetailView.from(order, orderItems);
    }

    private OrderDetailView detailView(Order order) {
        return OrderDetailView.from(order, orderItemRepository.findByOrderIdOrderByCreatedAtAsc(order.getId()));
    }

    private Order orderForUser(UUID orderId, UUID userId) {
        return orderRepository.findByIdAndUserId(orderId, userId)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Order not found"));
    }

    private UUID currentUserId(String authorizationHeader) {
        if (authorizationHeader == null || !authorizationHeader.startsWith("Bearer ")) {
            throw loginRequired();
        }
        String token = authorizationHeader.substring("Bearer ".length()).trim();
        UUID userId;
        try {
            userId = jwtTokenService.parseUserId(token);
        } catch (IllegalArgumentException ex) {
            throw loginRequired();
        }
        if (!userRepository.existsById(userId)) {
            throw loginRequired();
        }
        return userId;
    }

    private String requireIdempotencyKey(String value) {
        if (value == null || value.isBlank() || value.trim().length() > 128) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Idempotency key is required");
        }
        return value.trim();
    }

    private ApiException loginRequired() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "Login required");
    }
}
