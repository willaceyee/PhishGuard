# PhishGuard Database Schema

This is the Phase 1 logical draft. Primary and foreign keys will be implemented with SQLAlchemy during Phase 2.

## admins

- `admin_id` (primary key)
- `name`
- `email` (unique)
- `password_hash`
- `created_at`

## users

- `user_id` (primary key)
- `name`
- `email` (unique)
- `department`
- `role`
- `created_at`

## campaigns

- `campaign_id` (primary key)
- `campaign_name`
- `template_id` (foreign key)
- `created_by` (foreign key to admins)
- `scheduled_date`
- `status`
- `created_at`

## email_templates

- `template_id` (primary key)
- `template_name`
- `subject`
- `body`
- `category`
- `created_at`

## campaign_recipients

- `recipient_id` (primary key)
- `campaign_id` (foreign key)
- `user_id` (foreign key)
- `tracking_token` (unique)
- `created_at`

The combination of `campaign_id` and `user_id` is unique so a user is assigned to a campaign only once.

## tracking_events

- `event_id` (primary key)
- `recipient_id` (foreign key)
- `event_type`
- `occurred_at`

Tracking events store interaction types and timestamps only. Simulated form contents and credentials are never retained.

## training_results

- `training_id` (primary key)
- `user_id` (foreign key)
- `campaign_id` (foreign key)
- `completed`
- `completed_at`

## quiz_results

- `quiz_id` (primary key)
- `user_id` (foreign key)
- `campaign_id` (foreign key)
- `score`
- `completed_at`

## ml_predictions

- `prediction_id` (primary key)
- `input_url`
- `prediction_result`
- `confidence_score`
- `shap_explanation`
- `created_at`
