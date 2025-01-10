from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import shutil
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# init SQLAlchemy so we can use it later in our models


app = Flask(__name__, static_url_path='/static')

# check if the database dashboard.db exists in the db directory, if not copy from data_schema
if not os.path.exists(f"{BASE_DIR}/db/dashboard.db"):
    shutil.copyfile(f"{BASE_DIR}/../data_schema/database_dashboard.db", f"{BASE_DIR}/db/dashboard.db")
    shutil.copyfile(f"{BASE_DIR}/../data_schema/database_clean_server.db", f"{BASE_DIR}/db/dummy.db")


app.config['SECRET_KEY'] = '4323432nldsf'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{BASE_DIR}/db/dashboard.db'#  f'sqlite:///{BASE_DIR}/v1.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SQLALCHEMY_BINDS'] = {
    "db_admin": f'sqlite:///{BASE_DIR}/db/dashboard.db',
    "db_exp": f'sqlite:///{BASE_DIR}/db/dummy.db'
}

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.init_app(app)

from .models import User_mgmt as User


@login_manager.user_loader
def load_user(user_id):
    # since the user_id is just the primary key of our user table, use it in the query for the user
    return User.query.get(int(user_id))


# blueprint for auth routes in our app
from .auth import auth as auth_blueprint
app.register_blueprint(auth_blueprint)

from .admin_dashboard import admin as admin_blueprint

app.register_blueprint(admin_blueprint)

# blueprint for non-auth parts of app
from .main import main as main_blueprint
app.register_blueprint(main_blueprint)

from .user_interaction import user as user_blueprint

app.register_blueprint(user_blueprint)

