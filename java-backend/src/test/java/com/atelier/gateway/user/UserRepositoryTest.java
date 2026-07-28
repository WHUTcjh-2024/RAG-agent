package com.atelier.gateway.user;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class UserRepositoryTest {
    @Autowired
    private UserRepository userRepository;

    @Test
    void savesLocalUserAndFindsByEmailIgnoringCase() {
        UserAccount user = UserAccount.createLocal(
            "User@Example.com",
            "$2a$10$hashed-password",
            "陈昊"
        );

        userRepository.saveAndFlush(user);

        assertThat(userRepository.existsByEmailIgnoreCase("user@example.com")).isTrue();
        assertThat(userRepository.findByEmailIgnoreCase("USER@example.com"))
            .hasValueSatisfying(saved -> {
                assertThat(saved.getId()).isNotNull();
                assertThat(saved.getEmail()).isEqualTo("user@example.com");
                assertThat(saved.getPasswordHash()).isEqualTo("$2a$10$hashed-password");
                assertThat(saved.getDisplayName()).isEqualTo("陈昊");
                assertThat(saved.getProvider()).isEqualTo(AuthProvider.LOCAL);
                assertThat(saved.getProviderUserId()).isNull();
                assertThat(saved.getCreatedAt()).isNotNull();
                assertThat(saved.getUpdatedAt()).isNotNull();
            });
    }
}
