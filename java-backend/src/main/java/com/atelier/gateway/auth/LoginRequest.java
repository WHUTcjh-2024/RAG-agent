package com.atelier.gateway.auth;

public record LoginRequest(
    String email,
    String password
) {
}
