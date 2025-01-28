import os
import networkx as nx

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    send_file,
)
from flask_login import login_required, current_user

from y_web.models import (
    Exps,
    Admin_users,
    Population,
    Agent,
    Agent_Population,
    Page,
    Population_Experiment,
    Page_Population,
    Client,
    Client_Execution
)
from y_web.utils import (
    start_client,
    terminate_client,
)
import json
import shutil
from . import db, experiment_details

clientsr = Blueprint("clientsr", __name__)


def check_privileges(username):
    user = Admin_users.query.filter_by(username=username).first()

    if user.role != "admin":
        return redirect(url_for("main.index"))
    return


@clientsr.route("/admin/reset_client/<int:uid>")
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


@clientsr.route("/admin/run_client/<int:uid>/<int:idexp>")
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


@clientsr.route("/admin/resume_client/<int:uid>/<int:idexp>")
@login_required
def resume_client(uid, idexp):
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
    start_client(exp, client, population, resume=True)

    # set the population_experiment running_status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 1})
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/pause_client/<int:uid>/<int:idexp>")
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


@clientsr.route("/admin/stop_client/<int:uid>/<int:idexp>")
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


@clientsr.route("/admin/clients/<idexp>")
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


@clientsr.route("/admin/create_client", methods=["POST"])
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

    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]

    with open(
        f"{BASE_DIR}y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{name}-{population.name}.json",
        "w",
    ) as f:
        json.dump(config, f)

    # copy prompts.json into the experiment folder
    data_base_path = f"{BASE_DIR}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"
    shutil.copyfile(f"{BASE_DIR}data_schema{os.sep}prompts.json".replace("/y_web/utils", ""),
                        f"{data_base_path}prompts.json")

    # load experiment_details page
    return experiment_details(int(exp_id))


@clientsr.route("/admin/delete_client/<int:uid>")
@login_required
def delete_client(uid):
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    db.session.delete(client)
    db.session.commit()

    # remove the db file on the client
    BASE_PATH = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]
    path = f"{BASE_PATH}external{os.sep}YClient{os.sep}experiments{client.name}.db"
    if os.path.exists(path):
        os.remove(path)

    return redirect(request.referrer)


@clientsr.route("/admin/client_details/<int:uid>")
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


@clientsr.route('/admin/progress/<int:client_id>')
def get_progress(client_id):
    """Return the current progress as JSON."""
    # get client_execution
    client_execution = Client_Execution.query.filter_by(client_id=client_id).first()

    if client_execution is None:
        return json.dumps({"progress": 0})
    progress = int(100 * float(client_execution.elapsed_time)/float(client_execution.expected_duration_rounds)) if client_execution.expected_duration_rounds > 0 else 0
    return json.dumps({"progress": progress})


@clientsr.route("/admin/set_network/<int:uid>", methods=["POST"])
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


@clientsr.route("/admin/upload_network/<int:uid>", methods=["POST"])
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

    # get populations for client uid
    populations = Population_Experiment.query.filter_by(id_exp=client.id_exp).all()

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


@clientsr.route("/admin/download_agent_list/<int:uid>")
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

