# Redis Installation Guide for Windows

## Option 1: Using WSL (Recommended)

1. **Install WSL** (if not already installed):
```bash
wsl --install
```

2. **Install Redis in WSL**:
```bash
# Open WSL terminal
sudo apt update
sudo apt install redis-server
sudo service redis-server start
```

3. **Verify Redis is running**:
```bash
redis-cli ping
# Should return: PONG
```

## Option 2: Native Windows using Memurai

1. **Download Memurai** (Redis for Windows):
   - Go to: https://www.memurai.com/get-memurai
   - Download the free Developer Edition
   - Run the installer

2. **Start Memurai Service**:
   - It starts automatically after installation
   - Or use: `net start memurai`

3. **Verify**:
```bash
redis-cli ping
```

## Option 3: Using Docker

1. **Install Docker Desktop**:
   - Download from: https://www.docker.com/products/docker-desktop/

2. **Run Redis container**:
```bash
docker run -d -p 6379:6379 --name redis redis:latest
```

## Option 4: Download Pre-built Windows Binary

1. **Download from GitHub**:
   - Go to: https://github.com/microsoftarchive/redis/releases
   - Download Redis-x64-3.2.100.zip
   - Extract to C:\Redis

2. **Start Redis**:
```bash
cd C:\Redis
redis-server.exe
```

3. **Open new terminal for Redis CLI**:
```bash
cd C:\Redis
redis-cli.exe
```

## Quick Test

After installation, test Redis:
```bash
redis-cli
> SET test "Hello Redis"
> GET test
> exit
```