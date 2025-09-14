"""
Redis configuration and connection management
"""

import redis.asyncio as redis
from typing import Optional, Any
import json
import logging
import asyncio
import time  # CRITICAL FIX: Import time module at top level
from datetime import timedelta
import uuid

from app.config import settings

logger = logging.getLogger(__name__)

# Global Redis client
redis_client: Optional[redis.Redis] = None


async def init_redis():
    """
    Initialize Redis connection
    """
    global redis_client
    try:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True
        )
        # Test connection
        await redis_client.ping()
        logger.info("Redis connection established")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        raise


async def close_redis():
    """
    Close Redis connection
    """
    global redis_client
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")


async def get_redis() -> redis.Redis:
    """
    Get Redis client
    """
    if not redis_client:
        await init_redis()
    return redis_client


class CircuitBreaker:
    """
    Thread-safe circuit breaker pattern for Redis operations
    """
    def __init__(self, failure_threshold=5, recovery_timeout=60, half_open_max_calls=3):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.half_open_calls = 0

        # Add asyncio lock for thread safety
        self._lock = asyncio.Lock()

    async def is_open(self) -> bool:
        async with self._lock:
            if self.state == "OPEN":
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.half_open_calls = 0
                    return False
                return True
            return False

    async def record_success(self):
        async with self._lock:
            self.failure_count = 0
            self.half_open_calls = 0  # Reset half-open counter
            self.state = "CLOSED"

    async def record_failure(self):
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            self.half_open_calls = 0  # Reset half-open counter on failure

            if self.state == "HALF_OPEN" or self.failure_count >= self.failure_threshold:
                self.state = "OPEN"

    async def call(self, func, *args, **kwargs):
        if await self.is_open():
            raise Exception("Circuit breaker is open")

        # Check half-open state with proper locking
        async with self._lock:
            if self.state == "HALF_OPEN":
                if self.half_open_calls >= self.half_open_max_calls:
                    raise Exception("Half-open call limit exceeded")
                self.half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            await self.record_success()
            return result
        except Exception as e:
            await self.record_failure()
            raise


class RedisManager:
    """
    Production-ready Redis manager with circuit breaker and seat reservation
    """

    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self.circuit_breaker = CircuitBreaker()
        self.logger = logging.getLogger(__name__)

    async def get_client(self) -> redis.Redis:
        """Get Redis client with health check and circuit breaker"""
        if not self.client:
            self.client = await get_redis()

        # Health check with circuit breaker protection
        try:
            await self.circuit_breaker.call(self.client.ping)
        except Exception as e:
            self.logger.warning(f"Redis connection unhealthy, attempting reconnect: {e}")
            try:
                if self.client:
                    await asyncio.wait_for(self.client.close(), timeout=1.0)
            except asyncio.TimeoutError:
                self.logger.warning("Redis connection close timed out")
            except Exception:
                pass

            self.client = await get_redis()
            await self.circuit_breaker.call(self.client.ping)

        return self.client

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        client = await self.get_client()
        value = await client.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None
    ) -> bool:
        """Set value in cache with optional TTL"""
        client = await self.get_client()
        if not isinstance(value, str):
            value = json.dumps(value)

        if ttl:
            return await client.setex(key, ttl, value)
        return await client.set(key, value)

    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        client = await self.get_client()
        return await client.delete(key) > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists"""
        client = await self.get_client()
        return await client.exists(key) > 0

    async def expire(self, key: str, ttl: int) -> bool:
        """Set expiration for key"""
        client = await self.get_client()
        return await client.expire(key, ttl)

    async def incr(self, key: str) -> int:
        """Increment counter"""
        client = await self.get_client()
        return await client.incr(key)

    async def decr(self, key: str) -> int:
        """Decrement counter"""
        client = await self.get_client()
        return await client.decr(key)

    # Distributed locking methods with Lua scripts for atomicity
    async def acquire_lock(
        self,
        resource: str,
        identifier: Optional[str] = None,
        ttl: int = 300
    ) -> Optional[str]:
        """
        Acquire a distributed lock using atomic Lua script

        Args:
            resource: Resource to lock (e.g., "seat:123")
            identifier: Unique identifier for lock owner
            ttl: Time to live in seconds

        Returns:
            Lock identifier if successful, None otherwise
        """
        client = await self.get_client()
        lock_key = f"lock:{resource}"
        lock_value = identifier or str(uuid.uuid4())

        # Lua script for atomic lock acquisition with metadata
        lua_script = """
        local lock_key = KEYS[1]
        local lock_value = ARGV[1]
        local ttl = tonumber(ARGV[2])
        local timestamp = ARGV[3]

        -- Try to acquire lock
        if redis.call("set", lock_key, lock_value, "NX", "EX", ttl) then
            -- Set metadata for lock debugging
            local meta_key = lock_key .. ":meta"
            redis.call("hset", meta_key, "owner", lock_value, "acquired_at", timestamp, "ttl", ttl)
            redis.call("expire", meta_key, ttl)
            return lock_value
        else
            return nil
        end
        """

        try:
            timestamp = str(int(time.time()))
            result = await client.eval(
                lua_script,
                1,
                lock_key,
                lock_value,
                ttl,
                timestamp
            )

            if result:
                logger.debug(f"Lock acquired for {resource} with identifier {lock_value}")
                return result.decode() if isinstance(result, bytes) else result
            return None
        except Exception as e:
            logger.error(f"Error acquiring lock for {resource}: {e}")
            return None

    async def release_lock(
        self,
        resource: str,
        identifier: str
    ) -> bool:
        """
        Release a distributed lock using atomic Lua script

        Args:
            resource: Resource to unlock
            identifier: Lock owner identifier

        Returns:
            True if lock was released, False otherwise
        """
        client = await self.get_client()
        lock_key = f"lock:{resource}"

        # Enhanced Lua script for atomic lock release with cleanup
        lua_script = """
        local lock_key = KEYS[1]
        local identifier = ARGV[1]
        local meta_key = lock_key .. ":meta"

        -- Check if lock exists and belongs to the identifier
        local current_owner = redis.call("get", lock_key)
        if current_owner == identifier then
            -- Release lock and cleanup metadata
            redis.call("del", lock_key)
            redis.call("del", meta_key)
            return 1
        else
            return 0
        end
        """

        try:
            result = await client.eval(lua_script, 1, lock_key, identifier)
            released = result == 1

            if released:
                logger.debug(f"Lock released for {resource}")
            else:
                logger.warning(f"Failed to release lock for {resource} - wrong identifier or lock not found")

            return released
        except Exception as e:
            logger.error(f"Error releasing lock for {resource}: {e}")
            return False

    async def extend_lock(
        self,
        resource: str,
        identifier: str,
        ttl: int
    ) -> bool:
        """
        Extend a distributed lock's TTL using atomic Lua script

        Args:
            resource: Resource to extend lock for
            identifier: Lock owner identifier
            ttl: New TTL in seconds

        Returns:
            True if lock was extended, False otherwise
        """
        client = await self.get_client()
        lock_key = f"lock:{resource}"

        # Enhanced Lua script for atomic lock extension with metadata update
        lua_script = """
        local lock_key = KEYS[1]
        local identifier = ARGV[1]
        local ttl = tonumber(ARGV[2])
        local timestamp = ARGV[3]
        local meta_key = lock_key .. ":meta"

        -- Check if lock exists and belongs to the identifier
        if redis.call("get", lock_key) == identifier then
            -- Extend lock TTL
            redis.call("expire", lock_key, ttl)
            -- Update metadata
            redis.call("hset", meta_key, "extended_at", timestamp, "ttl", ttl)
            redis.call("expire", meta_key, ttl)
            return 1
        else
            return 0
        end
        """

        try:
            timestamp = str(int(time.time()))
            result = await client.eval(lua_script, 1, lock_key, identifier, ttl, timestamp)
            return result == 1
        except Exception as e:
            logger.error(f"Error extending lock for {resource}: {e}")
            return False

    async def is_locked(self, resource: str) -> bool:
        """Check if resource is locked"""
        lock_key = f"lock:{resource}"
        return await self.exists(lock_key)

    # Pub/Sub methods for real-time updates
    async def publish(self, channel: str, message: Any) -> int:
        """Publish message to channel"""
        client = await self.get_client()
        if not isinstance(message, str):
            message = json.dumps(message)
        return await client.publish(channel, message)

    async def subscribe(self, *channels):
        """Subscribe to channels"""
        client = await self.get_client()
        pubsub = client.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub

    async def get_lock_info(self, resource: str) -> Optional[dict]:
        """
        Get information about a lock for debugging
        """
        client = await self.get_client()
        lock_key = f"lock:{resource}"
        meta_key = f"{lock_key}:meta"

        try:
            lock_value = await client.get(lock_key)
            if not lock_value:
                return None

            metadata = await client.hgetall(meta_key)
            ttl = await client.ttl(lock_key)

            return {
                "resource": resource,
                "owner": lock_value,
                "ttl": ttl,
                "metadata": metadata
            }
        except Exception as e:
            logger.error(f"Error getting lock info for {resource}: {e}")
            return None

    async def cleanup_expired_locks(self, pattern: str = "lock:*") -> int:
        """
        Clean up any orphaned lock metadata
        Returns number of cleaned up locks
        """
        client = await self.get_client()
        cleaned = 0

        try:
            # Find all lock metadata keys
            meta_keys = await client.keys(f"{pattern}:meta")

            for meta_key in meta_keys:
                # Check if corresponding lock still exists
                lock_key = meta_key.replace(":meta", "")
                if not await client.exists(lock_key):
                    await client.delete(meta_key)
                    cleaned += 1
                    logger.debug(f"Cleaned up orphaned lock metadata: {meta_key}")

            return cleaned
        except Exception as e:
            logger.error(f"Error cleaning up expired locks: {e}")
            return 0

    # Seat reservation methods for booking system
    async def reserve_seats(
        self,
        event_id: str,
        seat_ids: list[str],
        user_id: str,
        ttl: int = 600  # 10 minutes
    ) -> tuple[bool, list[str]]:
        """
        Reserve multiple seats atomically with TTL
        Returns (success, failed_seat_ids)
        """
        client = await self.get_client()

        # Sort seat IDs to prevent deadlocks
        sorted_seat_ids = sorted(seat_ids)

        # Lua script for atomic multi-seat reservation
        # Based on Redis documentation: Lua scripts are atomic but cannot rollback
        # We use all-or-nothing approach: either all seats are available or none are reserved
        lua_script = """
        local event_id = ARGV[1]
        local user_id = ARGV[2]
        local ttl = tonumber(ARGV[3])
        local timestamp = ARGV[4]

        local keys_to_check = {}
        local keys_to_set = {}
        local meta_keys = {}

        -- Prepare all keys first
        for i = 5, #ARGV do
            local seat_id = ARGV[i]
            local key = "seat:reserved:" .. event_id .. ":" .. seat_id
            local meta_key = key .. ":meta"

            table.insert(keys_to_check, key)
            table.insert(keys_to_set, key)
            table.insert(meta_keys, meta_key)
        end

        -- Check if ALL seats are available first (no partial operations)
        local failed_seats = {}
        for i = 1, #keys_to_check do
            if redis.call("EXISTS", keys_to_check[i]) == 1 then
                -- This specific seat is taken
                local seat_id = ARGV[i + 4]  -- Map back to seat ID
                table.insert(failed_seats, seat_id)
            end
        end

        -- If ANY seats are unavailable, return the specific failed ones
        if #failed_seats > 0 then
            return {0, failed_seats}
        end

        -- All seats are available, reserve them atomically
        local reserved_seats = {}
        for i = 1, #keys_to_set do
            local seat_id = ARGV[i + 4]  -- Adjust index
            local key = keys_to_set[i]
            local meta_key = meta_keys[i]

            -- Set reservation
            redis.call("SET", key, user_id, "EX", ttl)
            -- Set metadata
            redis.call("HSET", meta_key, "user_id", user_id, "reserved_at", timestamp, "event_id", event_id)
            redis.call("EXPIRE", meta_key, ttl)

            table.insert(reserved_seats, seat_id)
        end

        return {1, reserved_seats}
        """

        try:
            timestamp = str(int(time.time()))
            args = [event_id, user_id, ttl, timestamp] + sorted_seat_ids

            result = await self.circuit_breaker.call(
                client.eval, lua_script, 0, *args
            )

            success = bool(result[0])
            seats = result[1]

            if success:
                self.logger.info(f"Reserved {len(seats)} seats for user {user_id} in event {event_id}")
                return True, []
            else:
                self.logger.warning(f"Failed to reserve seats {seats} for user {user_id}")
                return False, seats

        except Exception as e:
            self.logger.error(f"Error reserving seats: {e}")
            return False, seat_ids

    async def verify_seat_reservation(
        self,
        event_id: str,
        seat_ids: list[str],
        user_id: str
    ) -> bool:
        """
        Verify that seats are reserved by the specific user
        """
        client = await self.get_client()

        try:
            pipeline = client.pipeline()
            for seat_id in seat_ids:
                key = f"seat:reserved:{event_id}:{seat_id}"
                pipeline.get(key)

            results = await self.circuit_breaker.call(pipeline.execute)

            # All seats must be reserved by this user
            return all(result == user_id for result in results)

        except Exception as e:
            self.logger.error(f"Error verifying seat reservation: {e}")
            return False

    async def release_seat_reservations(
        self,
        event_id: str,
        seat_ids: list[str],
        user_id: str
    ) -> bool:
        """
        Release seat reservations for specific user
        """
        client = await self.get_client()

        lua_script = """
        local event_id = ARGV[1]
        local user_id = ARGV[2]
        local released_count = 0

        for i = 3, #ARGV do
            local seat_id = ARGV[i]
            local key = "seat:reserved:" .. event_id .. ":" .. seat_id
            local meta_key = key .. ":meta"

            -- Only release if reserved by this user
            local current_user = redis.call("GET", key)
            if current_user == user_id then
                redis.call("DEL", key, meta_key)
                released_count = released_count + 1
            end
        end

        return released_count
        """

        try:
            args = [event_id, user_id] + seat_ids
            released = await self.circuit_breaker.call(
                client.eval, lua_script, 0, *args
            )

            self.logger.info(f"Released {released} seat reservations for user {user_id}")
            return released == len(seat_ids)

        except Exception as e:
            self.logger.error(f"Error releasing seat reservations: {e}")
            return False

    async def extend_seat_reservations(
        self,
        event_id: str,
        seat_ids: list[str],
        user_id: str,
        ttl: int = 600
    ) -> bool:
        """
        Extend TTL for seat reservations
        """
        client = await self.get_client()

        try:
            pipeline = client.pipeline()
            for seat_id in seat_ids:
                key = f"seat:reserved:{event_id}:{seat_id}"
                meta_key = f"{key}:meta"

                # Only extend if reserved by this user
                pipeline.eval(
                    "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('EXPIRE', KEYS[1], ARGV[2]) else return 0 end",
                    1, key, user_id, ttl
                )
                pipeline.expire(meta_key, ttl)

            results = await self.circuit_breaker.call(pipeline.execute)

            # Check if all seats were extended successfully
            extended_count = sum(1 for i in range(0, len(results), 2) if results[i])
            return extended_count == len(seat_ids)

        except Exception as e:
            self.logger.error(f"Error extending seat reservations: {e}")
            return False

    # Rate limiting methods
    async def is_rate_limited(
        self,
        key: str,
        limit: int,
        window: int = 60
    ) -> tuple[bool, int]:
        """
        Check if rate limit is exceeded using atomic Lua script

        Args:
            key: Rate limit key (e.g., "user:123:bookings")
            limit: Maximum number of requests
            window: Time window in seconds

        Returns:
            Tuple of (is_limited, current_count)
        """
        client = await self.get_client()
        rate_key = f"rate:{key}"

        # Atomic Lua script for sliding window rate limiting
        lua_script = """
        local rate_key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local timestamp = tonumber(ARGV[3])
        local unique_id = ARGV[4]

        local window_start = timestamp - (window * 1000)

        -- Remove old entries
        redis.call("zremrangebyscore", rate_key, 0, window_start)

        -- Get current count
        local current_count = redis.call("zcard", rate_key)

        -- Check if we can add new request
        if current_count < limit then
            -- Add current request
            redis.call("zadd", rate_key, timestamp, unique_id)
            -- Set expiry
            redis.call("expire", rate_key, window + 1)
            return {0, current_count + 1}  -- not limited, new count
        else
            return {1, current_count}  -- limited, current count
        end
        """

        try:
            result = await self.circuit_breaker.call(
                self._execute_rate_limit_script,
                client, lua_script, rate_key, limit, window
            )

            is_limited = bool(result[0])
            current_count = int(result[1])

            return is_limited, current_count
        except Exception as e:
            self.logger.error(f"Error checking rate limit for {key}: {e}")
            return False, 0  # Fail open for rate limiting

    async def _execute_rate_limit_script(self, client, lua_script, rate_key, limit, window):
        """Helper method for rate limiting script execution"""
        now = await client.time()
        timestamp = now[0] * 1000 + now[1] // 1000
        unique_id = str(uuid.uuid4())

        return await client.eval(
            lua_script,
            1,
            rate_key,
            limit,
            window,
            timestamp,
            unique_id
        )


# Create global Redis manager
redis_manager = RedisManager()

# Add time import for circuit breaker
import time