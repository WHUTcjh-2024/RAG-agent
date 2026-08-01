package com.atelier.gateway.decision;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface BodyProfileRepository extends JpaRepository<BodyProfile, UUID> {
}
