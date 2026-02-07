# Database Containers (Reproducible Setup)

This folder contains all configuration files required to deploy the database containers for this anonymized artifact on a new device.

## 📦 Contents

```
migration/
├── docker-compose.yml                    # Default environment configuration (locomo dataset)
├── docker-compose.longmemeval_s.yml      # LongMemEval-S dataset environment
├── docker-compose.longmemeval_m.yml      # LongMemEval-M dataset environment
├── docker/
│   ├── postgres/
│   │   ├── init.sql                      # Database initialization script
│   │   └── postgresql.conf               # PostgreSQL performance configuration
│   ├── redis/
│   │   └── redis.conf                    # Redis cache configuration
│   ├── qdrant/
│   │   └── config.yaml                   # Vector database configuration
│   ├── neo4j/
│   │   └── neo4j.conf                    # Graph database configuration
│   ├── elasticsearch/
│   │   └── elasticsearch.yml             # Search engine configuration (optional)
│   └── prometheus/
│       └── prometheus.yml                # Monitoring configuration (optional)
└── README.md                             # This file
```

## 🚀 Quick Start

### Prerequisites
- Docker >= 20.10
- Docker Compose >= 2.0

### 1. Deploy Default Environment (for locomo dataset)

```bash
# Enter the migration folder
cd migration

# Start all core services (databases only)
docker-compose up -d

# Verify container status
docker-compose ps
```

**Services started (new ports):**
- ✅ PostgreSQL (host port 15432)
- ✅ Redis (host port 16379)
- ✅ Qdrant (host port 16333/16334)
- ✅ Neo4j (host port 17474/17687)

### 2. Deploy LongMemEval-S Environment

```bash
cd migration

# Start the independent LongMemEval-S environment
docker-compose -f docker-compose.longmemeval_s.yml -p timem_longmemeval_s up -d

# Verify container status
docker-compose -f docker-compose.longmemeval_s.yml -p timem_longmemeval_s ps
```

**Port mapping (to avoid conflicts):**
- PostgreSQL: 5433
- Redis: 6380
- Qdrant: 6335/6336
- Neo4j: 7475/7688

### 3. Deploy LongMemEval-M Environment

```bash
cd migration

# Start the independent LongMemEval-M environment
docker-compose -f docker-compose.longmemeval_m.yml -p timem_longmemeval_m up -d

# Verify container status
docker-compose -f docker-compose.longmemeval_m.yml -p timem_longmemeval_m ps
```

**Port mapping (to avoid conflicts):**
- PostgreSQL: 5434
- Redis: 6381
- Qdrant: 6337/6338
- Neo4j: 7476/7689

## 🔧 Database Connection Information

### PostgreSQL
```
Host: localhost
Port: 15432 (default) / 5433 (longmemeval_s) / 5434 (longmemeval_m)
User: timem_user
Password: timem_password
Database: timem_db
```

### Redis
```
Host: localhost
Port: 16379 (default) / 6380 (longmemeval_s) / 6381 (longmemeval_m)
```

### Qdrant
```
HTTP: http://localhost:16333 (default) / 6335 (longmemeval_s) / 6337 (longmemeval_m)
gRPC: localhost:16334 (default) / 6336 (longmemeval_s) / 6338 (longmemeval_m)
```

### Neo4j
```
HTTP: http://localhost:17474 (default) / 7475 (longmemeval_s) / 7476 (longmemeval_m)
Bolt: bolt://localhost:17687 (default) / 7688 (longmemeval_s) / 7689 (longmemeval_m)
User: neo4j
Password: neo4j_password
```

## 📋 Common Commands

### View Logs
```bash
# Default environment
docker-compose logs -f postgres

# LongMemEval-S environment
docker-compose -f docker-compose.longmemeval_s.yml -p timem_longmemeval_s logs -f postgres
```

### Stop Services
```bash
# Default environment
docker-compose down

# LongMemEval-S environment
docker-compose -f docker-compose.longmemeval_s.yml -p timem_longmemeval_s down

# LongMemEval-M environment
docker-compose -f docker-compose.longmemeval_m.yml -p timem_longmemeval_m down
```

### Delete Data Volumes (Use with caution)
```bash
# Default environment
docker-compose down -v

# LongMemEval-S environment
docker-compose -f docker-compose.longmemeval_s.yml -p timem_longmemeval_s down -v
```

## 🔍 Troubleshooting

### Container fails to start
1. Check if Docker daemon is running: `docker ps`
2. View container logs: `docker-compose logs <service_name>`
3. Ensure ports are not in use: `netstat -an | findstr :<port>`

### Database connection failed
1. Confirm container health status: `docker-compose ps`
2. Wait for containers to fully start (first startup may take 30-60 seconds)
3. Check firewall settings

### Performance issues
- PostgreSQL configuration is optimized for full-text search
- Redis configuration supports 512MB memory cache
- Qdrant configuration supports high-concurrency vector operations

## 📝 Configuration File Description

### init.sql
- Create all necessary database tables
- Configure full-text search indexes
- Initialize demo data (4 expert roles)
- Create triggers and custom functions

### postgresql.conf
- Optimize connection count (300 concurrent)
- Optimize memory configuration (256MB shared_buffers)
- Full-text search specific configuration
- SSD performance optimization parameters

### redis.conf
- Maximum memory 512MB
- LRU eviction policy
- AOF persistence enabled
- Slow query monitoring

### config.yaml (Qdrant)
- HNSW index parameter optimization
- Concurrent read/write optimization
- Snapshot configuration
- Vector index performance tuning

## ⚠️ Important Notes

1. **Data Persistence**: All data is stored in Docker volumes; stopping containers will not lose data
2. **Environment Isolation**: The three environments use different networks and ports and can run simultaneously
3. **First Startup**: PostgreSQL initialization may take 30-60 seconds, please wait patiently
4. **Production Environment**: It is recommended to change default passwords and configuration parameters

## 🔗 Related Documentation

- PostgreSQL Documentation: https://www.postgresql.org/docs/
- Redis Documentation: https://redis.io/documentation
- Qdrant Documentation: https://qdrant.tech/documentation/
- Neo4j Documentation: https://neo4j.com/docs/
