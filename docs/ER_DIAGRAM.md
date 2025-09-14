# 📊 Database Schema Documentation

## Overview

The Evently platform uses PostgreSQL as its primary database with a comprehensive schema designed for scalability and data integrity. The database supports concurrent bookings, seat-level reservations, payment processing, and comprehensive analytics.

**Visual Diagram**: See [ER-Diagram.png](./ER-Diagram.png) for the complete entity-relationship diagram.

## Core Entities

### 👥 Users & Authentication
- **Users**: Core user management with role-based access control (USER, ADMIN, ORGANIZER)
- **Notifications**: User communication system for booking updates and alerts

### 🏢 Venues & Events
- **Venues**: Physical locations with capacity and layout configuration
- **Events**: Time-bound activities hosted at venues with seat management
- **Seats**: Individual seat inventory with section, row, and pricing details

### 🎫 Booking System
- **Bookings**: Main reservation records with status tracking and expiration
- **BookingSeats**: Junction table linking bookings to specific seats
- **Waitlists**: Queue management for sold-out events

### 💳 Payment Processing
- **Payments**: Payment transaction records with gateway integration
- **Transactions**: Financial ledger for all monetary activities

### 📊 Analytics
- **Analytics**: Event performance metrics and capacity utilization data

## Key Relationships

1. **User-centric**: Users can create multiple bookings, join waitlists, and receive notifications
2. **Event Management**: Venues host events, which contain seats available for booking
3. **Booking Flow**: Bookings reserve specific seats and generate payment records
4. **Concurrency Control**: Optimistic locking on seats prevents double-booking
5. **Analytics**: Events generate metrics for capacity utilization and booking patterns

## Design Decisions

### Scalability Features
- **UUIDs**: All primary keys use UUIDs for distributed scaling
- **Indexed Fields**: Strategic indexes on frequently queried fields (user_id, event_id, status)
- **JSON Storage**: Flexible metadata storage for venue layouts and analytics

### Data Integrity
- **Foreign Key Constraints**: Referential integrity across all relationships
- **Status Enums**: Controlled vocabularies for booking and payment statuses
- **Timestamps**: Complete audit trail with created_at/updated_at on all entities

### Concurrency Handling
- **Optimistic Locking**: Version control on critical entities (seats, bookings)
- **Status-based State Machines**: Clear booking lifecycle management
- **Atomic Operations**: Database transactions ensure consistency during booking flow

## Performance Optimizations

1. **Database Indexes**: Strategic indexes on query patterns
2. **Connection Pooling**: Async connection management for high concurrency
3. **Cache Layer**: Redis caching for seat availability and user sessions
4. **Query Optimization**: Efficient joins and selective loading patterns