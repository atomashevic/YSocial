from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# init SQLAlchemy so we can use it later in our models
db = SQLAlchemy()

app = Flask(__name__, static_url_path='/static')

app.config['SECRET_KEY'] = '4323432nldsf'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{BASE_DIR}/v1.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

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

# blueprint for non-auth parts of app
from .main import main as main_blueprint
app.register_blueprint(main_blueprint)

from .user_interaction import user as user_blueprint

app.register_blueprint(user_blueprint)
