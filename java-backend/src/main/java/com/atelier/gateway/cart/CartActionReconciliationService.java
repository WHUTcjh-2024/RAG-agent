package com.atelier.gateway.cart;

import java.time.Duration;
import java.time.Instant;
import java.util.List;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** Reconciles durable Agent action commits against the actual cart state. */
@Service
public class CartActionReconciliationService {
    private static final int BATCH_SIZE = 100;
    private static final Duration RECHECK_INTERVAL = Duration.ofMinutes(5);

    private final AgentCartActionCommitRepository actionCommitRepository;
    private final CartItemRepository cartItemRepository;

    public CartActionReconciliationService(
        AgentCartActionCommitRepository actionCommitRepository,
        CartItemRepository cartItemRepository
    ) {
        this.actionCommitRepository = actionCommitRepository;
        this.cartItemRepository = cartItemRepository;
    }

    @Scheduled(fixedDelayString = "${cart.reconciliation-interval-ms:60000}")
    @Transactional
    public void reconcileDueActions() {
        Instant staleBefore = Instant.now().minus(RECHECK_INTERVAL);
        List<AgentCartActionCommit> commits = actionCommitRepository.findReconciliationCandidates(
            staleBefore,
            PageRequest.of(0, BATCH_SIZE)
        );
        commits.forEach(this::reconcile);
    }

    @Transactional
    public AgentCartActionCommit reconcileAction(String actionId) {
        AgentCartActionCommit commit = actionCommitRepository.findById(actionId)
            .orElseThrow(() -> new IllegalArgumentException("Agent action commit was not found"));
        reconcile(commit);
        return commit;
    }

    private void reconcile(AgentCartActionCommit commit) {
        CartItem item = commit.getCartItemId() == null
            ? null
            : cartItemRepository.findById(commit.getCartItemId()).orElse(null);
        commit.reconcile(item);
    }
}
