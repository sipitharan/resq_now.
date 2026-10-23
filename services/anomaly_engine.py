import json


def detect_gps_anomaly(previous, current, elapsed_seconds):
    if not current or not (-90 <= current[0] <= 90 and -180 <= current[1] <= 180):
        return {"category": "INVALID_COORDINATES", "severity": "HIGH"}
    if previous and elapsed_seconds > 0:
        from services.matching import distance_km
        speed = distance_km(previous[0], previous[1], current[0], current[1]) / (elapsed_seconds / 3600)
        if speed > 180:
            return {"category": "IMPOSSIBLE_MOVEMENT", "severity": "HIGH", "speed_kmh": round(speed, 1)}
    return None


def verification_flags(flags):
    return json.dumps(flags or [])
