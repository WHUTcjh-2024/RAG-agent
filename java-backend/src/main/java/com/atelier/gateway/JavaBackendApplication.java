package com.atelier.gateway;

import com.atelier.gateway.security.JwtProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableCaching
@EnableConfigurationProperties(JwtProperties.class)
public class JavaBackendApplication {
    public static void main(String[] args) {
        SpringApplication.run(JavaBackendApplication.class, args);
    }
}
