package com.atelier.gateway.wardrobe;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface WardrobeVersionRepository extends JpaRepository<WardrobeVersion, UUID> { }
