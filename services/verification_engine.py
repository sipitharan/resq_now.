from services.verification import assess_driver


def verify_driver(driver, proof_path):
    """Replaceable verification adapter; admin remains final authority."""
    return assess_driver(driver, driver.photo_path, proof_path, driver.ambulance_registration_number)
