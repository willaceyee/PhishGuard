# Final Report Screenshot Evidence

Captured on 10 November 2026 from a disposable SQLite database seeded by
`backend/scripts/seed_evidence.py`. All displayed identities use the reserved
`example.test` domain. The screenshots contain no passwords, personal email
addresses, real tracking links, or production URLs.

## Evidence Index

| File | Report evidence |
| --- | --- |
| `01-admin-login.jpg` | Administrator login screen with empty credential fields |
| `02-dashboard-analytics.jpg` | Campaign statistics, click-through rate, training completion, quiz performance, and user risk scores |
| `03-url-detection-shap.jpg` | Offline URL prediction and the five highest-impact SHAP factors for a reserved test URL |
| `04-awareness-training.jpg` | Five-part phishing-awareness lesson shown after a controlled simulation |
| `05-five-question-quiz.jpg` | Complete five-question awareness quiz and prior anonymized result |
| `06-passing-ci.jpg` | Pull request checks showing successful backend and frontend CI jobs |

## Capture Controls

- Application screenshots were captured at a 1440 by 900 browser viewport.
- The detector analyzed only a reserved `example.test` URL and did not visit it.
- The disposable database is excluded from Git and must not be replaced with a
  working administrator database.
- The CI screenshot was captured from pull request #1 on the feature branch.
