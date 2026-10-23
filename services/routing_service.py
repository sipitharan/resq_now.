from services.matching import distance_km


class DemoRoutingProvider:
    """Deterministic fallback routing provider; it does not represent live traffic."""

    name = "DEMO_ROUTING"

    def estimate(self, origin_lat, origin_lon, destination_lat, destination_lon):
        distance = distance_km(origin_lat, origin_lon, destination_lat, destination_lon) * 1.18
        return {"distance_km": round(distance, 2), "eta_minutes": max(2, round(distance / 0.55)), "traffic_source": self.name}


def get_routing_provider(config):
    return DemoRoutingProvider()
