# PhishGuard

PhishGuard is a phishing simulation and detection platform for organizational cybersecurity awareness.

## Phase 1 status

The project includes a Flask API, a React/Vite frontend, PostgreSQL-ready data models, JWT-protected administration APIs, and a controlled phishing-awareness simulation flow. Advanced machine learning and SHAP work is reserved for a later phase.

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
flask --app run.py upgrade-db
python run.py
```

The API is available at `http://127.0.0.1:5000/api/health`.

Create the first administrator once with `POST /api/auth/bootstrap`, then obtain a bearer token from `POST /api/auth/login`. See [the Phase 2 API guide](docs/phase2_api.md) for endpoints and examples.

Phase 3 tracking and simulation endpoints are documented in [the Phase 3 simulation guide](docs/phase3_simulation.md). The simulated landing page records interaction types only and never transmits or stores entered credentials.

Phase 4 awareness content, quiz scoring, completion storage, and reporting are documented in [the Phase 4 training guide](docs/phase4_training.md).

Phase 5 provides offline URL feature extraction, Random Forest training, a protected prediction API, and SHAP explanations. See [the Phase 5 ML guide](docs/phase5_ml_detection.md).

Phase 6 adds a responsive React administrator dashboard with campaign metrics, click and submission rates, training completion, quiz performance, and transparent user risk scores. See [the Phase 6 dashboard guide](docs/phase6_dashboard.md).

Phase 7 quality assurance includes automated CI, backend coverage enforcement, security checks, usability-study materials, and a real-world model-evaluation protocol. See [the Phase 7 testing guide](docs/phase7_testing_report.md).

The React administrator workspace now exposes the simulation and detection features directly: manage users and templates, create campaigns, assign recipients, copy tracking links, and analyze URLs with SHAP explanations. See [the administrator workspace guide](docs/admin_workspace.md).

Safe email delivery is disabled by default and uses local Mailpit by default.
An optional encrypted personal Gmail profile sends real email only to approved
recipients, with HTTPS tracking, fixed Gmail limits, exact preview confirmation,
visible simulation labels, and delivery event recording. See
[the safe email delivery guide](docs/safe_email_delivery.md).

For Gmail setup, generate a Fernet key locally from `backend`:

```powershell
.\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep the output secret and set it as `SENDING_PROFILE_ENCRYPTION_KEY` in the
backend environment. For an existing database, back it up and run
`flask --app run.py upgrade-db` once, then restart Flask with the configured key,
`MAIL_DELIVERY_ENABLED=1`, and a publicly reachable HTTPS `PUBLIC_BASE_URL`.
On **Users**, create and approve a user matching the Gmail sender. On **Sending
Profiles**, create the profile using a Google app password, select **Send test**
(which sends real email to that approved sender only), and **Enable** it. Never
enter the normal Google password. Choose Gmail explicitly when creating a
campaign; Mailpit remains the default. Follow the guide's limits, confirmation,
and credential-recovery instructions before sending.

### Train the development model

```powershell
cd backend
.\venv\Scripts\python.exe -m app.ml.prepare_demo_data
.\venv\Scripts\python.exe -m app.ml.train
```

The generated `.joblib` model is intentionally ignored by Git and must be trained locally or supplied through `ML_MODEL_PATH`.

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
