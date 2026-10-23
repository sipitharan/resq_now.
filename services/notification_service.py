from models import Notification, db


def notify(user_id, message):
    notification = Notification(user_id=user_id, message=message)
    db.session.add(notification)
    return notification
