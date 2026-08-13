package com.atelier.gateway.tryon;

import java.time.Duration;
import java.util.List;
import java.util.UUID;
import org.springframework.data.redis.RedisSystemException;
import org.springframework.data.domain.Range;
import org.springframework.data.redis.connection.stream.Consumer;
import org.springframework.data.redis.connection.stream.MapRecord;
import org.springframework.data.redis.connection.stream.PendingMessage;
import org.springframework.data.redis.connection.stream.ReadOffset;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamOffset;
import org.springframework.data.redis.connection.stream.StreamReadOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.StreamOperations;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

/**
 * Redis Stream consumer group backed by a small Redis set that suppresses duplicate
 * enqueue attempts. PostgreSQL remains the authoritative state machine, so a duplicate
 * delivery can never trigger a second render.
 */
@Component
public class TryOnQueue {
    private static final String STREAM = "fitme:tryon:jobs";
    private static final String PENDING_SET = "fitme:tryon:enqueued";
    private static final String GROUP = "tryon-workers";
    private static final DefaultRedisScript<Long> PUBLISH_IF_ABSENT = new DefaultRedisScript<>("""
        local added = redis.call('SADD', KEYS[2], ARGV[1])
        if added == 1 then
          redis.call('XADD', KEYS[1], '*', 'jobId', ARGV[1])
        end
        return added
        """, Long.class);

    private final StringRedisTemplate redisTemplate;
    private final String consumer = "java-" + UUID.randomUUID();
    private volatile boolean groupReady;

    public TryOnQueue(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    public void publish(UUID jobId) {
        Long added = redisTemplate.execute(PUBLISH_IF_ABSENT, List.of(STREAM, PENDING_SET), jobId.toString());
        if (Long.valueOf(1L).equals(added)) {
            ensureGroup();
        }
    }

    public List<QueueMessage> read(int limit) {
        if (limit < 1 || !Boolean.TRUE.equals(redisTemplate.hasKey(STREAM))) {
            return List.of();
        }
        ensureGroup();
        List<MapRecord<String, String, String>> records = streams().read(
            Consumer.from(GROUP, consumer),
            StreamReadOptions.empty().count(limit),
            StreamOffset.create(STREAM, ReadOffset.lastConsumed())
        );
        return records == null ? List.of() : records.stream().map(this::toMessage).toList();
    }

    public List<QueueMessage> reclaimStale(Duration idleTime, int limit) {
        if (limit < 1 || !Boolean.TRUE.equals(redisTemplate.hasKey(STREAM))) {
            return List.of();
        }
        ensureGroup();
        List<RecordId> staleIds = streams()
            .pending(STREAM, GROUP, Range.unbounded(), limit)
            .stream()
            .filter(message -> message.getElapsedTimeSinceLastDelivery().compareTo(idleTime) >= 0)
            .map(PendingMessage::getId)
            .toList();
        if (staleIds.isEmpty()) {
            return List.of();
        }
        List<MapRecord<String, String, String>> records = streams().claim(
            STREAM, GROUP, consumer, idleTime, staleIds.toArray(RecordId[]::new)
        );
        return records == null ? List.of() : records.stream().map(this::toMessage).toList();
    }

    public void acknowledge(QueueMessage message) {
        streams().acknowledge(STREAM, GROUP, message.recordId());
    }

    public void release(UUID jobId) {
        redisTemplate.opsForSet().remove(PENDING_SET, jobId.toString());
    }

    private QueueMessage toMessage(MapRecord<String, String, String> record) {
        String rawJobId = record.getValue().get("jobId");
        try {
            return new QueueMessage(record.getId(), UUID.fromString(rawJobId));
        } catch (IllegalArgumentException exception) {
            throw new IllegalStateException("Try-on queue contains an invalid job id", exception);
        }
    }

    private void ensureGroup() {
        if (groupReady) {
            return;
        }
        try {
            streams().createGroup(STREAM, ReadOffset.from("0-0"), GROUP);
        } catch (RedisSystemException exception) {
            if (exception.getMessage() == null || !exception.getMessage().contains("BUSYGROUP")) {
                throw exception;
            }
        }
        groupReady = true;
    }

    private StreamOperations<String, String, String> streams() {
        return redisTemplate.opsForStream();
    }

    public record QueueMessage(RecordId recordId, UUID jobId) { }
}
