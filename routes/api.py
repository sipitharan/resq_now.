from datetime import datetime
from functools import wraps
import re

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from flask_socketio import emit, join_room

from extensions import emit_realtime, get_pusher_client, socketio
from models import Ambulance, AuditLog, Booking, BookingEvent, BookingStatus, BookingType, DispatchDecision, Driver, DriverLocation, Hospital, HospitalStatus, Notification, RiskFlag, VerificationStatus, db
from services.dispatch_engine import recommend_ambulances
from services.routing_service import get_routing_provider
from services.matching import distance_km, nearby_ambulances

api_bp = Blueprint("api", __name__)


@api_bp.get("/status")
def status():
    return jsonify(status="ready")


def role_required(*roles):
    def decorator(function):
        @wraps(function)
        @login_required
        def wrapped(*args, **kwargs):
            if current_user.role not in roles:
                return jsonify(error="Forbidden"), 403
            return function(*args, **kwargs)
        return wrapped
    return decorator


@api_bp.post("/pusher/auth")
@login_required
def pusher_auth():
    if current_app.config["REALTIME_PROVIDER"] != "pusher":
        return jsonify(error="Pusher authentication is not enabled"), 404
    channel = request.form.get("channel_name", "")
    socket_id = request.form.get("socket_id", "")
    match = re.fullmatch(r"private-(driver|patient)-(\d+)", channel)
    if not match or not socket_id or not current_user.is_active:
        return jsonify(error="Forbidden"), 403

    profile_type, profile_id = match.groups()
    if profile_type == "driver":
        allowed = current_user.role == "DRIVER" and current_user.driver_profile and current_user.driver_profile.id == int(profile_id)
    else:
        allowed = current_user.role == "PATIENT" and current_user.patient_profile and current_user.patient_profile.id == int(profile_id)
    if not allowed:
        return jsonify(error="Forbidden"), 403

    pusher_client = get_pusher_client()
    if pusher_client is None:
        raise RuntimeError("Pusher is not initialized")
    return jsonify(pusher_client.authenticate(channel, socket_id))


@api_bp.post("/driver/status")
@role_required("DRIVER")
def update_driver_status():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON object is required"), 400
    online = data.get("online")
    if not isinstance(online, bool):
        return jsonify(error="An online boolean is required"), 400
    result, status_code = _set_driver_online(current_user.driver_profile, online)
    return jsonify(result), status_code


@api_bp.post("/driver/location")
@role_required("DRIVER")
def update_driver_location():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="A JSON object is required"), 400
    result, status_code = _process_driver_location(current_user.driver_profile, data)
    return jsonify(result), status_code


def booking_payload(booking):
    return {"id": booking.id, "type": booking.booking_type, "priority": booking.priority, "category": booking.emergency_category, "status": booking.status, "driver_name": booking.driver.user.name, "driver_mobile": booking.driver.user.mobile, "ambulance_number": booking.ambulance.number, "ambulance_type": booking.ambulance.ambulance_type, "patient_latitude": booking.pickup_latitude, "patient_longitude": booking.pickup_longitude, "eta_minutes": booking.eta_minutes, "distance_km": booking.distance_km, "dispatch_score": booking.smart_dispatch_score, "requested_at": booking.requested_at.isoformat() if booking.requested_at else None, "accepted_at": booking.accepted_at.isoformat() if booking.accepted_at else None}


def add_booking_event(booking, actor_user_id, event_type):
    db.session.add(BookingEvent(booking_id=booking.id, actor_user_id=actor_user_id, event_type=event_type))


def _set_driver_online(driver, online):
    if online and (driver.verification_status != VerificationStatus.VERIFIED.value or not current_user.is_active):
        return {"error": "Only active, verified drivers can go online"}, 409
    driver.is_online = online
    if not online:
        driver.latitude = None
        driver.longitude = None
    db.session.commit()
    return {"ok": True, "online": online}, 200


def _process_driver_location(driver, data):
    if not isinstance(data, dict):
        return {"error": "A JSON object is required"}, 400
    if not driver.is_online:
        return {"error": "Go online before sharing GPS"}, 409
    try:
        latitude, longitude = float(data["latitude"]), float(data["longitude"])
    except (KeyError, TypeError, ValueError):
        return {"error": "Valid GPS coordinates are required"}, 400
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        driver.gps_status = "LOST"
        driver.gps_anomaly_count = (driver.gps_anomaly_count or 0) + 1
        db.session.commit()
        return {"error": "GPS coordinates are outside the valid range"}, 400

    booking_id = data.get("booking_id")
    if booking_id is not None:
        try:
            booking_id = int(booking_id)
        except (TypeError, ValueError):
            return {"error": "Invalid booking ID"}, 400
        booking = db.session.get(Booking, booking_id)
        if not booking or booking.driver_id != driver.id:
            return {"error": "Booking does not belong to this driver"}, 403

    now = datetime.utcnow()
    if driver.latitude is not None and driver.longitude is not None and driver.last_gps_at:
        elapsed = max((now - driver.last_gps_at).total_seconds(), 1)
        jump = distance_km(driver.latitude, driver.longitude, latitude, longitude)
        if jump / (elapsed / 3600) > 180:
            driver.gps_status = "STALE"
            driver.gps_anomaly_count = (driver.gps_anomaly_count or 0) + 1
            db.session.commit()
            return {"error": "GPS movement was flagged as anomalous"}, 400

    driver.latitude, driver.longitude = latitude, longitude
    driver.last_gps_at, driver.gps_status = now, "LIVE"
    db.session.add(DriverLocation(
        driver_id=driver.id,
        booking_id=booking_id,
        latitude=latitude,
        longitude=longitude,
        speed=data.get("speed"),
        heading=data.get("heading"),
        accuracy=data.get("accuracy"),
        gps_status="LIVE",
    ))
    db.session.commit()

    if booking_id:
        booking = db.session.get(Booking, booking_id)
    else:
        booking = Booking.query.filter_by(driver_id=driver.id, booking_type="EMERGENCY").filter(
            Booking.status.in_(["ACCEPTED", "EN_ROUTE", "ARRIVED"])
        ).first()
    if booking and booking.driver_id == driver.id and booking.booking_type == "EMERGENCY" and booking.status in {"ACCEPTED", "EN_ROUTE", "ARRIVED"}:
        emit_realtime("ambulance_location_update", {
            "booking_id": booking.id,
            "latitude": latitude,
            "longitude": longitude,
            "speed": data.get("speed"),
            "heading": data.get("heading"),
            "accuracy": data.get("accuracy"),
            "timestamp": datetime.utcnow().isoformat(),
        }, room=f"patient:{booking.patient_id}")
    return {"ok": True}, 200


@api_bp.post("/location")
@role_required("PATIENT")
def patient_location():
    data = request.json or {}
    if not isinstance(data.get("latitude"), (int, float)) or not isinstance(data.get("longitude"), (int, float)):
        return jsonify(error="Valid coordinates required"), 400
    return jsonify(ok=True)


@api_bp.get("/ambulances")
@role_required("PATIENT")
def ambulances():
    latitude = request.args.get("latitude", type=float)
    longitude = request.args.get("longitude", type=float)
    if latitude is None or longitude is None:
        return jsonify(error="Location is required"), 400
    return jsonify(ambulances=nearby_ambulances(latitude, longitude, request.args.get("mode", "EMERGENCY") == "EMERGENCY"))


@api_bp.post("/bookings")
@role_required("PATIENT")
def create_booking():
    data = request.json or {}
    patient = current_user.patient_profile
    latitude, longitude = data.get("latitude", patient.latitude), data.get("longitude", patient.longitude)
    driver = db.session.get(Driver, data.get("driver_id"))
    booking_type = data.get("type", BookingType.EMERGENCY.value)
    priority = str(data.get("priority", "MEDIUM")).upper()
    if booking_type not in {BookingType.EMERGENCY.value, BookingType.NON_EMERGENCY.value} or priority not in {"CRITICAL", "HIGH", "MEDIUM", "LOW"}:
        return jsonify(error="Invalid booking type or dispatch priority"), 400
    if not driver or not driver.ambulance or latitude is None or longitude is None:
        return jsonify(error="Valid patient location and ambulance are required"), 400
    if booking_type == BookingType.EMERGENCY.value and (driver.verification_status != VerificationStatus.VERIFIED.value or not driver.is_online or driver.ambulance.status != "AVAILABLE"):
        return jsonify(error="This ambulance is not emergency eligible"), 409
    ranked = recommend_ambulances(latitude, longitude, data.get("category"), priority) if booking_type == BookingType.EMERGENCY.value else nearby_ambulances(latitude, longitude, False)
    candidate = next((item for item in ranked if item["driver_id"] == driver.id), None)
    routing = get_routing_provider(current_app.config).estimate(driver.latitude, driver.longitude, latitude, longitude) if driver.latitude is not None else {"distance_km": candidate["distance_km"] if candidate else None, "eta_minutes": candidate["eta_minutes"] if candidate else None}
    booking = Booking(patient_id=patient.id, driver_id=driver.id, ambulance_id=driver.ambulance.id, booking_type=booking_type, priority=priority, emergency_category=data.get("category"), pickup_latitude=latitude, pickup_longitude=longitude, distance_km=routing.get("distance_km"), eta_minutes=routing.get("eta_minutes"), smart_dispatch_score=candidate["dispatch_score"] if candidate else None)
    db.session.add(booking)
    db.session.flush()
    add_booking_event(booking, current_user.id, "REQUESTED")
    booking.notified_at = datetime.utcnow()
    add_booking_event(booking, current_user.id, "DRIVER_NOTIFIED")
    db.session.add(DispatchDecision(booking_id=booking.id, driver_id=driver.id, score=booking.smart_dispatch_score or 0, reason="[\"ETA\", \"distance\", \"capability\", \"reliability\", \"GPS freshness\", \"workload\"]"))
    db.session.add(Notification(user_id=driver.user_id, message=f"New {booking_type.replace('_', ' ').lower()} request #{booking.id}"))
    db.session.commit()
    emit_realtime("emergency_request_received", {"booking": booking_payload(booking)}, room=f"driver:{driver.id}")
    return jsonify(booking=booking_payload(booking)), 201


@api_bp.get("/bookings")
@login_required
def bookings():
    if current_user.role == "PATIENT":
        items = Booking.query.filter_by(patient_id=current_user.patient_profile.id).order_by(Booking.created_at.desc()).all()
    else:
        items = Booking.query.filter_by(driver_id=current_user.driver_profile.id).order_by(Booking.created_at.desc()).all()
    return jsonify(bookings=[booking_payload(item) for item in items])


@api_bp.post("/bookings/<int:booking_id>/decision")
@role_required("DRIVER")
def decision(booking_id):
    booking, driver = db.session.get(Booking, booking_id), current_user.driver_profile
    if not booking or booking.driver_id != driver.id or booking.status != BookingStatus.PENDING.value:
        return jsonify(error="Booking cannot be changed"), 409
    accept = bool((request.json or {}).get("accept"))
    if accept and booking.booking_type == BookingType.EMERGENCY.value and (driver.verification_status != VerificationStatus.VERIFIED.value or not driver.is_online):
        return jsonify(error="Only verified online drivers can accept requests"), 409
    booking.status = BookingStatus.ACCEPTED.value if accept else BookingStatus.REJECTED.value
    booking.accepted_at = datetime.utcnow() if accept else None
    booking.rejected_at = None if accept else datetime.utcnow()
    driver.total_requests = (driver.total_requests or 0) + 1
    if accept:
        driver.acceptance_rate = round(((driver.total_requests - 1) * driver.acceptance_rate + 100) / driver.total_requests, 2)
    else:
        driver.acceptance_rate = round((driver.total_requests - 1) * driver.acceptance_rate / driver.total_requests, 2)
    if accept:
        driver.ambulance.status = "BUSY"
    add_booking_event(booking, current_user.id, booking.status)
    db.session.add(Notification(user_id=booking.patient.user_id, message=f"Booking #{booking.id} {booking.status.lower()}"))
    fallback = None
    if not accept and booking.booking_type == BookingType.EMERGENCY.value:
        alternatives = recommend_ambulances(booking.pickup_latitude, booking.pickup_longitude, booking.emergency_category, booking.priority)
        fallback = next((item for item in alternatives if item["driver_id"] != driver.id), None)
        if fallback:
            alternative_driver = db.session.get(Driver, fallback["driver_id"])
            booking.driver_id, booking.ambulance_id = alternative_driver.id, alternative_driver.ambulance.id
            booking.status = BookingStatus.PENDING.value
            booking.escalation_count = (booking.escalation_count or 0) + 1
            add_booking_event(booking, current_user.id, "FALLBACK_SEARCH")
            db.session.add(Notification(user_id=alternative_driver.user_id, message=f"Fallback emergency request #{booking.id} requires a response."))
            db.session.add(Notification(user_id=booking.patient.user_id, message="The first ambulance declined. ResQNow is searching for an alternative."))
    db.session.commit()
    emit_realtime("booking_accepted" if accept else "booking_rejected", {"booking": booking_payload(booking)}, room=f"patient:{booking.patient_id}")
    if accept and booking.booking_type == BookingType.EMERGENCY.value:
        emit_realtime("tracking_started", {"booking": booking_payload(booking)}, room=f"patient:{booking.patient_id}")
    return jsonify(booking=booking_payload(booking), fallback_found=bool(fallback))


@api_bp.post("/bookings/<int:booking_id>/status")
@role_required("DRIVER")
def update_booking_status(booking_id):
    booking = db.session.get(Booking, booking_id)
    status_value = (request.json or {}).get("status")
    if not booking or booking.driver_id != current_user.driver_profile.id:
        return jsonify(error="Booking not found"), 404
    if status_value not in {"EN_ROUTE", "ARRIVED", "COMPLETED", "CANCELLED"}:
        return jsonify(error="Invalid status"), 400
    booking.status = status_value
    timestamp_fields = {"EN_ROUTE": "en_route_at", "ARRIVED": "arrived_at", "COMPLETED": "completed_at"}
    if status_value in timestamp_fields:
        setattr(booking, timestamp_fields[status_value], datetime.utcnow())
    if status_value == "COMPLETED":
        driver = current_user.driver_profile
        driver.completed_trips = (driver.completed_trips or 0) + 1
    if status_value == "CANCELLED":
        current_user.driver_profile.cancellation_rate = min(100, (current_user.driver_profile.cancellation_rate or 0) + 5)
    if status_value in {"COMPLETED", "CANCELLED"}:
        booking.ambulance.status = "AVAILABLE"
        emit_realtime("tracking_stopped", {"booking_id": booking.id}, room=f"patient:{booking.patient_id}")
    add_booking_event(booking, current_user.id, status_value)
    db.session.commit()
    emit_realtime("booking_status_changed", {"booking": booking_payload(booking)}, room=f"patient:{booking.patient_id}")
    return jsonify(booking=booking_payload(booking))


@api_bp.get("/admin/summary")
@role_required("ADMIN")
def admin_summary():
    drivers = Driver.query.all()
    return jsonify(total_drivers=len(drivers), verified_drivers=sum(d.verification_status == "VERIFIED" for d in drivers), pending_verification=sum(d.verification_status in {"PENDING", "UNDER_REVIEW", "PENDING REVIEW"} for d in drivers), online_ambulances=Ambulance.query.join(Driver).filter(Driver.is_online.is_(True), Ambulance.status == "AVAILABLE").count(), busy_ambulances=Ambulance.query.filter_by(status="BUSY").count(), active_emergencies=Booking.query.filter_by(booking_type="EMERGENCY").filter(Booking.status.in_(["PENDING", "ACCEPTED", "EN_ROUTE", "ARRIVED"])).count(), completed_bookings=Booking.query.filter_by(status="COMPLETED").count())


@api_bp.get("/admin/drivers")
@role_required("ADMIN")
def admin_drivers():
    return jsonify(drivers=[{"id": d.id, "name": d.user.name, "mobile": d.user.mobile, "email": d.user.email, "ambulance_number": d.ambulance_registration_number, "ambulance_type": d.ambulance.ambulance_type if d.ambulance else None, "available_timing": f"{d.available_start} - {d.available_end}", "photo_url": f"/admin/drivers/{d.id}/photo", "ai_result": d.ai_result, "ai_confidence": d.ai_confidence, "ai_risk_score": d.ai_risk_score, "ocr_result": d.ocr_result, "ocr_match": d.ocr_match, "registered_at": d.user.created_at.isoformat(), "latitude": d.latitude, "longitude": d.longitude, "verification_status": d.verification_status} for d in Driver.query.order_by(Driver.id.desc()).all()])


@api_bp.get("/admin/intelligence")
@role_required("ADMIN")
def admin_intelligence():
    emergencies = Booking.query.filter_by(booking_type=BookingType.EMERGENCY.value).all()
    active = [booking for booking in emergencies if booking.status in {"PENDING", "ACCEPTED", "EN_ROUTE", "ARRIVED"}]
    response_times = [(booking.accepted_at - booking.requested_at).total_seconds() for booking in emergencies if booking.accepted_at and booking.requested_at]
    arrival_times = [(booking.arrived_at - booking.requested_at).total_seconds() for booking in emergencies if booking.arrived_at and booking.requested_at]
    heatmap = [{"latitude": round(booking.pickup_latitude, 3), "longitude": round(booking.pickup_longitude, 3), "weight": 1} for booking in emergencies]
    drivers = Driver.query.all()
    for driver in drivers:
        if not driver.is_online or not driver.last_gps_at:
            driver.gps_status = "LOST"
        elif (datetime.utcnow() - driver.last_gps_at).total_seconds() > 30:
            driver.gps_status = "STALE"
    db.session.commit()
    payload = {
        "metrics": {
            "average_acceptance_seconds": round(sum(response_times) / len(response_times), 1) if response_times else 0,
            "average_arrival_seconds": round(sum(arrival_times) / len(arrival_times), 1) if arrival_times else 0,
            "utilization_percent": round(sum(driver.ambulance and driver.ambulance.status == "BUSY" for driver in drivers) / len(drivers) * 100, 1) if drivers else 0,
            "completed_emergencies": sum(booking.status == "COMPLETED" for booking in emergencies),
            "cancelled_emergencies": sum(booking.status == "CANCELLED" for booking in emergencies),
            "unserved_requests": sum(booking.status == "REJECTED" for booking in emergencies),
        },
        "gps_health": {"live": sum(driver.gps_status == "LIVE" for driver in drivers), "stale": sum(driver.gps_status == "STALE" for driver in drivers), "lost": sum(driver.gps_status == "LOST" for driver in drivers)},
        "active_emergencies": len(active),
        "heatmap": heatmap,
        "coverage": [{"zone": "Active network", "status": "GREEN" if len(drivers) >= 3 else "YELLOW" if drivers else "RED", "available": sum(bool(driver.is_online and driver.ambulance and driver.ambulance.status == "AVAILABLE") for driver in drivers)}],
        "alerts": [{"level": "WARNING", "message": f"{len(active)} emergency request(s) active"}] if active else [],
    }
    return jsonify(payload)


@api_bp.get("/hospitals")
@role_required("PATIENT", "ADMIN")
def hospitals():
    latitude = request.args.get("latitude", type=float)
    longitude = request.args.get("longitude", type=float)
    if latitude is None or longitude is None:
        return jsonify(error="Location is required"), 400
    items = []
    for hospital in Hospital.query.filter_by(is_active=True).all():
        distance = distance_km(latitude, longitude, hospital.latitude, hospital.longitude)
        status = hospital.status
        if status and status.emergency_ready:
            items.append({"id": hospital.id, "name": hospital.name, "speciality": hospital.speciality, "distance_km": round(distance, 2), "icu_available": status.icu_available, "beds_available": status.beds_available, "emergency_ready": True})
    return jsonify(hospitals=sorted(items, key=lambda item: (item["distance_km"], -item["beds_available"])))


@api_bp.post("/admin/bookings/<int:booking_id>/override")
@role_required("ADMIN")
def manual_dispatch_override(booking_id):
    booking = db.session.get(Booking, booking_id)
    driver = db.session.get(Driver, (request.json or {}).get("driver_id"))
    if not booking or not driver or not driver.ambulance or not driver.is_online or driver.ambulance.status != "AVAILABLE":
        return jsonify(error="A valid online available driver is required"), 400
    booking.driver_id, booking.ambulance_id = driver.id, driver.ambulance.id
    booking.status = BookingStatus.PENDING.value
    booking.escalation_count = (booking.escalation_count or 0) + 1
    db.session.add(DispatchDecision(booking_id=booking.id, driver_id=driver.id, score=0, reason="[\"ADMIN_MANUAL_OVERRIDE\"]", manual_override=True))
    add_booking_event(booking, current_user.id, "ADMIN_MANUAL_OVERRIDE")
    db.session.add(Notification(user_id=driver.user_id, message=f"Admin assigned emergency request #{booking.id}."))
    db.session.commit()
    emit_realtime("emergency_request_received", {"booking": booking_payload(booking)}, room=f"driver:{driver.id}")
    return jsonify(booking=booking_payload(booking), manual_override=True)


@api_bp.patch("/admin/hospitals/<int:hospital_id>/status")
@role_required("ADMIN")
def update_hospital_status(hospital_id):
    hospital = db.session.get(Hospital, hospital_id)
    data = request.json or {}
    if not hospital:
        return jsonify(error="Hospital not found"), 404
    status = hospital.status or HospitalStatus(hospital_id=hospital.id)
    status.emergency_ready = bool(data.get("emergency_ready", status.emergency_ready))
    status.icu_available = max(0, int(data.get("icu_available", status.icu_available)))
    status.beds_available = max(0, int(data.get("beds_available", status.beds_available)))
    db.session.add(status)
    db.session.commit()
    return jsonify(ok=True, hospital_id=hospital.id, emergency_ready=status.emergency_ready, icu_available=status.icu_available, beds_available=status.beds_available)


@api_bp.post("/admin/simulation/seed")
@role_required("ADMIN")
def seed_simulation():
    hospital = Hospital(name="DEMO City Emergency Hospital", latitude=12.02, longitude=77.02, city="DEMO CITY", zone="DEMO ZONE", speciality="Emergency and ICU")
    db.session.add(hospital)
    db.session.flush()
    db.session.add(HospitalStatus(hospital_id=hospital.id, emergency_ready=True, icu_available=8, beds_available=24))
    db.session.commit()
    return jsonify(ok=True, simulation=True, message="DEMO hospital seeded; simulated data is not live coverage.", hospital_id=hospital.id)


@api_bp.post("/admin/simulation/run")
@role_required("ADMIN")
def run_simulation():
    data = request.json or {}
    ambulance_count = max(1, min(int(data.get("ambulances", 10)), 100))
    request_count = max(1, min(int(data.get("requests", 20)), 1000))
    accepted = min(request_count, round(ambulance_count * 0.82))
    return jsonify(simulation=True, label="DEMO / SIMULATION", assumptions="Synthetic ambulances, requests, movement, and response times; not live operational data.", metrics={"ambulances": ambulance_count, "requests": request_count, "accepted": accepted, "unserved_requests": request_count - accepted, "dispatch_efficiency_percent": round(accepted / request_count * 100, 1), "utilization_percent": round(min(100, accepted / ambulance_count * 100), 1), "fallback_success_percent": 76})


@api_bp.post("/admin/drivers/<int:driver_id>/verification")
@role_required("ADMIN")
def review_driver(driver_id):
    driver = db.session.get(Driver, driver_id)
    status_value = (request.json or {}).get("status")
    status_map = {"APPROVE": "VERIFIED", "REJECT": "REJECTED", "REQUEST_REVIEW": "UNDER_REVIEW"}
    if not driver or status_value not in status_map:
        return jsonify(error="Invalid driver review"), 400
    driver.verification_status = status_map[status_value]
    if driver.verification_status == VerificationStatus.VERIFIED.value:
        driver.verified_at = datetime.utcnow()
    db.session.add(AuditLog(actor_user_id=current_user.id, action=f"DRIVER_{status_value}", resource_type="DRIVER", resource_id=driver.id, details=f"Status changed to {driver.verification_status}."))
    db.session.add(Notification(user_id=driver.user_id, message=f"Your ResQNow verification is now {driver.verification_status}."))
    db.session.commit()
    return jsonify(ok=True, driver_id=driver.id, status=driver.verification_status)


@api_bp.post("/admin/drivers/<int:driver_id>/disable")
@role_required("ADMIN")
def disable_driver(driver_id):
    driver = db.session.get(Driver, driver_id)
    if not driver:
        return jsonify(error="Driver not found"), 404
    driver.user.is_active = False
    driver.is_online = False
    if driver.ambulance:
        driver.ambulance.status = "OFFLINE"
    db.session.commit()
    return jsonify(ok=True)


@socketio.on("connect")
def socket_connect():
    if current_user.is_authenticated:
        if current_user.role == "DRIVER":
            join_room(f"driver:{current_user.driver_profile.id}")
        elif current_user.role == "PATIENT":
            join_room(f"patient:{current_user.patient_profile.id}")
    emit("notification", {"message": "Realtime connection established"})


@socketio.on("driver_online")
def driver_online(data=None):
    if current_user.is_authenticated and current_user.role == "DRIVER":
        driver = current_user.driver_profile
        if driver.verification_status != VerificationStatus.VERIFIED.value or not current_user.is_active:
            return
        driver.is_online = True
        db.session.commit()


@socketio.on("driver_offline")
def driver_offline(data=None):
    if current_user.is_authenticated and current_user.role == "DRIVER":
        _set_driver_online(current_user.driver_profile, False)


@socketio.on("driver_location_update")
def driver_location_update(data):
    if not current_user.is_authenticated or current_user.role != "DRIVER":
        return
    _process_driver_location(current_user.driver_profile, data)


@socketio.on("join_tracking")
def join_tracking(data):
    if not current_user.is_authenticated or current_user.role != "PATIENT":
        return
    booking = db.session.get(Booking, (data or {}).get("booking_id"))
    if booking and booking.patient.user_id == current_user.id and booking.booking_type == "EMERGENCY" and booking.status in {"ACCEPTED", "EN_ROUTE", "ARRIVED"}:
        join_room(f"patient:{booking.patient_id}")
