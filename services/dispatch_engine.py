from services.matching import nearby_ambulances


def recommend_ambulances(latitude, longitude, emergency_category=None, priority="MEDIUM"):
    candidates = nearby_ambulances(latitude, longitude, emergency=True)
    priority_bonus = {"CRITICAL": 10, "HIGH": 5, "MEDIUM": 0, "LOW": -2}.get(priority, 0)
    for candidate in candidates:
        candidate["dispatch_score"] = round(candidate["dispatch_score"] + priority_bonus, 2)
        candidate["score_reasons"] = ["verified driver", "live GPS", "available ambulance", "reliability and workload weighted"]
    return sorted(candidates, key=lambda item: item["dispatch_score"], reverse=True)
