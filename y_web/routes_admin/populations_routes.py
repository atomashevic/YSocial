from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
)
from flask_login import login_required, current_user

from y_web.models import (
    Exps,
    Admin_users,
    Population,
    Agent,
    Agent_Population,
    Population_Experiment,
)
from y_web.utils import (
    generate_population,
    get_ollama_models,
)

from y_web import db


population = Blueprint("population", __name__)


def check_privileges(username):
    user = Admin_users.query.filter_by(username=username).first()

    if user.role != "admin":
        return redirect(url_for("main.index"))
    return


@population.route("/admin/create_population_empty", methods=["POST", "GET"])
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


@population.route("/admin/create_population", methods=["POST"])
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


@population.route("/admin/populations_data")
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


@population.route("/admin/populations")
@login_required
def populations():
    check_privileges(current_user.username)

    # Regular expression to match model values

    models = get_ollama_models()

    return render_template("admin/populations.html", models=models)


@population.route("/admin/population_details/<int:uid>")
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


@population.route("/admin/add_to_experiment", methods=["POST"])
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


@population.route("/admin/delete_population/<int:uid>")
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

