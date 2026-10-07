# Safe email delivery

PhishGuard defaults to a local Mailpit test inbox. Administrators can optionally
configure one personal Gmail profile for real external email in authorized
security-awareness simulations. Gmail uses `smtp.gmail.com:587`, STARTTLS with
certificate verification, the full Gmail address, and a Google app password.
Never enter the normal Google account password.

## Safety controls

- Delivery is disabled by default.
- Every recipient must be approved by an administrator on the **Users** page.
- Mailpit campaigns and successful hourly deliveries are capped by
  `MAX_CAMPAIGN_RECIPIENTS` and `MAX_EMAILS_PER_HOUR`.
- Gmail is capped at 10 pending recipients per campaign and 20 successful Gmail
  campaign deliveries in the preceding rolling hour. These Gmail caps are fixed.
- Already delivered recipients are never sent the campaign twice.
- The administrator must review a preview and type an exact confirmation phrase.
- Every campaign subject starts with `[SECURITY SIMULATION]` and every campaign
  message contains a simulation notice and `X-PhishGuard-Simulation` header.
- Non-local Mailpit tracking URLs must use HTTPS. Gmail always requires an HTTPS
  `PUBLIC_BASE_URL` outside localhost, loopback, and obvious private networks.
- The simulation page never requests or accepts credentials.
- Delivery, click, landing, simulated continuation, training, and quiz events are
  recorded without message contents or credential values.

## Start Mailpit

Docker Desktop must be running:

```powershell
docker compose -f docker-compose.mailpit.yml up -d
```

If Docker is not installed, install the native Windows package instead:

```powershell
winget install --exact --id axllent.mailpit
```

Open a new PowerShell window and start it with:

```powershell
mailpit
```

Open the test inbox at <http://localhost:8025>. SMTP is available only on the local
computer at `127.0.0.1:1025`.

## Configure the backend

Set these values in the environment before starting Flask. Replace the example
address with the exact test recipient address stored in PhishGuard:

```powershell
Set-Item Env:PUBLIC_BASE_URL "http://localhost:5000"
Set-Item Env:MAIL_DELIVERY_ENABLED "1"
Set-Item Env:MAIL_HOST "127.0.0.1"
Set-Item Env:MAIL_PORT "1025"
Set-Item Env:MAIL_FROM "simulation@phishguard.test"
Set-Item Env:MAX_CAMPAIGN_RECIPIENTS "25"
Set-Item Env:MAX_EMAILS_PER_HOUR "50"
```

Restart Flask after changing environment configuration. Normal recipient approval
and revocation happen on the **Users** page immediately and do not require a
restart. Revoking approval blocks future delivery to that user immediately.

## Send a controlled Mailpit message

1. Create a template and include `[INSERT CAMPAIGN TRACKING LINK]` where the unique
   recipient link should appear.
2. On **Users**, select **Approve email** for each authorized test recipient.
3. Create a campaign with the default Mailpit delivery method and assign approved
   test users.
4. Open **Recipients & delivery**.
5. Review the sender, subject, allowed count, blocked count, and public URL status.
6. Type the displayed confirmation phrase exactly.
7. Select **Send to local Mailpit**.
8. Open <http://localhost:8025> to inspect and test the captured message.

Mailpit is a development inbox. Do not configure its relay feature or expose ports
8025 and 1025 beyond localhost.

## Configure personal Gmail delivery

1. Back up an existing database before upgrading it. From `backend`, generate a
   Fernet key locally:

   ```powershell
   .\venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Place the output in `SENDING_PROFILE_ENCRYPTION_KEY` in the backend environment
   or a local, untracked `.env`. Keep the key secret and preserve a secure backup;
   it encrypts the saved Gmail app password and is not stored in the database.
   Use the Flask CLI startup command in step 3 to load `.env` before constructing
   the app; `python run.py` requires these variables to be exported in PowerShell
   first.
2. Apply the one-time schema upgrade to the configured database:

   ```powershell
   .\venv\Scripts\python.exe -m flask --app run.py upgrade-db
   ```

   Running it again is safe and reports that the database is already up to date.
3. Deploy the tracking application at a public HTTPS URL, set `PUBLIC_BASE_URL` to
   that URL and `MAIL_DELIVERY_ENABLED=1`, and restart Flask once with the key and
   these settings. The backend checks URL structure and host category without
   probing reachability. Confirm that recipients can reach the deployment. For
   local startup from `backend`, use:

   ```powershell
   .\venv\Scripts\python.exe -m flask --app run.py run
   ```
4. On **Users**, create a user whose email exactly matches the sending Gmail
   address and select **Approve email** for that authorized sender.
5. Obtain a Google app password for the personal Gmail account. On **Sending
   Profiles**, enter Profile name, Display name, Gmail address, and Google app
   password, then select **Create profile**. Only one `@gmail.com` profile is
   supported. Spaces in an entered app password are removed before encryption.
6. Select **Send test**. This sends a real connection-test email only to the
   profile's own approved Gmail address. Confirm **Last test: Succeeded**, then
   select **Enable**. A disabled profile or a failed latest test blocks Gmail
   campaign delivery.

The stored app password is never displayed or returned by the API. **Save
metadata** preserves it; enter a new app password and select **Replace password**
only to replace it. Changing the Gmail address or replacing the password clears
the previous test result and blocks Gmail campaigns until **Send test** succeeds
again. Profile-name and display-name edits preserve the test result.
Mailpit remains the default for both existing and new campaigns.

## Send an authorized Gmail campaign

1. Create a template with `[INSERT CAMPAIGN TRACKING LINK]` and approve every
   authorized recipient on **Users**.
2. Create a campaign and explicitly choose the enabled Gmail profile under
   **Delivery method**, then assign recipients.
3. Open **Recipients & delivery** and review the real-delivery warning, sender,
   allowed and blocked recipients, previously delivered count, HTTPS status,
   profile readiness, and the 10-recipient / 20-per-hour limits. Resolve every
   blocked condition before sending.
4. Type the displayed phrase exactly: `SEND 1 REAL EMAIL` for one pending approved
   recipient, or `SEND N REAL EMAILS` for multiple recipients, with `N` replaced by
   the displayed count. Select **Send real Gmail emails**.

Each recipient receives a separate message with a unique tracking link. Campaign
messages keep the mandatory simulation labels and use the authenticated Gmail
address as the sender. Successful deliveries prevent duplicate sends. A partial
failure preserves successful delivery records; review a fresh preview before
manually retrying the remaining recipients. No automatic retry occurs.

## Stop delivery and recover credentials

- Revoke a recipient's approval on **Users** to block future delivery to them.
- Select **Disable** on **Sending Profiles** to block Gmail campaigns immediately.
  Deletion is rejected while any campaign references the profile, including
  completed campaigns. Use **Disable** to stop delivery without deleting campaign
  history; an unreferenced profile can be deleted.
- Rotating `SENDING_PROFILE_ENCRYPTION_KEY` without re-encrypting the saved app
  password makes that credential unusable. Preserve the key across restarts and
  deployments; the application has no automatic key-rotation workflow.
- A lost key requires deleting and recreating the profile with a new Google app
  password and a new securely stored key. Disable it first. If campaigns prevent
  deletion, resolve those references; this can require deleting their records.
  Back up needed history before doing so, then create, test, and enable the replacement.
- Gmail authentication failures require checking or replacing the Google app
  password. Connection or provider errors require resolving the reported category
  and testing again. Never put passwords or encryption keys into logs or reports.

Arbitrary SMTP hosts, sender spoofing, attachments, OAuth, Workspace relay,
scheduled sending, and multiple Gmail accounts are not supported.
