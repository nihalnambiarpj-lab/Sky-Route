"""
database.py
Handles all SQLite database setup and connection logic for SkyRoute.
"""

import sqlite3
import os
# pyrefly: ignore [missing-import]
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skyroute.db")

# Airports used across the search form and seed data (matches the homepage design).
AIRPORTS = [
    ("CCJ", "Kozhikode"),
    ("COK", "Kochi"),
    ("BLR", "Bengaluru"),
    ("BOM", "Mumbai"),
    ("DEL", "Delhi"),
    ("MAA", "Chennai"),
    ("GOI", "Goa"),
    ("HYD", "Hyderabad"),
]


def get_db():
    """Open a new database connection with row access by column name."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset=False):
    """Create tables. If reset=True, wipes any existing database file first."""
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = get_db()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name     TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS flights (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            flight_number  TEXT NOT NULL UNIQUE,
            origin_code    TEXT NOT NULL,
            origin_city    TEXT NOT NULL,
            destination_code TEXT NOT NULL,
            destination_city TEXT NOT NULL,
            departure_time TEXT NOT NULL,
            arrival_time   TEXT NOT NULL,
            gate           TEXT NOT NULL DEFAULT '—',
            price          REAL NOT NULL,
            seats_total    INTEGER NOT NULL DEFAULT 60,
            seats_taken    INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bookings (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            flight_id     INTEGER NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
            passenger_name TEXT NOT NULL,
            seat_number   TEXT NOT NULL,
            booking_ref   TEXT NOT NULL UNIQUE,
            status        TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled')),
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    # Seed an admin account only if no admin exists yet.
    admin = cur.execute("SELECT id FROM users WHERE role = 'admin'").fetchone()
    if not admin:
        cur.execute(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (
                "SkyRoute Admin",
                "admin@skyroute.com",
                generate_password_hash("Admin@123"),
                "admin",
            ),
        )

    # Seed flights matching the routes shown on the homepage's live departure board.
    count = cur.execute("SELECT COUNT(*) AS c FROM flights").fetchone()["c"]
    if count == 0:
        sample_flights = [
            # flight_no, o_code, o_city,      d_code, d_city,      depart,               arrive,               gate,  price,  seats_total, seats_taken
            ("SR204", "COK", "Kochi",       "DEL", "Delhi",      "2026-09-20 09:40", "2026-09-20 12:10", "G12", 6200.0, 60, 0),
            ("SR118", "CCJ", "Kozhikode",   "BLR", "Bengaluru",  "2026-09-20 11:05", "2026-09-20 12:35", "G04", 3800.0, 60, 0),
            ("SR331", "BOM", "Mumbai",      "MAA", "Chennai",    "2026-09-20 13:20", "2026-09-20 15:30", "G21", 5400.0, 60, 0),
            ("SR456", "HYD", "Hyderabad",   "GOI", "Goa",        "2026-09-20 15:50", "2026-09-20 17:10", "G09", 4700.0, 60, 0),
            ("SR087", "DEL", "Delhi",       "CCJ", "Kozhikode",  "2026-09-20 18:15", "2026-09-20 21:05", "G15", 7100.0, 60, 0),
            ("SR512", "BLR", "Bengaluru",   "BOM", "Mumbai",     "2026-09-20 20:30", "2026-09-20 22:00", "G07", 4200.0, 60, 0),
            ("SR620", "MAA", "Chennai",     "COK", "Kochi",      "2026-09-21 07:15", "2026-09-21 08:45", "G03", 3600.0, 60, 0),
            ("SR741", "GOI", "Goa",         "BOM", "Mumbai",     "2026-09-21 10:00", "2026-09-21 11:05", "G11", 3300.0, 60, 0),
        ]
        cur.executemany(
            """INSERT INTO flights
               (flight_number, origin_code, origin_city, destination_code, destination_city,
                departure_time, arrival_time, gate, price, seats_total, seats_taken)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            sample_flights,
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db(reset=True)
    print("Database initialized at:", DB_PATH)
    print("Seed admin login -> email: admin@skyroute.com | password: Admin@123")
