"""
Production-grade cache management with validation and invalidation
"""

import json
import logging
import hashlib
from typing import Any, Optional, List, Dict, Type, Union
from datetime import datetime, timezone
from pydantic import BaseModel, ValidationError

from app.core.redis import get_redis
from app.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Production-ready cache manager with validation and invalidation
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Cache version for invalidation coordination
        self.cache_version = "v1.0"

    def _generate_cache_key(self, prefix: str, params: Dict[str, Any]) -> str:
        """
        Generate consistent cache key with version and parameter hash
        """
        # Sort parameters for consistent key generation
        param_str = json.dumps(params, sort_keys=True, default=str)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        return f"{self.cache_version}:{prefix}:{param_hash}"

    def _generate_invalidation_pattern(self, prefix: str) -> str:
        """
        Generate pattern for cache invalidation
        """
        return f"{self.cache_version}:{prefix}:*"

    async def get_validated_cache(
        self,
        cache_key: str,
        response_model: Type[BaseModel],
        is_list: bool = False
    ) -> Optional[Union[BaseModel, List[BaseModel]]]:
        """
        Get cached data with strict Pydantic validation
        """
        try:
            redis_client = await get_redis()
            cached_data = await redis_client.get(cache_key)

            if not cached_data:
                return None

            # Parse JSON safely
            try:
                parsed_data = json.loads(cached_data)
            except json.JSONDecodeError as e:
                self.logger.warning(f"Invalid JSON in cache key {cache_key}: {e}")
                # Remove corrupted cache entry
                await redis_client.delete(cache_key)
                return None

            # Validate structure
            if is_list:
                if not isinstance(parsed_data, list):
                    self.logger.warning(f"Expected list in cache key {cache_key}, got {type(parsed_data)}")
                    await redis_client.delete(cache_key)
                    return None

                # Validate each item in list
                validated_items = []
                for i, item in enumerate(parsed_data):
                    try:
                        validated_item = response_model(**item)
                        validated_items.append(validated_item)
                    except ValidationError as e:
                        self.logger.warning(f"Validation failed for item {i} in cache key {cache_key}: {e}")
                        # Remove corrupted cache entry
                        await redis_client.delete(cache_key)
                        return None

                return validated_items
            else:
                # Validate single item
                try:
                    return response_model(**parsed_data)
                except ValidationError as e:
                    self.logger.warning(f"Validation failed for cache key {cache_key}: {e}")
                    # Remove corrupted cache entry
                    await redis_client.delete(cache_key)
                    return None

        except Exception as e:
            self.logger.error(f"Error retrieving cache for key {cache_key}: {e}")
            return None

    async def set_validated_cache(
        self,
        cache_key: str,
        data: Union[BaseModel, List[BaseModel]],
        ttl: int = 300
    ) -> bool:
        """
        Set cache data with validation and metadata
        """
        try:
            redis_client = await get_redis()

            # Serialize with validation
            if isinstance(data, list):
                # Validate each item has dict() method (Pydantic models)
                serialized_data = []
                for item in data:
                    if hasattr(item, 'model_dump'):
                        serialized_data.append(item.model_dump())
                    elif hasattr(item, 'dict'):
                        serialized_data.append(item.dict())
                    else:
                        raise ValueError(f"Item {item} is not a valid Pydantic model")
            else:
                if hasattr(data, 'model_dump'):
                    serialized_data = data.model_dump()
                elif hasattr(data, 'dict'):
                    serialized_data = data.dict()
                else:
                    raise ValueError(f"Data {data} is not a valid Pydantic model")

            # Add cache metadata
            cache_entry = {
                "data": serialized_data,
                "cached_at": datetime.now(timezone.utc).isoformat(),
                "version": self.cache_version,
                "ttl": ttl
            }

            # Store with TTL
            await redis_client.setex(
                cache_key,
                ttl,
                json.dumps(cache_entry, default=str)
            )

            self.logger.debug(f"Cache set for key {cache_key} with TTL {ttl}")
            return True

        except Exception as e:
            self.logger.error(f"Error setting cache for key {cache_key}: {e}")
            return False

    async def get_cache_data_only(
        self,
        cache_key: str,
        response_model: Type[BaseModel],
        is_list: bool = False
    ) -> Optional[Union[BaseModel, List[BaseModel]]]:
        """
        Get cache data from structured cache entry
        """
        try:
            redis_client = await get_redis()
            cached_entry = await redis_client.get(cache_key)

            if not cached_entry:
                return None

            # Parse cache entry
            try:
                cache_entry = json.loads(cached_entry)
            except json.JSONDecodeError:
                # Remove corrupted cache
                await redis_client.delete(cache_key)
                return None

            # Validate cache entry structure
            if not isinstance(cache_entry, dict) or "data" not in cache_entry:
                await redis_client.delete(cache_key)
                return None

            # Check cache version
            if cache_entry.get("version") != self.cache_version:
                self.logger.info(f"Cache version mismatch for key {cache_key}, invalidating")
                await redis_client.delete(cache_key)
                return None

            cached_data = cache_entry["data"]

            # Validate and return data
            if is_list:
                if not isinstance(cached_data, list):
                    await redis_client.delete(cache_key)
                    return None

                validated_items = []
                for item in cached_data:
                    try:
                        validated_items.append(response_model(**item))
                    except ValidationError:
                        await redis_client.delete(cache_key)
                        return None

                return validated_items
            else:
                try:
                    return response_model(**cached_data)
                except ValidationError:
                    await redis_client.delete(cache_key)
                    return None

        except Exception as e:
            self.logger.error(f"Error retrieving structured cache for key {cache_key}: {e}")
            return None

    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all cache keys matching pattern
        Returns number of keys deleted
        """
        try:
            redis_client = await get_redis()
            keys = await redis_client.keys(pattern)

            if keys:
                deleted_count = await redis_client.delete(*keys)
                self.logger.info(f"Invalidated {deleted_count} cache keys matching pattern: {pattern}")
                return deleted_count

            return 0

        except Exception as e:
            self.logger.error(f"Error invalidating cache pattern {pattern}: {e}")
            return 0

    async def invalidate_events_cache(self) -> int:
        """
        Invalidate all event-related cache
        """
        patterns = [
            f"{self.cache_version}:events:*",
            f"{self.cache_version}:event_detail:*",
            f"{self.cache_version}:event_seats:*"
        ]

        total_deleted = 0
        for pattern in patterns:
            deleted = await self.invalidate_pattern(pattern)
            total_deleted += deleted

        return total_deleted

    async def invalidate_event_cache(self, event_id: str) -> int:
        """
        Invalidate cache for specific event
        """
        patterns = [
            f"{self.cache_version}:event_detail:*{event_id}*",
            f"{self.cache_version}:event_seats:*{event_id}*",
            # Also invalidate general events list since it might contain this event
            f"{self.cache_version}:events:*"
        ]

        total_deleted = 0
        for pattern in patterns:
            deleted = await self.invalidate_pattern(pattern)
            total_deleted += deleted

        return total_deleted

    async def cleanup_expired_cache(self) -> int:
        """
        Clean up expired cache entries (maintenance task)
        """
        try:
            redis_client = await get_redis()
            # Redis automatically removes expired keys, but we can clean up
            # any orphaned metadata or corrupted entries

            all_keys = await redis_client.keys(f"{self.cache_version}:*")
            cleaned = 0

            for key in all_keys:
                try:
                    # Check if key exists and is valid
                    data = await redis_client.get(key)
                    if data:
                        json.loads(data)  # Validate JSON
                except (json.JSONDecodeError, Exception):
                    # Remove corrupted key
                    await redis_client.delete(key)
                    cleaned += 1

            if cleaned > 0:
                self.logger.info(f"Cleaned up {cleaned} corrupted cache entries")

            return cleaned

        except Exception as e:
            self.logger.error(f"Error during cache cleanup: {e}")
            return 0


# Global cache manager instance
cache_manager = CacheManager()