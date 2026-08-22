# Phase 7 Automated Test Evidence

Verification date: 22 August 2026  
Environment: Windows, Python 3.12, Node.js 20

## Backend

```text
26 passed
Statement coverage: 88.55%
Required threshold: 85%
```

Coverage includes authentication, password changes, CRUD APIs, simulation tracking, credential-free form behavior, training, quiz scoring, URL feature extraction, model training, SHAP prediction, dashboard aggregation, risk scoring, security headers, and CORS restrictions.

Run the evidence again with:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
```

## Frontend

```text
ESLint: passed
Vite production build: passed
```

Run the evidence again with:

```powershell
cd frontend
npm run lint
npm run build
```

## Continuous integration

`.github/workflows/ci.yml` runs both verification groups for pushes and pull requests targeting `main`.

## Evidence limitations

- Usability outcomes are not included because participant testing has not yet occurred.
- Real-world model-performance claims are not included because the current dataset is synthetic development data.
- Interface screenshots are not included yet; use the anonymous evidence seeder and the procedure in the Phase 7 guide to generate them without exposing real users or tokens.
