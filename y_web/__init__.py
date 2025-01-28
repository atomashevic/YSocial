from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import shutil
import os


import signal
import atexit

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# init SQLAlchemy so we can use it later in our models


app = Flask(__name__, static_url_path="/static")


client_processes = {}


def cleanup_subprocesses():
    """Terminate all subprocesses."""
    print("Cleaning up subprocesses...")
    for _, proc in client_processes.items():
        print(f"Terminating subprocess {proc.pid}...")
        proc.terminate() # Wait for the process to terminate
        proc.join()
    print("All subprocesses terminated.")


# Register cleanup for Ctrl+C (SIGINT)
def signal_handler(sig, frame):
    print("Ctrl+C detected, shutting down...")
    cleanup_subprocesses()
    exit(0)


signal.signal(signal.SIGINT, signal_handler)

# Register cleanup on normal program exit
atexit.register(cleanup_subprocesses)

# check if the database dashboard.db exists in the db directory, if not copy from data_schema
if not os.path.exists(f"{BASE_DIR}/db/dashboard.db"):
    shutil.copyfile(
        f"{BASE_DIR}/../data_schema/database_dashboard.db",
        f"{BASE_DIR}/db/dashboard.db",
    )
    shutil.copyfile(
        f"{BASE_DIR}/../data_schema/database_clean_server.db", f"{BASE_DIR}/db/dummy.db"
    )


app.config["SECRET_KEY"] = "4323432nldsf"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR}/db/dashboard.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SQLALCHEMY_BINDS"] = {
    "db_admin": f"sqlite:///{BASE_DIR}/db/dashboard.db",
    "db_exp": f"sqlite:///{BASE_DIR}/db/dummy.db",
}

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.init_app(app)

from .models import User_mgmt as User


@login_manager.user_loader
def load_user(user_id):
    # since the user_id is just the primary key of our user table, use it in the query for the user
    return User.query.get(int(user_id))


# blueprint for auth routes in our app
from .auth import auth as auth_blueprint

app.register_blueprint(auth_blueprint)


# blueprint for non-auth parts of app
from .main import main as main_blueprint

app.register_blueprint(main_blueprint)

from .user_interaction import user as user_blueprint

app.register_blueprint(user_blueprint)


from .admin_dashboard import admin as admin_blueprint

app.register_blueprint(admin_blueprint)

from .routes_admin.ollama_routes import ollama as ollama_blueprint

app.register_blueprint(ollama_blueprint)


from .routes_admin.populations_routes import population as population_blueprint

app.register_blueprint(population_blueprint)


from .routes_admin.pages_routes import pages as pages_blueprint

app.register_blueprint(pages_blueprint)

from .routes_admin.agents_routes import agents as agents_blueprint

app.register_blueprint(agents_blueprint)

from .routes_admin.users_routes import users as users_blueprint

app.register_blueprint(users_blueprint)

from .routes_admin.experiments_routes import experiments as experiments_blueprint

app.register_blueprint(experiments_blueprint)

from .routes_admin.clients_routes import clientsr as clients_blueprint

app.register_blueprint(clients_blueprint)

