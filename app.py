"""
app.py
SkyRoute — Flight Ticket Booking System backend.

Run with:
    python app.py

First-time setup (creates the database + seed admin/flights):
    python database.py
"""

import os
import secrets
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

from database import get_db, init_db, DB_PATH, AIRPORTS

app = Flask(__name__)
app.secret_key = os.environ.get("SKYROUTE_SECRET_KEY", secrets.token_hex(32))

# Make sure the database exists before the app starts handling requests.
if not os.path.exists(DB_PATH):
    init_db()


# --------------------------------------------------------------------------
# Access-control decorators
# --------------------------------------------------------------------------

def login_required(view):
    """Blocks the route entirely unless a user is logged in."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to do that. Booking is only available to registered users.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """Blocks the route unless the logged-in user has the admin role."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def flight_status(flight):
    """Simple derived status for the live board / listings — no invented delays."""
    if flight["seats_taken"] >= flight["seats_total"]:
        return "full"
    return "ontime"


app.jinja_env.globals["flight_status"] = flight_status


# --------------------------------------------------------------------------
# Public pages
# --------------------------------------------------------------------------

@app.route("/")
def home():
    db = get_db()
    upcoming = db.execute(
        "SELECT * FROM flights ORDER BY departure_time LIMIT 6"
    ).fetchall()
    db.close()
    return render_template("index.html", airports=AIRPORTS, upcoming=upcoming)


@app.route("/flights")
def flights():
    origin = request.args.get("from", "").strip()
    destination = request.args.get("to", "").strip()
    date = request.args.get("date", "").strip()

    query = "SELECT * FROM flights WHERE 1=1"
    params = []

    if origin:
        query += " AND (origin_code = ? OR origin_city LIKE ?)"
        params += [origin, f"%{origin}%"]
    if destination:
        query += " AND (destination_code = ? OR destination_city LIKE ?)"
        params += [destination, f"%{destination}%"]
    if date:
        query += " AND departure_time LIKE ?"
        params += [f"{date}%"]

    query += " ORDER BY departure_time"

    db = get_db()
    results = db.execute(query, params).fetchall()
    db.close()

    return render_template(
        "flights.html",
        flights=results,
        airports=AIRPORTS,
        selected_from=origin,
        selected_to=destination,
        selected_date=date,
    )


# --------------------------------------------------------------------------
# Auth: register / login / logout
# --------------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not full_name or not email or not password:
            flash("All fields are required.", "error")
            return render_template("register.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html")

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            db.close()
            flash("An account with that email already exists. Try logging in.", "error")
            return render_template("register.html")

        db.execute(
            "INSERT INTO users (full_name, email, password_hash, role) VALUES (?, ?, ?, 'user')",
            (full_name, email, generate_password_hash(password)),
        )
        db.commit()
        db.close()

        flash("Account created. You can now log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = user["id"]
        session["full_name"] = user["full_name"]
        session["role"] = user["role"]

        flash(f"Welcome back, {user['full_name']}!", "success")

        next_url = request.args.get("next")
        if user["role"] == "admin":
            return redirect(next_url or url_for("admin_dashboard"))
        return redirect(next_url or url_for("home"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


# --------------------------------------------------------------------------
# Booking — registered users only
# --------------------------------------------------------------------------

@app.route("/book/<int:flight_id>", methods=["GET", "POST"])
@login_required
def book_flight(flight_id):
    db = get_db()
    flight = db.execute("SELECT * FROM flights WHERE id = ?", (flight_id,)).fetchone()

    if flight is None:
        db.close()
        flash("That flight does not exist.", "error")
        return redirect(url_for("flights"))

    if request.method == "POST":
        passenger_name = request.form.get("passenger_name", "").strip()
        seat_number = request.form.get("seat_number", "").strip().upper()

        if not passenger_name or not seat_number:
            flash("Passenger name and seat number are required.", "error")
            return render_template("book.html", flight=flight)

        if flight["seats_taken"] >= flight["seats_total"]:
            db.close()
            flash("Sorry, this flight is fully booked.", "error")
            return redirect(url_for("flights"))

        seat_taken = db.execute(
            "SELECT id FROM bookings WHERE flight_id = ? AND seat_number = ? AND status = 'confirmed'",
            (flight_id, seat_number),
        ).fetchone()
        if seat_taken:
            db.close()
            flash(f"Seat {seat_number} is already taken. Please choose another.", "error")
            return render_template("book.html", flight=flight)

        booking_ref = "SR-" + secrets.token_hex(4).upper()
        db.execute(
            """INSERT INTO bookings (user_id, flight_id, passenger_name, seat_number, booking_ref)
               VALUES (?, ?, ?, ?, ?)""",
            (session["user_id"], flight_id, passenger_name, seat_number, booking_ref),
        )
        db.execute("UPDATE flights SET seats_taken = seats_taken + 1 WHERE id = ?", (flight_id,))
        db.commit()
        db.close()

        flash("Booking confirmed! Your e-ticket is below.", "success")
        return redirect(url_for("booking_confirmation", booking_ref=booking_ref))

    db.close()
    return render_template("book.html", flight=flight)


@app.route("/booking/<booking_ref>")
@login_required
def booking_confirmation(booking_ref):
    db = get_db()
    booking = db.execute(
        """SELECT bookings.*, flights.flight_number, flights.origin_code, flights.origin_city,
                  flights.destination_code, flights.destination_city, flights.departure_time,
                  flights.arrival_time, flights.gate, flights.price
           FROM bookings JOIN flights ON bookings.flight_id = flights.id
           WHERE bookings.booking_ref = ?""",
        (booking_ref,),
    ).fetchone()
    db.close()

    if booking is None:
        abort(404)

    # A user may only view their own e-ticket, unless they're an admin.
    if booking["user_id"] != session["user_id"] and session.get("role") != "admin":
        abort(403)

    return render_template("ticket.html", booking=booking)


@app.route("/my-bookings")
@login_required
def my_bookings():
    db = get_db()
    bookings = db.execute(
        """SELECT bookings.*, flights.flight_number, flights.origin_code, flights.origin_city,
                  flights.destination_code, flights.destination_city,
                  flights.departure_time, flights.arrival_time
           FROM bookings JOIN flights ON bookings.flight_id = flights.id
           WHERE bookings.user_id = ?
           ORDER BY bookings.created_at DESC""",
        (session["user_id"],),
    ).fetchall()
    db.close()
    return render_template("my_bookings.html", bookings=bookings)


# --------------------------------------------------------------------------
# Admin only
# --------------------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    users = db.execute("SELECT id, full_name, email, role, created_at FROM users ORDER BY created_at DESC").fetchall()
    flights_list = db.execute("SELECT * FROM flights ORDER BY departure_time").fetchall()
    bookings = db.execute(
        """SELECT bookings.*, users.full_name AS user_name, users.email AS user_email,
                  flights.flight_number, flights.origin_code, flights.destination_code
           FROM bookings
           JOIN users ON bookings.user_id = users.id
           JOIN flights ON bookings.flight_id = flights.id
           ORDER BY bookings.created_at DESC"""
    ).fetchall()
    db.close()
    return render_template(
        "admin.html",
        users=users,
        flights=flights_list,
        bookings=bookings,
    )


@app.route("/admin/flights/add", methods=["POST"])
@admin_required
def admin_add_flight():
    db = get_db()
    try:
        db.execute(
            """INSERT INTO flights
               (flight_number, origin_code, origin_city, destination_code, destination_city,
                departure_time, arrival_time, gate, price, seats_total, seats_taken)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                request.form["flight_number"].strip(),
                request.form["origin_code"].strip().upper(),
                request.form["origin_city"].strip(),
                request.form["destination_code"].strip().upper(),
                request.form["destination_city"].strip(),
                request.form["departure_time"].strip(),
                request.form["arrival_time"].strip(),
                request.form.get("gate", "—").strip() or "—",
                float(request.form["price"]),
                int(request.form["seats_total"]),
            ),
        )
        db.commit()
        flash("Flight added.", "success")
    except Exception as exc:
        flash(f"Could not add flight: {exc}", "error")
    finally:
        db.close()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/flights/delete/<int:flight_id>", methods=["POST"])
@admin_required
def admin_delete_flight(flight_id):
    db = get_db()
    db.execute("DELETE FROM flights WHERE id = ?", (flight_id,))
    db.commit()
    db.close()
    flash("Flight removed.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/users/delete/<int:user_id>", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    if user_id == session["user_id"]:
        flash("You can't delete your own admin account while logged in.", "error")
        return redirect(url_for("admin_dashboard"))
    db = get_db()
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    db.close()
    flash("User removed.", "success")
    return redirect(url_for("admin_dashboard"))


# --------------------------------------------------------------------------
# Error pages
# --------------------------------------------------------------------------

@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403, message="You don't have permission to view this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="That page doesn't exist."), 404


if __name__ == "__main__":
    app.run(debug=True, port=5000)
