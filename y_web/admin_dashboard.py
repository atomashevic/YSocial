from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_user, login_required, logout_user, current_user
from .models import Exps, Admin_users, Exp_stats, User_mgmt, Rounds
import json
import os
import pathlib, shutil
import uuid
from . import db, app

admin = Blueprint('admin', __name__)


def check_privileges(username):
    user = Admin_users.query.filter_by(username=username).first()

    if user.role != "admin":
        return redirect(url_for('main.index'))
    return

def reload_current_user(username):
    user = db.session.query(User_mgmt).filter_by(username=username).first()
    login_user(user, remember=True, force=True)

@admin.route('/admin/dashboard')
@login_required
def dashboard():
    check_privileges(current_user.username)
    return render_template("admin/dashboard.html")


@admin.route('/admin/experiments')
@login_required
def settings():
    check_privileges(current_user.username)

    # load all experiments
    experiments = Exps.query.limit(5).all()
    users = Admin_users.query.all()

    # check if current db is the same of the active experiment
    exp = Exps.query.filter_by(status=1).first()
    if exp:
        active_db = app.config['SQLALCHEMY_BINDS']["db_exp"]
        if not exp.exp_name in active_db:
            # change the active experiment
            db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})

    return render_template("admin/settings.html", experiments=experiments, users=users)

@admin.route('/admin/join_simulation')
@login_required
def join_simulation():
    # get user id for the current user logged in
    user_id = db.session.query(User_mgmt).filter_by(username=current_user.username).first().id
    # route the simulation home for the user
    return redirect(f"/feed/{user_id}/feed/rf/1")


@admin.route('/admin/select_experiment/<int:exp_id>')
@login_required
def change_active_experiment(exp_id):
    check_privileges(current_user.username)
    uname = current_user.username

    exp = Exps.query.filter_by(idexp=exp_id).first()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    app.config['SQLALCHEMY_BINDS']["db_exp"] = f'sqlite:///{BASE_DIR}/{exp.db_name}'

    # check if the user is present in the User_mgmt table
    user = db.session.query(User_mgmt).filter_by(username=current_user.username).first()

    if user is None:
        new_user = User_mgmt(email=current_user.email,
                             username=current_user.username,
                             password=current_user.password,
                             user_type="user",
                             leaning="neutral",
                             age=0,
                             recsys_type="default",
                             language="en",
                             frecsys_type="default",
                             round_actions=1,
                             toxicity="no",
                             )
        db.session.add(new_user)
        db.session.commit()

    db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})
    db.session.query(Exps).filter_by(db_name=exp.db_name).update({Exps.status: 1})
    db.session.commit()

    reload_current_user(uname)

    # load all experiments
    experiments = Exps.query.limit(5).all()
    users = Admin_users.query.all()

    return render_template("admin/settings.html", experiments=experiments, users=users)


@admin.route('/admin/users')
@login_required
def user_data():
    check_privileges(current_user.username)
    return render_template("admin/users.html")

@admin.route('/admin/populations')
@login_required
def populations_data():
    check_privileges(current_user.username)
    return render_template("admin/populations.html")

@admin.route('/admin/agents')
@login_required
def agent_data():
    check_privileges(current_user.username)
    return render_template("admin/agents.html")

@admin.route('/admin/pages')
@login_required
def page_data():
    check_privileges(current_user.username)
    return render_template("admin/pages.html")

@admin.route('/admin/user_data')
@login_required
def data():
    query = Admin_users.query

    # search filter
    search = request.args.get('search')
    if search:
        query = query.filter(db.or_(
            Admin_users.username.like(f'%{search}%'),
            Admin_users.email.like(f'%{search}%')
        ))
    total = query.count()

    # sorting
    sort = request.args.get('sort')
    if sort:
        order = []
        for s in sort.split(','):
            direction = s[0]
            name = s[1:]
            if name not in ['username', 'role', 'email']:
                name = 'name'
            col = getattr(Admin_users, name)
            if direction == '-':
                col = col.desc()
            order.append(col)
        if order:
            query = query.order_by(*order)

    # pagination
    start = request.args.get('start', type=int, default=-1)
    length = request.args.get('length', type=int, default=-1)
    if start != -1 and length != -1:
        query = query.offset(start).limit(length)

    # response
    res = query.all()

    return {
        'data': [{"id": user.id, "username": user.username,
                  "email": user.email, "password": user.password,
                  "last_seen": user.last_seen, "role": user.role} for user in res],
        'total': total,
    }

@admin.route('/admin/user_data', methods=['POST'])
@login_required
def update():
    data = request.get_json()
    if 'id' not in data:
        abort(400)
    user = Admin_users.query.get(data['id'])
    for field in ['username', 'password', 'email', 'last_seen', 'role']:
        if field in data:
            setattr(user, field, data[field])
    db.session.commit()
    return '', 204

@admin.route('/admin/upload_database', methods=['POST'])
@login_required
def upload_database():
    check_privileges(current_user.username)

    database = request.files['sqlite_filename']
    config = request.files['yserver_filename']
    uid = uuid.uuid4()
    pathlib.Path(f"y_web{os.sep}experiments{os.sep}{uid}").mkdir(parents=True, exist_ok=True)

    database.save(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}{database.filename}")
    config.save(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}{config.filename}")

    try:
        experiment = json.load(open(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}{config.filename}"))
        experiment = experiment["name"]

        # check if the experiment already exists
        exp = Exps.query.filter_by(exp_name=experiment).first()

        if exp:
            flash("The experiment already exists. Please check the experiment name and try again.")
            shutil.rmtree(f"y_web{os.sep}experiments{os.sep}{uid}", ignore_errors=True)
            return settings()

        exp = Exps(
                exp_name=experiment,
                db_name=f"experiments{os.sep}{uid}{os.sep}{database.filename}",
                owner="",
                exp_descr="",
                status=0
                )

        db.session.add(exp)
        db.session.commit()

        exp_stats = Exp_stats(
                exp_id=exp.idexp,
                rounds=0,
                agents=0,
                posts=0,
                reactions=0,
                mentions=0
                )

        db.session.add(exp_stats)
        db.session.commit()

    except:
        flash("There was an error loading the experiment files. Please check the files and try again.")
        # remove the directory containing the files
        shutil.rmtree(f"y_web{os.sep}experiments{os.sep}{uid}", ignore_errors=True)


    return settings()

@admin.route('/admin/create_experiment', methods=['POST', 'GET'])
@login_required
def create_experiment():
    check_privileges(current_user.username)

    exp_name = request.form.get('exp_name')
    exp_descr = request.form.get('exp_descr')
    owner = request.form.get('owner')
    host = request.form.get('host')
    port = int(request.form.get('port'))

    uid = uuid.uuid4()
    pathlib.Path(f"y_web{os.sep}experiments{os.sep}{uid}").mkdir(parents=True, exist_ok=True)

    # copy the clean database to the experiments folder
    shutil.copyfile(
        "data_schema/database_clean_server.db", f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db"
    )

    config = {
        "name": exp_name,
        "host": host,
        "port": port,
        "debug": "True",
        "reset_db": "False",
        "modules": ["news", "voting", "image"],
    }

    with open(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json", "w") as f:
        json.dump(config, f)

    # add the experiment to the database

    exp = Exps(
        exp_name=exp_name,
        db_name=f"experiments{os.sep}{uid}{os.sep}database_server.db",
        owner=db.session.query(Admin_users).filter_by(id=owner).first().username,
        exp_descr=exp_descr,
        status=0
    )

    db.session.add(exp)
    db.session.commit()

    exp_stats = Exp_stats(
        exp_id=exp.idexp,
        rounds=0,
        agents=0,
        posts=0,
        reactions=0,
        mentions=0
    )

    db.session.add(exp_stats)
    db.session.commit()

    # add first round to the simulation
    round = Rounds(
        day=0,
        hour=0
    )

    db.session.add(round)
    db.session.commit()

    return settings()

@admin.route('/admin/delete_simulation/<int:exp_id>')
@login_required
def delete_simulation(exp_id):

    # get the experiment
    exp = Exps.query.filter_by(idexp=exp_id).first()
    if exp:
        # remove the experiment folder
        shutil.rmtree(
            f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}",
            ignore_errors=True)

        # delete the experiment
        db.session.delete(exp)
        db.session.commit()

        # remove the experiment folder
        shutil.rmtree(f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[0]}{os.sep}{exp.db_name.split(os.sep)[1]}", ignore_errors=True)

    return settings()