# Phase 3 Simulation Guide

Phase 3 provides a controlled phishing-awareness flow for users who have been deliberately assigned to a campaign. It does not send email and must only be used with organizational authorization.

## Safety and privacy behavior

- Each recipient receives a cryptographically random 256-bit tracking token.
- Invalid tokens reveal no campaign or user information.
- Public simulation responses disable browser caching and referrer transmission.
- The simulated form has no named fields, so browsers do not transmit entered values.
- The submission route deliberately does not inspect or retain form contents.
- Events contain only the recipient association, interaction type, and timestamp.
- No real authentication service or third-party brand is imitated.

## Assign campaign recipients

`POST /api/campaigns/<campaign_id>/recipients`

This endpoint requires an administrator bearer token.

```json
{
  "user_ids": [1, 2, 3]
}
```

The response contains one tracking URL for each newly assigned user. Existing assignments are skipped safely.

List recipient tracking URLs with:

```text
GET /api/campaigns/<campaign_id>/recipients
```

## Recipient journey

```text
GET /track/<token>
  -> records link_clicked
  -> redirects to /simulation/<token>

GET /simulation/<token>
  -> records landing_viewed
  -> displays the controlled simulated form

POST /simulation/<token>/submit
  -> records form_submitted without reading form values
  -> redirects to /training/<token>

GET /training/<token>
  -> records training_viewed
  -> displays an initial phishing-awareness explanation
```

The full training and quiz experience will be expanded in Phase 4.

## Review campaign events

Administrators can retrieve the campaign event timeline with:

```text
GET /api/campaigns/<campaign_id>/events
```

Current event types are:

- `link_clicked`
- `landing_viewed`
- `form_submitted`
- `training_viewed`
