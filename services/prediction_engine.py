from collections import Counter


def predict_demand(bookings):
    """Research/demo estimate based on anonymized historical pickup cells."""
    cells = Counter((round(item.pickup_latitude, 2), round(item.pickup_longitude, 2)) for item in bookings)
    predictions = []
    for (latitude, longitude), count in cells.most_common():
        level = "CRITICAL" if count >= 20 else "HIGH" if count >= 10 else "MEDIUM" if count >= 3 else "LOW"
        predictions.append({"latitude": latitude, "longitude": longitude, "demand_level": level, "expected_demand": count, "is_estimate": True})
    return predictions
