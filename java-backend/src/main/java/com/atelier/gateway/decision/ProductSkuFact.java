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

    protected ProductSkuFact() {
    }

    public static ProductSkuFact create(
        String productId, String skuId, String size, BigDecimal chestCm,
        BigDecimal price, Boolean inStock, String returnPolicy, String version
    ) {
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
        return fact;
    }

    public String getProductId() { return productId; }
    public String getSkuId() { return skuId; }
    public String getSize() { return size; }
    public BigDecimal getChestCm() { return chestCm; }
    public BigDecimal getPrice() { return price; }
    public Boolean getInStock() { return inStock; }
    public String getReturnPolicy() { return returnPolicy; }
    public String getVersion() { return version; }
    public Instant getUpdatedAt() { return updatedAt; }
}
