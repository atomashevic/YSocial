import os

from flask import (
    Blueprint,
    render_template,
    redirect,
    request,
    flash,
    send_file,
)
from flask_login import login_required, current_user

from y_web.models import (
    Exps,
    Admin_users,
    Exp_stats,
    User_mgmt,
    Rounds,
    Population,
    Population_Experiment,
    User_Experiment,
    Client,
    Client_Execution,
)
from y_web.utils import terminate_process_on_port, start_server
import json
import pathlib, shutil
import uuid
from y_web import db, app
from y_web.utils.miscellanea import check_privileges, reload_current_user, ollama_status

experiments = Blueprint("experiments", __name__)


@experiments.route("/admin/experiments")
@login_required
def settings():
    check_privileges(current_user.username)

    # load all experiments
    experiments = Exps.query.limit(5).all()
    users = Admin_users.query.all()

    # check if current db is the same of the active experiment
    exp = Exps.query.filter_by(status=1).first()
    if exp:
        active_db = app.config["SQLALCHEMY_BINDS"]["db_exp"]
        if not exp.exp_name in active_db:
            # change the active experiment
            db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})

    ollamas = ollama_status()

    return render_template("admin/settings.html", experiments=experiments, users=users, ollamas=ollamas)


@experiments.route("/admin/join_simulation")
@login_required
def join_simulation():
    # get user id for the current user logged in
    user_id = (
        db.session.query(User_mgmt).filter_by(username=current_user.username).first().id
    )

    # check which experiment is active
    exp = Exps.query.filter_by(status=1).first()
    if exp is None:
        flash("No active experiment. Please load an experiment.")
        return redirect(request.referrer)

    # route the simulation home for the user
    return redirect(f"/feed/{user_id}/feed/rf/1")


@experiments.route("/admin/select_experiment/<int:exp_id>")
@login_required
def change_active_experiment(exp_id):
    check_privileges(current_user.username)
    uname = current_user.username

    exp = Exps.query.filter_by(idexp=exp_id).first()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]
    app.config["SQLALCHEMY_BINDS"]["db_exp"] = f"sqlite:///{BASE_DIR}/{exp.db_name}"

    # check if the user is present in the User_mgmt table
    user = db.session.query(User_mgmt).filter_by(username=current_user.username).first()

    if user is None:
        new_user = User_mgmt(
            email=current_user.email,
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

        # ad to experiment if not present
        user_exp = (
            db.session.query(User_Experiment)
            .filter_by(user_id=current_user.id, exp_id=exp_id)
            .first()
        )
        if user_exp is None:
            user_exp = User_Experiment(user_id=current_user.id, exp_id=exp_id)
            db.session.add(user_exp)
            db.session.commit()

    db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})
    db.session.query(Exps).filter_by(db_name=exp.db_name).update({Exps.status: 1})
    db.session.commit()

    reload_current_user(uname)

    return redirect(request.referrer)


@experiments.route("/admin/upload_database", methods=["POST"])
@login_required
def upload_database():
    check_privileges(current_user.username)

    database = request.files["sqlite_filename"]
    config = request.files["yserver_filename"]
    uid = uuid.uuid4()
    pathlib.Path(f"y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    database.save(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db")
    config.save(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json")

    try:
        experiment = json.load(
            open(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json")
        )
        experiment = experiment["name"]

        # check if the experiment already exists
        exp = Exps.query.filter_by(exp_name=experiment).first()

        if exp:
            flash(
                "The experiment already exists. Please check the experiment name and try again."
            )
            shutil.rmtree(f"y_web{os.sep}experiments{os.sep}{uid}", ignore_errors=True)
            return settings()

        exp = Exps(
            exp_name=experiment,
            db_name=f"experiments{os.sep}{uid}{os.sep}{database.filename}",
            owner="",
            exp_descr="",
            status=0,
        )

        db.session.add(exp)
        db.session.commit()

        exp_stats = Exp_stats(
            exp_id=exp.idexp, rounds=0, agents=0, posts=0, reactions=0, mentions=0
        )

        db.session.add(exp_stats)
        db.session.commit()

    except:
        flash(
            "There was an error loading the experiment files. Please check the files and try again."
        )
        # remove the directory containing the files
        shutil.rmtree(f"y_web{os.sep}experiments{os.sep}{uid}", ignore_errors=True)

    return settings()


@experiments.route("/admin/create_experiment", methods=["POST", "GET"])
@login_required
def create_experiment():
    check_privileges(current_user.username)

    exp_name = request.form.get("exp_name")
    exp_descr = request.form.get("exp_descr")
    owner = request.form.get("owner")
    host = request.form.get("host")
    port = int(request.form.get("port"))
    perspective_api = request.form.get("perspective_api")

    uid = uuid.uuid4()
    pathlib.Path(f"y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    # copy the clean database to the experiments folder
    shutil.copyfile(
        f"data_schema{os.sep}database_clean_server.db",
        f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db",
    )

    config = {
        "name": exp_name,
        "host": host,
        "port": port,
        "debug": "False",
        "reset_db": "False",
        "modules": ["news", "voting", "image"],
        "perspective_api": perspective_api if len(perspective_api) > 0 else None,
    }

    with open(
        f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json", "w"
    ) as f:
        json.dump(config, f)

    # add the experiment to the database

    exp = Exps(
        exp_name=exp_name,
        db_name=f"experiments{os.sep}{uid}{os.sep}database_server.db",
        owner=db.session.query(Admin_users).filter_by(id=owner).first().username,
        exp_descr=exp_descr,
        status=0,
        port=int(port),
        server=host,
    )

    db.session.add(exp)
    db.session.commit()

    exp_stats = Exp_stats(
        exp_id=exp.idexp, rounds=0, agents=0, posts=0, reactions=0, mentions=0
    )

    db.session.add(exp_stats)
    db.session.commit()

    # add first round to the simulation
    round = Rounds(day=0, hour=0)

    db.session.add(round)
    db.session.commit()

    return settings()


@experiments.route("/admin/delete_simulation/<int:exp_id>")
@login_required
def delete_simulation(exp_id):
    # get the experiment
    exp = Exps.query.filter_by(idexp=exp_id).first()
    if exp:
        # remove the experiment folder
        shutil.rmtree(
            f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}",
            ignore_errors=True,
        )

        # delete the experiment
        db.session.delete(exp)
        db.session.commit()

        # remove the experiment folder
        shutil.rmtree(
            f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[0]}{os.sep}{exp.db_name.split(os.sep)[1]}",
            ignore_errors=True,
        )

        # remove populaiton_experiment
        db.session.query(Population_Experiment).filter_by(id_exp=exp_id).delete()
        db.session.commit()

        # delete user experiment
        db.session.query(User_Experiment).filter_by(exp_id=exp_id).delete()
        db.session.commit()

        # get clients ids for the experiment
        clients = db.session.query(Client).filter_by(id_exp=exp_id).all()
        cids = [c.id for c in clients]

        # delete the clients
        db.session.query(Client).filter_by(id_exp=exp_id).delete()
        db.session.commit()

        for cid in cids:
            # delete the client executions
            db.session.query(Client_Execution).filter_by(client_id=cid).delete()
            db.session.commit()

    return redirect(request.referrer)


@experiments.route("/admin/experiments_data")
@login_required
def experiments_data():
    query = Exps.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Exps.exp_name.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["exp_name", "exp_descr", "owner"]:
                name = "name"
            col = getattr(Exps, name)
            if direction == "-":
                col = col.desc()
            order.append(col)
        if order:
            query = query.order_by(*order)

    # pagination
    start = request.args.get("start", type=int, default=-1)
    length = request.args.get("length", type=int, default=-1)
    if start != -1 and length != -1:
        query = query.offset(start).limit(length)

    # response
    res = query.all()

    return {
        "data": [
            {
                "idexp": exp.idexp,
                "exp_name": exp.exp_name,
                "exp_descr": exp.exp_descr,
                "owner": exp.owner,
                "web": "Loaded" if exp.status == 1 else "Not loaded",
                "running": "Running" if exp.running == 1 else "Stopped",
            }
            for exp in res
        ],
        "total": total,
    }


@experiments.route("/admin/experiment_details/<int:uid>")
@login_required
def experiment_details(uid):
    check_privileges(current_user.username)

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()

    # get experiment populations along with population names and ids
    experiment_populations = (
        db.session.query(Population_Experiment, Population)
        .join(Population)
        .filter(Population_Experiment.id_exp == uid)
        .all()
    )

    users = (
        db.session.query(Admin_users, User_Experiment)
        .join(User_Experiment)
        .filter(User_Experiment.exp_id == uid)
        .all()
    )

    # get experiment clients
    clients = Client.query.filter_by(id_exp=uid).all()

    ollamas = ollama_status()

    return render_template(
        "admin/experiment_details.html",
        experiment=experiment,
        clients=clients,
        users=users,
        len=len,
        ollamas=ollamas,
    )


@experiments.route("/admin/start_experiment/<int:uid>")
@login_required
def start_experiment(uid):
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=uid).first()

    # check if the experiment is already running
    if exp.running == 1:
        return experiment_details(uid)

    # update the experiment status
    db.session.query(Exps).filter_by(idexp=uid).update({Exps.running: 1})
    db.session.commit()

    # start the yserver
    start_server(exp)

    return redirect(request.referrer)  # experiment_details(uid)


@experiments.route("/admin/stop_experiment/<int:uid>")
@login_required
def stop_experiment(uid):
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=uid).first()

    # check if the experiment is already running
    if exp.running == 0:
        return experiment_details(uid)

    # stop the yserver
    terminate_process_on_port(exp.port)

    # the clients are killed as soon as the server stops
    # update client statuses
    # get all populations for the experiment and update the client_running status
    populations = Client.query.filter_by(id_exp=uid).all()
    for pop in populations:
        db.session.query(Client).filter_by(id=pop.population_id).update(
            {Client.status: 0}
        )
        db.session.commit()

    # update the experiment status
    db.session.query(Exps).filter_by(idexp=uid).update({Exps.running: 0})
    db.session.commit()

    return redirect(request.referrer)  # experiment_details(uid)


@experiments.route("/admin/download/<string:ftype>/<int:uid>")
@login_required
def download_experiment(uid, ftype):
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=uid).first()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("routes_admin")[0]

    if ftype == "experiment_db":
        filename = f"{BASE_DIR}{os.sep}{exp.db_name}"

    if ftype == "population":
        # @todo: create the population json file
        pass

    if ftype == "client":
        # @todo: implement
        pass

    return send_file(filename, as_attachment=True)


@experiments.route("/admin/prompts/<int:uid>")
@login_required
def prompts(uid):
    check_privileges(current_user.username)

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()
    # get the prompts file for the experiment
    prompts = f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json"

    # read the prompts file
    prompts = json.load(open(prompts))

    return render_template("admin/prompts.html", experiment=experiment, prompts=prompts)


@experiments.route("/admin/update_prompts/<int:uid>", methods=["POST"])
@login_required
def update_prompts(uid):
    check_privileges(current_user.username)

    # get experiment details
    experiment = Exps.query.filter_by(idexp=uid).first()
    # get the prompts file for the experiment
    prompts_filename = f"y_web{os.sep}experiments{os.sep}{experiment.db_name.split(os.sep)[1]}{os.sep}prompts.json"

    # read the prompts file
    prompts = json.load(open(prompts_filename))

    # update the prompts
    for key in request.form.keys():
        prompts[key] = request.form[key]

    # write the updated prompts
    json.dump(prompts, open(prompts_filename, "w"), indent=4)

    return redirect(request.referrer)
