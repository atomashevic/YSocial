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