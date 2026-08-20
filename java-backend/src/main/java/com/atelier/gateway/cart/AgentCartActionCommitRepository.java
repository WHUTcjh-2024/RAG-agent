package com.atelier.gateway.cart;

import java.time.Instant;
import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AgentCartActionCommitRepository extends JpaRepository<AgentCartActionCommit, String> {
    @Query("""
        select actionCommit from AgentCartActionCommit actionCommit
        where actionCommit.reconciledAt is null or actionCommit.reconciledAt < :staleBefore
        order by case when actionCommit.reconciledAt is null then 0 else 1 end, actionCommit.reconciledAt asc
        """)
    List<AgentCartActionCommit> findReconciliationCandidates(
        @Param("staleBefore") Instant staleBefore,
        Pageable pageable
    );
}
