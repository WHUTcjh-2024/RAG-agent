package com.atelier.gateway.decision;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "product_sku_facts")
public class ProductSkuFact {
    @Id
    @Column(name = "product_id")
    private String productId;
    @Column(name = "sku_id", nullable = false)
    private String skuId;
    @Column(name = "product_name")
    private String productName;
    @Column(name = "product_image_url")
    private String productImageUrl;
    @Column(name = "size")
    private String size;
    @Column(name = "chest_cm", precision = 6, scale = 2)
    private BigDecimal chestCm;
    @Column(name = "price", precision = 19, scale = 2)
    private BigDecimal price;
    @Column(name = "in_stock")
    private Boolean inStock;
    @Column(name = "return_policy")
    private String returnPolicy;
    @Column(name = "version", nullable = false)
    private String version;
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;
    @Column(name = "source_kind", nullable = false)
    private String sourceKind;
    @Column(name = "source_reference", nullable = false)
    private String sourceReference;
    @Column(name = "source_confidence", nullable = false, precision = 3, scale = 2)
    private BigDecimal sourceConfidence;

    protected ProductSkuFact() {
    }

    public static ProductSkuFact create(
        String productId, String skuId, String size, BigDecimal chestCm,
        BigDecimal price, Boolean inStock, String returnPolicy, String version
    ) {
        return create(
            productId, skuId, size, chestCm, price, inStock, returnPolicy, version,
            "MERCHANT_FEED", "catalog:" + productId, new BigDecimal("0.95")
        );
    }

    public static ProductSkuFact create(
        String productId, String skuId, String size, BigDecimal chestCm,
        BigDecimal price, Boolean inStock, String returnPolicy, String version,
        String sourceKind, String sourceReference, BigDecimal sourceConfidence
    ) {
        if (sourceKind == null || sourceKind.isBlank()) {
            throw new IllegalArgumentException("sourceKind is required");
        }
        if (sourceReference == null || sourceReference.isBlank()) {
            throw new IllegalArgumentException("sourceReference is required");
        }
        if (sourceConfidence == null || sourceConfidence.compareTo(BigDecimal.ZERO) < 0
            || sourceConfidence.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("sourceConfidence must be between 0 and 1");
        }
        ProductSkuFact fact = new ProductSkuFact();
        fact.productId = productId;
        fact.skuId = skuId;
        fact.size = size;
        fact.chestCm = chestCm;
        fact.price = price;
        fact.inStock = inStock;
        fact.returnPolicy = returnPolicy;
        fact.version = version;
        fact.updatedAt = Instant.now();
        fact.sourceKind = sourceKind.trim();
        fact.sourceReference = sourceReference.trim();
        fact.sourceConfidence = sourceConfidence;
        return fact;
    }

    public String getProductId() { return productId; }
    public String getSkuId() { return skuId; }
    public String getProductName() { return productName; }
    public String getProductImageUrl() { return productImageUrl; }
    public String getSize() { return size; }
    public BigDecimal getChestCm() { return chestCm; }
    public BigDecimal getPrice() { return price; }
    public Boolean getInStock() { return inStock; }
    public String getReturnPolicy() { return returnPolicy; }
    public String getVersion() { return version; }
    public Instant getUpdatedAt() { return updatedAt; }
    public String getSourceKind() { return sourceKind; }
    public String getSourceReference() { return sourceReference; }
    public BigDecimal getSourceConfidence() { return sourceConfidence; }
}
