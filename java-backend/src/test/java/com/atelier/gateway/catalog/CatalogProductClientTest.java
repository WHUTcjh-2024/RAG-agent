package com.atelier.gateway.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.atelier.gateway.common.ApiException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class CatalogProductClientTest {
    @Test
    void fetchesTheCatalogSnapshotAndIgnoresUnknownFields() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse().setBody("""
                {"article_id":"sku-001","prod_name":"Server Coat","image_url":"/media/coat.png","price":129.99,"ignored":"value"}
                """).addHeader("Content-Type", "application/json"));
            server.start();

            CatalogProductSnapshot snapshot = client(server).fetch("sku-001");

            assertThat(snapshot.productId()).isEqualTo("sku-001");
            assertThat(snapshot.productName()).isEqualTo("Server Coat");
            assertThat(snapshot.productImageUrl()).isEqualTo("/media/coat.png");
            assertThat(snapshot.unitPrice()).isEqualByComparingTo("129.99");
            assertThat(server.takeRequest().getPath()).isEqualTo("/api/products/sku-001");
        }
    }

    @Test
    void mapsNotFoundAndMalformedCatalogResponsesToSafeApiErrors() throws Exception {
        try (MockWebServer server = new MockWebServer()) {
            server.enqueue(new MockResponse().setResponseCode(404));
            server.enqueue(new MockResponse().setBody("{" + "\"article_id\":\"sku-001\"}"));
            server.start();
            CatalogProductClient client = client(server);

            assertThatThrownBy(() -> client.fetch("missing-sku"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.getStatus()).isEqualTo(HttpStatus.NOT_FOUND);
                    assertThat(error.getMessage()).isEqualTo("商品不存在");
                });
            assertThatThrownBy(() -> client.fetch("sku-001"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.getStatus()).isEqualTo(HttpStatus.BAD_GATEWAY);
                    assertThat(error.getMessage()).isEqualTo("商品目录暂不可用");
                });
        }
    }

    private CatalogProductClient client(MockWebServer server) {
        return new CatalogProductClient(new ObjectMapper(), server.url("/").toString(), Duration.ofSeconds(1));
    }
}
