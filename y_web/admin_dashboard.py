import random
import os
import networkx as nx

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    abort,
    send_file,
)
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
    Population_Experiment,
    Page_Population,
    User_Experiment,
    Client,
    Client_Execution
)
from y_web.utils import (
    generate_population,
    get_feed,
    terminate_process_on_port,
    start_server,
    start_client,
    terminate_client
)
import json
import pathlib, shutil
import uuid
from . import db, app
import re
import ollama

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

    # get all experiments
    experiments = Exps.query.all()
    # get all clients for each experiment
    exps = {}
    for e in experiments:
        exps[e.idexp] = {
            "experiment": e,
            "clients": Client.query.filter_by(id_exp=e.idexp).all(),

        }

    res = {}
    # get clients with client_execution information
    for exp, data in exps.items():
        res[exp] = {"experiment": data["experiment"], "clients": []}
        for client in data["clients"]:
            cl = Client_Execution.query.filter_by(client_id=client.id).first()
            client_executions = cl if cl is not None else -1
            res[exp]["clients"].append((client, client_executions))

    return render_template("admin/dashboard.html", experiments=res)


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

    return experiment_details(exp_id)


@admin.route("/admin/users")
@login_required
def user_data():
    check_privileges(current_user.username)
    return render_template("admin/users.html")


@admin.route("/admin/populations")
@login_required
def populations():
    check_privileges(current_user.username)

    # Regular expression to match model values
    pattern = r"model='(.*?)'"
    models = []
    # Extract all model values
    for i in ollama.list():
        models = re.findall(pattern, str(i))

    models = [m for m in models if len(m) > 0]

    return render_template("admin/populations.html", models=models)


@admin.route("/admin/agents")
@login_required
def agent_data():
    check_privileges(current_user.username)

    pattern = r"model='(.*?)'"
    models = []
    # Extract all model values
    for i in ollama.list():
        models = re.findall(pattern, str(i))

    models = [m for m in models if len(m) > 0]

    populations = Population.query.all()
    return render_template("admin/agents.html", populations=populations, models=models)


@admin.route("/admin/pages")
@login_required
def page_data():
    check_privileges(current_user.username)

    # Regular expression to match model values
    pattern = r"model='(.*?)'"
    models = []
    # Extract all model values
    for i in ollama.list():
        models = re.findall(pattern, str(i))

    models = [m for m in models if len(m) > 0]

    return render_template("admin/pages.html", models=models)


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

        # remove populaiton_experiment
        db.session.query(Population_Experiment).filter_by(id_exp=exp_id).delete()
        db.session.commit()

        # delete user experiment
        db.session.query(User_Experiment).filter_by(exp_id=exp_id).delete()
        db.session.commit()

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
    pg_type = request.form.get("pg_type")

    page = Page(
        name=name,
        descr=descr,
        page_type=page_type,
        feed=feed,
        keywords=keywords,
        logo=logo,
        pg_type=pg_type,
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

    return render_template(
        "admin/agent_details.html",
        agent=agent,
        agent_populations=pops,
        profile=agent_profiles,
        populations=populations,
    )


@admin.route("/admin/add_to_population", methods=["POST"])
@login_required
def add_to_population():
    check_privileges(current_user.username)

    agent_id = request.form.get("agent_id")
    population_id = request.form.get("population_id")

    # check if the agent is already in the population
    ap = Agent_Population.query.filter_by(
        agent_id=agent_id, population_id=population_id
    ).first()
    if ap:
        return agent_details(agent_id)

    ap = Agent_Population(agent_id=agent_id, population_id=population_id)

    db.session.add(ap)
    db.session.commit()

    return agent_details(agent_id)


@admin.route("/admin/population_details/<int:uid>")
@login_required
def population_details(uid):
    check_privileges(current_user.username)
    # get population details
    population = Population.query.filter_by(id=uid).first()

    # get all experiments
    experiments = Exps.query.all()

    # get experiment populations along with experiment names and ids
    experiment_populations = (
        db.session.query(Population_Experiment, Exps)
        .join(Exps)
        .filter(Population_Experiment.id_population == uid)
        .all()
    )

    exps = [(p[1].exp_name, p[1].idexp) for p in experiment_populations]

    # get all agents in the population
    agents = (
        db.session.query(Agent, Agent_Population)
        .join(Agent_Population)
        .filter(Agent_Population.population_id == uid)
        .all()
    )

    ln = {"leanings": [], "total": []}

    for a in agents:
        if a[0].leaning in ln["leanings"]:
            ln["total"][ln["leanings"].index(a[0].leaning)] += 1
        else:
            ln["leanings"].append(a[0].leaning)
            ln["total"].append(1)

    age = {"age": [], "total": []}

    for a in agents:
        if a[0].age in age["age"]:
            age["total"][age["age"].index(a[0].age)] += 1
        else:
            age["age"].append(a[0].age)
            age["total"].append(1)

    edu = {"education": [], "total": []}

    for a in agents:
        if a[0].education_level in edu["education"]:
            edu["total"][edu["education"].index(a[0].education_level)] += 1
        else:
            edu["education"].append(a[0].education_level)
            edu["total"].append(1)

    nat = {"nationalities": [], "total": []}
    for a in agents:
        if a[0].nationality in nat["nationalities"]:
            nat["total"][nat["nationalities"].index(a[0].nationality)] += 1
        else:
            nat["nationalities"].append(a[0].nationality)
            nat["total"].append(1)

    lang = {"languages": [], "total": []}
    for a in agents:
        if a[0].language in lang["languages"]:
            lang["total"][lang["languages"].index(a[0].language)] += 1
        else:
            lang["languages"].append(a[0].language)
            lang["total"].append(1)

    tox = {"toxicity": [], "total": []}
    for a in agents:
        if a[0].toxicity in tox["toxicity"]:
            tox["total"][tox["toxicity"].index(a[0].toxicity)] += 1
        else:
            if a[0].toxicity is not None:
                tox["toxicity"].append(a[0].toxicity)
                tox["total"].append(1)

    dd = {
        "age": age,
        "leaning": ln,
        "education": edu,
        "nationalities": nat,
        "languages": lang,
        "toxicity": tox,
    }

    topics = {}
    for a in agents:
        if a[0].interests:
            ints = a[0].interests.split(",")
            for t in ints:
                if t in topics:
                    topics[t] += 1
                else:
                    topics[t] = 1

    # most frequent crecsys amon agents
    crecsys = {}
    for a in agents:
        if a[0].crecsys:
            if a[0].crecsys in crecsys:
                crecsys[a[0].crecsys] += 1
            else:
                crecsys[a[0].crecsys] = 1

    # most frequent crecsys amon agents
    frecsys = {}
    for a in agents:
        if a[0].frecsys:
            if a[0].frecsys in frecsys:
                frecsys[a[0].frecsys] += 1
            else:
                frecsys[a[0].frecsys] = 1

    # most frequent crecsys amon agents
    llm = {}
    for a in agents:
        if a[0].ag_type:
            if a[0].ag_type in llm:
                llm[a[0].ag_type] += 1
            else:
                llm[a[0].ag_type] = 1

    try:
        population_updated_details = {
            "id": population.id,
            "name": population.name,
            "descr": population.descr,
            "size": len(agents),
            "llm": max(llm, key=llm.get),
            "age_min": min(dd["age"]["age"]),
            "age_max": max(dd["age"]["age"]),
            "education": ", ".join(dd["education"]["education"]),
            "leanings": ", ".join(dd["leaning"]["leanings"]),
            "nationalities": ", ".join(dd["nationalities"]["nationalities"]),
            "languages": ", ".join(dd["languages"]["languages"]),
            "interests": ", ".join([t for t in topics]),
            "toxicity": ", ".join(dd["toxicity"]["toxicity"]),
            "frecsys": max(frecsys, key=frecsys.get),
            "crecsys": max(crecsys, key=crecsys.get),
        }
        population = population_updated_details
    except:
        pass

    return render_template(
        "admin/population_details.html",
        population=population,
        experiments=experiments,
        population_experiments=exps,
        agents=agents,
        data=dd,
    )


@admin.route("/admin/add_to_experiment", methods=["POST"])
@login_required
def add_to_experiment():
    check_privileges(current_user.username)

    population_id = request.form.get("population_id")
    experiment_id = request.form.get("experiment_id")

    # check if the population is already in the experiment
    ap = Population_Experiment.query.filter_by(
        id_population=population_id, id_exp=experiment_id
    ).first()
    if ap:
        return population_details(population_id)

    ap = Population_Experiment(id_population=population_id, id_exp=experiment_id)

    db.session.add(ap)
    db.session.commit()

    return population_details(population_id)


@admin.route("/admin/delete_population/<int:uid>")
@login_required
def delete_population(uid):
    check_privileges(current_user.username)

    population = Population.query.filter_by(id=uid).first()
    db.session.delete(population)
    db.session.commit()

    # delete agent_population entries
    agent_population = Agent_Population.query.filter_by(population_id=uid).all()
    for ap in agent_population:
        db.session.delete(ap)
        db.session.commit()

    # delete population_experiment entries
    population_experiment = Population_Experiment.query.filter_by(
        id_population=uid
    ).all()
    for pe in population_experiment:
        db.session.delete(pe)
        db.session.commit()

    return populations()


@admin.route("/admin/delete_page/<int:uid>")
@login_required
def delete_page(uid):
    check_privileges(current_user.username)

    page = Page.query.filter_by(id=uid).first()
    db.session.delete(page)
    db.session.commit()

    # delete page_population entries
    page_population = Page_Population.query.filter_by(page_id=uid).all()
    for pp in page_population:
        db.session.delete(pp)
        db.session.commit()

    return page_data()


@admin.route("/admin/delete_agent/<int:uid>")
@login_required
def delete_agent(uid):
    check_privileges(current_user.username)

    agent = Agent.query.filter_by(id=uid).first()
    db.session.delete(agent)
    db.session.commit()

    # delete agent_population entries
    agent_population = Agent_Population.query.filter_by(agent_id=uid).all()
    for ap in agent_population:
        db.session.delete(ap)
        db.session.commit()

    # delete agent_profile entries
    agent_profile = Agent_Profile.query.filter_by(agent_id=uid).all()
    for ap in agent_profile:
        db.session.delete(ap)
        db.session.commit()

    return agent_data()


@admin.route("/admin/page_details/<int:uid>")
@login_required
def page_details(uid):
    check_privileges(current_user.username)

    # get page details
    page = Page.query.filter_by(id=uid).first()

    # get agent populations along with population names and ids
    page_populations = (
        db.session.query(Page_Population, Population)
        .join(Population)
        .filter(Page_Population.page_id == uid)
        .all()
    )

    pops = [(p[1].name, p[1].id) for p in page_populations]

    # get all populations
    populations = Population.query.all()

    feed = get_feed(page.feed)

    return render_template(
        "admin/page_details.html",
        page=page,
        page_populations=pops,
        populations=populations,
        feeds=feed[:3],
    )


@admin.route("/admin/add_page_to_population", methods=["POST"])
@login_required
def add_page_to_population():
    check_privileges(current_user.username)

    page_id = request.form.get("page_id")
    population_id = request.form.get("population_id")

    # check if the page is already in the population
    ap = Page_Population.query.filter_by(
        page_id=page_id, population_id=population_id
    ).first()
    if ap:
        return page_details(page_id)

    ap = Page_Population(page_id=page_id, population_id=population_id)

    db.session.add(ap)
    db.session.commit()

    return page_details(page_id)


@admin.route("/admin/user_details/<int:uid>")
@login_required
def user_details(uid):
    check_privileges(current_user.username)

    # get user details
    user = Admin_users.query.filter_by(id=uid).first()

    # get experiments for the user
    experiments = Exps.query.filter_by(owner=user.username).all()

    # get all experiments
    all_experiments = Exps.query.all()

    # get user experiments
    joined_exp = User_Experiment.query.filter_by(user_id=uid).all()

    # get user experiments details for the ones joined
    joined_exp = [
        (j.exp_id, Exps.query.filter_by(idexp=j.exp_id).first().exp_name)
        for j in joined_exp
    ]

    return render_template(
        "admin/user_details.html",
        user=user,
        user_experiments=experiments,
        all_experiments=all_experiments,
        user_experiments_joined=joined_exp,
    )


@admin.route("/admin/add_user", methods=["POST"])
@login_required
def add_user():
    check_privileges(current_user.username)

    username = request.form.get("username")
    email = request.form.get("email")
    password = request.form.get("password")
    role = request.form.get("role")

    user = Admin_users(username=username, email=email, password=password, role=role)

    db.session.add(user)
    db.session.commit()

    return user_data()


@admin.route("/admin/delete_user/<int:uid>")
@login_required
def delete_user(uid):
    check_privileges(current_user.username)

    user = Admin_users.query.filter_by(id=uid).first()
    db.session.delete(user)
    db.session.commit()

    return user_data()


@admin.route("/admin/add_user_to_experiment", methods=["POST"])
@login_required
def add_user_to_experiment():
    check_privileges(current_user.username)

    user_id = request.form.get("user_id")
    experiment_id = request.form.get("experiment_id")

    # get username
    user = Admin_users.query.filter_by(id=user_id).first()
    # get experiment
    exp = Exps.query.filter_by(idexp=experiment_id).first()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    app.config["SQLALCHEMY_BINDS"]["db_exp"] = f"sqlite:///{BASE_DIR}/{exp.db_name}"

    # check if the user is present in the User_mgmt table
    user_exp = db.session.query(User_mgmt).filter_by(username=user.username).first()

    if user_exp is None:
        new_user = User_mgmt(
            email=user.email,
            username=user.username,
            password=user.password,
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
            .filter_by(user_id=user_id, exp_id=experiment_id)
            .first()
        )

        if user_exp is None:
            user_exp = User_Experiment(user_id=user_id, exp_id=experiment_id)
            db.session.add(user_exp)
            db.session.commit()

    db.session.query(Exps).filter_by(status=1).update({Exps.status: 0})
    db.session.query(Exps).filter_by(db_name=exp.db_name).update({Exps.status: 1})
    db.session.commit()

    return user_details(user_id)


@admin.route("/admin/experiments_data")
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


@admin.route("/admin/experiment_details/<int:uid>")
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

    return render_template(
        "admin/experiment_details.html",
        experiment=experiment,
        clients=clients,
        users=users,
        len=len,
    )


@admin.route("/admin/start_experiment/<int:uid>")
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

    return redirect(request.referrer) #experiment_details(uid)


@admin.route("/admin/stop_experiment/<int:uid>")
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


@admin.route("/admin/reset_client/<int:uid>")
@login_required
def reset_client(uid):
    check_privileges(current_user.username)

    # delete experiment json files
    client = Client.query.filter_by(id=uid).first()
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    population = Population.query.filter_by(id=client.population_id).first()
    path = f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}{population.name}.json"
    if os.path.exists(path):
        os.remove(path)

    path = f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json"
    if os.path.exists(path):
        os.remove(path)

    # copy the original prompts.json file
    BASE = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]
    shutil.copy(
        f"{BASE}data_schema{os.sep}prompts.json",
        f"y_web{os.sep}experiments{os.sep}{exp.db_name.split(os.sep)[1]}{os.sep}prompts.json",
    )

    # delete client execution
    db.session.query(Client_Execution).filter_by(client_id=uid).delete()
    db.session.commit()

    return redirect(request.referrer)


@admin.route("/admin/run_client/<int:uid>/<int:idexp>")
@login_required
def run_client(uid, idexp):
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    # get the client
    client = Client.query.filter_by(id=uid).first()

    # check if the experiment is already running
    if exp.running == 0:
        return redirect(request.referrer)

    # get population of the experiment
    population = Population.query.filter_by(id=client.population_id).first()
    start_client(exp, client, population)

    # set the population_experiment running_status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
    db.session.commit()

    return redirect(request.referrer)


@admin.route("/admin/resume_client/<int:uid>/<int:idexp>")
@login_required
def resume_client(uid, idexp):
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    # get the client
    client = Client.query.filter_by(id=uid).first()

    # check if the experiment is already running
    if exp.running == 0:
        return experiment_details(idexp)

    # get population of the experiment
    population = Population.query.filter_by(id=client.population_id).first()
    start_client(exp, client, population, resume=True)

    # set the population_experiment running_status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
    db.session.commit()

    return redirect(request.referrer)


@admin.route("/admin/pause_client/<int:uid>/<int:idexp>")
@login_required
def pause_client(uid, idexp):
    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client
    client = Client.query.filter_by(id=uid).first()
    terminate_client(client, pause=True)

    return redirect(request.referrer)


@admin.route("/admin/stop_client/<int:uid>/<int:idexp>")
@login_required
def stop_client(uid, idexp):
    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client
    client = Client.query.filter_by(id=uid).first()
    terminate_client(client, pause=False)

    return redirect(request.referrer) #experiment_details(idexp)


@admin.route("/admin/clients/<idexp>")
@login_required
def clients(idexp):
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()
    # get population assigned to the experiment
    populations = Population_Experiment.query.filter_by(id_exp=idexp).all()
    # get the populations details
    pops = [Population.query.filter_by(id=p.id_population).first() for p in populations]

    return render_template("admin/clients.html", experiment=exp, populations=pops)


@admin.route("/admin/create_client", methods=["POST"])
@login_required
def create_client():
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    exp_id = request.form.get("id_exp")
    population_id = request.form.get("population_id")
    days = request.form.get("days")
    percentage_new_agents_iteration = request.form.get(
        "percentage_new_agents_iteration"
    )
    percentage_removed_agents_iteration = request.form.get(
        "percentage_removed_agents_iteration"
    )
    max_length_thread_reading = request.form.get("max_length_thread_reading")
    reading_from_follower_ratio = request.form.get("reading_from_follower_ratio")
    probability_of_daily_follow = request.form.get("probability_of_daily_follow")
    attention_window = request.form.get("attention_window")
    visibility_rounds = request.form.get("visibility_rounds")
    post = request.form.get("post")
    share = request.form.get("share")
    image = request.form.get("image")
    comment = request.form.get("comment")
    read = request.form.get("read")
    news = request.form.get("news")
    search = request.form.get("search")
    vote = request.form.get("vote")
    llm = request.form.get("llm")
    llm_api_key = request.form.get("llm_api_key")
    llm_max_tokens = request.form.get("llm_max_tokens")
    llm_temperature = request.form.get("llm_temperature")
    llm_v_agent = request.form.get("llm_v_agent")
    llm_v = request.form.get("llm_v")
    llm_v_api_key = request.form.get("llm_v_api_key")
    llm_v_max_tokens = request.form.get("llm_v_max_tokens")
    llm_v_temperature = request.form.get("llm_v_temperature")

    # create the Client object
    client = Client(
        name=name,
        descr=descr,
        id_exp=exp_id,
        population_id=population_id,
        days=days,
        percentage_new_agents_iteration=percentage_new_agents_iteration,
        percentage_removed_agents_iteration=percentage_removed_agents_iteration,
        max_length_thread_reading=max_length_thread_reading,
        reading_from_follower_ratio=reading_from_follower_ratio,
        probability_of_daily_follow=probability_of_daily_follow,
        attention_window=attention_window,
        visibility_rounds=visibility_rounds,
        post=post,
        share=share,
        image=image,
        comment=comment,
        read=read,
        news=news,
        search=search,
        vote=vote,
        llm=llm,
        llm_api_key=llm_api_key,
        llm_max_tokens=llm_max_tokens,
        llm_temperature=llm_temperature,
        llm_v_agent=llm_v_agent,
        llm_v=llm_v,
        llm_v_api_key=llm_v_api_key,
        llm_v_max_tokens=llm_v_max_tokens,
        llm_v_temperature=llm_v_temperature,
        status=0,
    )

    db.session.add(client)
    db.session.commit()

    # create the configuration file for the client
    # get experiment
    exp = Exps.query.filter_by(idexp=exp_id).first()
    # get population
    population = Population.query.filter_by(id=population_id).first()

    config = {
        "servers": {
            "llm": llm,
            "llm_api_key": llm_api_key,
            "llm_max_tokens": int(llm_max_tokens),
            "llm_temperature": float(llm_temperature),
            "llm_v": llm_v,
            "llm_v_api_key": llm_v_api_key,
            "llm_v_max_tokens": int(llm_v_max_tokens),
            "llm_v_temperature": float(llm_v_temperature),
            "api": f"http://{exp.server}:{exp.port}/",
        },
        "simulation": {
            "name": name,
            "population": population.name,
            "client": "YClientWeb",
            "days": int(days),
            "slots": 24,
            "percentage_new_agents_iteration": float(percentage_new_agents_iteration),
            "percentage_removed_agents_iteration": float(percentage_removed_agents_iteration),
            "hourly_activity": {
                "10": 0.021,
                "16": 0.032,
                "8": 0.020,
                "12": 0.024,
                "15": 0.032,
                "17": 0.032,
                "23": 0.025,
                "6": 0.017,
                "18": 0.032,
                "11": 0.022,
                "13": 0.027,
                "14": 0.030,
                "20": 0.030,
                "21": 0.029,
                "7": 0.018,
                "22": 0.027,
                "9": 0.020,
                "3": 0.020,
                "5": 0.017,
                "4": 0.018,
                "1": 0.021,
                "2": 0.020,
                "0": 0.023,
                "19": 0.031,
            },
            "actions_likelihood": {
                "post": float(post),
                "image": float(image),
                "news": float(news),
                "comment": float(comment),
                "read": float(read),
                "share": float(share),
                "search": float(search),
                "cast": float(vote),
            },
        },
        "posts": {
            "visibility_rounds": int(visibility_rounds),
            "emotions": {
                "admiration": None,
                "amusement": None,
                "anger": None,
                "annoyance": None,
                "approval": None,
                "caring": None,
                "confusion": None,
                "curiosity": None,
                "desire": None,
                "disappointment": None,
                "disapproval": None,
                "disgust": None,
                "embarrassment": None,
                "excitement": None,
                "fear": None,
                "gratitude": None,
                "grief": None,
                "joy": None,
                "love": None,
                "nervousness": None,
                "optimism": None,
                "pride": None,
                "realization": None,
                "relief": None,
                "remorse": None,
                "sadness": None,
                "surprise": None,
                "trust": None,
            },
        },
        "agents": {
            "reading_from_follower_ratio": float(reading_from_follower_ratio),
            "max_length_thread_reading": int(max_length_thread_reading),
            "attention_window": int(attention_window),
            "probability_of_daily_follow": float(probability_of_daily_follow),
        },
    }

    uid = exp.db_name.split(os.sep)[1]

    with open(
        f"y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{name}-{population.name}.json",
        "w",
    ) as f:
        json.dump(config, f)

    return experiment_details(exp_id)


@admin.route("/admin/delete_client/<int:uid>")
@login_required
def delete_client(uid):
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    db.session.delete(client)
    db.session.commit()

    return experiment_details(client.id_exp)


@admin.route("/admin/client_details/<int:uid>")
@login_required
def client_details(uid):
    check_privileges(current_user.username)

    # get client details
    client = Client.query.filter_by(id=uid).first()
    experiment = Exps.query.filter_by(idexp=client.id_exp).first()

    # get population for the client
    population = Population.query.filter_by(id=client.population_id).first()
    # get the pages included to the population
    pages = (
        db.session.query(Page, Page_Population)
        .join(Page_Population)
        .filter(Page_Population.population_id == client.population_id)
        .all()
    )

    return render_template(
        "admin/client_details.html",
        client=client,
        experiment=experiment,
        population=population,
        pages=pages,
    )


@admin.route("/admin/download/<string:ftype>/<int:uid>")
@login_required
def download_experiment(uid, ftype):
    check_privileges(current_user.username)

    exp = Exps.query.filter_by(idexp=uid).first()

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    if ftype == "experiment_db":
        filename = f"{BASE_DIR}{os.sep}{exp.db_name}"

    if ftype == "population":
        # @todo: create the population json file
        pass

    if ftype == "client":
        # @todo: implement
        pass

    return send_file(filename, as_attachment=True)


@app.route('/admin/progress/<int:client_id>')
def get_progress(client_id):
    """Return the current progress as JSON."""
    # get client_execution
    client_execution = Client_Execution.query.filter_by(client_id=client_id).first()

    if client_execution is None:
        return json.dumps({"progress": 0})
    progress = int(100 * float(client_execution.elapsed_time)/float(client_execution.expected_duration_rounds)) if client_execution.expected_duration_rounds > 0 else 0
    return json.dumps({"progress": progress})


@admin.route("/admin/set_network/<int:uid>", methods=["POST"])
@login_required
def set_network(uid):
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get populations for client uid
    populations = Population_Experiment.query.filter_by(id_exp=uid).all()
    # get agents for the populations
    agents = Agent_Population.query.filter(Agent_Population.population_id.in_([p.id_population for p in populations])).all()
    # get agent ids for all agents in populations
    agent_ids = [a.agent_id for a in agents]

    # get data from form
    network = request.form.get("network_model")
    if network == "BA":
        m = int(request.form.get("m"))
    if network == "ER":
        p = float(request.form.get("p"))
    else:
        return redirect(request.referrer)

    g = nx.erdos_renyi_graph(len(agent_ids), p=p) if network == "ER" else nx.barabasi_albert_graph(len(agent_ids), m=m)

    # get the client experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    # get the experiment folder
    BASE = os.path.dirname(os.path.abspath(__file__))
    exp_folder = exp.db_name.split(os.sep)[1]

    with open(f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv", "w") as f:
        for n in g.edges:
            f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
        f.flush()

    client.network_type = network
    db.session.commit()

    return redirect(request.referrer)


@admin.route("/admin/upload_network/<int:uid>", methods=["POST"])
@login_required
def upload_network(uid):
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get the client experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    # get the experiment folder
    BASE = os.path.dirname(os.path.abspath(__file__))
    exp_folder = exp.db_name.split(os.sep)[1]

    network = request.files["network_filename"]

    network.save(f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network_temp.csv")

    agents = Agent_Population.query.filter(
    Agent_Population.population_id.in_([p.id_population for p in populations])).all()
    # get agent ids for all agents in populations
    agent_map = {a.name: a.agent_id for a in agents}

    try:
        with open(f"{BASE}{os.sep}experiments{os.path.sep}{exp_folder}{os.sep}{client.name}_network.csv", "r") as o:
            with open(f"{BASE}{os.sep}experiments{os.path.sep}{exp_folder}{os.sep}{client.name}_network_temp.csv", "r") as f:
                for l in f:
                    l.rstrip().split(",")
                    o.write(f"{agent_map[l[0]]},{agent_map[l[1]]}\n")
    except:
        flash("File format error: provide a csv file containing two columns with agent names. No header required.", "error")
        return redirect(request.referrer)

    # delete the temp file
    os.remove(f"{BASE}{os.sep}experiments{os.path.sep}{exp_folder}{os.sep}{client.name}_network_temp.csv")

    client.network_type = network
    db.session.commit()
    return redirect(request.referrer)


@admin.route("/admin/download_agent_list/<int:uid>")
@login_required
def download_agent_list(uid):
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get populations associated to the client
    populations = Population_Experiment.query.filter_by(id_exp=client.id_exp).all()

    # get agents in the populations
    agents = Agent_Population.query.filter(
        Agent_Population.population_id.in_([p.id_population for p in populations])).all()

    # get the experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    # get the experiment folder
    BASE = os.path.dirname(os.path.abspath(__file__))
    exp_folder = exp.db_name.split(os.sep)[1]

    with open(f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv", "w") as f:
        for a in agents:
            agent = Agent.query.filter_by(id=a.agent_id).first()
            f.write(f"{agent.name}\n")
        f.flush()

    return send_file(f"{BASE}{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv", as_attachment=True)
