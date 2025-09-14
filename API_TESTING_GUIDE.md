# 🧪 **EVENTLY API COMPLETE TESTING GUIDE**

## 📋 **PREREQUISITES**

- **Database**: PostgreSQL with password `sriman`
- **Redis**: Running on default port 6379
- **Python**: 3.11+ with all dependencies installed
- **Environment**: All environment variables configured

## ⚙️ **ENVIRONMENT SETUP**

Create `.env` file with:
```env
DATABASE_URL=postgresql+asyncpg://postgres:sriman@localhost:5432/evently
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=test_secret_key_1234567890123456789012345678901234567890
JWT_SECRET_KEY=jwt_test_key_1234567890123456789012345678901234567890
APP_ENV=development
DEBUG=true
```

## 🗄️ **DATABASE SETUP**

```bash
# Create database
createdb evently

# Run migrations
cd C:\Users\srima\Desktop\Challenge\evently
python migrations/add_production_constraints.py
```

## 🚀 **START APPLICATION**

```bash
cd C:\Users\srima\Desktop\Challenge\evently
set PYTHONPATH=%cd%
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🔐 **AUTHENTICATION ENDPOINTS TESTING**

### **1. User Registration**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"john.doe@example.com\",\"password\":\"SecurePass123!\",\"full_name\":\"John Doe\",\"phone\":\"+1234567890\"}"
```

**Expected Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "email": "john.doe@example.com",
    "full_name": "John Doe",
    "phone": "+1234567890",
    "role": "USER",
    "is_active": true,
    "created_at": "2024-01-15T10:30:00Z"
  }
}
```

### **2. User Login**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=john.doe@example.com&password=SecurePass123!"
```

**Expected Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "user": {
    "id": "123e4567-e89b-12d3-a456-426614174000",
    "email": "john.doe@example.com",
    "full_name": "John Doe",
    "role": "USER",
    "is_active": true
  }
}
```

### **3. Get Current User**

**Test Command:**
```bash
# Replace {ACCESS_TOKEN} with actual token from login
curl -X GET http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer {ACCESS_TOKEN}"
```

**Expected Response:**
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "email": "john.doe@example.com",
  "full_name": "John Doe",
  "phone": "+1234567890",
  "role": "USER",
  "is_active": true,
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### **4. Token Refresh**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"{REFRESH_TOKEN}\"}"
```

### **5. User Logout**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/logout \
  -H "Authorization: Bearer {ACCESS_TOKEN}"
```

**Expected Response:**
```json
{
  "message": "Successfully logged out"
}
```

---

## 🏛️ **ADMIN SETUP**

### **Create Admin User**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@evently.com\",\"password\":\"AdminPass123!\",\"full_name\":\"Admin User\",\"phone\":\"+1234567891\"}"
```

### **Admin Login**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin@evently.com&password=AdminPass123!"
```

---

## 🏢 **VENUE MANAGEMENT**

### **1. Create Venue (Admin)**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/admin/venues \
  -H "Authorization: Bearer {ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Grand Amphitheater\",\"address\":\"123 Music Ave, Los Angeles, CA\",\"city\":\"Los Angeles\",\"capacity\":5000}"
```

**Expected Response:**
```json
{
  "id": "venue-456",
  "name": "Grand Amphitheater",
  "address": "123 Music Ave, Los Angeles, CA",
  "city": "Los Angeles",
  "capacity": 5000,
  "created_at": "2024-01-15T11:00:00Z",
  "updated_at": "2024-01-15T11:00:00Z"
}
```

### **2. List Venues**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/venues?skip=0&limit=20"
```

---

## 🎪 **EVENT MANAGEMENT**

### **1. Create Event (Admin)**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/admin/events \
  -H "Authorization: Bearer {ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Summer Concert Festival\",\"description\":\"Amazing outdoor concert with top artists\",\"venue_id\":\"{VENUE_ID}\",\"start_time\":\"2024-08-15T20:00:00Z\",\"end_time\":\"2024-08-16T02:00:00Z\",\"capacity\":1000}"
```

**Expected Response:**
```json
{
  "id": "event-123e4567-e89b-12d3-a456-426614174000",
  "name": "Summer Concert Festival",
  "description": "Amazing outdoor concert with top artists",
  "venue_id": "venue-456",
  "start_time": "2024-08-15T20:00:00Z",
  "end_time": "2024-08-16T02:00:00Z",
  "capacity": 1000,
  "available_seats": 1000,
  "status": "upcoming",
  "created_by": "admin-user-id",
  "created_at": "2024-01-15T10:45:00Z",
  "updated_at": "2024-01-15T10:45:00Z"
}
```

### **2. List Events**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/events?skip=0&limit=10&status=upcoming"
```

**Expected Response:**
```json
[
  {
    "id": "event-123e4567-e89b-12d3-a456-426614174000",
    "name": "Summer Concert Festival",
    "description": "Amazing outdoor concert with top artists",
    "venue_id": "venue-456",
    "start_time": "2024-08-15T20:00:00Z",
    "end_time": "2024-08-16T02:00:00Z",
    "capacity": 1000,
    "available_seats": 1000,
    "status": "upcoming",
    "created_at": "2024-01-15T10:30:00Z",
    "updated_at": "2024-01-15T10:30:00Z",
    "venue": {
      "id": "venue-456",
      "name": "Grand Amphitheater",
      "city": "Los Angeles",
      "address": "123 Music Ave, Los Angeles, CA"
    }
  }
]
```

### **3. Get Event Details**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/events/{EVENT_ID}"
```

### **4. Get Event Seats**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/events/{EVENT_ID}/seats?section=VIP&status=available"
```

### **5. Update Event (Admin)**

**Test Command:**
```bash
curl -X PUT http://localhost:8000/api/v1/admin/events/{EVENT_ID} \
  -H "Authorization: Bearer {ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Summer Concert Festival - Updated\",\"description\":\"Updated description with more details\"}"
```

---

## 🎫 **BOOKING SYSTEM**

### **1. Create Booking**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/bookings \
  -H "Authorization: Bearer {USER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"event_id\":\"{EVENT_ID}\",\"seat_ids\":[\"{SEAT_ID_1}\",\"{SEAT_ID_2}\"]}"
```

**Expected Success Response:**
```json
{
  "id": "booking-789",
  "booking_code": "EVT12345678",
  "event": {
    "id": "event-123e4567-e89b-12d3-a456-426614174000",
    "name": "Summer Concert Festival",
    "start_time": "2024-08-15T20:00:00Z",
    "venue_name": "Grand Amphitheater",
    "venue_city": "Los Angeles"
  },
  "seats": [
    {
      "section": "VIP",
      "row": "A",
      "seat_number": "1",
      "price": 250.00
    }
  ],
  "total_amount": 500.00,
  "status": "pending",
  "expires_at": "2024-01-15T10:40:00Z",
  "created_at": "2024-01-15T10:35:00Z"
}
```

**Expected Error Responses:**

*Seats Unavailable (409):*
```json
{
  "detail": {
    "error_type": "seats_unavailable",
    "message": "Seats no longer available: ['seat-002']",
    "suggest_alternatives": true
  }
}
```

*Reservation Failed (423):*
```json
{
  "detail": {
    "error_type": "reservation_failed",
    "message": "Redis seat reservation failed for seats: ['seat-001']",
    "retry_after": 5
  }
}
```

### **2. Confirm Booking**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/bookings/{BOOKING_ID}/confirm \
  -H "Authorization: Bearer {USER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{\"payment_reference\":\"pi_1234567890abcdef\"}"
```

**Expected Response:**
```json
{
  "message": "Booking confirmed successfully",
  "booking_code": "EVT12345678"
}
```

### **3. Get User Bookings**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/bookings?skip=0&limit=10" \
  -H "Authorization: Bearer {USER_TOKEN}"
```

### **4. Get Booking Details**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/bookings/{BOOKING_ID}" \
  -H "Authorization: Bearer {USER_TOKEN}"
```

### **5. Cancel Booking**

**Test Command:**
```bash
curl -X POST http://localhost:8000/api/v1/bookings/{BOOKING_ID}/cancel \
  -H "Authorization: Bearer {USER_TOKEN}"
```

**Expected Response:**
```json
{
  "message": "Booking cancelled successfully",
  "booking_id": "booking-789"
}
```

---

## 📊 **ADMIN ANALYTICS**

### **1. Dashboard Analytics**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/admin/analytics/dashboard?start_date=2024-01-01&end_date=2024-01-31" \
  -H "Authorization: Bearer {ADMIN_TOKEN}"
```

**Expected Response:**
```json
{
  "summary": {
    "total_bookings": 1250,
    "total_revenue": 125000.50,
    "total_events": 45,
    "avg_capacity_utilization": 78.5,
    "cancellation_rate": 5.2
  },
  "popular_events": [
    {
      "id": "event-123",
      "name": "Summer Concert Festival",
      "booking_count": 150
    }
  ]
}
```

### **2. Get Users (Admin)**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/admin/users?skip=0&limit=50" \
  -H "Authorization: Bearer {ADMIN_TOKEN}"
```

---

## 🏥 **HEALTH CHECKS**

### **1. Basic Health Check**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/health"
```

**Expected Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T11:30:00Z",
  "version": "1.0.0",
  "environment": "development"
}
```

### **2. Detailed Health Check**

**Test Command:**
```bash
curl -X GET "http://localhost:8000/api/v1/health/detailed"
```

---

## 🧪 **COMPLETE TEST SEQUENCE**

### **Step-by-Step Testing Flow**

```bash
# 1. Register user
USER_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"testuser@example.com","password":"TestPass123!","full_name":"Test User"}')

# Extract token
USER_TOKEN=$(echo $USER_RESPONSE | jq -r '.access_token')

# 2. Register admin
ADMIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@evently.com","password":"AdminPass123!","full_name":"Admin User"}')

# Extract admin token
ADMIN_TOKEN=$(echo $ADMIN_RESPONSE | jq -r '.access_token')

# 3. Create venue
VENUE_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/admin/venues \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Venue","address":"123 Test St","city":"Test City","capacity":1000}')

# Extract venue ID
VENUE_ID=$(echo $VENUE_RESPONSE | jq -r '.id')

# 4. Create event
EVENT_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/admin/events \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Test Event\",\"venue_id\":\"$VENUE_ID\",\"start_time\":\"2024-12-25T20:00:00Z\",\"end_time\":\"2024-12-25T23:00:00Z\",\"capacity\":100}")

# Extract event ID
EVENT_ID=$(echo $EVENT_RESPONSE | jq -r '.id')

# 5. Get event seats
SEATS_RESPONSE=$(curl -s -X GET "http://localhost:8000/api/v1/events/$EVENT_ID/seats")

# Extract first two seat IDs
SEAT_ID_1=$(echo $SEATS_RESPONSE | jq -r '.[0].id')
SEAT_ID_2=$(echo $SEATS_RESPONSE | jq -r '.[1].id')

# 6. Create booking
BOOKING_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/bookings \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"event_id\":\"$EVENT_ID\",\"seat_ids\":[\"$SEAT_ID_1\",\"$SEAT_ID_2\"]}")

# Extract booking ID
BOOKING_ID=$(echo $BOOKING_RESPONSE | jq -r '.id')

# 7. Confirm booking
curl -X POST http://localhost:8000/api/v1/bookings/$BOOKING_ID/confirm \
  -H "Authorization: Bearer $USER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"payment_reference":"test_payment_123"}'

# 8. View booking history
curl -X GET "http://localhost:8000/api/v1/bookings" \
  -H "Authorization: Bearer $USER_TOKEN"
```

---

## ⚠️ **ERROR SCENARIOS TESTING**

### **1. Authentication Errors**

```bash
# Invalid credentials
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=invalid@email.com&password=wrongpassword"

# Expected: 401 Unauthorized
```

### **2. Authorization Errors**

```bash
# Access admin endpoint without admin token
curl -X POST http://localhost:8000/api/v1/admin/events \
  -H "Authorization: Bearer {USER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Event"}'

# Expected: 403 Forbidden
```

### **3. Validation Errors**

```bash
# Invalid email format
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"invalid-email","password":"test123"}'

# Expected: 422 Validation Error
```

### **4. Business Logic Errors**

```bash
# Try to book same seats twice
curl -X POST http://localhost:8000/api/v1/bookings \
  -H "Authorization: Bearer {USER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"event_id":"{EVENT_ID}","seat_ids":["{ALREADY_BOOKED_SEAT_ID}"]}'

# Expected: 409 Conflict or 423 Locked
```

### **5. Rate Limiting**

```bash
# Rapid booking attempts (11 requests in quick succession)
for i in {1..11}; do
  curl -X POST http://localhost:8000/api/v1/bookings \
    -H "Authorization: Bearer {USER_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"event_id":"{EVENT_ID}","seat_ids":["{SEAT_ID}"]}' &
done

# Expected: 429 Too Many Requests after 10th request
```

---

## 📊 **PERFORMANCE TESTING**

### **1. Concurrent Booking Test**

```bash
# Test concurrent bookings (simulate 10 users booking simultaneously)
EVENT_ID="your-event-id"
SEAT_IDS=("seat1" "seat2" "seat3" "seat4" "seat5" "seat6" "seat7" "seat8" "seat9" "seat10")

for i in {0..9}; do
  curl -X POST http://localhost:8000/api/v1/bookings \
    -H "Authorization: Bearer {USER_TOKEN_$i}" \
    -H "Content-Type: application/json" \
    -d "{\"event_id\":\"$EVENT_ID\",\"seat_ids\":[\"${SEAT_IDS[$i]}\"]}" &
done

wait
# Check that no double bookings occurred
```

### **2. Cache Performance Test**

```bash
# Test cache performance (100 requests to same endpoint)
for i in {1..100}; do
  curl -s -X GET "http://localhost:8000/api/v1/events" > /dev/null &
done

wait
# Monitor response times - should improve after first request due to caching
```

---

## 🔧 **TROUBLESHOOTING**

### **Common Issues:**

1. **Database Connection Error**:
   - Check PostgreSQL is running
   - Verify password is `sriman`
   - Database `evently` exists

2. **Redis Connection Error**:
   - Check Redis is running on port 6379
   - Verify Redis is accessible

3. **Authentication Errors**:
   - Check JWT tokens are valid and not expired
   - Verify environment variables are set

4. **Permission Errors**:
   - Ensure user has correct role for admin endpoints
   - Check token belongs to correct user

### **Debug Commands:**

```bash
# Check database connection
psql -U postgres -h localhost -d evently

# Check Redis connection
redis-cli ping

# Check application logs
tail -f app.log

# Verify environment variables
echo $DATABASE_URL
echo $SECRET_KEY
```

---

## 📝 **TEST RESULTS DOCUMENTATION**

For each test, document:
- ✅ **Status**: Pass/Fail
- 🕐 **Response Time**: Actual response time
- 📊 **Response Code**: HTTP status code
- 📝 **Notes**: Any issues or observations

### **Sample Test Results:**

| Endpoint | Status | Response Time | Status Code | Notes |
|----------|--------|---------------|-------------|-------|
| POST /auth/register | ✅ Pass | 245ms | 201 | User created successfully |
| POST /auth/login | ✅ Pass | 189ms | 200 | Token generated |
| GET /events | ✅ Pass | 67ms | 200 | Cache hit |
| POST /bookings | ✅ Pass | 423ms | 201 | Booking created with Saga |
| POST /bookings/{id}/confirm | ✅ Pass | 178ms | 200 | Booking confirmed |

This comprehensive testing guide ensures thorough validation of all API endpoints with proper error handling, performance testing, and documentation.