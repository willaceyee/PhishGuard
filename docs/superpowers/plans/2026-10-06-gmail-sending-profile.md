# Gmail Sending Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one encrypted personal-Gmail sending profile while keeping Mailpit as the default and enforcing approved-recipient, HTTPS, rate-limit, confirmation, and no-credential-collection controls.

**Architecture:** A `SendingProfile` model owns encrypted Gmail credentials and safe connection-test metadata; campaigns optionally reference that profile, with a null reference meaning Mailpit. A focused sending-profile service handles encryption and Gmail STARTTLS authentication, while the existing delivery service selects the transport and applies channel-specific controls without weakening shared safety checks.

**Tech Stack:** Flask 3.1, Flask-SQLAlchemy, Flask-JWT-Extended, Python `smtplib`, `cryptography.fernet`, React/Vite, Vitest, React Testing Library, pytest.

**Spec:** `docs/superpowers/specs/2026-10-06-gmail-sending-profile-design.md`

## Global Constraints

- Support exactly one personal Gmail profile and one built-in Mailpit delivery choice.
- Mailpit remains the default for new and existing campaigns.
- Gmail uses `smtp.gmail.com:587`, STARTTLS with certificate verification, the complete Gmail address, and a Google app password.
- Gmail delivery is capped at 10 recipients per campaign and 20 successful Gmail messages per rolling hour.
- Every Gmail recipient must have `simulation_email_approved=true`.
- Gmail requires an HTTPS `PUBLIC_BASE_URL` whose host is not localhost, loopback, or an obvious private-network address; the backend must not probe that URL.
- Gmail confirmation text is exactly `SEND N REAL EMAIL` or `SEND N REAL EMAILS`.
- Every message retains the `[SECURITY SIMULATION]` prefix, simulation notice, and `X-PhishGuard-Simulation` header.
- Never request or store the normal Google password; never return or log plaintext/encrypted app-password material.
- Do not add arbitrary SMTP hosts, sender spoofing, attachments, OAuth, Workspace relay, scheduling, or multiple Gmail profiles.
- Preserve unrelated working-tree changes and existing Mailpit, tracking, training, analytics, and ML behavior.

## File Structure

- Create `backend/app/sending_profiles.py`: encryption, safe serialization, Gmail validation, connection testing, and profile API blueprint.
- Create `backend/tests/test_sending_profiles.py`: profile CRUD, encryption, secret non-disclosure, and SMTP test behavior.
- Create `frontend/src/pages/SendingProfiles.jsx`: the single-profile administrator form and status card.
- Create `frontend/src/test/setup.js`: DOM test setup.
- Create `frontend/src/pages/SendingProfiles.test.jsx`: profile UI behavior.
- Create `frontend/src/pages/Campaigns.test.jsx`: Mailpit default and Gmail-warning behavior.
- Modify `backend/app/models.py`: `SendingProfile`, campaign reference, and delivery-channel event metadata.
- Modify `backend/app/email_delivery.py`: transport selection, Gmail safety checks, channel-specific limits, and SMTP delivery.
- Modify `backend/app/routes.py`: accept and serialize campaign profile selection.
- Modify `backend/app/simulation.py`: return safe delivery error categories through existing preview/send endpoints.
- Modify `backend/app/__init__.py`: register the sending-profile blueprint and extend the built-in schema upgrade.
- Modify `backend/config.py`, `backend/.env.example`, and `backend/requirements.txt`: encryption key and Gmail limits.
- Modify `backend/tests/test_resources.py` and `backend/tests/test_simulation.py`: campaign selection and Gmail delivery coverage.
- Modify `frontend/src/services/api.js`: profile API functions and campaign profile field.
- Modify `frontend/src/pages/Dashboard.jsx`: sidebar/page registration.
- Modify `frontend/src/pages/Campaigns.jsx`: transport selector, Gmail preview, warning, and confirmation behavior.
- Modify `frontend/src/styles.css`: profile status and real-delivery warning styles.
- Modify `frontend/package.json`: Vitest and Testing Library scripts/dependencies.
- Modify `README.md` and `docs/safe_email_delivery.md`: setup, key generation, Gmail app-password usage, limits, and safety boundaries.

---

### Task 1: Encrypted Sending-Profile Model and Schema Upgrade

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/app/models.py`
- Modify: `backend/app/__init__.py`
- Create: `backend/app/sending_profiles.py`
- Create: `backend/tests/test_sending_profiles.py`

**Interfaces:**
- Produces: `SendingProfile.to_safe_dict() -> dict`
- Produces: `encrypt_app_password(value: str) -> str`
- Produces: `decrypt_app_password(value: str) -> str`
- Produces: nullable `Campaign.sending_profile_id` and `Campaign.sending_profile`
- Produces: nullable `TrackingEvent.delivery_channel`

- [ ] **Step 1: Add failing model and encryption tests**

Create `backend/tests/test_sending_profiles.py` with tests that construct a Gmail profile, verify the database stores ciphertext, verify decryption returns the normalized app password, and verify `to_safe_dict()` contains `credential_configured=True` but neither secret field.

```python
from app.extensions import db
from app.models import SendingProfile
from app.sending_profiles import decrypt_app_password, encrypt_app_password


def test_app_password_is_encrypted_and_never_serialized(app):
    with app.app_context():
        encrypted = encrypt_app_password("abcd efgh ijkl mnop")
        profile = SendingProfile(
            name="Personal Gmail",
            provider="gmail",
            from_name="Security Awareness",
            from_email="owner@gmail.com",
            encrypted_app_password=encrypted,
        )
        db.session.add(profile)
        db.session.commit()

        assert encrypted != "abcdefghijklmnop"
        assert decrypt_app_password(encrypted) == "abcdefghijklmnop"
        serialized = profile.to_safe_dict()
        assert serialized["credential_configured"] is True
        assert "encrypted_app_password" not in serialized
        assert "app_password" not in serialized
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest tests/test_sending_profiles.py -q
```

Expected: collection/import failure because `SendingProfile` and encryption helpers do not exist.

- [ ] **Step 3: Add dependency and configuration**

Add `cryptography==46.0.3` to `backend/requirements.txt`. Add these configuration values:

```python
SENDING_PROFILE_ENCRYPTION_KEY = os.getenv("SENDING_PROFILE_ENCRYPTION_KEY", "")
GMAIL_MAX_CAMPAIGN_RECIPIENTS = 10
GMAIL_MAX_EMAILS_PER_HOUR = 20
```

In `TestConfig`, generate a valid isolated Fernet key:

```python
from cryptography.fernet import Fernet

SENDING_PROFILE_ENCRYPTION_KEY = Fernet.generate_key().decode()
```

Document empty development values in `.env.example`; do not commit a generated real key.

- [ ] **Step 4: Implement minimal model and crypto helpers**

Add `SendingProfile` with a database uniqueness constraint on `provider`, safe serialization, and UTC timestamps. Add nullable `Campaign.sending_profile_id` and `TrackingEvent.delivery_channel`.

In `backend/app/sending_profiles.py`, implement:

```python
def cipher():
    value = current_app.config["SENDING_PROFILE_ENCRYPTION_KEY"]
    if not value:
        raise RuntimeError("Sending-profile encryption is not configured")
    return Fernet(value.encode())


def encrypt_app_password(value):
    normalized = "".join(value.split())
    if not normalized:
        raise ValueError("Google app password is required")
    return cipher().encrypt(normalized.encode()).decode()


def decrypt_app_password(value):
    return cipher().decrypt(value.encode()).decode()
```

Extend `upgrade-db` to create `sending_profiles` with `SendingProfile.__table__.create(checkfirst=True)`, then add nullable `sending_profile_id` to `campaigns` and nullable `delivery_channel` to `tracking_events` only when absent. Keep the existing user-column migration intact.

- [ ] **Step 5: Install dependency and run focused tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pytest tests/test_sending_profiles.py -q
```

Expected: PASS; no secret appears in failure output.

- [ ] **Step 6: Commit the storage foundation**

```powershell
git add backend/requirements.txt backend/config.py backend/.env.example backend/app/models.py backend/app/__init__.py backend/app/sending_profiles.py backend/tests/test_sending_profiles.py
git commit -m "Add encrypted Gmail sending profile storage"
```

### Task 2: Sending-Profile API and Safe Gmail Connection Test

**Files:**
- Modify: `backend/app/sending_profiles.py`
- Modify: `backend/app/__init__.py`
- Modify: `backend/tests/test_sending_profiles.py`

**Interfaces:**
- Consumes: `SendingProfile`, `encrypt_app_password`, `decrypt_app_password`
- Produces: `sending_profiles` Flask blueprint
- Produces: `GET /api/sending-profile`
- Produces: `POST /api/sending-profile`
- Produces: `PATCH /api/sending-profile`
- Produces: `DELETE /api/sending-profile`
- Produces: `POST /api/sending-profile/test`
- Produces: `test_gmail_profile(profile: SendingProfile) -> None`

- [ ] **Step 1: Write failing authenticated API tests**

Cover unauthenticated rejection, creation, single-profile conflict, safe retrieval, metadata edit preserving ciphertext, explicit password replacement, enable/disable, deletion, and invalid non-Gmail addresses. Assert no response contains either plaintext or ciphertext.

```python
def test_profile_crud_never_returns_secret(client, auth_headers):
    created = client.post("/api/sending-profile", headers=auth_headers, json={
        "name": "Personal Gmail",
        "from_name": "Security Awareness",
        "from_email": "owner@gmail.com",
        "app_password": "abcd efgh ijkl mnop",
    })
    assert created.status_code == 201
    body = created.get_json()["profile"]
    assert body["credential_configured"] is True
    assert "password" not in str(body).lower()
    assert client.post("/api/sending-profile", headers=auth_headers, json={
        "name": "Second", "from_name": "Second",
        "from_email": "second@gmail.com", "app_password": "abcdefghijklmnop",
    }).status_code == 409
```

- [ ] **Step 2: Run API tests and verify 404 failures**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_sending_profiles.py -q
```

Expected: FAIL because the blueprint routes are not registered.

- [ ] **Step 3: Implement validation and CRUD routes**

Use a strict `@gmail.com` address check for this personal-Gmail version. All routes require `@jwt_required()`. POST requires all fields; PATCH permits `name`, `from_name`, `from_email`, `enabled`, and optional non-empty `app_password`. DELETE removes only the single stored profile. Register the blueprint in `create_app()`.

- [ ] **Step 4: Add failing Gmail connection-test tests**

Create an approved user whose email exactly matches the profile sender. Mock `smtplib.SMTP` and assert this call order and behavior:

```python
smtp_class.assert_called_once_with("smtp.gmail.com", 587, timeout=10)
smtp.starttls.assert_called_once()
smtp.login.assert_called_once_with("owner@gmail.com", "abcdefghijklmnop")
smtp.send_message.assert_called_once()
```

Also verify missing approved sender returns 403, `SMTPAuthenticationError` returns safe code `gmail_authentication_failed`, other `SMTPException` returns `gmail_provider_rejected`, and `OSError` returns `gmail_connection_failed`. Assert raw exception strings never appear in responses.

- [ ] **Step 5: Implement connection testing**

Implement `test_gmail_profile(profile)` with `ssl.create_default_context()`, `SMTP.starttls(context=context)`, login, and one clearly labeled test message to `profile.from_email`. Route-level code must verify a matching approved `User` before decrypting. Store `last_tested_at`, `last_test_succeeded`, and commit after every test result.

- [ ] **Step 6: Run focused tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_sending_profiles.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit the profile API**

```powershell
git add backend/app/sending_profiles.py backend/app/__init__.py backend/tests/test_sending_profiles.py
git commit -m "Add Gmail sending profile API"
```

### Task 3: Campaign Delivery-Profile Selection

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/routes.py`
- Modify: `backend/tests/test_resources.py`

**Interfaces:**
- Consumes: nullable `Campaign.sending_profile_id`
- Produces: `Campaign.to_dict()` keys `delivery_method` and `sending_profile`
- Produces: campaign POST/PATCH input `sending_profile_id: int | null`

- [ ] **Step 1: Write failing campaign selection tests**

Create a profile fixture through the API. Verify a new campaign without `sending_profile_id` serializes as Mailpit, a campaign with the profile serializes safe metadata, PATCH can switch both directions, and unknown/non-numeric profile IDs return 404/400.

```python
assert campaign["delivery_method"] == "mailpit"
assert campaign["sending_profile"] is None

gmail = client.patch(
    f"/api/campaigns/{campaign_id}",
    headers=auth_headers,
    json={"sending_profile_id": profile_id},
).get_json()["campaign"]
assert gmail["delivery_method"] == "gmail"
assert gmail["sending_profile"]["profile_id"] == profile_id
```

- [ ] **Step 2: Run focused resource tests and verify failure**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_resources.py -q
```

Expected: FAIL because campaign serialization and request handling omit the profile.

- [ ] **Step 3: Implement selection and safe serialization**

Add the `sending_profile` relationship and serialize only `profile.to_safe_dict()`. Add one helper in `routes.py` that accepts `None` or an integer ID and verifies the referenced profile exists. Do not require enabled/tested status until preview/send so administrators can configure campaigns before testing the profile.

- [ ] **Step 4: Run focused tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_resources.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit campaign selection**

```powershell
git add backend/app/models.py backend/app/routes.py backend/tests/test_resources.py
git commit -m "Allow campaigns to select Gmail delivery"
```

### Task 4: Gmail Campaign Preview and Delivery Safety Controls

**Files:**
- Modify: `backend/app/email_delivery.py`
- Modify: `backend/app/simulation.py`
- Modify: `backend/tests/test_simulation.py`

**Interfaces:**
- Consumes: `Campaign.sending_profile`, `decrypt_app_password()`
- Produces: `delivery_preview(campaign) -> dict` with `delivery_method`, `real_delivery`, limits, profile metadata, and channel-specific phrase
- Produces: `send_campaign(campaign) -> int` selecting Mailpit or Gmail
- Produces: `public_gmail_url_is_safe() -> bool`

- [ ] **Step 1: Add failing preview safety tests**

Test that Mailpit output remains unchanged. For Gmail, test disabled/untested profiles, unapproved recipients, `http://`, localhost, loopback IPv4/IPv6, and private IPv4 hosts. Verify `https://training.example.org` is structurally accepted without any network request.

```python
assert preview["delivery_method"] == "gmail"
assert preview["real_delivery"] is True
assert preview["confirmation_phrase"] == "SEND 1 REAL EMAIL"
assert preview["campaign_recipient_limit"] == 10
assert preview["hourly_delivery_limit"] == 20
```

- [ ] **Step 2: Run Gmail preview tests and verify failure**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_simulation.py -q -k gmail
```

Expected: FAIL because delivery preview has only Mailpit semantics.

- [ ] **Step 3: Implement transport-aware preview and URL validation**

Use `ipaddress.ip_address()` when the hostname is an IP and reject loopback, private, link-local, reserved, or unspecified addresses. Reject hostname values `localhost` and names ending `.local`. Require `https` for Gmail. Do not make HTTP or DNS calls.

Return these stable preview fields:

```python
{
    "delivery_method": "gmail",
    "real_delivery": True,
    "profile": campaign.sending_profile.to_safe_dict(),
    "delivery_enabled": True,
    "profile_ready": profile.enabled and profile.last_test_succeeded,
    "public_url_safe": public_gmail_url_is_safe(),
    "campaign_recipient_limit": 10,
    "hourly_delivery_limit": 20,
    "confirmation_phrase": "SEND 1 REAL EMAIL",
}
```

- [ ] **Step 4: Add failing Gmail send tests**

Mock SMTP and verify STARTTLS, login, separate messages, correct sender/display name, unique tracking links, and delivery events with `delivery_channel="gmail"`. Add tests for 11 recipients, 20 prior Gmail deliveries in the rolling hour, wrong confirmation, disabled/untested profile, duplicate prevention, and partial failure.

For partial failure, make the second `send_message()` raise `SMTPException`; assert the first recipient has `email_delivered/gmail`, the second has `email_failed/gmail`, and retry preview excludes only the first recipient.

- [ ] **Step 5: Implement Gmail delivery with shared safety checks**

Keep `message_for(campaign, recipient)` shared but select the From identity by transport. Keep one SMTP connection per campaign, call STARTTLS only for Gmail, and commit after each successful recipient exactly as the Mailpit flow currently does. Count hourly Gmail sends with:

```python
db.select(db.func.count(TrackingEvent.event_id)).where(
    TrackingEvent.event_type == "email_delivered",
    TrackingEvent.delivery_channel == "gmail",
    TrackingEvent.occurred_at >= since,
)
```

Record `delivery_channel="mailpit"` for new Mailpit events while treating historical null-channel `email_delivered` events as delivered for duplicate prevention.

Map safe exceptions in `simulation.py` to 400, 403, or 502 without raw SMTP text.

- [ ] **Step 6: Run delivery tests and full backend suite**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_simulation.py -q
.\venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass and coverage remains at least 85%.

- [ ] **Step 7: Commit Gmail delivery**

```powershell
git add backend/app/email_delivery.py backend/app/simulation.py backend/tests/test_simulation.py
git commit -m "Add guarded Gmail campaign delivery"
```

### Task 5: Sending Profiles Administrator Page

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/src/test/setup.js`
- Modify: `frontend/src/services/api.js`
- Create: `frontend/src/pages/SendingProfiles.jsx`
- Create: `frontend/src/pages/SendingProfiles.test.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes API routes from Task 2
- Produces API helpers `getSendingProfile`, `createSendingProfile`, `updateSendingProfile`, `testSendingProfile`, `deleteSendingProfile`
- Produces React component `SendingProfiles({ token })`

- [ ] **Step 1: Add the frontend test runner**

Add script `"test": "vitest run"`, dev dependencies `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/jest-dom`, and Vite test configuration using `environment: "jsdom"` and `setupFiles: "./src/test/setup.js"`. Import `@testing-library/jest-dom/vitest` in setup.

- [ ] **Step 2: Write failing profile-page tests**

Mock the API module and test empty-state creation, configured credential masking, metadata editing without a password, explicit password replacement, test-email success/failure status, enable/disable, and delete confirmation. Assert rendered content never contains the supplied app password.

```jsx
render(<SendingProfiles token="token" />)
expect(await screen.findByText('No Gmail profile configured')).toBeInTheDocument()
expect(screen.getByLabelText('Google app password')).toHaveAttribute('type', 'password')
```

- [ ] **Step 3: Run the UI test and verify failure**

```powershell
cd frontend
& "C:\Program Files\nodejs\npm.cmd" install
& "C:\Program Files\nodejs\npm.cmd" test -- SendingProfiles.test.jsx
```

Expected: FAIL because the component and API helpers do not exist.

- [ ] **Step 4: Implement API helpers and the profile page**

The form contains Profile name, Display name, Gmail address, and password fields. Existing profile view shows `App password: Configured`, last-test status, and buttons for Save, Replace password, Send test, Enable/Disable, and Delete. Clear the password state immediately after successful create/replace and never populate it from response data.

- [ ] **Step 5: Register sidebar navigation and styles**

Import the page in `Dashboard.jsx`, add `sendingProfiles` to titles/navigation, and render it. Add only the status-card, credential-state, and warning styles required by this page, following existing classes and responsive layout.

- [ ] **Step 6: Run focused test, lint, and build**

```powershell
& "C:\Program Files\nodejs\npm.cmd" test -- SendingProfiles.test.jsx
& "C:\Program Files\nodejs\npm.cmd" run lint
& "C:\Program Files\nodejs\npm.cmd" run build
```

Expected: all pass.

- [ ] **Step 7: Commit the profile UI**

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/test/setup.js frontend/src/services/api.js frontend/src/pages/SendingProfiles.jsx frontend/src/pages/SendingProfiles.test.jsx frontend/src/pages/Dashboard.jsx frontend/src/styles.css
git commit -m "Add Gmail sending profile workspace"
```

### Task 6: Campaign Gmail Selection and Real-Delivery Confirmation UI

**Files:**
- Modify: `frontend/src/services/api.js`
- Modify: `frontend/src/pages/Campaigns.jsx`
- Create: `frontend/src/pages/Campaigns.test.jsx`
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: campaign `sending_profile_id`, safe profile API, transport-aware preview
- Produces: campaign delivery selector and real-delivery safety UI

- [ ] **Step 1: Write failing campaign UI tests**

Test that Mailpit is selected by default, Gmail appears only for an enabled configured profile, and selecting Gmail sends `sending_profile_id` during campaign creation. Render a Gmail preview and assert the real-delivery warning, limits, HTTPS/profile readiness warnings, and exact `SEND N REAL EMAILS` text. Assert the send button remains disabled until every preview check passes and confirmation matches exactly.

- [ ] **Step 2: Run the focused test and verify failure**

```powershell
& "C:\Program Files\nodejs\npm.cmd" test -- Campaigns.test.jsx
```

Expected: FAIL because Campaigns has no transport selector or Gmail warning.

- [ ] **Step 3: Implement campaign selection and preview behavior**

Load the safe Gmail profile alongside campaigns/templates/users. Add a Delivery method selector with Mailpit first. Include `sending_profile_id: null | profile_id` in create requests. In the final preview:

- label Mailpit as local test delivery;
- label Gmail as real external delivery;
- show campaign/hourly Gmail limits;
- show profile-not-ready and unsafe-URL warnings;
- keep the button disabled for blocked recipients, disabled delivery, unready profile, unsafe URL, zero allowed recipients, limit failures, or confirmation mismatch;
- use the preview-provided confirmation phrase rather than reconstructing it in JavaScript.

- [ ] **Step 4: Run focused tests, all frontend tests, lint, and build**

```powershell
& "C:\Program Files\nodejs\npm.cmd" test -- Campaigns.test.jsx
& "C:\Program Files\nodejs\npm.cmd" test
& "C:\Program Files\nodejs\npm.cmd" run lint
& "C:\Program Files\nodejs\npm.cmd" run build
```

Expected: all pass.

- [ ] **Step 5: Commit campaign UI changes**

```powershell
git add frontend/src/services/api.js frontend/src/pages/Campaigns.jsx frontend/src/pages/Campaigns.test.jsx frontend/src/styles.css
git commit -m "Add real Gmail delivery confirmation UI"
```

### Task 7: Documentation, Migration Rehearsal, and Final Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/safe_email_delivery.md`
- Modify: `backend/.env.example`
- Test: complete repository

**Interfaces:**
- Consumes all prior tasks
- Produces administrator setup and operating instructions

- [ ] **Step 1: Document key generation and one-time migration**

Add this key-generation command without showing or committing a real generated value:

```powershell
.\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Document placing the output in `SENDING_PROFILE_ENCRYPTION_KEY`, running `flask --app run.py upgrade-db`, restarting Flask once, creating an approved user matching the Gmail sender, creating/testing the profile, deploying an HTTPS public URL, and selecting Gmail on a campaign.

- [ ] **Step 2: Document operational safety and recovery**

State that the normal Google password must never be entered, Mailpit remains the default, revoking a user blocks future delivery immediately, disabling/deleting the profile blocks Gmail campaigns, rotating the encryption key without re-encrypting the saved password makes the profile unusable, and a lost key requires deleting/recreating the profile with a new app password.

- [ ] **Step 3: Rehearse migration against a temporary SQLite copy**

Copy the existing local database to a temporary path outside the repository, point `DATABASE_URL` at that explicit copy, run:

```powershell
.\venv\Scripts\python.exe -m flask --app run.py upgrade-db
.\venv\Scripts\python.exe -m flask --app run.py upgrade-db
```

Expected: first run adds the table/columns; second reports already up to date. Do not modify or commit the real database during this rehearsal.

- [ ] **Step 4: Run final backend verification**

```powershell
cd backend
.\venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass and total coverage is at least 85%.

- [ ] **Step 5: Run final frontend verification**

```powershell
cd ..\frontend
& "C:\Program Files\nodejs\npm.cmd" test
& "C:\Program Files\nodejs\npm.cmd" run lint
& "C:\Program Files\nodejs\npm.cmd" run build
```

Expected: tests, lint, and production build pass.

- [ ] **Step 6: Check the final diff for secrets and accidental files**

```powershell
cd ..
rg -n "[A-Za-z0-9]{16}" backend docs frontend --glob '!frontend/node_modules/**' --glob '!frontend/dist/**'
git diff --check
git status --short
```

Review every match; confirm no real app password, Fernet key, database file, `.env`, build output, or unrelated user change is staged.

- [ ] **Step 7: Commit documentation and final adjustments**

```powershell
git add README.md docs/safe_email_delivery.md backend/.env.example
git commit -m "Document guarded Gmail delivery setup"
```

- [ ] **Step 8: Request final code review**

Use the `requesting-code-review` skill against the complete Gmail feature diff. Resolve only findings attributable to this feature, rerun the relevant focused tests, and repeat the full verification commands before declaring completion.
