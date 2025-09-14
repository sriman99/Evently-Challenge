#!/usr/bin/env python3
"""
Complete API Testing Script for Evently Backend
Tests all endpoints systematically with PostgreSQL password: sriman
"""

import requests
import json
import time
from datetime import datetime, timedelta
import uuid

# Configuration
BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"

class EventlyAPITester:
    def __init__(self):
        self.user_token = None
        self.admin_token = None
        self.venue_id = None
        self.event_id = None
        self.booking_id = None
        self.seat_ids = []
        self.test_results = []

    def log_test(self, test_name, success, response_code, response_time, notes=""):
        """Log test results"""
        status = "[PASS]" if success else "[FAIL]"
        self.test_results.append({
            "test": test_name,
            "status": status,
            "code": response_code,
            "time": f"{response_time:.0f}ms",
            "notes": notes
        })
        print(f"{status} | {test_name} | {response_code} | {response_time:.0f}ms | {notes}")

    def make_request(self, method, url, data=None, headers=None, expected_codes=[200, 201]):
        """Make HTTP request and measure performance"""
        start_time = time.time()

        try:
            if method == 'GET':
                response = requests.get(url, headers=headers)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers)

            response_time = (time.time() - start_time) * 1000
            success = response.status_code in expected_codes

            return response, response_time, success

        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            print(f"Request failed: {str(e)}")
            return None, response_time, False

    def test_health_check(self):
        """Test basic health check"""
        print("\n[HEALTH] TESTING HEALTH CHECKS")
        print("-" * 50)

        # Basic health check
        response, response_time, success = self.make_request('GET', f"{BASE_URL}/api/v1/health/status")

        if response and success:
            self.log_test("Health Check", True, response.status_code, response_time, "Service healthy")
        else:
            self.log_test("Health Check", False, response.status_code if response else 0, response_time, "Service unavailable")

    def test_authentication(self):
        """Test all authentication endpoints"""
        print("\n[AUTH] TESTING AUTHENTICATION")
        print("-" * 50)

        # 1. User Registration
        user_data = {
            "email": f"testuser_{uuid.uuid4().hex[:8]}@example.com",
            "password": "TestPass123!",
            "full_name": "Test User",
            "phone": "+1234567890"
        }

        response, response_time, success = self.make_request(
            'POST', f"{API_BASE}/auth/register", user_data
        )

        if success and response:
            user_response = response.json()
            self.user_token = user_response.get("access_token")
            self.log_test("User Registration", True, response.status_code, response_time, "User created with token")
        else:
            self.log_test("User Registration", False, response.status_code if response else 0, response_time, "Registration failed")
            return False

        # 2. User Login
        login_data = {
            "username": user_data["email"],
            "password": user_data["password"]
        }

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        login_payload = "&".join([f"{k}={v}" for k, v in login_data.items()])

        start_time = time.time()
        try:
            response = requests.post(f"{API_BASE}/auth/login", data=login_payload, headers=headers)
            response_time = (time.time() - start_time) * 1000
            success = response.status_code == 200

            if success:
                login_response = response.json()
                self.user_token = login_response.get("access_token")  # Update token
                self.log_test("User Login", True, response.status_code, response_time, "Login successful")
            else:
                self.log_test("User Login", False, response.status_code, response_time, "Login failed")
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            self.log_test("User Login", False, 0, response_time, f"Request failed: {str(e)}")

        # 3. Get Current User
        if self.user_token:
            headers = {"Authorization": f"Bearer {self.user_token}"}
            response, response_time, success = self.make_request(
                'GET', f"{API_BASE}/auth/me", headers=headers
            )

            if success:
                self.log_test("Get Current User", True, response.status_code, response_time, "User profile retrieved")
            else:
                self.log_test("Get Current User", False, response.status_code if response else 0, response_time, "Profile retrieval failed")

        # 4. Create Admin User
        admin_data = {
            "email": f"admin_{uuid.uuid4().hex[:8]}@evently.com",
            "password": "AdminPass123!",
            "full_name": "Admin User",
            "phone": "+1234567891"
        }

        response, response_time, success = self.make_request(
            'POST', f"{API_BASE}/auth/register", admin_data
        )

        if success and response:
            admin_response = response.json()
            self.admin_token = admin_response.get("access_token")
            self.log_test("Admin Registration", True, response.status_code, response_time, "Admin user created")
        else:
            self.log_test("Admin Registration", False, response.status_code if response else 0, response_time, "Admin creation failed")

        return True

    def test_venue_management(self):
        """Test venue management endpoints"""
        print("\n[VENUES] TESTING VENUE MANAGEMENT")
        print("-" * 50)

        if not self.admin_token:
            print("[SKIP] Skipping venue tests - no admin token")
            return False

        # 1. Create Venue
        venue_data = {
            "name": f"Test Venue {uuid.uuid4().hex[:8]}",
            "address": "123 Test Street, Test City, TC",
            "city": "Test City",
            "capacity": 1000
        }

        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response, response_time, success = self.make_request(
            'POST', f"{API_BASE}/admin/venues", venue_data, headers
        )

        if success and response:
            venue_response = response.json()
            self.venue_id = venue_response.get("id")
            self.log_test("Create Venue", True, response.status_code, response_time, f"Venue created: {self.venue_id}")
        else:
            self.log_test("Create Venue", False, response.status_code if response else 0, response_time, "Venue creation failed")
            return False

        # 2. List Venues
        response, response_time, success = self.make_request(
            'GET', f"{API_BASE}/venues?skip=0&limit=10"
        )

        if success:
            venues = response.json()
            self.log_test("List Venues", True, response.status_code, response_time, f"Found {len(venues)} venues")
        else:
            self.log_test("List Venues", False, response.status_code if response else 0, response_time, "Venue listing failed")

        return True

    def test_event_management(self):
        """Test event management endpoints"""
        print("\n[EVENTS] TESTING EVENT MANAGEMENT")
        print("-" * 50)

        if not self.admin_token or not self.venue_id:
            print("[SKIP] Skipping event tests - missing admin token or venue")
            return False

        # 1. Create Event
        future_date = datetime.now() + timedelta(days=30)
        event_data = {
            "name": f"Test Event {uuid.uuid4().hex[:8]}",
            "description": "Test event for API testing",
            "venue_id": self.venue_id,
            "start_time": future_date.isoformat() + "Z",
            "end_time": (future_date + timedelta(hours=3)).isoformat() + "Z",
            "capacity": 100
        }

        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response, response_time, success = self.make_request(
            'POST', f"{API_BASE}/admin/events", event_data, headers
        )

        if success and response:
            event_response = response.json()
            self.event_id = event_response.get("id")
            self.log_test("Create Event", True, response.status_code, response_time, f"Event created: {self.event_id}")
        else:
            self.log_test("Create Event", False, response.status_code if response else 0, response_time, "Event creation failed")
            return False

        # 2. List Events
        response, response_time, success = self.make_request(
            'GET', f"{API_BASE}/events?skip=0&limit=10&status=upcoming"
        )

        if success:
            events = response.json()
            self.log_test("List Events", True, response.status_code, response_time, f"Found {len(events)} events")
        else:
            self.log_test("List Events", False, response.status_code if response else 0, response_time, "Event listing failed")

        # 3. Get Event Details
        if self.event_id:
            response, response_time, success = self.make_request(
                'GET', f"{API_BASE}/events/{self.event_id}"
            )

            if success:
                self.log_test("Get Event Details", True, response.status_code, response_time, "Event details retrieved")
            else:
                self.log_test("Get Event Details", False, response.status_code if response else 0, response_time, "Event details failed")

        # 4. Get Event Seats
        if self.event_id:
            response, response_time, success = self.make_request(
                'GET', f"{API_BASE}/events/{self.event_id}/seats"
            )

            if success and response:
                seats = response.json()
                self.seat_ids = [seat["id"] for seat in seats[:5]]  # Get first 5 seats
                self.log_test("Get Event Seats", True, response.status_code, response_time, f"Found {len(seats)} seats")
            else:
                self.log_test("Get Event Seats", False, response.status_code if response else 0, response_time, "Seat retrieval failed")

        # 5. Update Event
        if self.event_id:
            update_data = {
                "name": event_data["name"] + " - Updated",
                "description": "Updated description for testing"
            }

            headers = {"Authorization": f"Bearer {self.admin_token}"}
            response, response_time, success = self.make_request(
                'PUT', f"{API_BASE}/admin/events/{self.event_id}", update_data, headers
            )

            if success:
                self.log_test("Update Event", True, response.status_code, response_time, "Event updated successfully")
            else:
                self.log_test("Update Event", False, response.status_code if response else 0, response_time, "Event update failed")

        return True

    def test_booking_system(self):
        """Test complete booking system"""
        print("\n[BOOKINGS] TESTING BOOKING SYSTEM")
        print("-" * 50)

        if not self.user_token or not self.event_id or not self.seat_ids:
            print("[SKIP] Skipping booking tests - missing prerequisites")
            return False

        # 1. Create Booking
        booking_data = {
            "event_id": self.event_id,
            "seat_ids": self.seat_ids[:2]  # Book first 2 seats
        }

        headers = {"Authorization": f"Bearer {self.user_token}"}
        response, response_time, success = self.make_request(
            'POST', f"{API_BASE}/bookings", booking_data, headers, [201, 409, 423]
        )

        if response and response.status_code == 201:
            booking_response = response.json()
            self.booking_id = booking_response.get("id")
            self.log_test("Create Booking", True, response.status_code, response_time, f"Booking created: {self.booking_id}")
        elif response and response.status_code in [409, 423]:
            self.log_test("Create Booking", True, response.status_code, response_time, "Expected conflict/lock response")
            # Try with different seats
            booking_data["seat_ids"] = self.seat_ids[2:4]
            response, response_time, success = self.make_request(
                'POST', f"{API_BASE}/bookings", booking_data, headers, [201]
            )
            if success and response:
                booking_response = response.json()
                self.booking_id = booking_response.get("id")
                self.log_test("Create Booking (Retry)", True, response.status_code, response_time, f"Booking created: {self.booking_id}")
        else:
            self.log_test("Create Booking", False, response.status_code if response else 0, response_time, "Booking creation failed")

        # 2. Get User Bookings
        if self.user_token:
            response, response_time, success = self.make_request(
                'GET', f"{API_BASE}/bookings", headers=headers
            )

            if success:
                bookings = response.json()
                self.log_test("Get User Bookings", True, response.status_code, response_time, f"Found {len(bookings)} bookings")
            else:
                self.log_test("Get User Bookings", False, response.status_code if response else 0, response_time, "Booking retrieval failed")

        # 3. Get Booking Details
        if self.booking_id:
            response, response_time, success = self.make_request(
                'GET', f"{API_BASE}/bookings/{self.booking_id}", headers=headers
            )

            if success:
                self.log_test("Get Booking Details", True, response.status_code, response_time, "Booking details retrieved")
            else:
                self.log_test("Get Booking Details", False, response.status_code if response else 0, response_time, "Booking details failed")

        # 4. Confirm Booking
        if self.booking_id:
            confirm_data = {"payment_reference": f"test_payment_{uuid.uuid4().hex[:8]}"}

            response, response_time, success = self.make_request(
                'POST', f"{API_BASE}/bookings/{self.booking_id}/confirm", confirm_data, headers
            )

            if success:
                self.log_test("Confirm Booking", True, response.status_code, response_time, "Booking confirmed")
            elif response and response.status_code == 410:
                self.log_test("Confirm Booking", True, response.status_code, response_time, "Expected expired booking response")
            else:
                self.log_test("Confirm Booking", False, response.status_code if response else 0, response_time, "Booking confirmation failed")

        # 5. Test Booking Cancellation (create new booking first)
        cancel_booking_data = {
            "event_id": self.event_id,
            "seat_ids": self.seat_ids[4:5]  # Book seat 5
        }

        response, response_time, success = self.make_request(
            'POST', f"{API_BASE}/bookings", cancel_booking_data, headers, [201, 409, 423]
        )

        if response and response.status_code == 201:
            cancel_booking_response = response.json()
            cancel_booking_id = cancel_booking_response.get("id")

            # Cancel the booking
            response, response_time, success = self.make_request(
                'POST', f"{API_BASE}/bookings/{cancel_booking_id}/cancel", headers=headers
            )

            if success:
                self.log_test("Cancel Booking", True, response.status_code, response_time, "Booking cancelled successfully")
            else:
                self.log_test("Cancel Booking", False, response.status_code if response else 0, response_time, "Booking cancellation failed")

        return True

    def test_admin_analytics(self):
        """Test admin analytics endpoints"""
        print("\n[ANALYTICS] TESTING ADMIN ANALYTICS")
        print("-" * 50)

        if not self.admin_token:
            print("[SKIP] Skipping analytics tests - no admin token")
            return False

        # 1. Dashboard Analytics
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")

        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response, response_time, success = self.make_request(
            'GET', f"{API_BASE}/admin/analytics/dashboard?start_date={start_date}&end_date={end_date}",
            headers=headers
        )

        if success:
            self.log_test("Dashboard Analytics", True, response.status_code, response_time, "Analytics retrieved")
        else:
            self.log_test("Dashboard Analytics", False, response.status_code if response else 0, response_time, "Analytics failed")

        # 2. Get Users
        response, response_time, success = self.make_request(
            'GET', f"{API_BASE}/admin/users?skip=0&limit=10", headers=headers
        )

        if success:
            users = response.json()
            self.log_test("Get Users (Admin)", True, response.status_code, response_time, f"Found {len(users)} users")
        else:
            self.log_test("Get Users (Admin)", False, response.status_code if response else 0, response_time, "User retrieval failed")

        return True

    def test_error_scenarios(self):
        """Test various error scenarios"""
        print("\n[ERROR-TESTS] TESTING ERROR SCENARIOS")
        print("-" * 50)

        # 1. Invalid Authentication
        response, response_time, success = self.make_request(
            'POST', f"{API_BASE}/auth/login",
            {"username": "invalid@email.com", "password": "wrongpass"},
            expected_codes=[401]
        )

        if response and response.status_code == 401:
            self.log_test("Invalid Login", True, response.status_code, response_time, "Expected authentication error")
        else:
            self.log_test("Invalid Login", False, response.status_code if response else 0, response_time, "Should return 401")

        # 2. Unauthorized Access
        response, response_time, success = self.make_request(
            'GET', f"{API_BASE}/admin/users", expected_codes=[401, 403]
        )

        if response and response.status_code in [401, 403]:
            self.log_test("Unauthorized Access", True, response.status_code, response_time, "Expected authorization error")
        else:
            self.log_test("Unauthorized Access", False, response.status_code if response else 0, response_time, "Should return 401/403")

        # 3. Validation Error
        response, response_time, success = self.make_request(
            'POST', f"{API_BASE}/auth/register",
            {"email": "invalid-email", "password": "123"},
            expected_codes=[422]
        )

        if response and response.status_code == 422:
            self.log_test("Validation Error", True, response.status_code, response_time, "Expected validation error")
        else:
            self.log_test("Validation Error", False, response.status_code if response else 0, response_time, "Should return 422")

        # 4. Not Found Error
        response, response_time, success = self.make_request(
            'GET', f"{API_BASE}/events/nonexistent-id", expected_codes=[404]
        )

        if response and response.status_code == 404:
            self.log_test("Not Found Error", True, response.status_code, response_time, "Expected not found error")
        else:
            self.log_test("Not Found Error", False, response.status_code if response else 0, response_time, "Should return 404")

    def test_rate_limiting(self):
        """Test rate limiting functionality"""
        print("\n[RATE-LIMIT] TESTING RATE LIMITING")
        print("-" * 50)

        if not self.user_token:
            print("[SKIP] Skipping rate limit tests - no user token")
            return

        # Make rapid requests to trigger rate limiting
        headers = {"Authorization": f"Bearer {self.user_token}"}
        rate_limit_hit = False

        for i in range(12):  # Try 12 requests rapidly
            response, response_time, success = self.make_request(
                'GET', f"{API_BASE}/events", headers=headers, expected_codes=[200, 429]
            )

            if response and response.status_code == 429:
                rate_limit_hit = True
                break

            time.sleep(0.1)  # Small delay between requests

        if rate_limit_hit:
            self.log_test("Rate Limiting", True, 429, response_time, "Rate limit triggered as expected")
        else:
            self.log_test("Rate Limiting", False, 200, 0, "Rate limit not triggered - may need adjustment")

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("[SUMMARY] TEST RESULTS SUMMARY")
        print("="*70)

        passed = sum(1 for result in self.test_results if "[PASS]" in result["status"])
        total = len(self.test_results)

        print(f"Total Tests: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {total - passed}")
        print(f"Success Rate: {(passed/total)*100:.1f}%")
        print()

        print(f"{'Test Name':<35} {'Status':<8} {'Code':<6} {'Time':<8} {'Notes':<20}")
        print("-" * 85)

        for result in self.test_results:
            print(f"{result['test']:<35} {result['status']:<8} {result['code']:<6} {result['time']:<8} {result['notes']:<20}")

    def run_all_tests(self):
        """Run complete test suite"""
        print("[START] STARTING EVENTLY API COMPREHENSIVE TESTING")
        print("=" * 70)
        print(f"Base URL: {BASE_URL}")
        print(f"Testing Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70)

        try:
            # Core functionality tests
            self.test_health_check()
            self.test_authentication()
            self.test_venue_management()
            self.test_event_management()
            self.test_booking_system()
            self.test_admin_analytics()

            # Error and edge case tests
            self.test_error_scenarios()
            self.test_rate_limiting()

            # Print comprehensive summary
            self.print_summary()

        except KeyboardInterrupt:
            print("\n[WARNING] Testing interrupted by user")
            self.print_summary()
        except Exception as e:
            print(f"\n[ERROR] Testing failed with error: {str(e)}")
            self.print_summary()

if __name__ == "__main__":
    print("EVENTLY API TESTING SCRIPT")
    print("=" * 50)
    print("Prerequisites:")
    print("- PostgreSQL running with password 'sriman'")
    print("- Redis running on default port")
    print("- Evently application running on localhost:8000")
    print("- Database 'evently' created and migrations run")
    print()

    print("Starting automated testing...")

    tester = EventlyAPITester()
    tester.run_all_tests()