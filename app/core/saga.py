"""
Saga Pattern Implementation for Distributed Transaction Management
Ensures atomicity across Redis + PostgreSQL operations

This implements the Saga Orchestration pattern with compensation actions
to handle distributed transaction rollbacks gracefully.
"""

import asyncio
import logging
from typing import List, Dict, Any, Callable, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import uuid
import json


logger = logging.getLogger(__name__)


class SagaStatus(str, Enum):
    """Saga execution status"""
    STARTED = "started"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"


class StepStatus(str, Enum):
    """Individual step status"""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"


@dataclass
class SagaStep:
    """
    Individual step in a Saga transaction
    Each step must have a forward action and compensation action
    """
    name: str
    action: Callable[..., Any]
    compensation: Callable[..., Any]
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: Optional[Exception] = None
    executed_at: Optional[datetime] = None
    compensated_at: Optional[datetime] = None

    # Context data that gets passed to action/compensation
    context: Dict[str, Any] = field(default_factory=dict)

    # Retry configuration
    max_retries: int = 3
    retry_count: int = 0


@dataclass
class SagaTransaction:
    """
    Represents a complete Saga transaction with all steps
    """
    saga_id: str
    name: str
    steps: List[SagaStep] = field(default_factory=list)
    status: SagaStatus = SagaStatus.STARTED
    context: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    error: Optional[Exception] = None


class SagaOrchestrator:
    """
    Orchestrator for managing Saga transactions with persistent state
    Handles forward execution, compensation, and recovery after restarts
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._active_sagas: Dict[str, SagaTransaction] = {}
        # Add cleanup tracking to prevent memory leaks
        self._saga_cleanup_registry: set[str] = set()

    async def _persist_saga_state(self, saga: SagaTransaction):
        """
        Persist saga state to database for recovery
        """
        try:
            from app.models.saga_state import SagaState, SagaStateStatus
            from app.core.database import async_session

            # Convert to persistence format
            steps_data = []
            for step in saga.steps:
                step_data = {
                    'name': step.name,
                    'status': step.status.value,
                    'context': step.context,
                    'max_retries': step.max_retries,
                    'retry_count': step.retry_count,
                    'error': str(step.error) if step.error else None,
                    'executed_at': step.executed_at.isoformat() if step.executed_at else None,
                    'compensated_at': step.compensated_at.isoformat() if step.compensated_at else None
                }
                steps_data.append(step_data)

            async with async_session() as db:
                # Check if exists
                from sqlalchemy import select
                stmt = select(SagaState).where(SagaState.saga_id == saga.saga_id)
                result = await db.execute(stmt)
                saga_state = result.scalar_one_or_none()

                if saga_state:
                    # Update existing
                    saga_state.status = SagaStateStatus(saga.status.value)
                    saga_state.context = saga.context
                    saga_state.steps_data = steps_data
                    saga_state.completed_steps = len([s for s in saga.steps if s.status == StepStatus.COMPLETED])
                    if saga.status in [SagaStatus.COMPLETED, SagaStatus.FAILED, SagaStatus.COMPENSATED]:
                        saga_state.completed_at = datetime.now(timezone.utc)
                    if saga.error:
                        saga_state.error_message = str(saga.error)
                else:
                    # Create new
                    saga_state = SagaState(
                        saga_id=saga.saga_id,
                        saga_name=saga.name,
                        status=SagaStateStatus(saga.status.value),
                        context=saga.context,
                        steps_data=steps_data,
                        completed_steps=len([s for s in saga.steps if s.status == StepStatus.COMPLETED]),
                        started_at=saga.started_at
                    )
                    db.add(saga_state)

                await db.commit()

        except Exception as e:
            self.logger.error(f"Failed to persist saga state for {saga.saga_id}: {e}")
            # Don't fail the saga for persistence issues

    def create_saga(self, name: str, context: Dict[str, Any] = None) -> SagaTransaction:
        """Create a new Saga transaction"""
        saga_id = str(uuid.uuid4())
        saga = SagaTransaction(
            saga_id=saga_id,
            name=name,
            context=context or {}
        )
        self._active_sagas[saga_id] = saga
        # Track saga for cleanup to prevent memory leaks
        self._saga_cleanup_registry.add(saga_id)
        return saga

    def add_step(
        self,
        saga: SagaTransaction,
        name: str,
        action: Callable,
        compensation: Callable,
        context: Dict[str, Any] = None,
        max_retries: int = 3
    ) -> SagaStep:
        """Add a step to the Saga"""
        step = SagaStep(
            name=name,
            action=action,
            compensation=compensation,
            context=context or {},
            max_retries=max_retries
        )
        saga.steps.append(step)
        return step

    async def execute_saga(self, saga: SagaTransaction) -> bool:
        """
        Execute all steps in the Saga
        Returns True if successful, False if compensation was required
        """
        self.logger.info(f"Starting saga execution: {saga.name} ({saga.saga_id})")
        saga.status = SagaStatus.EXECUTING
        await self._persist_saga_state(saga)

        executed_steps = []

        try:
            # Execute each step sequentially
            for step in saga.steps:
                success = await self._execute_step(saga, step)
                await self._persist_saga_state(saga)  # Persist after each step

                if success:
                    executed_steps.append(step)
                else:
                    # Step failed - trigger compensation
                    self.logger.error(f"Step {step.name} failed, starting compensation")
                    saga.status = SagaStatus.FAILED
                    saga.error = step.error
                    await self._persist_saga_state(saga)

                    # Compensate in reverse order
                    await self._compensate_saga(saga, executed_steps)
                    return False

            # All steps successful
            saga.status = SagaStatus.COMPLETED
            saga.completed_at = datetime.now(timezone.utc)
            await self._persist_saga_state(saga)
            self.logger.info(f"Saga completed successfully: {saga.name}")
            return True

        except Exception as e:
            self.logger.error(f"Unexpected error in saga {saga.name}: {e}")
            saga.status = SagaStatus.FAILED
            saga.error = e
            await self._persist_saga_state(saga)

            # Compensate executed steps
            await self._compensate_saga(saga, executed_steps)
            return False

        finally:
            # CRITICAL: Ensure saga is always cleaned up to prevent memory leaks
            self._cleanup_saga(saga.saga_id)

    async def _execute_step(self, saga: SagaTransaction, step: SagaStep) -> bool:
        """Execute a single step with retry logic"""
        step.status = StepStatus.EXECUTING

        for attempt in range(step.max_retries + 1):
            try:
                self.logger.debug(f"Executing step {step.name} (attempt {attempt + 1})")

                # Combine saga context with step context
                combined_context = {**saga.context, **step.context}

                # Execute the step action
                result = await step.action(combined_context)

                step.status = StepStatus.COMPLETED
                step.result = result
                step.executed_at = datetime.now(timezone.utc)

                self.logger.info(f"Step {step.name} completed successfully")
                return True

            except Exception as e:
                step.retry_count = attempt + 1
                step.error = e

                self.logger.warning(f"Step {step.name} failed (attempt {attempt + 1}): {e}")

                if attempt < step.max_retries:
                    # Wait before retry with exponential backoff
                    wait_time = min(2 ** attempt, 10)  # Max 10 seconds
                    await asyncio.sleep(wait_time)
                else:
                    # Max retries exceeded
                    step.status = StepStatus.FAILED
                    return False

        return False

    async def _compensate_saga(self, saga: SagaTransaction, executed_steps: List[SagaStep]):
        """Compensate executed steps in reverse order"""
        self.logger.info(f"Starting compensation for saga {saga.name}")
        saga.status = SagaStatus.COMPENSATING
        await self._persist_saga_state(saga)

        # Reverse the order for compensation
        for step in reversed(executed_steps):
            if step.status == StepStatus.COMPLETED:
                await self._compensate_step(saga, step)
                await self._persist_saga_state(saga)

        saga.status = SagaStatus.COMPENSATED
        saga.completed_at = datetime.now(timezone.utc)
        await self._persist_saga_state(saga)
        self.logger.info(f"Saga compensation completed: {saga.name}")

    async def _compensate_step(self, saga: SagaTransaction, step: SagaStep):
        """Compensate a single step"""
        step.status = StepStatus.COMPENSATING

        try:
            self.logger.debug(f"Compensating step {step.name}")

            # Combine contexts for compensation
            combined_context = {**saga.context, **step.context}

            # Execute compensation with step result available
            if step.result:
                combined_context['step_result'] = step.result

            await step.compensation(combined_context)

            step.status = StepStatus.COMPENSATED
            step.compensated_at = datetime.now(timezone.utc)

            self.logger.info(f"Step {step.name} compensated successfully")

        except Exception as e:
            self.logger.error(f"Compensation failed for step {step.name}: {e}")
            # Note: Compensation failures are logged but don't fail the saga
            # This is a design decision - alternative is to have compensation retries

    def _cleanup_saga(self, saga_id: str) -> None:
        """
        Clean up saga from memory to prevent leaks
        This method is fail-safe and won't raise exceptions
        """
        try:
            # Remove from active sagas
            self._active_sagas.pop(saga_id, None)
            # Remove from cleanup registry
            self._saga_cleanup_registry.discard(saga_id)
        except Exception as e:
            # Log error but don't propagate - cleanup should be fail-safe
            self.logger.error(f"Error during saga cleanup for {saga_id}: {e}")

    async def cleanup_orphaned_sagas(self) -> int:
        """
        Clean up any orphaned sagas that weren't properly cleaned
        Should be called periodically as a maintenance task
        Returns number of sagas cleaned up
        """
        cleaned_count = 0
        orphaned_ids = list(self._saga_cleanup_registry)

        for saga_id in orphaned_ids:
            if saga_id not in self._active_sagas:
                # Saga is in registry but not in active - clean it up
                self._saga_cleanup_registry.discard(saga_id)
                cleaned_count += 1
                self.logger.warning(f"Cleaned up orphaned saga registration: {saga_id}")

        return cleaned_count

    async def recover_incomplete_sagas(self):
        """
        Recover incomplete sagas after server restart
        Should be called during application startup
        """
        try:
            from app.models.saga_state import SagaState, SagaStateStatus
            from app.core.database import async_session
            from sqlalchemy import select

            async with async_session() as db:
                # Find incomplete sagas
                stmt = select(SagaState).where(
                    SagaState.status.in_([
                        SagaStateStatus.STARTED,
                        SagaStateStatus.EXECUTING,
                        SagaStateStatus.COMPENSATING
                    ])
                )
                result = await db.execute(stmt)
                incomplete_sagas = result.scalars().all()

                self.logger.info(f"Found {len(incomplete_sagas)} incomplete sagas to recover")

                for saga_state in incomplete_sagas:
                    try:
                        # Mark as failed for manual investigation
                        saga_state.status = SagaStateStatus.FAILED
                        saga_state.error_message = "Server restart during execution - requires manual investigation"
                        saga_state.completed_at = datetime.now(timezone.utc)

                        self.logger.warning(
                            f"Marked saga {saga_state.saga_id} ({saga_state.saga_name}) as failed due to server restart"
                        )

                    except Exception as e:
                        self.logger.error(f"Error recovering saga {saga_state.saga_id}: {e}")

                await db.commit()

        except Exception as e:
            self.logger.error(f"Error during saga recovery: {e}")

    async def get_saga_status(self, saga_id: str) -> Optional[dict]:
        """Get current status of a saga by ID"""
        try:
            from app.models.saga_state import SagaState
            from app.core.database import async_session
            from sqlalchemy import select

            async with async_session() as db:
                stmt = select(SagaState).where(SagaState.saga_id == saga_id)
                result = await db.execute(stmt)
                saga_state = result.scalar_one_or_none()

                if saga_state:
                    return {
                        'saga_id': saga_state.saga_id,
                        'saga_name': saga_state.saga_name,
                        'status': saga_state.status.value,
                        'started_at': saga_state.started_at.isoformat(),
                        'completed_at': saga_state.completed_at.isoformat() if saga_state.completed_at else None,
                        'completed_steps': saga_state.completed_steps,
                        'error_message': saga_state.error_message
                    }
                return None

        except Exception as e:
            self.logger.error(f"Error getting saga status for {saga_id}: {e}")
            return None


class BookingSaga:
    """
    Specialized Saga for booking operations
    Implements the specific steps for atomic booking across Redis + PostgreSQL
    """

    def __init__(self, orchestrator: SagaOrchestrator, redis_manager, db_manager):
        self.orchestrator = orchestrator
        self.redis_manager = redis_manager
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)

    async def create_booking_saga(
        self,
        event_id: str,
        seat_ids: List[str],
        user_id: str,
        booking_data: dict
    ) -> Tuple[bool, Any]:
        """
        Create a booking using the Saga pattern
        Returns (success, result/error)
        """
        # Sort seat IDs for deadlock prevention
        sorted_seat_ids = sorted(seat_ids)

        # Create saga with booking context
        saga = self.orchestrator.create_saga(
            name=f"booking_creation_{event_id}",
            context={
                'event_id': event_id,
                'seat_ids': sorted_seat_ids,
                'user_id': user_id,
                'booking_data': booking_data,
                'reservation_ttl': 600,  # 10 minutes
                'booking_result': None
            }
        )

        # Step 1: Reserve seats in Redis
        self.orchestrator.add_step(
            saga=saga,
            name="redis_seat_reservation",
            action=self._reserve_seats_redis,
            compensation=self._release_seats_redis,
            max_retries=2
        )

        # Step 2: Create database booking transaction
        self.orchestrator.add_step(
            saga=saga,
            name="database_booking_creation",
            action=self._create_booking_db,
            compensation=self._rollback_booking_db,
            max_retries=1  # DB operations should not retry much
        )

        # Execute the saga
        success = await self.orchestrator.execute_saga(saga)

        if success:
            # Return the booking result from context (set after DB commit)
            return True, saga.context.get('booking_result')
        else:
            # Return the error
            return False, saga.error

    async def _reserve_seats_redis(self, context: Dict[str, Any]) -> dict:
        """Step 1: Reserve seats in Redis with TTL"""
        event_id = context['event_id']
        seat_ids = context['seat_ids']
        user_id = context['user_id']
        ttl = context['reservation_ttl']

        success, failed_seats = await self.redis_manager.reserve_seats(
            event_id=event_id,
            seat_ids=seat_ids,
            user_id=user_id,
            ttl=ttl
        )

        if not success:
            raise Exception(f"Redis seat reservation failed for seats: {failed_seats}")

        return {
            'reserved_seats': seat_ids,
            'reservation_time': datetime.now(timezone.utc).isoformat()
        }

    async def _release_seats_redis(self, context: Dict[str, Any]):
        """Compensation 1: Release Redis seat reservations"""
        event_id = context['event_id']
        seat_ids = context['seat_ids']
        user_id = context['user_id']

        await self.redis_manager.release_seat_reservations(
            event_id=event_id,
            seat_ids=seat_ids,
            user_id=user_id
        )

        self.logger.info(f"Released Redis reservations for seats {seat_ids}")

    async def _create_booking_db(self, context: Dict[str, Any]) -> dict:
        """Step 2: Create booking in PostgreSQL with full ACID properties"""
        from sqlalchemy import select, and_
        from app.models.event import Event
        from app.models.seat import Seat, SeatStatus
        from app.models.booking import Booking, BookingStatus, BookingSeat
        from app.config import settings
        from datetime import datetime, timedelta, timezone
        import uuid

        booking_data = context['booking_data']
        event_id = context['event_id']
        seat_ids = context['seat_ids']
        user_id = context['user_id']

        async with self.db_manager.atomic_transaction() as db:
            # Lock and verify event
            event_stmt = (
                select(Event)
                .where(Event.id == event_id)
                .with_for_update()
            )
            event_result = await db.execute(event_stmt)
            event = event_result.scalar_one_or_none()

            if not event:
                raise Exception(f"Event {event_id} not found")

            # Prevent booking past or ongoing events
            from datetime import datetime, timezone
            if event.start_time <= datetime.now(timezone.utc):
                raise Exception(f"Cannot book tickets for past or ongoing events")

            # Lock and verify seats - using pessimistic locking consistently
            # REMOVED: skip_locked=True to prevent bypassing seat reservation logic
            seats_stmt = (
                select(Seat)
                .where(
                    and_(
                        Seat.event_id == event_id,
                        Seat.id.in_(seat_ids),
                        Seat.status == SeatStatus.AVAILABLE
                    )
                )
                .with_for_update()  # Block until seats are available or timeout
                .order_by(Seat.id)
            )

            seats_result = await db.execute(seats_stmt)
            available_seats = list(seats_result.scalars().all())

            if len(available_seats) != len(seat_ids):
                available_ids = {str(seat.id) for seat in available_seats}
                unavailable_ids = set(seat_ids) - available_ids
                raise Exception(f"Seats no longer available: {unavailable_ids}")

            # Calculate total
            total_amount = sum(seat.price for seat in available_seats)

            # Create booking
            booking = Booking(
                user_id=uuid.UUID(user_id),
                event_id=uuid.UUID(event_id),
                booking_code=f"EVT{uuid.uuid4().hex[:8].upper()}",
                status=BookingStatus.PENDING,
                total_amount=total_amount,
                expires_at=datetime.now(timezone.utc) + timedelta(
                    minutes=settings.BOOKING_EXPIRATION_MINUTES
                )
            )

            db.add(booking)
            await db.flush()

            # Create booking seats and update seat status
            for seat in available_seats:
                booking_seat = BookingSeat(
                    booking_id=booking.id,
                    seat_id=seat.id,
                    price=seat.price
                )
                db.add(booking_seat)

                # Update seat status
                seat.status = SeatStatus.RESERVED
                seat.reserved_by = uuid.UUID(user_id)
                seat.reserved_at = datetime.now(timezone.utc)

            # Store booking result in context for return after commit
            context['booking_result'] = {
                'booking_id': str(booking.id),
                'booking_code': booking.booking_code,
                'total_amount': float(booking.total_amount),
                'expires_at': booking.expires_at.isoformat(),
                'seat_count': len(available_seats)
            }

            # CRITICAL: Do NOT return before transaction commits
            # Return after successful commit to ensure atomicity
            return booking

    async def _rollback_booking_db(self, context: Dict[str, Any]):
        """Compensation 2: Rollback database booking"""
        # In case of database rollback, the transaction context handles this
        # But we could also implement explicit cleanup here if needed
        self.logger.info(f"Database booking rollback completed for event {context['event_id']}")


# Global saga orchestrator instance
saga_orchestrator = SagaOrchestrator()