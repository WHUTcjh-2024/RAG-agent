package com.atelier.gateway.order;

import com.atelier.gateway.common.ApiException;
import org.springframework.http.HttpStatus;

final class CartPriceChangedException extends ApiException {
    CartPriceChangedException() {
        super(HttpStatus.CONFLICT, "Cart price changed; review the refreshed cart");
    }
}
