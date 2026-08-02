package com.atelier.gateway.wardrobe;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "wardrobe_feedback_events")
public class WardrobeFeedbackEvent {
    @Id
    private UUID id;
    @Column(name = "user_id", nullable = false)
    private UUID userId;
    @Column(name = "task_id", length = 100)
    private String taskId;
    @Column(name = "plan_ref", length = 100)
    private String planRef;
    @Column(name = "item_ref", length = 128)
    private String itemRef;
    @Column(name = "outcome", nullable = false, length = 32)
    private String outcome;
    @Column(name = "fit_feedback", length = 32)
    private String fitFeedback;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected WardrobeFeedbackEvent() { }

    public static WardrobeFeedbackEvent create(UUID userId, WardrobeService.FeedbackInput input) {
        WardrobeFeedbackEvent event = new WardrobeFeedbackEvent();
        event.id = UUID.randomUUID();
        event.userId = userId;
        event.taskId = input.taskId();
        event.planRef = input.planRef();
        event.itemRef = input.itemRef();
        event.outcome = input.outcome();
        event.fitFeedback = input.fitFeedback();
        event.createdAt = Instant.now();
        return event;
    }
}
