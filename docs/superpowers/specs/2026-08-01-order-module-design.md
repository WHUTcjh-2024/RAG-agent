# Java Order Module Design

## Goal

Provide authenticated Java API endpoints for creating, viewing, and
cancelling orders. Orders are created from selected cart items and retain
their own product snapshots for later payment, inventory, and delivery work.

## Scope

This iteration includes:

- Create an order from selected cart items.
- List the current user's orders and view one order.
- Cancel a pending-payment order.
- JWT authentication and user-level data isolation.

It excludes payments, stock reservation, promotions, shipping addresses,
delivery, and frontend changes.

## Data Model

Use two tables:

- `orders`: `id`, `user_id`, `status`, `total_amount`, `created_at`, and
  `updated_at`.
- `order_items`: `id`, `order_id`, `product_id`, `product_name`,
  `product_image_url`, `unit_price`, `quantity`, `subtotal`, and
  `created_at`.

New orders use the `PENDING_PAYMENT` status. A cancelled order uses
`CANCELLED`. All amounts use `DECIMAL(19, 2)`; the order total is the sum of
the item subtotals.

## API

- `POST /api/orders`: create an order from selected cart items; no body.
- `GET /api/orders`: list the current user's orders, newest first.
- `GET /api/orders/{orderId}`: get one current-user order with its items.
- `POST /api/orders/{orderId}/cancel`: cancel a pending-payment order.

Every endpoint uses the existing `Authorization: Bearer <JWT>` convention.

## Create Flow

1. Read and validate the current user from the JWT.
2. Load that user's cart items with `selected = true`.
3. If no items are selected, return `400 No selected cart items`.
4. Create the order and copy each cart item to an order-item snapshot.
5. Calculate per-item subtotals and the order total from cart snapshots.
6. Delete only the cart items that were included in the order.

Creation and cart deletion run in one database transaction, so any failure
rolls back the entire operation.

## Authorization And Errors

- Missing, invalid, or inactive-user JWT: `401 Login required`.
- Another user's order or a missing order: `404 Order not found`.
- Cancelling an order that is not pending payment: `400 Order cannot be
  cancelled`.
- Creating without selected items: `400 No selected cart items`.

The implementation uses the existing `ApiException` and standard error body.

## Tests

Integration tests will cover:

- Login is required to create an order.
- Creation copies item snapshots, calculates totals, and preserves unselected
  cart items.
- No selected item produces a bad request.
- Users cannot read another user's order or order detail.
- A pending-payment order can be cancelled.
- An already cancelled order cannot be cancelled again.

Each behaviour starts with a failing test before the smallest implementation
is added. The final verification command is `mvn test`.
