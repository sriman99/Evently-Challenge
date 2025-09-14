# 📚 API Documentation

## Base URL
```
Production: https://api.evently.com
Development: http://localhost:8000
```

## API Version
Current Version: `v1`

All endpoints are prefixed with `/api/v1`

## Authentication
The API uses JWT (JSON Web Tokens) for authentication.

### Headers
```http
Authorization: Bearer <access_token>
Content-Type: application/json
```

## Rate Limiting
- Public endpoints: 100 requests/minute
- Authenticated endpoints: 200 requests/minute
- Booking endpoints: 10 requests/minute per user
- Admin endpoints: 1000 requests/minute

## Response Format

### Success Response
```json
{
    "success": true,
    "data": {},
    "message": "Operation successful",
    "timestamp": "2024-01-15T10:30:00Z"
}
```

### Error Response
```json
{
    "success": false,
    "error": {
        "code": "ERROR_CODE",
        "message": "Human readable error message",
        "details": {}
    },
    "timestamp": "2024-01-15T10:30:00Z"
}
```

### Pagination Response
```json
{
    "success": true,
    "data": [],
    "pagination": {
        "page": 1,
        "per_page": 20,
        "total": 100,
        "total_pages": 5,
        "has_next": true,
        "has_prev": false
    },
    "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## 🔐 Authentication Endpoints

### Register User
```http
POST /api/v1/auth/register
```

**Request Body:**
```json
{
    "email": "user@example.com",
    "password": "SecurePass123!",
    "full_name": "John Doe",
    "phone": "+1234567890"
}
```

**Response:**
```json
{
    "success": true,
    "data": {
        "user": {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "user@example.com",
            "full_name": "John Doe",
            "role": "user",
            "created_at": "2024-01-15T10:30:00Z"
        },
        "access_token": "eyJhbGciOiJIUzI1...",
        "refresh_token": "eyJhbGciOiJIUzI1...",
        "token_type": "bearer",
        "expires_in": 1800
    },
    "message": "Registration successful"
}
```

### Login
```http
POST /api/v1/auth/login
```

**Request Body:**
```json
{
    "email": "user@example.com",
    "password": "SecurePass123!"
}
```

**Response:**
```json
{
    "success": true,
    "data": {
        "access_token": "eyJhbGciOiJIUzI1...",
        "refresh_token": "eyJhbGciOiJIUzI1...",
        "token_type": "bearer",
        "expires_in": 1800
    }
}
```

### Refresh Token
```http
POST /api/v1/auth/refresh
```

**Request Body:**
```json
{
    "refresh_token": "eyJhbGciOiJIUzI1..."
}
```

---

## 🎭 Event Endpoints

### List Events
```http
GET /api/v1/events
```

**Query Parameters:**
- `page` (integer): Page number (default: 1)
- `per_page` (integer): Items per page (default: 20, max: 100)
- `status` (string): Filter by status (upcoming, ongoing, completed)
- `venue_id` (uuid): Filter by venue
- `start_date` (date): Filter events starting after this date
- `end_date` (date): Filter events starting before this date
- `search` (string): Search in event name and description

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "name": "Summer Music Festival",
            "description": "Annual summer music festival",
            "venue": {
                "id": "550e8400-e29b-41d4-a716-446655440002",
                "name": "Central Park Arena",
                "city": "New York",
                "capacity": 50000
            },
            "start_time": "2024-07-15T18:00:00Z",
            "end_time": "2024-07-15T23:00:00Z",
            "capacity": 50000,
            "available_seats": 12500,
            "status": "upcoming",
            "min_price": 50.00,
            "max_price": 500.00
        }
    ],
    "pagination": {
        "page": 1,
        "per_page": 20,
        "total": 45,
        "total_pages": 3
    }
}
```

### Get Event Details
```http
GET /api/v1/events/{event_id}
```

**Response:**
```json
{
    "success": true,
    "data": {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "Summer Music Festival",
        "description": "Annual summer music festival featuring top artists",
        "venue": {
            "id": "550e8400-e29b-41d4-a716-446655440002",
            "name": "Central Park Arena",
            "address": "123 Park Avenue",
            "city": "New York",
            "state": "NY",
            "country": "USA",
            "postal_code": "10001",
            "capacity": 50000,
            "layout_config": {}
        },
        "start_time": "2024-07-15T18:00:00Z",
        "end_time": "2024-07-15T23:00:00Z",
        "capacity": 50000,
        "available_seats": 12500,
        "status": "upcoming",
        "price_tiers": [
            {"tier": "VIP", "price": 500.00, "available": 100},
            {"tier": "Premium", "price": 200.00, "available": 500},
            {"tier": "General", "price": 50.00, "available": 12000}
        ],
        "created_at": "2024-01-01T00:00:00Z"
    }
}
```

### Get Available Seats
```http
GET /api/v1/events/{event_id}/seats
```

**Query Parameters:**
- `section` (string): Filter by section
- `price_tier` (string): Filter by price tier
- `status` (string): Filter by status (default: available)

**Response:**
```json
{
    "success": true,
    "data": {
        "event_id": "550e8400-e29b-41d4-a716-446655440001",
        "sections": [
            {
                "name": "VIP",
                "rows": [
                    {
                        "row": "A",
                        "seats": [
                            {
                                "id": "550e8400-e29b-41d4-a716-446655440003",
                                "seat_number": "1",
                                "price": 500.00,
                                "status": "available"
                            }
                        ]
                    }
                ]
            }
        ],
        "summary": {
            "total_available": 12500,
            "by_tier": {
                "VIP": 100,
                "Premium": 500,
                "General": 11900
            }
        }
    }
}
```

---

## 🎫 Booking Endpoints

### Create Booking
```http
POST /api/v1/bookings
```

**Request Body:**
```json
{
    "event_id": "550e8400-e29b-41d4-a716-446655440001",
    "seat_ids": [
        "550e8400-e29b-41d4-a716-446655440003",
        "550e8400-e29b-41d4-a716-446655440004"
    ]
}
```

**Response:**
```json
{
    "success": true,
    "data": {
        "booking": {
            "id": "550e8400-e29b-41d4-a716-446655440005",
            "booking_code": "EVT2024011500001",
            "event": {
                "id": "550e8400-e29b-41d4-a716-446655440001",
                "name": "Summer Music Festival",
                "start_time": "2024-07-15T18:00:00Z"
            },
            "seats": [
                {
                    "section": "VIP",
                    "row": "A",
                    "seat_number": "1",
                    "price": 500.00
                }
            ],
            "total_amount": 1000.00,
            "status": "pending",
            "expires_at": "2024-01-15T10:35:00Z",
            "created_at": "2024-01-15T10:30:00Z"
        },
        "payment_url": "/api/v1/payments/initiate/550e8400-e29b-41d4-a716-446655440005"
    }
}
```

### Confirm Booking
```http
POST /api/v1/bookings/{booking_id}/confirm
```

**Request Body:**
```json
{
    "payment_method": "credit_card",
    "payment_details": {
        "token": "stripe_token_123"
    }
}
```

### Cancel Booking
```http
DELETE /api/v1/bookings/{booking_id}
```

**Response:**
```json
{
    "success": true,
    "data": {
        "booking_id": "550e8400-e29b-41d4-a716-446655440005",
        "status": "cancelled",
        "refund_status": "processing",
        "refund_amount": 1000.00
    },
    "message": "Booking cancelled successfully"
}
```

### Get User Bookings
```http
GET /api/v1/users/bookings
```

**Query Parameters:**
- `status` (string): Filter by status (pending, confirmed, cancelled)
- `page` (integer): Page number
- `per_page` (integer): Items per page

---

## 👤 User Endpoints

### Get User Profile
```http
GET /api/v1/users/profile
```

**Response:**
```json
{
    "success": true,
    "data": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "user@example.com",
        "full_name": "John Doe",
        "phone": "+1234567890",
        "role": "user",
        "created_at": "2024-01-01T00:00:00Z",
        "stats": {
            "total_bookings": 15,
            "upcoming_events": 3,
            "total_spent": 2500.00
        }
    }
}
```

### Update User Profile
```http
PUT /api/v1/users/profile
```

**Request Body:**
```json
{
    "full_name": "John Smith",
    "phone": "+1234567891"
}
```

---

## 📊 Admin Endpoints

### Create Event
```http
POST /api/v1/admin/events
```

**Request Body:**
```json
{
    "name": "New Year Concert",
    "description": "Welcome 2025 with music",
    "venue_id": "550e8400-e29b-41d4-a716-446655440002",
    "start_time": "2024-12-31T20:00:00Z",
    "end_time": "2025-01-01T01:00:00Z",
    "capacity": 10000,
    "seat_configuration": {
        "sections": [
            {
                "name": "VIP",
                "rows": ["A", "B"],
                "seats_per_row": 20,
                "price": 300.00
            }
        ]
    }
}
```

### Update Event
```http
PUT /api/v1/admin/events/{event_id}
```

### Get Analytics Dashboard
```http
GET /api/v1/admin/analytics/dashboard
```

**Query Parameters:**
- `start_date` (date): Start date for analytics
- `end_date` (date): End date for analytics

**Response:**
```json
{
    "success": true,
    "data": {
        "summary": {
            "total_events": 25,
            "total_bookings": 15000,
            "total_revenue": 750000.00,
            "average_capacity_utilization": 75.5
        },
        "top_events": [
            {
                "event_id": "550e8400-e29b-41d4-a716-446655440001",
                "name": "Summer Music Festival",
                "bookings": 5000,
                "revenue": 250000.00,
                "utilization": 95.0
            }
        ],
        "booking_trends": [
            {
                "date": "2024-01-01",
                "bookings": 150,
                "revenue": 7500.00
            }
        ],
        "revenue_by_category": {
            "VIP": 300000.00,
            "Premium": 250000.00,
            "General": 200000.00
        }
    }
}
```

---

## 🔄 Waitlist Endpoints

### Join Waitlist
```http
POST /api/v1/waitlist/join
```

**Request Body:**
```json
{
    "event_id": "550e8400-e29b-41d4-a716-446655440001",
    "notification_preferences": {
        "email": true,
        "sms": true
    }
}
```

**Response:**
```json
{
    "success": true,
    "data": {
        "waitlist_id": "550e8400-e29b-41d4-a716-446655440006",
        "position": 42,
        "estimated_wait_time": "2-3 days",
        "event": {
            "id": "550e8400-e29b-41d4-a716-446655440001",
            "name": "Summer Music Festival"
        }
    }
}
```

---

## 🔔 WebSocket Endpoints

### Real-time Seat Updates
```javascript
// Connect to WebSocket
ws://localhost:8000/ws/events/{event_id}

// Subscribe to event
{
    "action": "subscribe",
    "event_id": "550e8400-e29b-41d4-a716-446655440001"
}

// Receive updates
{
    "type": "seat_update",
    "data": {
        "seat_id": "550e8400-e29b-41d4-a716-446655440003",
        "status": "booked",
        "available_seats": 12499
    }
}
```

---

## 🚨 Error Codes

| Code | Description | HTTP Status |
|------|-------------|------------|
| `AUTH_INVALID_CREDENTIALS` | Invalid email or password | 401 |
| `AUTH_TOKEN_EXPIRED` | JWT token has expired | 401 |
| `AUTH_UNAUTHORIZED` | User not authorized for this action | 403 |
| `BOOKING_SEATS_UNAVAILABLE` | Selected seats no longer available | 409 |
| `BOOKING_EXPIRED` | Booking has expired | 410 |
| `BOOKING_NOT_FOUND` | Booking does not exist | 404 |
| `EVENT_NOT_FOUND` | Event does not exist | 404 |
| `EVENT_SOLD_OUT` | Event is sold out | 409 |
| `PAYMENT_FAILED` | Payment processing failed | 402 |
| `RATE_LIMIT_EXCEEDED` | Too many requests | 429 |
| `VALIDATION_ERROR` | Request validation failed | 400 |
| `SERVER_ERROR` | Internal server error | 500 |

---

## 📋 Status Codes

### HTTP Status Codes Used
- `200 OK` - Successful GET, PUT
- `201 Created` - Successful POST creating new resource
- `204 No Content` - Successful DELETE
- `400 Bad Request` - Invalid request parameters
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Authenticated but not authorized
- `404 Not Found` - Resource not found
- `409 Conflict` - Resource conflict (e.g., seats already booked)
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error

---

## 🔄 Idempotency

For critical operations like bookings and payments, the API supports idempotency keys:

```http
POST /api/v1/bookings
Idempotency-Key: unique-request-id-123
```

The server will return the same response for repeated requests with the same idempotency key within 24 hours.

---

## 🧪 Testing

### Test Environment
```
Base URL: https://sandbox.api.evently.com
```

### Test Credentials
```json
{
    "email": "test@evently.com",
    "password": "TestPass123!"
}
```

### Test Credit Card
```json
{
    "number": "4242424242424242",
    "exp_month": 12,
    "exp_year": 2025,
    "cvc": "123"
}
```

---

## 📝 Changelog

### Version 1.0.0 (2024-01-15)
- Initial API release
- Basic authentication and authorization
- Event management endpoints
- Booking system with concurrency control
- Admin analytics dashboard
- WebSocket support for real-time updates