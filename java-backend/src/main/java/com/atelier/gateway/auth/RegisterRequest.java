package com.atelier.gateway.auth;

public record RegisterRequest(
    String email,
    String password,
    String displayName
) {
}
