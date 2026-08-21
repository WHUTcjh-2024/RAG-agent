package com.atelier.gateway.order;

import java.util.Optional;

@FunctionalInterface
interface CheckoutRule {
    Optional<CheckoutRuleViolation> validate(CheckoutRuleContext context);
}
