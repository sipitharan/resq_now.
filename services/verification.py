import hashlib
import json
from pathlib import Path

from models import VerificationRecord


def _normalize_plate(value):
    return "".join(str(value or "").upper().split())


def assess_driver(driver, photo_name=None, photo_path=None, registered_number=None):
    """Run available local checks; absent models/providers always require review."""
    flags = []
    risk_score = 50
    confidence = 0
    ocr_result = None
    ocr_match = "UNREADABLE"
    photo_sha256 = None
    path = Path(photo_path) if photo_path else None
    if not path or not path.is_file() or path.stat().st_size == 0:
        flags.append("Photo is missing or empty")
        return {"ai_result": "AI_FAILED", "confidence": 0, "risk_score": 100, "ocr_result": None, "ocr_match": ocr_match, "flags": json.dumps(flags), "photo_sha256": None}
    photo_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if VerificationRecord.query.filter(VerificationRecord.photo_sha256 == photo_sha256).first():
        flags.append("Duplicate or reused photo detected")
        risk_score += 30
    try:
        from PIL import Image
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.width < 320 or image.height < 240:
                flags.append("Photo resolution is too low")
                risk_score += 20
    except ImportError:
        flags.append("Image analysis provider is not installed")
    except (OSError, ValueError):
        flags.append("Photo is not a decodable image")
        return {"ai_result": "AI_FAILED", "confidence": 0, "risk_score": 100, "ocr_result": None, "ocr_match": ocr_match, "flags": json.dumps(flags), "photo_sha256": photo_sha256}
    flags.extend(["Person detection model is not configured", "Ambulance detection model is not configured", "OCR provider is not configured"])
    if ocr_result:
        ocr_match = "MATCH" if _normalize_plate(ocr_result) == _normalize_plate(registered_number) else "MISMATCH"
    return {"ai_result": "AI_REVIEW_REQUIRED", "confidence": confidence, "risk_score": min(risk_score + 15, 100), "ocr_result": ocr_result, "ocr_match": ocr_match, "flags": json.dumps(flags), "photo_sha256": photo_sha256}
