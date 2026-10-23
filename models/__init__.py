from datetime import datetime
from enum import Enum
import json

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Role(str, Enum):
    DRIVER = "DRIVER"
    PATIENT = "PATIENT"
    ADMIN = "ADMIN"


class VerificationStatus(str, Enum):
    PENDING = "PENDING"
    UNDER_REVIEW = "UNDER_REVIEW"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"


class BookingType(str, Enum):
    EMERGENCY = "EMERGENCY"
    NON_EMERGENCY = "NON_EMERGENCY"


class BookingStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EN_ROUTE = "EN_ROUTE"
    ARRIVED = "ARRIVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    mobile = db.Column(db.String(30), unique=True, nullable=False, index=True)
    email = db.Column(db.String(160), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, index=True)
    mobile_verified = db.Column(db.Boolean, default=False, nullable=False)
    verification_timestamp = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def set_password(self, value):
        self.password_hash = generate_password_hash(value)

    def check_password(self, value):
        return check_password_hash(self.password_hash, value)


class Driver(db.Model):
    __tablename__ = "drivers"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    phone = db.Column(db.String(30), unique=True, nullable=True, index=True)
    phone_verified = db.Column(db.Boolean, default=False, nullable=False)
    verified_at = db.Column(db.DateTime, nullable=True)
    verification_status = db.Column(db.String(30), default=VerificationStatus.PENDING.value, nullable=False, index=True)
    ambulance_registration_number = db.Column(db.String(40), unique=True, nullable=True, index=True)
    verification_score = db.Column(db.Integer, nullable=True)
    photo_path = db.Column(db.String(255), nullable=True)
    ai_result = db.Column(db.String(30), nullable=True)
    ai_confidence = db.Column(db.Integer, nullable=True)
    ai_risk_score = db.Column(db.Integer, nullable=True)
    ocr_result = db.Column(db.String(80), nullable=True)
    ocr_match = db.Column(db.String(20), nullable=True)
    is_online = db.Column(db.Boolean, default=False, nullable=False, index=True)
    available_start = db.Column(db.String(5), nullable=True)
    available_end = db.Column(db.String(5), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    last_gps_at = db.Column(db.DateTime, nullable=True, index=True)
    gps_status = db.Column(db.String(10), default="LOST", nullable=False)
    reliability_score = db.Column(db.Float, default=50, nullable=False)
    acceptance_rate = db.Column(db.Float, default=0, nullable=False)
    cancellation_rate = db.Column(db.Float, default=0, nullable=False)
    completed_trips = db.Column(db.Integer, default=0, nullable=False)
    total_requests = db.Column(db.Integer, default=0, nullable=False)
    average_response_seconds = db.Column(db.Float, default=0, nullable=False)
    gps_anomaly_count = db.Column(db.Integer, default=0, nullable=False)
    user = db.relationship("User", backref=db.backref("driver_profile", uselist=False))


class Patient(db.Model):
    __tablename__ = "patients"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    user = db.relationship("User", backref=db.backref("patient_profile", uselist=False))


class Ambulance(db.Model):
    __tablename__ = "ambulances"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id", ondelete="CASCADE"), unique=True, nullable=False)
    number = db.Column(db.String(40), unique=True, nullable=True, index=True)
    ambulance_type = db.Column(db.String(80), nullable=True)
    capabilities = db.Column(db.Text, nullable=True, default="[]")
    status = db.Column(db.String(20), default="AVAILABLE", nullable=False, index=True)
    driver = db.relationship("Driver", backref=db.backref("ambulance", uselist=False))


class Booking(db.Model):
    __tablename__ = "bookings"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=False, index=True)
    ambulance_id = db.Column(db.Integer, db.ForeignKey("ambulances.id"), nullable=False)
    booking_type = db.Column(db.String(20), nullable=False, index=True)
    status = db.Column(db.String(20), default=BookingStatus.PENDING.value, nullable=False, index=True)
    pickup_latitude = db.Column(db.Float, nullable=False)
    pickup_longitude = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    smart_dispatch_score = db.Column(db.Float, nullable=True)
    distance_km = db.Column(db.Float, nullable=True)
    eta_minutes = db.Column(db.Integer, nullable=True)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    notified_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    en_route_at = db.Column(db.DateTime, nullable=True)
    arrived_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    rejected_at = db.Column(db.DateTime, nullable=True)
    escalation_count = db.Column(db.Integer, default=0, nullable=False)
    priority = db.Column(db.String(12), default="MEDIUM", nullable=False, index=True)
    emergency_category = db.Column(db.String(80), nullable=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey("hospitals.id"), nullable=True, index=True)
    patient = db.relationship("Patient", backref="bookings")
    driver = db.relationship("Driver", backref="bookings")
    ambulance = db.relationship("Ambulance", backref="bookings")


class DriverLocation(db.Model):
    __tablename__ = "driver_locations"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), nullable=True, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    speed = db.Column(db.Float, nullable=True)
    heading = db.Column(db.Float, nullable=True)
    accuracy = db.Column(db.Float, nullable=True)
    gps_status = db.Column(db.String(10), default="LIVE", nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class BookingEvent(db.Model):
    __tablename__ = "booking_events"
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class VerificationRecord(db.Model):
    __tablename__ = "verification_records"
    id = db.Column(db.Integer, primary_key=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_score = db.Column(db.Integer, nullable=False, default=50)
    flags = db.Column(db.Text, nullable=False, default="[]")
    ambulance_proof_path = db.Column(db.String(255), nullable=True)
    mobile_verified = db.Column(db.Boolean, default=False, nullable=False)
    document_status = db.Column(db.String(30), default="SUBMITTED", nullable=False)
    ai_risk_score = db.Column(db.Integer, nullable=True)
    ai_flags = db.Column(db.Text, nullable=True)
    ai_result = db.Column(db.String(30), nullable=True)
    ai_confidence = db.Column(db.Integer, nullable=True)
    ocr_result = db.Column(db.String(80), nullable=True)
    ocr_match = db.Column(db.String(20), nullable=True)
    photo_sha256 = db.Column(db.String(64), nullable=True, index=True)
    review_status = db.Column(db.String(30), default=VerificationStatus.PENDING.value, nullable=False)
    document_name = db.Column(db.String(255), nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class AdminUser(db.Model):
    __tablename__ = "admin_users"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)


class Hospital(db.Model):
    __tablename__ = "hospitals"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    state = db.Column(db.String(80), nullable=True, index=True)
    district = db.Column(db.String(100), nullable=True, index=True)
    city = db.Column(db.String(100), nullable=True, index=True)
    zone = db.Column(db.String(100), nullable=True, index=True)
    speciality = db.Column(db.String(160), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)
    status = db.relationship("HospitalStatus", backref="hospital", uselist=False, cascade="all, delete-orphan")


class HospitalStatus(db.Model):
    __tablename__ = "hospital_status"
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey("hospitals.id", ondelete="CASCADE"), unique=True, nullable=False)
    emergency_ready = db.Column(db.Boolean, default=True, nullable=False)
    icu_available = db.Column(db.Integer, default=0, nullable=False)
    beds_available = db.Column(db.Integer, default=0, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class EmergencyContact(db.Model):
    __tablename__ = "emergency_contacts"
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    mobile = db.Column(db.String(30), nullable=False)
    consented = db.Column(db.Boolean, default=False, nullable=False)


class CoverageZone(db.Model):
    __tablename__ = "coverage_zones"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    state = db.Column(db.String(80), nullable=True, index=True)
    district = db.Column(db.String(100), nullable=True, index=True)
    city = db.Column(db.String(100), nullable=True, index=True)
    zone = db.Column(db.String(100), nullable=True, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    coverage_status = db.Column(db.String(10), default="RED", nullable=False)
    available_ambulances = db.Column(db.Integer, default=0, nullable=False)
    demand_level = db.Column(db.String(10), default="LOW", nullable=False)


class DemandPrediction(db.Model):
    __tablename__ = "demand_predictions"
    id = db.Column(db.Integer, primary_key=True)
    zone = db.Column(db.String(120), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    demand_level = db.Column(db.String(10), nullable=False)
    expected_demand = db.Column(db.Float, nullable=False, default=0)
    is_demo = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class DispatchDecision(db.Model):
    __tablename__ = "dispatch_decisions"
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id"), nullable=True)
    score = db.Column(db.Float, nullable=False)
    reason = db.Column(db.Text, nullable=False, default="[]")
    manual_override = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class RiskFlag(db.Model):
    __tablename__ = "risk_flags"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    driver_id = db.Column(db.Integer, db.ForeignKey("drivers.id", ondelete="CASCADE"), nullable=True, index=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True, index=True)
    category = db.Column(db.String(60), nullable=False)
    severity = db.Column(db.String(20), nullable=False, default="WARNING")
    details = db.Column(db.Text, nullable=False)
    reviewed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(80), nullable=False, index=True)
    resource_type = db.Column(db.String(80), nullable=False)
    resource_id = db.Column(db.Integer, nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


