# Port Logistics Backend Setup

Follow these commands to initialize the application from scratch.

## 1. Start Database (PostGIS)

Ensure Docker is running, then start the PostGIS container:

```bash
docker run -d \
  --name port_logistics_db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=port_logistics \
  -p 5432:5432 \
  postgis/postgis:16-3.4
```

## 2. Environment Setup

Run these commands from the `src/data_module_new` directory:

Create and activate a virtual environment:

```bash
# Create venv
python3 -m venv venv

# Activate venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure environment variables:

```bash
# Copy example env file
cp .env.example .env

# Edit .env and verify DATABASE_URL matches the Docker config above
# (Default in .env.example typically works with the Docker command above)
```

## 3. Database Initialization

Run Alembic migrations to create the schema:

```bash
alembic upgrade head
```

Seed the database with initial data (Gates, Zones, Users, etc.):

```bash
python scripts/seed_data.py
```

## 4. Run Application

Start the development server:

```bash
uvicorn app.main:app --reload
```

## Resources

- **API Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
