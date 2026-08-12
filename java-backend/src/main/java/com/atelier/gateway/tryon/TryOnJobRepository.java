package com.atelier.gateway.tryon;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import jakarta.persistence.LockModeType;

public interface TryOnJobRepository extends JpaRepository<TryOnJob, UUID> {
    Optional<TryOnJob> findByUserIdAndIdempotencyKey(UUID userId, String idempotencyKey);

    Optional<TryOnJob> findByIdAndUserId(UUID id, UUID userId);

    List<TryOnJob> findTop50ByUserIdOrderByCreatedAtDesc(UUID userId);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select job from TryOnJob job where job.id = :id")
    Optional<TryOnJob> findByIdForUpdate(@Param("id") UUID id);

    @Query(value = """
        SELECT id FROM virtual_try_on_jobs
        WHERE status = 'QUEUED' AND available_at <= :now
        ORDER BY created_at ASC
        LIMIT :limit
        """, nativeQuery = true)
    List<UUID> findReadyJobIds(@Param("now") Instant now, @Param("limit") int limit);

    @Query(value = """
        SELECT id FROM virtual_try_on_jobs
        WHERE status = 'PROCESSING' AND updated_at <= :stalledBefore
        ORDER BY updated_at ASC
        LIMIT :limit
        """, nativeQuery = true)
    List<UUID> findStalledJobIds(@Param("stalledBefore") Instant stalledBefore, @Param("limit") int limit);
}
