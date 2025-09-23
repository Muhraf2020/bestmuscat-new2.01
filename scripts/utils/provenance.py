from datetime import datetime
def make_prov(stage, provider, fields):
    return {
        "stage": stage,
        "provider": provider or "unknown",
        "fields": fields or [],
        "collected_at": datetime.utcnow().strftime("%Y-%m-%d")
    }
