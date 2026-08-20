package com.atelier.gateway.tryon;

import java.util.List;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TryOnJobEventRepository extends JpaRepository<TryOnJobEvent, UUID> {
    List<TryOnJobEvent> findByJobIdOrderByCreatedAtAsc(UUID jobId);
}
