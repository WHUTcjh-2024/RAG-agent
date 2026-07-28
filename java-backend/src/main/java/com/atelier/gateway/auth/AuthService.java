package com.atelier.gateway.auth;

import com.atelier.gateway.auth.AuthResponses.AuthResult;
import com.atelier.gateway.auth.AuthResponses.UserView;
import com.atelier.gateway.common.ApiException;
import com.atelier.gateway.security.JwtTokenService;
import com.atelier.gateway.security.PasswordHasher;
import com.atelier.gateway.user.UserAccount;
import com.atelier.gateway.user.UserRepository;
import java.util.Locale;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuthService {
    private static final Pattern EMAIL_PATTERN = Pattern.compile("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");

    private final UserRepository userRepository;
    private final PasswordHasher passwordHasher;
    private final JwtTokenService jwtTokenService;

    public AuthService(
        UserRepository userRepository,
        PasswordHasher passwordHasher,
        JwtTokenService jwtTokenService
    ) {
        this.userRepository = userRepository;
        this.passwordHasher = passwordHasher;
        this.jwtTokenService = jwtTokenService;
    }

    @Transactional
    public AuthResult register(RegisterRequest request) {
        String email = normalizeEmail(request.email());
        String displayName = normalizeDisplayName(request.displayName());
        validatePassword(request.password());

        if (userRepository.existsByEmailIgnoreCase(email)) {
            throw new ApiException(HttpStatus.CONFLICT, "邮箱已经被注册");
        }

        UserAccount user = UserAccount.createLocal(
            email,
            passwordHasher.hash(request.password()),
            displayName
        );
        UserAccount saved = userRepository.save(user);
        return new AuthResult(UserView.from(saved), jwtTokenService.createAccessToken(saved.getId()));
    }

    @Transactional(readOnly = true)
    public AuthResult login(LoginRequest request) {
        String email = normalizeEmail(request.email());
        UserAccount user = userRepository.findByEmailIgnoreCase(email)
            .orElseThrow(this::invalidCredentials);

        if (!passwordHasher.matches(request.password(), user.getPasswordHash())) {
            throw invalidCredentials();
        }

        return new AuthResult(UserView.from(user), jwtTokenService.createAccessToken(user.getId()));
    }

    @Transactional(readOnly = true)
    public UserView currentUser(String authorizationHeader) {
        if (authorizationHeader == null || !authorizationHeader.startsWith("Bearer ")) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "请先登录");
        }
        String token = authorizationHeader.substring("Bearer ".length()).trim();
        UUID userId;
        try {
            userId = jwtTokenService.parseUserId(token);
        } catch (IllegalArgumentException ex) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "请先登录");
        }
        UserAccount user = userRepository.findById(userId)
            .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "请先登录"));
        return UserView.from(user);
    }

    private String normalizeEmail(String email) {
        if (email == null || email.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "邮箱不能为空");
        }
        String normalized = email.trim().toLowerCase(Locale.ROOT);
        if (!EMAIL_PATTERN.matcher(normalized).matches()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "邮箱格式不正确");
        }
        return normalized;
    }

    private String normalizeDisplayName(String displayName) {
        if (displayName == null || displayName.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "昵称不能为空");
        }
        return displayName.trim();
    }

    private void validatePassword(String password) {
        if (password == null || password.length() < 8) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "密码长度至少 8 位");
        }
    }

    private ApiException invalidCredentials() {
        return new ApiException(HttpStatus.UNAUTHORIZED, "邮箱或密码错误");
    }
}
