package com.atelier.gateway.auth;

import com.atelier.gateway.user.AuthProvider;
import com.atelier.gateway.user.UserAccount;
import java.util.UUID;

public final class AuthResponses {
    private AuthResponses() {
    }

    public record AuthResult(UserView user, String accessToken) {
    }

    public record UserView(
        UUID id,
        String email,
        String displayName,
        AuthProvider provider
    ) {
        public static UserView from(UserAccount user) {
            return new UserView(
                user.getId(),
                user.getEmail(),
                user.getDisplayName(),
                user.getProvider()
            );
        }
    }
}
