"""
Test Saga Pattern Implementation
Tests the new Saga-based booking system for atomicity
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
import uuid

from app.core.saga import SagaOrchestrator, BookingSaga, SagaStatus
from app.models.booking import BookingStatus
from app.schemas.booking import BookingCreate


class TestSagaOrchestrator:
    """Test the core Saga orchestrator functionality"""

    @pytest_asyncio.fixture
    async def orchestrator(self):
        return SagaOrchestrator()

    @pytest_asyncio.fixture
    async def mock_redis_manager(self):
        mock = AsyncMock()
        mock.reserve_seats.return_value = (True, [])
        mock.release_seat_reservations.return_value = None
        return mock

    @pytest_asyncio.fixture
    async def mock_db_manager(self):
        mock = AsyncMock()
        mock.atomic_transaction.return_value.__aenter__ = AsyncMock()
        mock.atomic_transaction.return_value.__aexit__ = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_saga_creation(self, orchestrator):
        """Test basic saga creation"""
        saga = orchestrator.create_saga(
            name="test_saga",
            context={"test_key": "test_value"}
        )

        assert saga.name == "test_saga"
        assert saga.context["test_key"] == "test_value"
        assert saga.status == SagaStatus.STARTED
        assert len(saga.steps) == 0

    @pytest.mark.asyncio
    async def test_successful_saga_execution(self, orchestrator):
        """Test successful saga execution with compensation"""
        saga = orchestrator.create_saga("test_success")

        # Mock functions
        async def step1_action(context):
            return {"step1": "completed"}

        async def step1_compensation(context):
            pass

        async def step2_action(context):
            return {"step2": "completed"}

        async def step2_compensation(context):
            pass

        # Add steps
        orchestrator.add_step(saga, "step1", step1_action, step1_compensation)
        orchestrator.add_step(saga, "step2", step2_action, step2_compensation)

        # Execute saga
        success = await orchestrator.execute_saga(saga)

        assert success is True
        assert saga.status == SagaStatus.COMPLETED
        assert len(saga.steps) == 2
        assert saga.steps[0].result == {"step1": "completed"}
        assert saga.steps[1].result == {"step2": "completed"}

    @pytest.mark.asyncio
    async def test_failed_saga_with_compensation(self, orchestrator):
        """Test saga failure triggers compensation"""
        saga = orchestrator.create_saga("test_failure")

        step1_compensated = False

        async def step1_action(context):
            return {"step1": "completed"}

        async def step1_compensation(context):
            nonlocal step1_compensated
            step1_compensated = True

        async def step2_action(context):
            raise Exception("Step 2 failed")

        async def step2_compensation(context):
            pass

        # Add steps
        orchestrator.add_step(saga, "step1", step1_action, step1_compensation)
        orchestrator.add_step(saga, "step2", step2_action, step2_compensation)

        # Execute saga
        success = await orchestrator.execute_saga(saga)

        assert success is False
        assert saga.status == SagaStatus.COMPENSATED
        assert step1_compensated is True


class TestBookingSaga:
    """Test the booking-specific Saga implementation"""

    @pytest_asyncio.fixture
    async def booking_saga(self):
        orchestrator = SagaOrchestrator()
        mock_redis = AsyncMock()
        mock_db = AsyncMock()

        # Setup Redis mock
        mock_redis.reserve_seats.return_value = (True, [])
        mock_redis.release_seat_reservations.return_value = None

        # Setup DB mock
        mock_db.atomic_transaction.return_value.__aenter__ = AsyncMock()
        mock_db.atomic_transaction.return_value.__aexit__ = AsyncMock()

        return BookingSaga(orchestrator, mock_redis, mock_db)

    @pytest.mark.asyncio
    async def test_booking_saga_creation(self, booking_saga):
        """Test booking saga setup"""
        assert booking_saga.orchestrator is not None
        assert booking_saga.redis_manager is not None
        assert booking_saga.db_manager is not None

    @pytest.mark.asyncio
    async def test_redis_reservation_step(self, booking_saga):
        """Test Redis reservation step in isolation"""
        context = {
            'event_id': str(uuid.uuid4()),
            'seat_ids': ['seat1', 'seat2'],
            'user_id': str(uuid.uuid4()),
            'reservation_ttl': 600
        }

        # Mock successful reservation
        booking_saga.redis_manager.reserve_seats.return_value = (True, [])

        result = await booking_saga._reserve_seats_redis(context)

        assert 'reserved_seats' in result
        assert result['reserved_seats'] == ['seat1', 'seat2']
        assert 'reservation_time' in result

        # Verify Redis manager was called correctly
        booking_saga.redis_manager.reserve_seats.assert_called_once_with(
            event_id=context['event_id'],
            seat_ids=context['seat_ids'],
            user_id=context['user_id'],
            ttl=context['reservation_ttl']
        )

    @pytest.mark.asyncio
    async def test_redis_reservation_failure(self, booking_saga):
        """Test Redis reservation failure"""
        context = {
            'event_id': str(uuid.uuid4()),
            'seat_ids': ['seat1', 'seat2'],
            'user_id': str(uuid.uuid4()),
            'reservation_ttl': 600
        }

        # Mock failed reservation
        booking_saga.redis_manager.reserve_seats.return_value = (False, ['seat1'])

        with pytest.raises(Exception, match="Redis seat reservation failed"):
            await booking_saga._reserve_seats_redis(context)

    @pytest.mark.asyncio
    async def test_redis_compensation(self, booking_saga):
        """Test Redis reservation compensation"""
        context = {
            'event_id': str(uuid.uuid4()),
            'seat_ids': ['seat1', 'seat2'],
            'user_id': str(uuid.uuid4())
        }

        await booking_saga._release_seats_redis(context)

        booking_saga.redis_manager.release_seat_reservations.assert_called_once_with(
            event_id=context['event_id'],
            seat_ids=context['seat_ids'],
            user_id=context['user_id']
        )


class TestBookingSagaIntegration:
    """Integration tests for booking saga with mocked dependencies"""

    @pytest_asyncio.fixture
    async def integration_setup(self):
        """Setup for integration testing"""
        orchestrator = SagaOrchestrator()

        # Create mocks
        redis_manager = AsyncMock()
        db_manager = AsyncMock()

        # Configure Redis mock for success
        redis_manager.reserve_seats.return_value = (True, [])
        redis_manager.release_seat_reservations.return_value = None

        # Configure DB mock for success
        db_session_mock = AsyncMock()
        async_context_mock = AsyncMock()
        async_context_mock.__aenter__ = AsyncMock(return_value=db_session_mock)
        async_context_mock.__aexit__ = AsyncMock(return_value=None)
        db_manager.atomic_transaction.return_value = async_context_mock

        # Mock database query results
        event_result_mock = MagicMock()
        event_mock = MagicMock()
        event_mock.id = uuid.uuid4()
        event_result_mock.scalar_one_or_none.return_value = event_mock

        seats_result_mock = MagicMock()
        seat1 = MagicMock()
        seat1.id = uuid.uuid4()
        seat1.price = 100.0
        seat2 = MagicMock()
        seat2.id = uuid.uuid4()
        seat2.price = 150.0
        seats_result_mock.scalars.return_value.all.return_value = [seat1, seat2]

        db_session_mock.execute.side_effect = [event_result_mock, seats_result_mock]
        db_session_mock.add.return_value = None
        db_session_mock.flush.return_value = None

        booking_saga = BookingSaga(orchestrator, redis_manager, db_manager)

        return {
            'saga': booking_saga,
            'redis': redis_manager,
            'db': db_manager,
            'seats': [seat1, seat2]
        }

    @pytest.mark.asyncio
    async def test_successful_booking_saga(self, integration_setup):
        """Test complete successful booking saga"""
        setup = integration_setup
        booking_saga = setup['saga']

        # Test data
        event_id = str(uuid.uuid4())
        seat_ids = [str(uuid.uuid4()), str(uuid.uuid4())]
        user_id = str(uuid.uuid4())
        booking_data = {
            'event_id': event_id,
            'seat_ids': seat_ids
        }

        # Execute booking saga
        success, result = await booking_saga.create_booking_saga(
            event_id=event_id,
            seat_ids=seat_ids,
            user_id=user_id,
            booking_data=booking_data
        )

        # Verify success
        assert success is True
        assert 'booking_id' in result
        assert 'booking_code' in result
        assert 'total_amount' in result

        # Verify Redis was called
        setup['redis'].reserve_seats.assert_called_once()

        # Verify DB transaction was used
        setup['db'].atomic_transaction.assert_called_once()

    @pytest.mark.asyncio
    async def test_booking_saga_redis_failure(self, integration_setup):
        """Test booking saga with Redis failure triggers compensation"""
        setup = integration_setup
        booking_saga = setup['saga']

        # Configure Redis to fail
        setup['redis'].reserve_seats.return_value = (False, ['seat1'])

        # Test data
        event_id = str(uuid.uuid4())
        seat_ids = [str(uuid.uuid4())]
        user_id = str(uuid.uuid4())
        booking_data = {'event_id': event_id, 'seat_ids': seat_ids}

        # Execute booking saga
        success, result = await booking_saga.create_booking_saga(
            event_id=event_id,
            seat_ids=seat_ids,
            user_id=user_id,
            booking_data=booking_data
        )

        # Verify failure and compensation
        assert success is False
        assert "Redis seat reservation failed" in str(result)

        # Redis should have been called multiple times (retry logic)
        # The exact number depends on max_retries configuration
        assert setup['redis'].reserve_seats.call_count >= 1

        # DB transaction should not have been called
        setup['db'].atomic_transaction.assert_not_called()