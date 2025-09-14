# Evently Backend Deployment Guide

## Quick Start

### Local Development
```bash
# 1. Clone repository
git clone <repository-url>
cd evently

# 2. Set up environment
cp .env.example .env
# Edit .env with your configuration

# 3. Start services with Docker
docker-compose up -d

# 4. Run database migrations
docker-compose exec app alembic upgrade head

# 5. Access application
# API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Manual Setup (Without Docker)

#### Prerequisites
- Python 3.11+
- PostgreSQL 14+
- Redis 6+

#### Steps
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up PostgreSQL
createdb evently
createdb evently_test

# 3. Start Redis
redis-server

# 4. Run migrations
alembic upgrade head

# 5. Start application
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Production Deployment

### Using Docker Compose
```bash
# 1. Build and start services
docker-compose -f docker-compose.yml up -d --build

# 2. Scale application
docker-compose up -d --scale app=3

# 3. View logs
docker-compose logs -f app
```

### Kubernetes Deployment
```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: evently-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: evently
  template:
    metadata:
      labels:
        app: evently
    spec:
      containers:
      - name: app
        image: evently-backend:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: evently-secrets
              key: database-url
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: evently-secrets
              key: redis-url
```

### Environment Variables

Required environment variables:
```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/evently
REDIS_URL=redis://localhost:6379

# Security
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret

# Services (Optional for basic deployment)
STRIPE_SECRET_KEY=sk_test_...
SENDGRID_API_KEY=SG...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
```

### Health Checks

The application provides health check endpoints:
- `/health/live` - Liveness probe
- `/health/ready` - Readiness probe

### Monitoring

Access monitoring tools:
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001
- pgAdmin: http://localhost:5050
- Redis Commander: http://localhost:8081

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Performance Tuning

1. **Database Connection Pool**
   - Configured in `app/core/database.py`
   - Default: 20 connections

2. **Redis Connection Pool**
   - Configured in `app/core/redis.py`
   - Default: 50 connections

3. **Worker Processes**
   - For production: `gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker`

### Security Checklist

- [ ] Change all default passwords
- [ ] Enable HTTPS/TLS
- [ ] Set secure SECRET_KEY
- [ ] Configure CORS properly
- [ ] Enable rate limiting
- [ ] Set up firewall rules
- [ ] Regular security updates

### Backup Strategy

```bash
# Database backup
pg_dump -U postgres evently > backup_$(date +%Y%m%d).sql

# Redis backup
redis-cli BGSAVE
```

### Troubleshooting

1. **Database Connection Issues**
   ```bash
   docker-compose logs postgres
   docker-compose exec postgres psql -U postgres
   ```

2. **Redis Connection Issues**
   ```bash
   docker-compose logs redis
   docker-compose exec redis redis-cli ping
   ```

3. **Application Logs**
   ```bash
   docker-compose logs -f app
   tail -f logs/app.log
   ```

### Load Testing

```bash
# Install locust
pip install locust

# Run load tests
locust -f tests/load_test.py --host=http://localhost:8000
```

### Support

For issues, check:
1. Application logs in `/logs`
2. Docker logs: `docker-compose logs`
3. Health endpoints: `/health/live` and `/health/ready`