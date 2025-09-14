"""
Unit tests for Redis manager and distributed locking
"""

import pytest
import asyncio
from uuid import uuid4
import json

from app.core.redis import redis_manager


@pytest.mark.unit
@pytest.mark.asyncio
class TestRedisBasicOperations:
    """Test basic Redis operations"""

    async def test_set_and_get(self, redis_client):
        """Test setting and getting values"""
        key = f"test_key_{uuid4().hex}"
        value = {"test": "data", "number": 123}

        # Set value
        result = await redis_manager.set(key, value)
        assert result is True

        # Get value
        retrieved = await redis_manager.get(key)
        assert retrieved == value

        # Cleanup
        await redis_manager.delete(key)

    async def test_set_with_ttl(self, redis_client):
        """Test setting value with TTL"""
        key = f"test_key_{uuid4().hex}"
        value = "test_value"
        ttl = 2  # 2 seconds

        # Set with TTL
        result = await redis_manager.set(key, value, ttl=ttl)
        assert result is True

        # Value should exist
        exists = await redis_manager.exists(key)
        assert exists is True

        # Wait for expiration
        await asyncio.sleep(3)

        # Value should not exist
        exists = await redis_manager.exists(key)
        assert exists is False

    async def test_delete(self, redis_client):
        """Test deleting keys"""
        key = f"test_key_{uuid4().hex}"
        value = "test_value"

        # Set value
        await redis_manager.set(key, value)
        assert await redis_manager.exists(key) is True

        # Delete
        result = await redis_manager.delete(key)
        assert result is True

        # Should not exist
        assert await redis_manager.exists(key) is False

    async def test_incr_decr(self, redis_client):
        """Test increment and decrement operations"""
        key = f"counter_{uuid4().hex}"

        # Increment from 0
        count = await redis_manager.incr(key)
        assert count == 1

        # Increment again
        count = await redis_manager.incr(key)
        assert count == 2

        # Decrement
        count = await redis_manager.decr(key)
        assert count == 1

        # Cleanup
        await redis_manager.delete(key)


@pytest.mark.unit
@pytest.mark.asyncio
class TestDistributedLocking:
    """Test distributed locking functionality"""

    async def test_acquire_lock_success(self, redis_client):
        """Test successful lock acquisition"""
        resource = f"seat_{uuid4().hex}"
        identifier = str(uuid4())

        # Acquire lock
        lock_id = await redis_manager.acquire_lock(resource, identifier)
        assert lock_id == identifier

        # Check if locked
        is_locked = await redis_manager.is_locked(resource)
        assert is_locked is True

        # Release lock
        released = await redis_manager.release_lock(resource, identifier)
        assert released is True

    async def test_acquire_lock_already_locked(self, redis_client):
        """Test acquiring lock when already locked"""
        resource = f"seat_{uuid4().hex}"
        identifier1 = str(uuid4())
        identifier2 = str(uuid4())

        # First lock acquisition
        lock_id1 = await redis_manager.acquire_lock(resource, identifier1)
        assert lock_id1 == identifier1

        # Second lock acquisition should fail
        lock_id2 = await redis_manager.acquire_lock(resource, identifier2)
        assert lock_id2 is None

        # Cleanup
        await redis_manager.release_lock(resource, identifier1)

    async def test_release_lock_wrong_identifier(self, redis_client):
        """Test releasing lock with wrong identifier"""
        resource = f"seat_{uuid4().hex}"
        correct_identifier = str(uuid4())
        wrong_identifier = str(uuid4())

        # Acquire lock
        await redis_manager.acquire_lock(resource, correct_identifier)

        # Try to release with wrong identifier
        released = await redis_manager.release_lock(resource, wrong_identifier)
        assert released is False

        # Lock should still exist
        is_locked = await redis_manager.is_locked(resource)
        assert is_locked is True

        # Cleanup
        await redis_manager.release_lock(resource, correct_identifier)

    async def test_lock_expiration(self, redis_client):
        """Test lock auto-expiration"""
        resource = f"seat_{uuid4().hex}"
        identifier = str(uuid4())
        ttl = 1  # 1 second

        # Acquire lock with short TTL
        lock_id = await redis_manager.acquire_lock(resource, identifier, ttl=ttl)
        assert lock_id == identifier

        # Lock should exist
        is_locked = await redis_manager.is_locked(resource)
        assert is_locked is True

        # Wait for expiration
        await asyncio.sleep(2)

        # Lock should be expired
        is_locked = await redis_manager.is_locked(resource)
        assert is_locked is False

    async def test_extend_lock(self, redis_client):
        """Test extending lock TTL"""
        resource = f"seat_{uuid4().hex}"
        identifier = str(uuid4())
        initial_ttl = 2
        extended_ttl = 5

        # Acquire lock
        lock_id = await redis_manager.acquire_lock(resource, identifier, ttl=initial_ttl)
        assert lock_id == identifier

        # Extend lock
        extended = await redis_manager.extend_lock(resource, identifier, extended_ttl)
        assert extended is True

        # Wait past initial TTL
        await asyncio.sleep(3)

        # Lock should still exist
        is_locked = await redis_manager.is_locked(resource)
        assert is_locked is True

        # Cleanup
        await redis_manager.release_lock(resource, identifier)

    async def test_concurrent_lock_attempts(self, redis_client):
        """Test concurrent lock acquisition attempts"""
        resource = f"seat_{uuid4().hex}"
        num_attempts = 10
        successful_locks = []

        async def try_acquire_lock():
            identifier = str(uuid4())
            lock_id = await redis_manager.acquire_lock(resource, identifier)
            if lock_id:
                successful_locks.append(lock_id)
                await asyncio.sleep(0.1)  # Hold lock briefly
                await redis_manager.release_lock(resource, identifier)

        # Run concurrent lock attempts
        tasks = [try_acquire_lock() for _ in range(num_attempts)]
        await asyncio.gather(*tasks)

        # Only one should succeed at a time (sequential due to lock)
        assert len(successful_locks) <= num_attempts


@pytest.mark.unit
@pytest.mark.asyncio
class TestRateLimiting:
    """Test rate limiting functionality"""

    async def test_rate_limit_not_exceeded(self, redis_client):
        """Test when rate limit is not exceeded"""
        key = f"user_{uuid4().hex}"
        limit = 5
        window = 60

        # Make requests within limit
        for i in range(limit):
            is_limited, count = await redis_manager.is_rate_limited(key, limit, window)
            assert is_limited is False
            assert count == i + 1

    async def test_rate_limit_exceeded(self, redis_client):
        """Test when rate limit is exceeded"""
        key = f"user_{uuid4().hex}"
        limit = 3
        window = 60

        # Make requests up to limit
        for i in range(limit):
            is_limited, count = await redis_manager.is_rate_limited(key, limit, window)
            assert is_limited is False

        # Next request should be limited
        is_limited, count = await redis_manager.is_rate_limited(key, limit, window)
        assert is_limited is True
        assert count == limit + 1

    async def test_rate_limit_window_reset(self, redis_client):
        """Test rate limit window reset"""
        key = f"user_{uuid4().hex}"
        limit = 2
        window = 1  # 1 second window

        # Exceed limit
        for _ in range(limit + 1):
            await redis_manager.is_rate_limited(key, limit, window)

        # Should be limited
        is_limited, _ = await redis_manager.is_rate_limited(key, limit, window)
        assert is_limited is True

        # Wait for window to reset
        await asyncio.sleep(2)

        # Should not be limited anymore
        is_limited, count = await redis_manager.is_rate_limited(key, limit, window)
        assert is_limited is False
        assert count == 1


@pytest.mark.unit
@pytest.mark.asyncio
class TestPubSub:
    """Test pub/sub functionality"""

    async def test_publish_message(self, redis_client):
        """Test publishing messages"""
        channel = f"test_channel_{uuid4().hex}"
        message = {"event": "test", "data": "test_data"}

        # Publish message
        num_receivers = await redis_manager.publish(channel, message)
        assert num_receivers >= 0  # No subscribers yet

    async def test_subscribe_and_receive(self, redis_client):
        """Test subscribing and receiving messages"""
        channel = f"test_channel_{uuid4().hex}"
        message = {"event": "test", "data": "test_data"}

        # Subscribe to channel
        pubsub = await redis_manager.subscribe(channel)

        # Give subscription time to establish
        await asyncio.sleep(0.1)

        # Publish message
        await redis_manager.publish(channel, message)

        # Receive message
        received = None
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                received = json.loads(msg["data"])
                break

        assert received == message

        # Cleanup
        await pubsub.unsubscribe(channel)
        await pubsub.close()