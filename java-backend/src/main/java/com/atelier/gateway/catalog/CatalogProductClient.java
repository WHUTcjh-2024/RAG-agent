package com.atelier.gateway.catalog;

import com.atelier.gateway.common.ApiException;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.math.BigDecimal;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/**
 * Reads the live catalog directly from the Python service. The browser never supplies
 * names, media URLs, or prices used by carts and orders.
 */
@Component
public class CatalogProductClient implements CatalogProductGateway {
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final String upstreamBaseUrl;
    private final Duration requestTimeout;

    public CatalogProductClient(
        ObjectMapper objectMapper,
        @Value("${catalog.upstream-base-url}") String upstreamBaseUrl,
        @Value("${catalog.request-timeout:3s}") Duration requestTimeout
    ) {
        this.objectMapper = objectMapper;
        this.upstreamBaseUrl = normalizeBaseUrl(upstreamBaseUrl);
        this.requestTimeout = requestTimeout;
        this.httpClient = HttpClient.newBuilder().connectTimeout(requestTimeout).build();
    }

    @Override
    public CatalogProductSnapshot fetch(String productId) {
        String requestedId = requireProductId(productId);
        HttpRequest request = HttpRequest.newBuilder(productUri(requestedId))
            .GET()
            .timeout(requestTimeout)
            .header("Accept", "application/json")
            .build();
        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() == HttpStatus.NOT_FOUND.value()) {
                throw new ApiException(HttpStatus.NOT_FOUND, "商品不存在");
            }
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw catalogUnavailable();
            }
            return toSnapshot(requestedId, objectMapper.readValue(response.body(), CatalogProductPayload.class));
        } catch (ApiException exception) {
            throw exception;
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw catalogUnavailable();
        } catch (IOException | IllegalArgumentException exception) {
            throw catalogUnavailable();
        }
    }

    private CatalogProductSnapshot toSnapshot(String requestedId, CatalogProductPayload payload) {
        String productId = normalized(payload.articleId());
        String productName = normalized(payload.productName());
        BigDecimal unitPrice = payload.price();
        if (!requestedId.equals(productId) || productName == null || unitPrice == null || unitPrice.signum() < 0) {
            throw catalogUnavailable();
        }
        return new CatalogProductSnapshot(productId, productName, normalized(payload.imageUrl()), unitPrice);
    }

    private URI productUri(String productId) {
        String encodedId = URLEncoder.encode(productId, StandardCharsets.UTF_8).replace("+", "%20");
        return URI.create(upstreamBaseUrl + "/api/products/" + encodedId);
    }

    private String requireProductId(String value) {
        String productId = normalized(value);
        if (productId == null) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "商品编号不能为空");
        }
        return productId;
    }

    private String normalized(String value) {
        return value == null || value.isBlank() ? null : value.trim();
    }

    private String normalizeBaseUrl(String value) {
        String baseUrl = normalized(value);
        if (baseUrl == null) {
            throw new IllegalArgumentException("catalog.upstream-base-url must be configured");
        }
        return baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
    }

    private ApiException catalogUnavailable() {
        return new ApiException(HttpStatus.BAD_GATEWAY, "商品目录暂不可用");
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    private record CatalogProductPayload(
        @JsonProperty("article_id") String articleId,
        @JsonProperty("prod_name") String productName,
        @JsonProperty("image_url") String imageUrl,
        BigDecimal price
    ) {
    }
}
