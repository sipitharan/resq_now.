from datetime import datetime
import hashlib
from io import BytesIO
from pathlib import Path
import re
import secrets
import tempfile

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_login import login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from extensions import limiter
from models import Ambulance, AuditLog, Driver, Patient, User, VerificationRecord, db
from services.supabase_storage import download_private_object, is_configured, upload_private_object
from services.verification import assess_driver

auth_bp = Blueprint("auth", __name__)


def _valid_mobile(value):
    return bool(re.fullmatch(r"\+?[0-9]{8,15}", value.strip()))


def _normalize_indian_mobile(value):
    mobile = str(value or "").strip()
    if re.fullmatch(r"[6-9][0-9]{9}", mobile):
        return f"+91{mobile}"
    if re.fullmatch(r"\+91[6-9][0-9]{9}", mobile):
        return mobile
    if re.fullmatch(r"91[6-9][0-9]{9}", mobile):
        return f"+{mobile}"
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form.get("mobile", "").strip()
        user = User.query.filter((User.mobile == mobile) | (User.email == mobile)).first()
        if user and user.check_password(request.form.get("password", "")) and user.is_active:
            login_user(user, remember=bool(request.form.get("remember")))
            session.permanent = True
            return redirect(url_for("main.dashboard"))
        flash("Incorrect mobile number or password.", "error")
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        role = request.form.get("role", "PATIENT").upper()
        if role not in {"PATIENT", "DRIVER"}:
            flash("Select a valid account type.", "error")
            return render_template("register.html")

        if role == "PATIENT":
            name = request.form.get("name", "").strip()
            mobile = request.form.get("mobile", "").strip()
            password = request.form.get("password", "")
            if not name or not _valid_mobile(mobile) or len(password) < 8:
                flash("Full name, valid mobile number, and a password of at least 8 characters are required.", "error")
                return render_template("register.html")
            if User.query.filter_by(mobile=mobile).first():
                flash("This mobile number is already registered. Please login instead.", "error")
                return redirect(url_for("auth.login"))
            user = User(name=name, mobile=mobile, email=request.form.get("email", "").strip() or None, role="PATIENT", mobile_verified=False)
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(Patient(user_id=user.id))
            user.is_active = True
            db.session.commit()
            flash("Patient registration complete. Please login.", "success")
            return redirect(url_for("auth.login"))

        name = request.form.get("name", "").strip()
        mobile = request.form.get("mobile", "").strip()
        password = request.form.get("password", "")
        email = request.form.get("email", "").strip()
        normalized_phone = _normalize_indian_mobile(mobile)
        ambulance_number = request.form.get("ambulance_number", "").strip().upper()
        ambulance_type = request.form.get("ambulance_type", "").strip()
        available_start = request.form.get("available_start", "").strip()
        available_end = request.form.get("available_end", "").strip()
        try:
            latitude = float(request.form.get("latitude", ""))
            longitude = float(request.form.get("longitude", ""))
        except (TypeError, ValueError):
            latitude = longitude = None
        photo = request.files.get("photo")
        required = (name, normalized_phone, email, password, ambulance_number, ambulance_type, available_start, available_end, photo and photo.filename, latitude, longitude)
        if not all(required):
            flash("All driver, ambulance, original photo, and GPS fields are required.", "error")
            return render_template("register.html")
        if len(name) < 3 or len(password) < 8 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Full name and a password of at least 8 characters are required.", "error")
            return render_template("register.html")
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            flash("Enter a valid current GPS location.", "error")
            return render_template("register.html")
        if User.query.filter_by(mobile=normalized_phone).first() or User.query.filter_by(email=email).first():
            flash("This mobile number or email is already registered. Please login instead.", "error")
            return redirect(url_for("auth.login"))
        if Ambulance.query.filter_by(number=ambulance_number).first():
            flash("This ambulance registration number is already registered.", "error")
            return render_template("register.html")
        safe_name = secure_filename(photo.filename)
        extension = Path(safe_name).suffix.lower()
        if extension not in current_app.config["UPLOAD_EXTENSIONS"] or photo.mimetype not in current_app.config["UPLOAD_MIME_TYPES"]:
            flash("Upload a JPG, JPEG, PNG, or WEBP image.", "error")
            return render_template("register.html")
        remote_storage = is_configured()
        upload_dir = Path(tempfile.gettempdir()) / "resqnow-uploads" if remote_storage else Path(current_app.instance_path) / "secure_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        photo_name = f"driver-{secrets.token_hex(16)}{extension}"
        photo_path = upload_dir / photo_name
        photo.save(photo_path)
        if photo_path.stat().st_size == 0:
            photo_path.unlink(missing_ok=True)
            flash("The uploaded image is empty or invalid.", "error")
            return render_template("register.html")

        user = User(name=name, mobile=normalized_phone, email=email, role="DRIVER", mobile_verified=True, is_active=True)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        driver = Driver(user_id=user.id, phone=normalized_phone, phone_verified=True, available_start=available_start, available_end=available_end, ambulance_registration_number=ambulance_number, verification_status="PENDING", latitude=latitude, longitude=longitude, gps_status="LIVE", last_gps_at=datetime.utcnow(), photo_path=photo_name)
        db.session.add(driver)
        db.session.flush()
        db.session.add(Ambulance(driver_id=driver.id, number=ambulance_number, ambulance_type=ambulance_type))
        result = assess_driver(driver, photo_name, str(photo_path), ambulance_number)
        if remote_storage:
            try:
                upload_private_object(photo_name, photo_path, photo.mimetype)
            finally:
                photo_path.unlink(missing_ok=True)
        driver.ai_result = result["ai_result"]
        driver.ai_confidence = result["confidence"]
        driver.ai_risk_score = result["risk_score"]
        driver.ocr_result = result["ocr_result"]
        driver.ocr_match = result["ocr_match"]
        db.session.add(VerificationRecord(driver_id=driver.id, ambulance_proof_path=photo_name, document_name=photo_name, mobile_verified=True, risk_score=result["risk_score"], ai_risk_score=result["risk_score"], ai_flags=result["flags"], ai_result=result["ai_result"], ai_confidence=result["confidence"], ocr_result=result["ocr_result"], ocr_match=result["ocr_match"], photo_sha256=result["photo_sha256"], review_status="PENDING"))
        db.session.add(AuditLog(action="DRIVER_REGISTERED", resource_type="DRIVER", resource_id=driver.id, details="Driver registration submitted for admin review."))
        db.session.add(AuditLog(action="AI_VERIFICATION", resource_type="DRIVER", resource_id=driver.id, details=result["ai_result"]))
        db.session.commit()
        login_user(user, remember=True)
        session.permanent = True
        flash("Registration submitted. Your ambulance will appear to patients only after admin approval.", "success")
        return redirect(url_for("main.dashboard"))

    return render_template("register.html")


@auth_bp.get("/admin/drivers/<int:driver_id>/photo")
def driver_photo(driver_id):
    from flask_login import current_user
    if not current_user.is_authenticated or current_user.role != "ADMIN":
        return jsonify(error="Forbidden"), 403
    driver = db.session.get(Driver, driver_id)
    if driver and driver.photo_path and is_configured():
        content, content_type = download_private_object(driver.photo_path)
        return send_file(BytesIO(content), mimetype=content_type, max_age=0)
    path = Path(current_app.instance_path) / "secure_uploads" / (driver.photo_path if driver else "")
    if not driver or not driver.photo_path or not path.is_file():
        return jsonify(error="Photo not found"), 404
    return send_file(path, conditional=True)


@auth_bp.get("/logout")
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("main.index"))
