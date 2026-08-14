package com.atelier.gateway.tryon;

import com.atelier.gateway.common.ApiException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

@Component
public class TryOnInferenceClient {
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final TryOnProperties properties;

    public TryOnInferenceClient(ObjectMapper objectMapper, TryOnProperties properties) {
        this.objectMapper = objectMapper;
        this.properties = properties;
        this.httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    }

    public byte[] render(TryOnJob job) throws RetryableTryOnException {
        try {
            String requestBody = objectMapper.writeValueAsString(new InferenceRequest(
                job.getId(), job.getProductId(), objectMapper.readTree(job.getBodyProfileJson())
            ));
            HttpRequest request = HttpRequest.newBuilder(endpoint())
                .timeout(properties.providerTimeout())
                .header("Content-Type", "application/json")
                .header("Accept", "image/*")
                .header("X-Agent-Internal-Token", properties.internalToken())
                .header("X-Request-Id", job.getId().toString())
                .POST(HttpRequest.BodyPublishers.ofString(requestBody))
                .build();
            HttpResponse<byte[]> response = httpClient.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() == 404) {
                throw new ApiException(HttpStatus.NOT_FOUND, "Product was not found");
            }
            if (response.statusCode() == 429 || response.statusCode() >= 500) {
                throw new RetryableTryOnException("PROVIDER_UNAVAILABLE", "Inference provider is unavailable");
            }
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Inference provider rejected the job");
            }
            String contentType = response.headers().firstValue("Content-Type").orElse("");
            if (!contentType.startsWith("image/") || response.body().length == 0 || response.body().length > 20 * 1024 * 1024) {
                throw new ApiException(HttpStatus.UNPROCESSABLE_ENTITY, "Inference provider returned an invalid image");
            }
            return response.body();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new RetryableTryOnException("PROVIDER_UNAVAILABLE", "Inference was interrupted", exception);
        } catch (IOException exception) {
            throw new RetryableTryOnException("PROVIDER_UNAVAILABLE", "Inference provider is unavailable", exception);
        }
    }

    private URI endpoint() {
        String baseUrl = properties.inferenceBaseUrl();
        if (baseUrl == null || baseUrl.isBlank()) {
            throw new IllegalStateException("tryon.inference-base-url must be configured");
        }
        return URI.create(baseUrl.replaceAll("/$", "") + "/internal/try-on/render");
    }

    private record InferenceRequest(UUID job_id, String product_id, Object body_profile) { }

    public static class RetryableTryOnException extends RuntimeException {
        private final String code;

        RetryableTryOnException(String code, String message) {
            super(message);
            this.code = code;
        }

        RetryableTryOnException(String code, String message, Throwable cause) {
            super(message, cause);
            this.code = code;
        }

        public String getCode() { return code; }
    }
}
