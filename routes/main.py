from flask import Blueprint, render_template
from flask_login import current_user, login_required
from models import db

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html")


@main_bp.get("/dashboard")
@login_required
def dashboard():
    if current_user.role == "DRIVER":
        return render_template("driver_dashboard.html")
    if current_user.role == "ADMIN":
        return render_template("admin.html")
    return render_template("patient_dashboard.html")


@main_bp.get("/tracking/<int:booking_id>")
@login_required
def tracking(booking_id):
    from models import Booking
    booking = db.session.get(Booking, booking_id)
    allowed = booking and (current_user.id == booking.patient.user_id or current_user.id == booking.driver.user_id)
    if not allowed or booking.booking_type != "EMERGENCY" or booking.status not in {"ACCEPTED", "EN_ROUTE", "ARRIVED"}:
        return "Tracking is available only for an accepted emergency booking.", 403
    return render_template("tracking.html", booking=booking)
