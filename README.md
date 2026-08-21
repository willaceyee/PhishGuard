# PhishGuard

PhishGuard is a phishing simulation and detection platform for organizational cybersecurity awareness.

## Phase 1 status

The project includes a Flask API, a React/Vite frontend, PostgreSQL-ready data models, JWT-protected administration APIs, an initial database design, and a CP2 feature checklist. Advanced machine learning and SHAP work is reserved for a later phase.

## Main modules

1. Admin authentication
2. User management
3. Phishing campaign management
4. Email template management
5. Tracking link and fake landing page
6. Awareness training and quiz module
7. Machine learning phishing detection
8. SHAP-based explanation
9. Analytics dashboard

## Technology stack

- Frontend: React with Vite
- Backend: Python Flask
- Database: PostgreSQL
- Machine learning: Scikit-learn and SHAP
- Deployment: Docker and Nginx

## Run locally

### Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
flask --app run.py init-db
python run.py
```

The API is available at `http://127.0.0.1:5000/api/health`.

Create the first administrator once with `POST /api/auth/bootstrap`, then obtain a bearer token from `POST /api/auth/login`. See [the Phase 2 API guide](docs/phase2_api.md) for endpoints and examples.

Run the backend tests with:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

The frontend is available at `http://localhost:5173` and calls the Flask health endpoint.
