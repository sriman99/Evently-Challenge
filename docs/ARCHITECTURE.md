# 🏗️ Evently Architecture Documentation

## High-Level System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EVENTLY ARCHITECTURE                         │
└─────────────────────────────────────────────────────────────────────┘

┌──────────────┐    ┌─────────────────────────────────────────────────┐
│   Frontend   │────│              API Gateway                        │
│  (Not impl.) │    │         Rate Limiting & Auth                    │
└──────────────┘    └─────────────────────────────────────────────────┘
                                            │
                    ┌───────────────────────────────────────────────────┐
                    │            FastAPI Application Server             │
                    │  ┌─────────────────────────────────────────────┐  │
                    │  │           Authentication Layer              │  │
                    │  │     JWT + Role-Based Access Control        │  │
                    │  └─────────────────────────────────────────────┘  │
                    │  ┌─────────────────────────────────────────────┐  │
                    │  │               API Endpoints                 │  │
                    │  │  Auth │ Events │ Bookings │ Admin │ WS     │  │
                    │  └─────────────────────────────────────────────┘  │
                    │  ┌─────────────────────────────────────────────┐  │
                    │  │              Business Logic                 │  │
                    │  │    Saga Orchestrator │ Circuit Breaker     │  │
                    │  └─────────────────────────────────────────────┘  │
                    │  ┌─────────────────────────────────────────────┐  │
                    │  │             Service Layer                   │  │
                    │  │  Booking │ Event │ User │ Analytics Service │  │
                    │  └─────────────────────────────────────────────┘  │
                    └───────────────────────────────────────────────────┘
                             │                          │
          ┌──────────────────────────────┐    ┌─────────────────────────┐
          │      Cache Layer (Redis)     │    │   Persistence Layer    │
          │  ┌─────────────────────────┐ │    │  ┌───────────────────┐ │
          │  │   Distributed Locks    │ │    │  │   PostgreSQL DB   │ │
          │  │   Session Storage      │ │    │  │                   │ │
          │  │   Response Caching     │ │    │  │   Users           │ │
          │  │   Rate Limit State     │ │    │  │   Events          │ │
          │  │   Booking Reservations │ │    │  │   Bookings        │ │
          │  └─────────────────────────┘ │    │  │   Seats           │ │
          └──────────────────────────────┘    │  │   Venues          │ │
                                              │  │   Saga States     │ │
          ┌──────────────────────────────┐    │  └───────────────────┘ │
          │    Message Queue (RabbitMQ)  │    └─────────────────────────┘
          │  ┌─────────────────────────┐ │              │
          │  │   Async Tasks          │ │    ┌─────────────────────────┐
          │  │   Notification Queue   │ │    │    Monitoring Stack    │
          │  │   Booking Workflows    │ │    │  ┌───────────────────┐ │
          │  │   Payment Processing   │ │    │  │   Prometheus      │ │
          │  └─────────────────────────┘ │    │  │   Health Checks   │ │
          └──────────────────────────────┘    │  │   Metrics         │ │
                                              │  └───────────────────┘ │
                                              └─────────────────────────┘
```

## Core System Components

### 1. API Layer (FastAPI)
**Responsibilities:**
- RESTful API endpoints with OpenAPI documentation
- WebSocket connections for real-time updates
- Request validation and response serialization
- Authentication and authorization middleware
- Rate limiting and security headers

**Key Features:**
- Async/await pattern for high concurrency
- Automatic OpenAPI/Swagger documentation
- Pydantic models for data validation
- CORS middleware for frontend integration
- Comprehensive error handling

### 2. Authentication & Security
**Implementation:**
- JWT tokens with HS256/RS256 algorithms
- Role-based access control (User, Organizer, Admin)
- Token blacklisting for secure logout
- Request rate limiting with sliding window
- Input validation and sanitization

**Security Measures:**
- SQL injection prevention with parameterized queries
- CSRF protection with secure headers
- Password hashing with bcrypt
- Environment-based configuration
- Comprehensive audit logging

### 3. Business Logic Layer

#### Saga Pattern Implementation
```python
class BookingSaga:
    def __init__(self, orchestrator):
        self.orchestrator = orchestrator
        self.state = SagaState.STARTED

    async def execute(self):
        try:
            # Step 1: Reserve seats
            await self.reserve_seats()

            # Step 2: Create booking
            await self.create_booking()

            # Step 3: Process payment
            await self.process_payment()

            # Step 4: Confirm booking
            await self.confirm_booking()

        except Exception:
            await self.compensate()
```

#### Circuit Breaker Pattern
```python
@circuit_breaker(failure_threshold=5, reset_timeout=60)
async def external_payment_service():
    # External service call with fallback
    pass
```

### 4. Concurrency Control Architecture

#### Multi-Layer Protection Strategy
```
┌─────────────────────────────────────────────────────────────────┐
│                    CONCURRENCY CONTROL LAYERS                   │
├─────────────────────────────────────────────────────────────────┤
│  Layer 1: Application Level                                     │
│  ├─ Input validation and business rules                         │
│  ├─ Booking limits per user                                     │
│  └─ Event capacity checks                                       │
├─────────────────────────────────────────────────────────────────┤
│  Layer 2: Redis Distributed Locks                              │
│  ├─ Seat reservation locks (TTL: 5 minutes)                    │
│  ├─ User booking locks (prevent double booking)                │
│  └─ Event capacity locks (atomic operations)                   │
├─────────────────────────────────────────────────────────────────┤
│  Layer 3: Database Transactions                                │
│  ├─ PostgreSQL SELECT FOR UPDATE                               │
│  ├─ Atomic booking operations                                  │
│  └─ Constraint enforcement                                     │
├─────────────────────────────────────────────────────────────────┤
│  Layer 4: Database Constraints                                 │
│  ├─ CHECK constraints on capacity                              │
│  ├─ Foreign key constraints                                    │
│  └─ Unique constraints on critical fields                     │
└─────────────────────────────────────────────────────────────────┘
```

#### Seat Reservation Algorithm
```python
async def reserve_seats(self, event_id: UUID, seat_ids: List[UUID], user_id: UUID):
    lock_key = f"booking:event:{event_id}:user:{user_id}"

    async with distributed_lock(lock_key, timeout=300):
        # Step 1: Check seat availability
        available_seats = await self.get_available_seats(event_id, seat_ids)

        if len(available_seats) != len(seat_ids):
            raise SeatUnavailableError("Some seats are no longer available")

        # Step 2: Create Redis reservation
        reservation_data = {
            "user_id": str(user_id),
            "seat_ids": [str(sid) for sid in seat_ids],
            "timestamp": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat()
        }

        await redis_client.setex(
            f"reservation:{event_id}:{user_id}",
            300,
            json.dumps(reservation_data)
        )

        # Step 3: Update seat status in database
        async with database.transaction():
            await self.update_seat_status(seat_ids, SeatStatus.RESERVED)

        return reservation_data
```

## Database Architecture

### Schema Design Philosophy
- **Normalized Structure**: Eliminates data redundancy
- **Referential Integrity**: Foreign key constraints ensure consistency
- **Performance Optimization**: Strategic indexing on frequently queried columns
- **Data Validation**: CHECK constraints prevent invalid states

### Key Entity Relationships
```
Users (1:N) ────────────── Bookings (N:1) ────────────── Events
  │                           │                           │
  │                           │                           │
  └── (1:N) UserSessions      └── (1:N) BookingSeats     └── (1:N) Seats
                                         │                           │
                                         │                           │
                                         └────────── (N:1) ──────────┘

Events (N:1) ────────────── Venues
  │
  └── (1:N) ────────────── EventAnalytics

Users (1:N) ────────────── SagaStates (audit trail)
```

### Database Optimizations

#### Indexing Strategy
```sql
-- High-frequency query optimization
CREATE INDEX idx_events_status_start_time ON events(status, start_time);
CREATE INDEX idx_seats_event_status ON seats(event_id, status);
CREATE INDEX idx_bookings_user_status ON bookings(user_id, status);
CREATE INDEX idx_bookings_event_created ON bookings(event_id, created_at);

-- Unique constraints for business rules
CREATE UNIQUE INDEX idx_seats_event_section_row_number
ON seats(event_id, section, row, seat_number);

-- Partial indexes for specific queries
CREATE INDEX idx_available_seats
ON seats(event_id) WHERE status = 'AVAILABLE';
```

#### Database Constraints
```sql
-- Business rule enforcement
ALTER TABLE events ADD CONSTRAINT check_capacity_positive
CHECK (capacity > 0);

ALTER TABLE events ADD CONSTRAINT check_available_seats_valid
CHECK (available_seats >= 0 AND available_seats <= capacity);

ALTER TABLE bookings ADD CONSTRAINT check_booking_amount_positive
CHECK (total_amount >= 0);

-- Data consistency
ALTER TABLE seats ADD CONSTRAINT check_seat_price_positive
CHECK (price >= 0);
```

## Scalability Architecture

### Horizontal Scaling Strategy

#### Stateless Application Design
- All session data stored in Redis
- Database connection pooling
- Load balancer friendly (no sticky sessions)
- Container-ready deployment

#### Caching Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                        CACHING LAYERS                           │
├─────────────────────────────────────────────────────────────────┤
│  L1: Application Cache (In-Memory)                              │
│  ├─ User session data                                           │
│  ├─ Frequently accessed configuration                           │
│  └─ Short-term computation results                              │
├─────────────────────────────────────────────────────────────────┤
│  L2: Redis Cache (Distributed)                                 │
│  ├─ API response caching (TTL: 5-300 seconds)                  │
│  ├─ Database query results                                     │
│  ├─ Event listings with filtering                              │
│  └─ User authentication tokens                                 │
├─────────────────────────────────────────────────────────────────┤
│  L3: Database Query Optimization                               │
│  ├─ Connection pooling                                         │
│  ├─ Query result caching                                       │
│  └─ Read replicas (future enhancement)                         │
└─────────────────────────────────────────────────────────────────┘
```

#### Cache Invalidation Strategy
```python
class CacheManager:
    async def invalidate_events_cache(self):
        """Invalidate all event-related cache entries"""
        patterns = [
            f"{self.cache_version}:events:*",
            f"{self.cache_version}:event_detail:*",
            f"{self.cache_version}:event_seats:*"
        ]

        for pattern in patterns:
            keys = await self.redis.keys(pattern)
            if keys:
                await self.redis.delete(*keys)
```

### Performance Optimizations

#### Database Connection Management
```python
# Async connection pool configuration
DATABASE_CONFIG = {
    "pool_size": 20,
    "max_overflow": 40,
    "pool_timeout": 30,
    "pool_recycle": 3600,
    "pool_pre_ping": True
}
```

#### Query Optimization
```python
# Optimized event listing with eager loading
async def get_events_optimized(filters):
    query = (
        select(Event)
        .options(
            selectinload(Event.venue),
            selectinload(Event.seats)
        )
        .where(build_filters(filters))
        .order_by(Event.start_time)
        .limit(50)
    )

    result = await db.execute(query)
    return result.scalars().all()
```

## Fault Tolerance & Resilience

### Circuit Breaker Implementation
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, reset_timeout=60):
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED

    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError("Circuit breaker is open")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
```

### Error Handling Strategy
```python
# Structured error responses
class APIError(Exception):
    def __init__(self, message: str, error_code: str, status_code: int = 400):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code

@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "request_id": request.state.request_id
            }
        }
    )
```

## Monitoring & Observability

### Health Check Architecture
```python
@router.get("/health/status")
async def comprehensive_health_check():
    checks = {
        "database": await check_database_health(),
        "redis": await check_redis_health(),
        "external_services": await check_external_services()
    }

    overall_status = "healthy" if all(checks.values()) else "degraded"

    return {
        "status": overall_status,
        "environment": settings.APP_ENV,
        "version": settings.APP_VERSION,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }
```

### Metrics Collection
```python
# Prometheus metrics integration
REQUEST_COUNT = Counter(
    "app_requests_total",
    "Total requests",
    ["method", "endpoint", "status"]
)

REQUEST_DURATION = Histogram(
    "app_request_duration_seconds",
    "Request duration",
    ["method", "endpoint"]
)

BOOKING_OPERATIONS = Counter(
    "booking_operations_total",
    "Booking operations",
    ["operation", "status"]
)
```

## Security Architecture

### Authentication Flow
```
1. User Login Request
   ├─ Credentials validation
   ├─ Password verification (bcrypt)
   ├─ JWT token generation
   └─ Session creation in Redis

2. Protected Request
   ├─ JWT token extraction
   ├─ Token validation & signature verification
   ├─ Blacklist check in Redis
   ├─ Role-based authorization
   └─ Request processing

3. User Logout
   ├─ JWT token blacklisting
   ├─ Session cleanup in Redis
   └─ Response confirmation
```

### Data Protection
- **Encryption at Rest**: Database encryption
- **Encryption in Transit**: TLS 1.3 for all connections
- **Sensitive Data Handling**: No plaintext storage of passwords
- **Audit Trail**: Complete logging of all critical operations

## Deployment Architecture

### Container Strategy
```dockerfile
FROM python:3.11-slim

# Multi-stage build for optimization
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Environment Configuration
```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/evently
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
```

## Trade-offs & Design Decisions

### 1. Concurrency Control
**Decision**: Multi-layer approach (Redis + PostgreSQL)
**Trade-off**: Slight complexity increase for maximum data consistency
**Rationale**: Prevents overselling while maintaining high performance

### 2. Caching Strategy
**Decision**: Cache-aside pattern with validation
**Trade-off**: Additional cache management complexity
**Rationale**: Significant performance improvement for read-heavy workloads

### 3. Database Design
**Decision**: Normalized schema with computed properties
**Trade-off**: More complex queries vs. data consistency
**Rationale**: Ensures data integrity and reduces storage redundancy

### 4. Authentication Approach
**Decision**: JWT with Redis blacklisting
**Trade-off**: Stateless tokens vs. secure logout capability
**Rationale**: Combines JWT benefits with proper session management

### 5. Error Handling
**Decision**: Structured error responses with correlation IDs
**Trade-off**: Additional complexity for debugging benefits
**Rationale**: Improves troubleshooting and user experience

## Future Scaling Considerations

### Database Scaling
- **Read Replicas**: Separate read/write operations
- **Sharding**: Partition data by geographic region or event type
- **Connection Pooling**: PgBouncer for connection management

### Service Decomposition
- **Event Service**: Event management and analytics
- **Booking Service**: Booking operations and seat management
- **User Service**: Authentication and user management
- **Notification Service**: Real-time notifications and messaging

### Infrastructure Enhancements
- **CDN Integration**: Static asset caching
- **Message Queue Scaling**: RabbitMQ clustering
- **Cache Distribution**: Redis Cluster for high availability
- **Monitoring Enhancement**: Distributed tracing with Jaeger

---

This architecture demonstrates a production-ready system capable of handling high concurrency, ensuring data consistency, and providing excellent performance while maintaining clear separation of concerns and scalability paths.