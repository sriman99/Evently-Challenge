# 🏗️ Evently System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CDN / CloudFlare                         │
│                    (Static Assets, Edge Caching)                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                      NGINX Load Balancer                         │
│                    (SSL Termination, Routing)                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│                     API Gateway (Rate Limiting)                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼────────┐    ┌────────▼────────┐   ┌────────▼────────┐
│  FastAPI App   │    │  FastAPI App    │   │  FastAPI App    │
│   Instance 1   │    │   Instance 2    │   │   Instance 3    │
└───────┬────────┘    └────────┬────────┘   └────────┬────────┘
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼────────┐    ┌────────▼────────┐   ┌────────▼────────┐
│  PostgreSQL    │    │     Redis       │   │   RabbitMQ      │
│   (Primary)    │    │  (Cache/Lock)   │   │  (Message Queue)│
└───────┬────────┘    └─────────────────┘   └─────────────────┘
        │
┌───────▼────────┐
│  PostgreSQL    │
│   (Replica)    │
└────────────────┘
```

## Component Architecture

### 1. API Gateway Layer
- **Purpose**: Entry point for all client requests
- **Responsibilities**:
  - Rate limiting (Token Bucket algorithm)
  - Request routing
  - Authentication verification
  - Request/Response logging
  - DDoS protection

### 2. Application Layer (FastAPI)
- **Purpose**: Business logic processing
- **Components**:
  - REST API endpoints
  - WebSocket connections
  - Authentication middleware
  - Request validation
  - Response serialization

### 3. Service Layer
- **Purpose**: Core business logic
- **Services**:
  - **AuthService**: User authentication and authorization
  - **EventService**: Event management and queries
  - **BookingService**: Booking creation and management
  - **PaymentService**: Payment processing
  - **NotificationService**: Email/SMS notifications
  - **AnalyticsService**: Data aggregation and reporting

### 4. Data Layer
- **PostgreSQL**: Primary data store
  - User data
  - Event information
  - Booking records
  - Transaction history

- **Redis**: Cache and distributed locking
  - Session storage
  - Distributed locks for seat reservation
  - Cached event data
  - Real-time seat availability

- **RabbitMQ**: Message queue
  - Async notification processing
  - Analytics data processing
  - Background job queue

## Concurrency Control Architecture

### Multi-Layer Approach

```
Layer 1: Redis Distributed Lock
├── Acquire lock with TTL (5 minutes)
├── Unique lock key per seat
└── Automatic expiration

Layer 2: Database Optimistic Locking
├── Version field on seat records
├── Check version on update
└── Retry on version mismatch

Layer 3: Database Transaction Isolation
├── SERIALIZABLE isolation level
├── Atomic operations
└── Automatic rollback on conflict
```

### Booking Flow Sequence

```
1. User Selection
   └── Select seats from UI

2. Lock Acquisition
   ├── Redis lock per seat (TTL: 5 min)
   └── Return lock tokens

3. Availability Check
   ├── Database query
   └── Validate all seats available

4. Reservation Creation
   ├── Create pending booking
   ├── Update seat status to 'reserved'
   └── Set expiration timer

5. Payment Processing
   ├── Initialize payment
   ├── Process with gateway
   └── Await confirmation

6. Booking Confirmation
   ├── Update booking status
   ├── Update seat status to 'booked'
   └── Generate booking code

7. Lock Release
   ├── Remove Redis locks
   └── Clean up temporary data

8. Notification
   ├── Queue email notification
   ├── Queue SMS notification
   └── Send real-time update via WebSocket
```

## Database Architecture

### Partitioning Strategy

```sql
-- Events table partitioned by month
CREATE TABLE events (
    id UUID PRIMARY KEY,
    start_time TIMESTAMP,
    ...
) PARTITION BY RANGE (start_time);

-- Create monthly partitions
CREATE TABLE events_2024_01 PARTITION OF events
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

### Indexing Strategy

```sql
-- Performance-critical indexes
CREATE INDEX idx_seats_availability
    ON seats(event_id, status)
    WHERE status = 'available';

CREATE INDEX idx_bookings_user_status
    ON bookings(user_id, status);

CREATE INDEX idx_events_upcoming
    ON events(start_time)
    WHERE status = 'upcoming';
```

### Connection Pooling

```python
# PgBouncer configuration
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
reserve_pool_size = 5
```

## Caching Architecture

### Cache Hierarchy

```
L1: CDN Cache (CloudFlare)
├── Static assets (permanent)
├── Event images (1 hour)
└── API responses (5 minutes)

L2: Redis Cache
├── Event details (5 minutes)
├── Seat availability (10 seconds)
├── User sessions (30 minutes)
└── Analytics data (1 minute)

L3: Application Cache
├── Configuration (until restart)
├── Venue layouts (1 hour)
└── Frequently accessed data (5 minutes)
```

### Cache Invalidation

```python
# Event-based invalidation
on_booking_created → invalidate event_seats_cache
on_event_updated → invalidate event_details_cache
on_payment_confirmed → invalidate booking_cache
```

## Scalability Design

### Horizontal Scaling

```yaml
# Kubernetes deployment
apiVersion: apps/v1
kind: Deployment
metadata:
  name: evently-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
  template:
    spec:
      containers:
      - name: api
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
```

### Auto-scaling Rules

```yaml
# HPA configuration
metrics:
- type: Resource
  resource:
    name: cpu
    target:
      type: Utilization
      averageUtilization: 70
- type: Resource
  resource:
    name: memory
    target:
      type: Utilization
      averageUtilization: 80
```

## Security Architecture

### Authentication Flow

```
1. User Login
   └── POST /auth/login with credentials

2. Credential Validation
   ├── Verify email exists
   └── Check password hash (bcrypt)

3. Token Generation
   ├── Create JWT access token (30 min)
   ├── Create refresh token (7 days)
   └── Store refresh token in Redis

4. Token Usage
   ├── Include in Authorization header
   └── Validate on each request

5. Token Refresh
   ├── Use refresh token
   └── Issue new access token
```

### API Security

```python
# Rate limiting configuration
RATE_LIMITS = {
    "/api/v1/events": "100/minute",
    "/api/v1/bookings": "10/minute/user",
    "/api/v1/admin/*": "1000/minute"
}

# CORS configuration
CORS_ORIGINS = [
    "https://evently.com",
    "https://app.evently.com"
]
```

## Monitoring & Observability

### Metrics Collection

```python
# Prometheus metrics
request_count = Counter('api_requests_total')
request_duration = Histogram('api_request_duration_seconds')
active_bookings = Gauge('active_bookings_total')
```

### Logging Strategy

```python
# Structured logging
{
    "timestamp": "2024-01-15T10:30:00Z",
    "level": "INFO",
    "service": "booking-service",
    "trace_id": "abc123",
    "user_id": "user_456",
    "action": "booking_created",
    "event_id": "event_789",
    "duration_ms": 45
}
```

### Health Checks

```python
# Health check endpoints
GET /health/live    # Kubernetes liveness probe
GET /health/ready   # Kubernetes readiness probe
GET /health/startup # Kubernetes startup probe
```

## Disaster Recovery

### Backup Strategy

```bash
# Database backup
pg_dump evently > backup_$(date +%Y%m%d).sql

# Redis backup
redis-cli BGSAVE

# Automated backups every 6 hours
0 */6 * * * /scripts/backup.sh
```

### Failover Plan

1. **Database Failover**: Automatic promotion of read replica
2. **Redis Failover**: Redis Sentinel for automatic failover
3. **Application Failover**: Kubernetes handles pod failures
4. **Regional Failover**: Multi-region deployment with DNS failover

## Performance Optimization

### Query Optimization

```sql
-- Use EXPLAIN ANALYZE for query planning
EXPLAIN ANALYZE
SELECT s.* FROM seats s
WHERE s.event_id = $1
  AND s.status = 'available'
ORDER BY s.price, s.section, s.row;
```

### Connection Optimization

```python
# Async database operations
async with db.transaction():
    await seat_repo.reserve_seats(seat_ids)
    await booking_repo.create_booking(booking_data)
```

### Caching Strategy

```python
@cache(ttl=300)
async def get_event_details(event_id: str):
    return await event_repository.get_by_id(event_id)
```

## Development & Deployment

### CI/CD Pipeline

```yaml
# GitHub Actions workflow
steps:
  - Test: Run pytest
  - Lint: Run flake8 and mypy
  - Build: Docker image
  - Deploy: Push to registry
  - Release: Deploy to Kubernetes
```

### Environment Management

```bash
# Environment-specific configs
├── config/
│   ├── development.yaml
│   ├── staging.yaml
│   └── production.yaml
```

## Technology Decisions & Trade-offs

### Why FastAPI?
- **Pros**: High performance, async support, automatic API docs
- **Cons**: Smaller ecosystem than Django/Flask
- **Decision**: Performance and async capabilities outweigh ecosystem size

### Why PostgreSQL?
- **Pros**: ACID compliance, strong consistency, mature
- **Cons**: Vertical scaling limitations
- **Decision**: Consistency requirements mandate RDBMS

### Why Redis?
- **Pros**: Fast, distributed locking, pub/sub support
- **Cons**: Memory limitations, persistence complexity
- **Decision**: Speed and locking capabilities critical for bookings

### Why RabbitMQ?
- **Pros**: Reliable delivery, routing flexibility
- **Cons**: Additional infrastructure complexity
- **Decision**: Reliable async processing worth the complexity

## Future Enhancements

1. **GraphQL API**: Alternative to REST for flexible queries
2. **Event Sourcing**: Complete audit trail of all changes
3. **CQRS Pattern**: Separate read/write models for scale
4. **Service Mesh**: Istio for advanced traffic management
5. **Multi-region**: Global distribution for lower latency