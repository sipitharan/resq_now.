# ResQNow

ResQNow is a Flask prototype for coordinating verified ambulance teams with patients, using SQLite and Socket.IO locally and PostgreSQL, Supabase Storage, and Pusher Channels on Vercel. It supports emergency and non-emergency requests, role-based authentication, browser GPS, and Leaflet maps.

The platform also includes a rule-based Smart Dispatch Score, driver reliability and GPS health signals, timestamped emergency timelines, hospital capacity data, anonymized demand intelligence, admin dispatch override, and clearly labelled DEMO/SIMULATION controls. These intelligence features are research aids, not medical diagnosis, official verification, live traffic data, or a replacement for India's 112/108 services.

## Run on Windows

```powershell
cd D:\ResQNow
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000.

## Deploy to Vercel

Vercel serves the Flask application through `api/index.py`. Configure these project environment variables in Vercel:

- `RESQNOW_SECRET_KEY`: a long, randomly generated secret.
- `DATABASE_URL`: a persistent PostgreSQL connection URL. The app adapts PostgreSQL URLs to its installed psycopg 3 driver.
- `REALTIME_PROVIDER=pusher`, plus `PUSHER_APP_ID`, `PUSHER_KEY`, `PUSHER_SECRET`, and `PUSHER_CLUSTER` from a Pusher Channels app.
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`, plus `SUPABASE_STORAGE_BUCKET` (defaults to `driver-documents`).

Create the named bucket in Supabase and keep it private. The service-role key is used only by the server and must never be added to browser configuration. Set the Vercel environment variables for every deployment environment and redeploy after changing them. Local development continues to use Socket.IO and local uploads unless the corresponding hosted services are configured.

For an operations account, create one explicitly with credentials held in environment variables:

```powershell
$env:RESQNOW_ADMIN_MOBILE = "5550000000"
$env:RESQNOW_ADMIN_PASSWORD = "use-a-long-unique-password"
.\.venv\Scripts\python.exe seed_admin.py
```

## Two-window test

1. In window one, register a driver with a unique mobile number and ambulance number. Sign in, open the driver dashboard, go online, and allow GPS.
2. Driver verification starts as `UNDER_REVIEW`. For local testing, change the driver's `verification_status` to `VERIFIED` using an authenticated admin review flow or the database inspection tools. Only verified, online, available drivers appear in emergency search.

3. In window two, register a patient, sign in, select Emergency, allow GPS, and search. Submit a request to the driver.
4. Accept the request in the driver dashboard. The patient receives `booking_accepted` and `tracking_started` over Socket.IO locally or Pusher Channels on Vercel. Send location updates with the driver's browser GPS watcher.
5. Use booking status updates to move through `EN_ROUTE`, `ARRIVED`, and `COMPLETED`. Completion stops tracking and returns the ambulance to `AVAILABLE`.
6. Repeat with Non-emergency. It creates a booking but never starts tracking.

## Included behavior

- Password hashing with Werkzeug and Flask-Login sessions.
- Role checks for patient, driver, and admin API operations.
- SQLite foreign keys, unique identifiers, indexes, booking events, notifications, location history, and verification records.
- Secure filenames, image MIME/extension allow-list, and a 5 MB upload limit for driver photos.
- AI-assisted verification performs local image integrity and duplicate checks. Person, ambulance, and OCR providers must be configured for automated signals; otherwise every submission is `AI_REVIEW_REQUIRED` and requires admin review.
- Emergency matching filters for verified, online, available drivers and sorts by Haversine distance. Non-emergency matching uses the same verified network but does not require a time-window check in the search layer.
- Emergency GPS updates are accepted only from the authenticated booking driver and are broadcast only to the patient's private room. Non-emergency bookings do not receive location broadcasts.

## Production readiness checklist

This is a functional local prototype, not a dispatch or clinical system. Before real-world deployment, add HTTPS everywhere, a managed database, CSRF protection on every state-changing form/API, secure secret management, MFA and verified phone ownership, antivirus and encrypted document storage, strict CORS and rate limits, audit logging, data retention/deletion controls, consent and privacy notices, regulated driver/vehicle verification, monitoring and alerting, dispatch escalation procedures, accessibility review, load testing, and legal/clinical safety review. Replace the prototype heuristic verifier with an auditable human workflow and approved verification providers; do not represent risk scoring as official approval.

## Main routes and events

Public routes are `/`, `/login`, and `/register`; authenticated users enter `/dashboard`. API resources live below `/api`: `/ambulances`, `/location`, `/bookings`, admin summary, verification review, and driver disable. Socket.IO includes `driver_online`, `driver_offline`, `driver_location_update`, `emergency_request_received`, `booking_accepted`, `booking_rejected`, `booking_status_changed`, `tracking_started`, `ambulance_location_update`, `tracking_stopped`, and `notification`.
