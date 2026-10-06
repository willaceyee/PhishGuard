# Gmail Sending Profile Design

## Purpose

Add one optional personal Gmail sending profile to PhishGuard while retaining
Mailpit as the default delivery method. Gmail delivery is for authorized
security-awareness simulations only and must preserve PhishGuard's recipient
approval, rate limits, duplicate prevention, simulation labeling, and
no-credential-collection controls.

## Scope

The first version supports exactly two delivery choices:

1. Local Mailpit, which remains the default.
2. One personal Gmail profile using `smtp.gmail.com:587`, STARTTLS, a full Gmail
   address, and a Google app password.

Multiple Gmail accounts, arbitrary SMTP servers, Google Workspace relay, OAuth,
scheduled delivery, and attachment support are out of scope.

## Data Model

Add a `SendingProfile` record with these fields:

- `profile_id`
- `name`
- `provider`, fixed to `gmail`
- `from_name`
- `from_email`
- `encrypted_app_password`
- `enabled`
- `last_tested_at`
- `last_test_succeeded`
- `created_at`
- `updated_at`

The database permits at most one Gmail profile. Mailpit remains configuration,
not a database profile.

Add an optional sending-profile relationship to campaigns. A missing profile
means Mailpit. Campaign API responses expose the selected delivery method and
safe profile metadata but never encrypted or decrypted credential material.

## Secret Handling

The Gmail app password is encrypted before database storage with a Fernet key
provided through `SENDING_PROFILE_ENCRYPTION_KEY`. The encryption key is never
stored in the database or returned through an API.

The backend removes spaces from an entered app password before encryption. API
responses report only whether a credential is configured. Editing profile
metadata preserves the existing credential unless the administrator explicitly
submits a replacement app password.

The normal Google account password is never requested or accepted. Passwords,
encrypted values, SMTP authentication payloads, and detailed credential errors
must not be written to application logs.

## Administrator Interface

Add a **Sending Profiles** page to the authenticated administrator workspace.
The page supports:

- creating the single Gmail profile;
- editing its name, display name, and Gmail address;
- replacing its app password;
- sending a connection-test message;
- enabling or disabling Gmail delivery;
- deleting the profile.

The page displays configured/tested status and the last successful test time. It
never displays the saved app password.

The campaign page offers Mailpit and the enabled Gmail profile. Mailpit is the
default for new campaigns. Selecting Gmail displays a persistent real-delivery
warning.

## Gmail Connection Test

The connection test:

1. validates that the sender uses a syntactically valid Gmail address;
2. decrypts the stored app password only inside the backend operation;
3. connects to `smtp.gmail.com:587`;
4. negotiates STARTTLS with certificate verification;
5. authenticates with the full Gmail address and app password;
6. sends a clearly labeled test message only to the same sender address, which
   must also belong to an administrator-approved PhishGuard user;
7. stores the test timestamp and success state.

The API returns a safe category for authentication, connection, or provider
rejection errors without returning raw SMTP details.

## Campaign Delivery Flow

Mailpit retains its existing behavior and limits.

Before Gmail delivery, the backend requires all of the following:

- email delivery is enabled globally;
- the Gmail profile is enabled and its most recent connection test succeeded;
- every pending recipient has `simulation_email_approved` enabled;
- the campaign has no more than 10 pending Gmail recipients;
- no more than 20 successful Gmail deliveries occurred during the preceding
  rolling hour;
- `PUBLIC_BASE_URL` uses HTTPS and its hostname is not localhost, a loopback
  address, or an obvious private-network address;
- at least one approved, undelivered recipient remains;
- the administrator enters the exact phrase `SEND N REAL EMAIL` or
  `SEND N REAL EMAILS`, as grammatically appropriate.

The preview identifies real Gmail delivery, the sender, allowed and blocked
recipients, previously delivered count, applicable limits, public URL status,
and confirmation phrase.

PhishGuard validates only the configured URL structure and host category. It does
not probe the URL from the backend because that would add an outbound-request and
SSRF risk. The administrator remains responsible for confirming that recipients
can reach the HTTPS deployment before real delivery.

Every Gmail message retains the mandatory `[SECURITY SIMULATION]` subject prefix,
simulation notice, and `X-PhishGuard-Simulation` header. The From address is the
authenticated Gmail address with the configured display name. Arbitrary sender
impersonation is not supported.

Messages are sent separately so each recipient receives only their unique
tracking link. Successful sends create `email_delivered` events. Failed attempts
create `email_failed` events. Existing delivery events continue to prevent
duplicate sends. A partial failure preserves successful delivery records and
does not retry those recipients automatically.

## Safety Boundaries

- Gmail delivery is opt-in per campaign; Mailpit is the default.
- Only individually approved recipients are eligible.
- Gmail is capped at 10 recipients per campaign and 20 successful messages per
  rolling hour.
- Gmail delivery is blocked when the tracking application is not publicly
  reachable over HTTPS.
- The simulated landing page does not request, transmit, inspect, or store real
  credentials.
- The application does not support arbitrary SMTP hosts, sender spoofing,
  attachments, or suppression of simulation labels.

## Error Handling

Administrator-facing errors distinguish these categories:

- missing or invalid profile configuration;
- invalid or expired Gmail app password;
- SMTP connection or TLS failure;
- Gmail rejection or throttling;
- unapproved recipients;
- campaign or hourly limit exceeded;
- unsafe or local public URL;
- no undelivered approved recipients.

Raw provider responses remain server-side and are sanitized before logging.

## Verification

Backend tests will verify:

- profile CRUD and the single-profile constraint;
- app-password encryption and decryption;
- secrets never appear in API responses or logs;
- metadata edits preserve the stored password;
- SMTP connection tests use STARTTLS and authenticate correctly through mocks;
- test messages can only target the approved sender address;
- Gmail delivery is blocked for untested or disabled profiles;
- unapproved recipients, unsafe URLs, duplicates, and limit violations are
  blocked;
- the 10-recipient and 20-per-hour Gmail limits;
- partial delivery failures preserve correct events;
- existing Mailpit behavior remains unchanged.

Frontend tests and checks will verify:

- profile creation and password replacement states;
- credential masking and absence from API-derived UI state;
- Mailpit default selection;
- Gmail warnings, limits, preview, and confirmation phrase;
- disabled states when any real-delivery safety check fails.

The complete backend test suite, coverage threshold, frontend lint, and frontend
production build must pass before the feature is considered complete.
