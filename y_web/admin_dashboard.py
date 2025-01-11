import random

from flask import Blueprint, render_template, redirect, url_for, request, flash, abort
from flask_login import login_user, login_required, current_user
from .models import (
    Exps,
    Admin_users,
    Exp_stats,
    User_mgmt,
    Rounds,
    Population,
    Agent,
    Agent_Population,
    Agent_Profile,
    Page,
)
from y_web.data_generation import generate_population
import json
import os
import pathlib, shutil
import uuid
from . import db, app
import re

admin = Blueprint("admin", __name__)


def check_privileges(username):
    user = Admin_users.query.filter_by(username=username).first()

    if user.role != "admin":
        return redirect(url_for("main.index"))
    return


def reload_current_user(username):
    user = db.session.query(User_mgmt).filter_by(username=username).first()
    login_user(user, remember=True, force=True)


@admin.route("/admin/dashboard")
@login_required
def dashboard():
    check_privileges(current_user.username)
    return render_template("admin/dashboard.html")


@admin.route("/admin/experiments")
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

    return render_template("admin/settings.html", experiments=experiments, users=users)


@admin.route("/admin/join_simulation")
@login_required
def join_simulation():
    # get user id for the current user logged in
    user_id = (
        db.session.query(User_mgmt).filter_by(username=current_user.username).first().id
    )
    # route the simulation home for the user
    return redirect(f"/feed/{user_id}/feed/rf/1")


@admin.route("/admin/select_experiment/<int:exp_id>")
@login_required
def change_active_experiment(exp_id):
    check_privileges(current_user.username)
    uname = current_user.username

    exp = Exps.query.filter_by(idexp=exp_id).first()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
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

    db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})
    db.session.query(Exps).filter_by(db_name=exp.db_name).update({Exps.status: 1})
    db.session.commit()

    reload_current_user(uname)

    # load all experiments
    experiments = Exps.query.limit(5).all()
    users = Admin_users.query.all()

    return render_template("admin/settings.html", experiments=experiments, users=users)


@admin.route("/admin/users")
@login_required
def user_data():
    check_privileges(current_user.username)
    return render_template("admin/users.html")


@admin.route("/admin/populations")
@login_required
def populations():
    check_privileges(current_user.username)
    return render_template("admin/populations.html")


@admin.route("/admin/agents")
@login_required
def agent_data():
    check_privileges(current_user.username)

    populations = Population.query.all()
    return render_template("admin/agents.html", populations=populations)


@admin.route("/admin/pages")
@login_required
def page_data():
    check_privileges(current_user.username)
    return render_template("admin/pages.html")


@admin.route("/admin/user_data")
@login_required
def users_data():
    query = Admin_users.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(
            db.or_(
                Admin_users.username.like(f"%{search}%"),
                Admin_users.email.like(f"%{search}%"),
            )
        )
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["username", "role", "email"]:
                name = "name"
            col = getattr(Admin_users, name)
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
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "password": user.password,
                "last_seen": user.last_seen,
                "role": user.role,
            }
            for user in res
        ],
        "total": total,
    }


@admin.route("/admin/user_data", methods=["POST"])
@login_required
def update():
    data = request.get_json()
    if "id" not in data:
        abort(400)
    user = Admin_users.query.get(data["id"])
    for field in ["username", "password", "email", "last_seen", "role"]:
        if field in data:
            setattr(user, field, data[field])
    db.session.commit()
    return "", 204


@admin.route("/admin/upload_database", methods=["POST"])
@login_required
def upload_database():
    check_privileges(current_user.username)

    database = request.files["sqlite_filename"]
    config = request.files["yserver_filename"]
    uid = uuid.uuid4()
    pathlib.Path(f"y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    database.save(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}{database.filename}")
    config.save(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}{config.filename}")

    try:
        experiment = json.load(
            open(f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}{config.filename}")
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


@admin.route("/admin/create_experiment", methods=["POST", "GET"])
@login_required
def create_experiment():
    check_privileges(current_user.username)

    exp_name = request.form.get("exp_name")
    exp_descr = request.form.get("exp_descr")
    owner = request.form.get("owner")
    host = request.form.get("host")
    port = int(request.form.get("port"))

    uid = uuid.uuid4()
    pathlib.Path(f"y_web{os.sep}experiments{os.sep}{uid}").mkdir(
        parents=True, exist_ok=True
    )

    # copy the clean database to the experiments folder
    shutil.copyfile(
        "data_schema/database_clean_server.db",
        f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}database_server.db",
    )

    config = {
        "name": exp_name,
        "host": host,
        "port": port,
        "debug": "True",
        "reset_db": "False",
        "modules": ["news", "voting", "image"],
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


@admin.route("/admin/delete_simulation/<int:exp_id>")
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

    return settings()


@admin.route("/admin/create_population_empty", methods=["POST", "GET"])
@login_required
def create_population_empty():
    check_privileges(current_user.username)

    name = request.form.get("empty_population_name")
    descr = request.form.get("empty_population_descr")

    # add the experiment to the database
    pop = Population(name=name, descr=descr)

    db.session.add(pop)
    db.session.commit()

    return populations()


@admin.route("/admin/create_population", methods=["POST"])
@login_required
def create_population():
    check_privileges(current_user.username)

    name = request.form.get("pop_name")
    descr = request.form.get("pop_descr")
    n_agents = request.form.get("n_agents")
    user_type = request.form.get("user_type")
    age_min = int(request.form.get("age_min"))
    age_max = int(request.form.get("age_max"))
    education_levels = request.form.get("education_levels")
    political_leanings = request.form.get("political_leanings")
    nationalities = request.form.get("nationalities")
    languages = request.form.get("languages")
    interests = request.form.get("interests")
    toxicity_levels = request.form.get("toxicity_levels")
    frecsys = request.form.get("frecsys_type")
    crecsys = request.form.get("recsys_type")

    population = Population(
        name=name,
        descr=descr,
        size=n_agents,
        llm=user_type,
        age_min=age_min,
        age_max=age_max,
        education=education_levels,
        leanings=political_leanings,
        nationalities=nationalities,
        languages=languages,
        interests=interests,
        toxicity=toxicity_levels,
        frecsys=frecsys,
        crecsys=crecsys,
    )

    db.session.add(population)
    db.session.commit()

    generate_population(name)

    return populations()


@admin.route("/admin/populations_data")
@login_required
def populations_data():
    query = Population.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(
            db.or_(
                Population.name.like(f"%{search}%"),
            )
        )
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["name", "descr"]:
                name = "name"
            col = getattr(Population, name)
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
        "data": [{"id": pop.id, "name": pop.name, "descr": pop.descr} for pop in res],
        "total": total,
    }


@admin.route("/admin/agents_data")
@login_required
def agents_data():
    query = Agent.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(db.or_(Agent.name.like(f"%{search}%")))
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["name", "gender", "age", "nationality"]:
                name = "name"
            col = getattr(Agent, name)
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
                "id": agent.id,
                "name": " ".join(re.findall("[A-Z][^A-Z]*", agent.name)),
                "age": agent.age,
                "gender": agent.gender,
                "nationality": agent.nationality,
            }
            for agent in res
        ],
        "total": total,
    }


@admin.route("/admin/create_agent", methods=["POST"])
@login_required
def create_agent():
    check_privileges(current_user.username)

    user_type = request.form.get("user_type")
    recsys_type = request.form.get("recsys_type")
    frecsys_type = request.form.get("frecsys_type")
    population = request.form.get("population")
    name = request.form.get("name")
    age = request.form.get("age")
    gender = request.form.get("gender")
    language = request.form.get("language")
    nationality = request.form.get("nationality")
    education_level = request.form.get("education_level")
    leaning = request.form.get("leaning")
    interests = request.form.get("interests")
    oe = request.form.get("oe")
    co = request.form.get("co")
    ex = request.form.get("ex")
    ag = request.form.get("ag")
    ne = request.form.get("ne")
    toxicity = request.form.get("toxicity")
    alt_profile = request.form.get("alt_profile")

    agent = Agent(
        name=name,
        age=age,
        ag_type=user_type,
        leaning=leaning,
        interests=interests,
        ag=ag,
        co=co,
        oe=oe,
        ne=ne,
        ex=ex,
        language=language,
        education_level=education_level,
        round_actions=random.randint(1, 3),
        toxicity=toxicity,
        nationality=nationality,
        gender=gender,
        crecsys=recsys_type,
        frecsys=frecsys_type,
    )

    db.session.add(agent)
    db.session.commit()

    if population != "none":
        ap = Agent_Population(agent_id=agent.id, population_id=population)
        db.session.add(ap)
        db.session.commit()

    if alt_profile != "":
        agent_profile = Agent_Profile(agent_id=agent.id, profile=alt_profile)
        db.session.add(agent_profile)
        db.session.commit()

    return agent_data()


@admin.route("/admin/create_page", methods=["POST"])
@login_required
def create_page():
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    page_type = request.form.get("page_type")
    feed = request.form.get("feed")
    keywords = request.form.get("keywords")
    logo = request.form.get("logo")

    page = Page(
        name=name,
        descr=descr,
        page_type=page_type,
        feed=feed,
        keywords=keywords,
        logo=logo,
    )

    db.session.add(page)
    db.session.commit()

    return page_data()


@admin.route("/admin/pages_data")
@login_required
def pages_data():
    query = Page.query

    # search filter
    search = request.args.get("search")
    if search:
        query = query.filter(
            db.or_(
                Page.name.like(f"%{search}%"),
                Page.descr.like(f"%{search}%"),
                Page.keywords.like(f"%{search}%"),
            )
        )
    total = query.count()

    # sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]
            name = s[1:]
            if name not in ["name", "descr", "keywords", "page_type"]:
                name = "name"
            col = getattr(Page, name)
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
                "id": page.id,
                "name": page.name,
                "descr": page.descr,
                "keywords": page.keywords,
                "page_type": page.page_type,
            }
            for page in res
        ],
        "total": total,
    }


@admin.route("/admin/agent_details/<int:uid>")
@login_required
def agent_details(uid):
    check_privileges(current_user.username)
    # get agent details
    agent = Agent.query.filter_by(id=uid).first()

    # get agent populations along with population names and ids
    agent_populations = (
        db.session.query(Agent_Population, Population)
        .join(Population)
        .filter(Agent_Population.agent_id == uid)
        .all()
    )

    # get agent profiles
    agent_profiles = Agent_Profile.query.filter_by(agent_id=uid).first()

    pops = [(p[1].name, p[1].id) for p in agent_populations]

    # get all populations
    populations = Population.query.all()

    return render_template("admin/agent_details.html", agent=agent, agent_populations=pops,
                           profile=agent_profiles, populations=populations)


@admin.route("/admin/add_to_population", methods=["POST"])
@login_required
def add_to_population():
    check_privileges(current_user.username)

    agent_id = request.form.get("agent_id")
    population_id = request.form.get("population_id")

    ap = Agent_Population(agent_id=agent_id, population_id=population_id)

    db.session.add(ap)
    db.session.commit()

    return agent_details(agent_id)