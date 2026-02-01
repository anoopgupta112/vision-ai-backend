# Lead Generation Platform - Backend

Flask-based backend API for the Lead Generation platform with MongoDB, Redis, and background job processing.

## Features

- 🔐 **Authentication**: JWT-based user authentication
- 🎯 **Lead Generation**: Google Maps scraping with email extraction
- 💳 **Credits System**: User credits and transaction ledger
- 👨‍💼 **Admin Dashboard**: User management and job monitoring
- 🔄 **Background Jobs**: Redis Queue for async lead extraction
- 🐳 **Docker**: Fully containerized with Docker Compose

## Quick Start

### Local Development

```bash
# Clone repository
git clone https://github.com/yourusername/main_dashboard.git
cd main_dashboard

# Copy environment file
cp .env.example .env

# Start services
docker-compose up -d

# Check health
curl http://localhost:8000/health
```

### Environment Variables

Create `.env` file:

```env
FLASK_ENV=development
SECRET_KEY=your-secret-key-change-this
MONGODB_URI=mongodb://mongo:27017/lead_gen_dev
REDIS_URL=redis://redis:6379/0
FRONTEND_URL=http://localhost:5173
```

## Project Structure

```
app/
├── core/              # Shared: config, database, middleware
├── auth/              # Authentication (login, register)
├── lead_gen/          # Lead generation product
│   ├── jobs/          # Job management & scraping
│   ├── leads/         # Lead storage & export
│   └── credits/       # Credits system
├── admin/             # Admin APIs (users, jobs, stats)
└── payments/          # Payments (placeholder)
```

## API Endpoints

| Module | Prefix | Description |
|--------|--------|-------------|
| Auth | `/api/auth` | Login, register, profile |
| Lead Gen | `/api/lead_gen` | Jobs, leads, credits |
| Admin | `/api/admin` | User management, monitoring |

See [API.md](API.md) for full documentation.

## Services

- **Backend** (Flask): `http://localhost:8000`
- **Worker** (RQ): Background job processor
- **MongoDB**: Database on port `27017`
- **Redis**: Queue on port `6379`

## Development

```bash
# View logs
docker-compose logs -f backend
docker-compose logs -f worker

# Restart services
docker-compose restart backend worker

# Rebuild after code changes
docker-compose up -d --build

# Create admin user
docker-compose exec backend python create_admin_user.py
```

## Deployment

Automated deployment via GitHub Actions on push to `main` branch.

See [.github/README.md](.github/README.md) for deployment setup.

### Quick Deploy

1. **Setup server** (one-time):
   ```bash
   cd /root/deployed_repos
   git clone https://github.com/yourusername/main_dashboard.git
   cd main_dashboard
   cp .env.example .env
   # Edit .env with production values
   docker-compose up -d --build
   ```

2. **Configure GitHub Secrets**:
   - `SSH_HOST` - Server IP
   - `SSH_USER` - SSH username
   - `SSH_KEY` - Private SSH key

3. **Deploy**:
   ```bash
   git push origin main
   ```

## Testing

```bash
# Run tests
docker-compose exec backend python -m pytest

# Test health endpoint
curl http://localhost:8000/health

# Test authentication
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}'
```

## Adding New Modules

1. Create folder: `app/your_module/`
2. Add `model.py` (database operations)
3. Add `pipeline.py` (business logic)
4. Add `routes.py` or `views.py` (API endpoints)
5. Register blueprint in `app/__init__.py`

## Tech Stack

- **Framework**: Flask 3.0
- **Database**: MongoDB
- **Queue**: Redis + RQ
- **Scraping**: Playwright
- **Container**: Docker + Docker Compose

## License

MIT
