# SkyRoute — Flight Ticket Booking System

A Flask + SQLite backend for the SkyRoute academic project: registration, login,
flight booking restricted to logged-in users, and an admin-only management panel.

## Setup

1. Install Python 3.10+ if you don't already have it.
2. Open a terminal in this folder and install dependencies:

   ```
   pip install -r requirements.txt
   ```

3. Create the database (creates `skyroute.db`, seeds 5 sample flights and one admin account):

   ```
   python database.py
   ```

   This prints the seed admin login. By default it is:
   - Email: `admin@skyroute.com`
   - Password: `Admin@123`

   **Change this password (or delete the admin row and register a new one via SQL) before
   showing this to anyone else** — it's a placeholder for the demo.

4. Run the server:

   ```
   python app.py
   ```

5. Open `http://127.0.0.1:5000` in your browser.

## How access control works

- **Anyone** can view the homepage and the flight list (`/flights`).
- **Booking a flight** (`/book/<id>`) requires being logged in. The route is wrapped in a
  `@login_required` decorator — if there's no `user_id` in the session, Flask redirects to
  `/login` with a "please log in" message and the booking never happens. There is no way to
  reach the booking form or submit a booking while unauthenticated.
- **The admin panel** (`/admin`) requires the logged-in user to have `role = 'admin'` in the
  database. A logged-in ordinary user who tries to visit `/admin` gets a 403 Forbidden page —
  they cannot see it just by knowing the URL.
- Passwords are never stored in plain text — they're hashed with Werkzeug's
  `generate_password_hash` / `check_password_hash` (PBKDF2).

## Project structure

```
skyroute/
├── app.py              # Flask routes, auth logic, decorators
├── database.py         # SQLite schema + seed data
├── skyroute.db          # created after running database.py
├── requirements.txt
├── templates/           # Jinja2 HTML templates (all pages)
└── static/css/style.css # Emirates-inspired red/gold theme
```

## Making a second admin account

There's no public "make me an admin" button (on purpose). To promote a user, run:

```
python -c "
from database import get_db
db = get_db()
db.execute(\"UPDATE users SET role='admin' WHERE email=?\", ('someone@example.com',))
db.commit()
"
```

## Design

The visual design (dark "night/amber" boarding-pass theme, Big Shoulders Display + Inter +
IBM Plex Mono) is your original homepage, carried through every page — login, booking, the
e-ticket, and the admin panel all reuse the same tokens and boarding-pass card styling.

The homepage search widget and the "Live board" section are wired to the real database:
- Searching by route/date on the homepage submits to `/flights?from=..&to=..&date=..`,
  which filters actual rows in the `flights` table.
- The departure board on the homepage shows the next 6 real flights, not placeholder rows.

## Notes / next steps

- This is a demo-grade project for coursework: it uses Flask's built-in dev server and a
  single SQLite file. For anything beyond a class submission, you'd want a production WSGI
  server, HTTPS, CSRF protection on forms, and rate-limiting on login.
