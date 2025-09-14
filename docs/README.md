# Evently Documentation

This folder contains all project documentation required for the Evently challenge deliverables.

## 📋 Challenge Deliverables

### Primary Deliverables:
- **[Evently-Architecture.png](./Evently-Architecture.png)** - 🎯 High-level system architecture diagram
- **[ER-Diagram.png](./ER-Diagram.png)** - 🎯 Entity-relationship database schema
- **[API_DOCUMENTATION.md](./API_DOCUMENTATION.md)** - Complete API endpoint documentation
- **[CHALLENGE_DELIVERABLES.md](./CHALLENGE_DELIVERABLES.md)** - Deliverables checklist and compliance

### Supporting Documentation:
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** - Detailed architecture explanations and design decisions
- **[ER_DIAGRAM.md](./ER_DIAGRAM.md)** - Detailed database schema documentation

### Additional Resources:
- **[API_TESTING_GUIDE.md](./API_TESTING_GUIDE.md)** - Step-by-step testing instructions for evaluators
- **[Evently_API_Postman_Collection.json](./Evently_API_Postman_Collection.json)** - Postman collection for API testing

## 🚀 Quick Links

- **Live API**: https://evently-challenge-production.up.railway.app/
- **Swagger UI**: https://evently-challenge-production.up.railway.app/docs
- **Demo Credentials**: admin@evently.com / Admin123! | demo@evently.com / Demo123!

## 📊 System Highlights

- **Concurrency**: Optimistic locking + Redis seat reservations
- **Scalability**: Async FastAPI + PostgreSQL + Redis caching
- **Architecture**: Saga pattern for distributed transactions
- **Features**: Seat-level booking, notifications, analytics, waitlists
- **Security**: JWT authentication + role-based access control