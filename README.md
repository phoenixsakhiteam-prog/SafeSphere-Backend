# SafeSphere Backend — FastAPI + Supabase

## Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/YOUR_USERNAME/SafeSphere-Backend.git
cd SafeSphere-Backend
pip install -r requirements.txt
```

### 2. Set Up Supabase
1. Go to [supabase.com](https://supabase.com) → New Project
2. Open **SQL Editor** → paste contents of `supabase_schema.sql` → Run
3. Go to **Settings → API** → copy your URL and service role key

### 3. Configure Environment
```bash
cp .env.example .env
# Edit .env with your Supabase credentials
```

### 4. Run
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Test
- Health check: http://localhost:8000
- API docs:     http://localhost:8000/docs

## API Endpoints

| Method | Endpoint              | Description           |
|--------|-----------------------|-----------------------|
| GET    | /                     | Health check          |
| POST   | /register             | Register user         |
| GET    | /users                | All users             |
| POST   | /alert                | Send SOS alert        |
| GET    | /alerts               | All alerts            |
| GET    | /alerts/{id}          | Single alert          |
| PUT    | /alerts/{id}/resolve  | Resolve alert         |
| DELETE | /alerts/{id}          | Delete alert          |
| GET    | /stats                | Dashboard stats       |
