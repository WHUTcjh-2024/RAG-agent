package com.atelier.gateway.tryon;

import com.atelier.gateway.common.ApiException;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Instant;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

@Component
public class TryOnResultSigner {
    private static final long URL_TTL_SECONDS = 15 * 60;
    private static final String HMAC_ALGORITHM = "HmacSHA256";

    private final TryOnProperties properties;

    public TryOnResultSigner(TryOnProperties properties) {
        this.properties = properties;
    }

    public String url(TryOnJob job) {
        if (job.getStatus() != TryOnStatus.SUCCEEDED || job.getOutputKey() == null) {
            throw new ApiException(HttpStatus.NOT_FOUND, "Try-on result was not found");
        }
        long expires = Instant.now().plusSeconds(URL_TTL_SECONDS).getEpochSecond();
        return "/api/try-on/jobs/" + job.getId() + "/result?expires=" + expires + "&signature=" + sign(job, expires);
    }

    public boolean verify(TryOnJob job, long expires, String suppliedSignature) {
        if (expires < Instant.now().getEpochSecond() || suppliedSignature == null || job.getOutputKey() == null) {
            return false;
        }
        return MessageDigest.isEqual(
            sign(job, expires).getBytes(StandardCharsets.US_ASCII),
            suppliedSignature.getBytes(StandardCharsets.US_ASCII)
        );
    }

    private String sign(TryOnJob job, long expires) {
        try {
            Mac mac = Mac.getInstance(HMAC_ALGORITHM);
            mac.init(new SecretKeySpec(properties.resultSigningSecret().getBytes(StandardCharsets.UTF_8), HMAC_ALGORITHM));
            String payload = job.getId() + "\n" + job.getUserId() + "\n" + job.getOutputKey() + "\n" + expires;
            return java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(
                mac.doFinal(payload.getBytes(StandardCharsets.UTF_8))
            );
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("Cannot sign try-on result URL", exception);
        }
    }
}
