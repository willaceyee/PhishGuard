# Phase 6 Analytics Dashboard Guide

Phase 6 combines simulation and training signals into a protected administrator dashboard.

## Dashboard API

`GET /api/dashboard/overview`

The endpoint requires an administrator bearer token and returns three sections:

- `summary`: system-wide totals and rates;
- `campaigns`: performance metrics for each campaign;
- `user_risks`: prioritized user-level risk records.

Repeated tracking events are deduplicated per campaign recipient. For example, opening the same tracking link several times counts as one unique click.

## Summary metrics

- Total campaigns, users, and recipient assignments
- Unique clicks and click-through rate
- Simulated form submissions and submission rate
- Training completions and completion rate
- Average quiz percentage
- Number of high-risk users

Rates use campaign recipient assignments as the denominator. An empty dashboard returns `0.0` rates rather than division errors.

## Campaign metrics

Each campaign includes:

- status and recipient count;
- unique clicks and click-through rate;
- unique simulated submissions and submission rate;
- training starts and completions;
- training completion rate;
- quiz-response count and average score.

## User risk method

Risk is a transparent prioritization aid, not a disciplinary verdict. Each campaign assignment receives up to 100 points:

| Factor | Points |
|---|---:|
| Clicked the simulation link | 25 |
| Submitted the simulated form | 45 |
| Training remains incomplete | 20 |
| Quiz knowledge gap | 0–10 |

The quiz component is proportional to the gap below 100%. A missing quiz receives 10 points. Scores are capped at 100.

Risk bands are:

- Low: 0–29
- Medium: 30–59
- High: 60–100

When a user appears in multiple campaigns, the dashboard shows the rounded average of their assignment-level risk scores. The API also returns the risk weights and thresholds so the interface and future reports can disclose the calculation.

## React administrator interface

The frontend now provides:

- administrator login;
- session-scoped JWT storage;
- automatic logout when authorization expires;
- summary metric cards;
- responsive campaign and user-risk tables;
- visual click-rate bars and risk bands;
- refresh, loading, error, and empty states.

Run both services during development:

```powershell
# Terminal 1
cd backend
.\venv\Scripts\Activate.ps1
python run.py

# Terminal 2
cd frontend
npm run dev
```

Open `http://localhost:5173` and sign in with the bootstrapped administrator account.
