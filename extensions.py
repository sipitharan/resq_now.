from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

socketio = SocketIO(async_mode="threading", cors_allowed_origins="*")
pusher_client = None
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/day", "60/hour", "10/minute"],
    storage_uri="memory://",
)


def initialize_realtime(app):
    global pusher_client

    provider = app.config["REALTIME_PROVIDER"]
    if provider == "socketio":
        pusher_client = None
        return
    if provider != "pusher":
        raise RuntimeError(f"Unsupported realtime provider: {provider}")

    required = ("PUSHER_APP_ID", "PUSHER_KEY", "PUSHER_SECRET", "PUSHER_CLUSTER")
    missing = [name for name in required if not app.config.get(name)]
    if missing:
        raise RuntimeError(f"Pusher configuration is missing: {', '.join(missing)}")

    from pusher import Pusher

    pusher_client = Pusher(
        app_id=app.config["PUSHER_APP_ID"],
        key=app.config["PUSHER_KEY"],
        secret=app.config["PUSHER_SECRET"],
        cluster=app.config["PUSHER_CLUSTER"],
        ssl=True,
    )


def emit_realtime(event, payload, room):
    from flask import current_app

    if current_app.config["REALTIME_PROVIDER"] == "pusher":
        if pusher_client is None:
            raise RuntimeError("Pusher is not initialized")
        channel = f"private-{room.replace(':', '-')}"
        pusher_client.trigger(channel, event, payload)
        return

    socketio.emit(event, payload, room=room)


def get_pusher_client():
    return pusher_client
