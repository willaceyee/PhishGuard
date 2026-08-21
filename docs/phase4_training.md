# Phase 4 Training Guide

Phase 4 extends the simulation redirect into structured phishing-awareness content, a four-question quiz, stored completion records, and administrator reporting.

## Learner journey

The tracking token continues to identify the authorized campaign recipient without requiring a separate learner account.

```text
GET /training/<token>
  -> starts a training result if needed
  -> displays four awareness lessons

GET /quiz/<token>
  -> displays four multiple-choice questions
  -> does not expose correct answers in the page

POST /quiz/<token>
  -> validates that every answer is present and valid
  -> scores answers on the server
  -> marks training complete
  -> stores the latest quiz result
  -> records quiz_completed

GET /quiz/<token>/result
  -> displays the score and key lessons
```

## Awareness topics

1. Inspect the real sender address and link destination.
2. Pause when a message creates urgency or fear.
3. Verify requests through a known official channel.
4. Report suspicious messages to protect other users.

## Result behavior

- A training result is created when the learner first views the training page.
- It is marked complete when a valid quiz is submitted.
- One current quiz result is stored for each campaign recipient.
- Retaking the quiz replaces the previous score and completion time.
- The score stores correct answers and total questions; submitted answer choices are not retained.

## Administrator reporting

These endpoints require an administrator bearer token:

```text
GET /api/campaigns/<campaign_id>/training-results
GET /api/campaigns/<campaign_id>/quiz-results
```

Training results include start time, completion state, and completion time. Quiz results include score, total questions, percentage, and completion time.
