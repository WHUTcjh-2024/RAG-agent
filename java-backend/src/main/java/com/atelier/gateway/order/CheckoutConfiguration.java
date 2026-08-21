package com.atelier.gateway.order;

import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class CheckoutConfiguration {
    @Bean("checkoutCatalogExecutor")
    ThreadPoolTaskExecutor checkoutCatalogExecutor(CheckoutProperties properties) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(properties.catalogParallelism());
        executor.setMaxPoolSize(properties.catalogParallelism());
        executor.setQueueCapacity(properties.catalogParallelism() * 4);
        executor.setThreadNamePrefix("checkout-catalog-");
        executor.setRejectedExecutionHandler(new ThreadPoolExecutor.CallerRunsPolicy());
        executor.initialize();
        return executor;
    }
}
