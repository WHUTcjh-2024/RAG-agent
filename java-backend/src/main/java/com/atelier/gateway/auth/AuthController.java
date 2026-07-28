package com.atelier.gateway.auth;

import com.atelier.gateway.auth.AuthResponses.AuthResult;
import com.atelier.gateway.auth.AuthResponses.UserView;
import org.springframework.http.HttpHeaders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthService authService;

    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    @PostMapping("/register")
    public Mono<AuthResult> register(@RequestBody RegisterRequest request) {
        return Mono.fromCallable(() -> authService.register(request))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @PostMapping("/login")
    public Mono<AuthResult> login(@RequestBody LoginRequest request) {
        return Mono.fromCallable(() -> authService.login(request))
            .subscribeOn(Schedulers.boundedElastic());
    }

    @GetMapping("/me")
    public Mono<UserView> me(@RequestHeader(name = HttpHeaders.AUTHORIZATION, required = false) String authorization) {
        return Mono.fromCallable(() -> authService.currentUser(authorization))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
