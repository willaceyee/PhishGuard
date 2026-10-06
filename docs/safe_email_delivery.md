# Safe local email delivery

PhishGuard sends simulation messages only to a local Mailpit test inbox. It does not
use Gmail or relay messages to the public internet.

## Safety controls

- Delivery is disabled by default.
- Every recipient must be approved by an administrator on the **Users** page.
- A campaign is capped by `MAX_CAMPAIGN_RECIPIENTS`.
- Successful deliveries are capped by `MAX_EMAILS_PER_HOUR`.
- Already delivered recipients are never sent the campaign twice.
- The administrator must review a preview and type an exact confirmation phrase.
- Every subject starts with `[SECURITY SIMULATION]` and every message contains a
  simulation notice and `X-PhishGuard-Simulation` header.
- Non-local tracking URLs must use HTTPS.
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
restart.

## Send a controlled message

1. Create a template and include `[INSERT CAMPAIGN TRACKING LINK]` where the unique
   recipient link should appear.
2. On **Users**, select **Approve email** for each authorized test recipient.
3. Create a campaign and assign approved test users.
4. Open **Recipients & delivery**.
5. Review the sender, subject, allowed count, blocked count, and public URL status.
6. Type the displayed confirmation phrase exactly.
7. Select **Send to local Mailpit**.
8. Open <http://localhost:8025> to inspect and test the captured message.

Mailpit is a development inbox. Do not configure its relay feature or expose ports
8025 and 1025 beyond localhost.
