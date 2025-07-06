from y_web.models import (
    Admin_users,
    User_mgmt,
)

from y_web.utils import (
    is_ollama_running,
    is_ollama_installed,
)

from y_web import db
from flask_login import login_user

from flask import redirect, url_for


def check_privileges(username):
    user = Admin_users.query.filter_by(username=username).first()

    if user.role != "admin":
        return redirect(url_for("main.index"))
    return


def reload_current_user(username):
    user = db.session.query(User_mgmt).filter_by(username=username).first()
    login_user(user, remember=True, force=True)


def ollama_status():
    return {
        "status": is_ollama_running(),
        "installed": is_ollama_installed(),
    }


def check_connection():
    try:
        db.engine.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"PostgreSQL connection error: {e}")
        return False


def get_db_type():
    db_uri = db.get_engine().url
    if db_uri.drivername == "postgresql":
        return "postgresql"
    elif db_uri.drivername == "sqlite":
        return "sqlite"
    else:
        raise ValueError(f"Unsupported database type: {db_uri.drivername}")


def get_db_port():
    db_uri = db.get_engine().url
    if db_uri.drivername == "postgresql":
        return db_uri.port or 5432  # Default PostgreSQL port
    elif db_uri.drivername == "sqlite":
        return None  # SQLite does not use a port
    else:
        raise ValueError(f"Unsupported database type: {db_uri.drivername}")


def get_db_server():
    db_uri = db.get_engine().url
    if db_uri.drivername == "postgresql":
        return db_uri.host or "localhost"  # Default to localhost if no host is specified
    elif db_uri.drivername == "sqlite":
        return None  # SQLite does not use a server
    else:
        raise ValueError(f"Unsupported database type: {db_uri.drivername}")