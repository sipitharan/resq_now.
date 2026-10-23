import os

from app import app
from models import AdminUser, User, db


with app.app_context():
    mobile = os.environ.get("RESQNOW_ADMIN_MOBILE")
    password = os.environ.get("RESQNOW_ADMIN_PASSWORD")
    if not mobile or not password:
        raise SystemExit("Set RESQNOW_ADMIN_MOBILE and RESQNOW_ADMIN_PASSWORD before running this command.")

    stale_admins = User.query.filter_by(role="ADMIN").all()
    for user in stale_admins:
        db.session.query(AdminUser).filter_by(user_id=user.id).delete()
        db.session.delete(user)

    existing = User.query.filter_by(mobile=mobile).first()
    if existing:
        db.session.query(AdminUser).filter_by(user_id=existing.id).delete()
        db.session.delete(existing)

    user = User(name="ResQNow Operations", mobile=mobile, role="ADMIN", mobile_verified=True, is_active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    db.session.add(AdminUser(user_id=user.id))
    db.session.commit()
    print(f"Admin account reset for mobile {mobile}. Store the credentials in a secret manager.")