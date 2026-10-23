from math import atan2, cos, radians, sin, sqrt
from datetime import datetime
import json

from models import Ambulance, Booking, Driver, VerificationStatus


def distance_km(lat1, lon1, lat2, lon2):
    earth_radius = 6371
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return earth_radius * 2 * atan2(sqrt(a), sqrt(1 - a))


def nearby_ambulances(latitude, longitude, emergency=False):
    query = Ambulance.query.join(Driver).filter(
        Driver.is_online.is_(True),
        Driver.verification_status == VerificationStatus.VERIFIED.value,
        Ambulance.status == "AVAILABLE",
        Driver.latitude.isnot(None),
        Driver.longitude.isnot(None),
    )
    results = []
    for ambulance in query.all():
        driver = ambulance.driver
        current_time = datetime.utcnow().strftime("%H:%M")
        if driver.available_start and driver.available_end and not (driver.available_start <= current_time <= driver.available_end):
            continue
        distance = distance_km(latitude, longitude, driver.latitude, driver.longitude)
        gps_age = max(0, (datetime.utcnow() - (driver.last_gps_at or datetime.utcnow())).total_seconds())
        gps_freshness = max(0, 100 - min(gps_age / 3, 100))
        workload = Booking.query.filter(Booking.driver_id == driver.id, Booking.status.in_(["PENDING", "ACCEPTED", "EN_ROUTE", "ARRIVED"])).count()
        capability = 100 if (ambulance.ambulance_type or "").lower() in {"advanced life support", "basic life support"} else 70
        eta = max(2, round(distance / 0.55))
        dispatch_score = round(
            max(0, 100 - min(distance * 2.5, 45))
            + max(0, 30 - eta)
            + capability * 0.10
            + driver.reliability_score * 0.15
            + gps_freshness * 0.10
            - workload * 8,
            2,
        )
        try:
            capabilities = json.loads(ambulance.capabilities or "[]")
        except (TypeError, ValueError):
            capabilities = []
        results.append({
            "id": ambulance.id,
            "driver_id": driver.id,
            "driver_name": driver.user.name,
            "ambulance_number": ambulance.number,
            "ambulance_type": ambulance.ambulance_type,
            "mobile": driver.user.mobile,
            "latitude": driver.latitude,
            "longitude": driver.longitude,
            "distance_km": round(distance, 2),
            "eta_minutes": eta,
            "availability": f"{driver.available_start or 'Flexible'} - {driver.available_end or 'Flexible'}",
            "gps_status": driver.gps_status,
            "gps_age_seconds": round(gps_age),
            "reliability_score": round(driver.reliability_score, 1),
            "workload": workload,
            "capabilities": capabilities,
            "dispatch_score": dispatch_score,
            "emergency_eligible": driver.verification_status == VerificationStatus.VERIFIED.value,
        })
    return sorted(results, key=lambda item: item["dispatch_score"], reverse=True)
