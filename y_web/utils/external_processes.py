import subprocess
import os
import re
import sys
from requests import post
import json
import time
import random
from multiprocessing import Process
from y_web.models import Client_Execution, Agent_Population, Agent, Page, Page_Population, Ollama_Pull
from y_web import db, client_processes
import shutil
import requests
from ollama import Client as oclient


def terminate_process_on_port(port):
    """
    Terminate the process using the specified port

    :param port: the port number
    """
    try:
        result = subprocess.run(
            ["lsof", "-t", "-i", f":{port}"], capture_output=True, text=True, check=True
        )
        pid = result.stdout.strip()

        if pid:
            print(f"Found process {pid} using port {port}. Killing process...")
            os.kill(int(pid), 9)  # Send SIGKILL to the process
            print(f"Process {pid} terminated.")
        else:
            print(f"No process found using port {port}.")
    except Exception as e:
        print(f"Error: {e}")
        pass


def start_server(exp):
    """
    Start the y_server in a detached screen

    :param exp: the experiment object
    """
    yserver_path = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]
    sys.path.append(f"{yserver_path}{os.sep}external{os.sep}YServer{os.sep}")
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("utils")[0]
    config = (
        f"{yserver_path}y_web{os.sep}{exp.db_name.split('database_server.db')[0]}config_server.json"
    )
    exp_uid = exp.db_name.split(os.sep)[1]
    flask_command = f"python {yserver_path}external{os.sep}YServer{os.sep}y_server_run.py -c {config}"

    # Command to run in the detached screen
    screen_command = f"screen -dmS {exp_uid} {flask_command}"
    print(f"Starting server for experiment {exp_uid}...")
    subprocess.run(screen_command, shell=True, check=True)

    # Wait for the server to start
    time.sleep(10)
    data = {"path": f"{BASE_DIR[1:]}{exp.db_name}"}
    headers = {"Content-Type": "application/json"}
    ns = f"http://{exp.server}:{exp.port}/change_db"
    post(f"{ns}", headers=headers, data=json.dumps(data))


def is_ollama_installed():
    # Step 1: Check if Ollama is installed
    try:
        subprocess.run(["ollama", "--version"], capture_output=True, text=True, check=True)
        print("Ollama is installed.")
        return True
    except FileNotFoundError:
        print("Ollama is not installed.")
        return False
    except subprocess.CalledProcessError as e:
        print(f"Error checking Ollama installation: {e}")
        return False


def is_ollama_running():
    # Step 2: Check if Ollama is running
    try:
        response = requests.get("http://127.0.0.1:11434/api/version")
        if response.status_code == 200:
            print("Ollama is running.")
            return True
        else:
            print(f"Ollama responded but not running correctly. Status: {response.status_code}")
            return False
    except requests.ConnectionError:
        print("Ollama is not running or cannot be reached.")
        return False


def start_ollama_server():

    if is_ollama_installed() :
        if not is_ollama_running():
            screen_command = f"screen -dmS ollama ollama serve"

            print(f"Starting ollama server...")
            subprocess.run(screen_command, shell=True, check=True)

            # Wait for the server to start
            time.sleep(5)
        else:
            print("Ollama is already running.")
    else:
        print("Ollama is not installed.")


def pull_ollama_model(model_name):
    if is_ollama_running():
        process = Process(target=start_ollama_pull, args=(model_name,))
        process.start()
        client_processes[model_name] = process


def start_ollama_pull(model_name):
    ol_client = oclient(
        host='http://127.0.0.1:11434',
        headers={'x-some-header': 'some-value'}
    )

    for progress in ol_client.pull(model_name, stream=True):

        model = Ollama_Pull.query.filter_by(model_name=model_name).first()
        if not model:
            model = Ollama_Pull(model_name=model_name, status=0)
            db.session.add(model)
            db.session.commit()

        total = progress.get('total')
        completed = progress.get('completed')
        if completed is not None:
            current = float(completed) / float(total)
            # update the model status
            model = Ollama_Pull.query.filter_by(model_name=model_name).first()
            model.status = current
            db.session.commit()


def get_ollama_models():
    pattern = r"model='(.*?)'"
    models = []

    ol_client = oclient(
        host='http://0.0.0.0:11434',
        headers={'x-some-header': 'some-value'}
    )

    # Extract all model values
    for i in ol_client.list():
        models = re.findall(pattern, str(i))

    models = [m for m in models if len(m) > 0]
    return models


def delete_ollama_model(model_name):
    ol_client = oclient(
        host='http://0.0.0.0:11434',
        headers={'x-some-header': 'some-value'}
    )

    ol_client.delete(model_name)


def delete_model_pull(model_name):
    if model_name in client_processes:
        process = client_processes[model_name]
        process.terminate()
        process.join()

    model = Ollama_Pull.query.filter_by(model_name=model_name).first()
    db.session.delete(model)
    db.session.commit()

def terminate_client(cli, pause=False):
    """
    Stop the y_client

    :param cli: the client object
    """
    process = client_processes[cli.name]
    process.terminate()
    process.join()

    # update client execution object
    if not pause:
        ce = Client_Execution.query.filter_by(client_id=cli.id).first()
        ce.expected_duration_rounds = 0
        ce.elapsed_time = 0
        db.session.commit()


def start_client(exp, cli, population, resume=False):
    process = Process(target=start_client_process, args=(exp, cli, population, resume, ))
    process.start()
    client_processes[cli.name] = process


def start_client_process(exp, cli, population, resume=False):
    """
    Start the y_client

    :param exp:
    :param cli:
    :param population:
    :return:
    """

    yclient_path = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]
    sys.path.append(f"{yclient_path}{os.sep}external{os.sep}YClient/")
    from y_client.clients import YClientWeb

    # get experiment base path
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("utils")[0]
    # get the experiment configuration
    uid = exp.db_name.split(os.sep)[1]
    data_base_path = f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}"
    config_file = json.load(
        open(f"{data_base_path}client_{cli.name}-{population.name}.json")
    )

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    filename = f"{BASE_DIR}{os.sep}{exp.db_name.split('database_server.db')[0]}{population.name.replace(' ', '')}.json".replace(
        "utils/", "")

    # check if a Client_Execution object exists for client_id
    ce = Client_Execution.query.filter_by(client_id=cli.id).first()
    if ce:
        if not resume:
            ce.elapsed_time = 0
            ce.expected_duration_rounds = cli.days * 24
        first_run = False

    else:
        first_run = True
        # writing the agent file
        agents = Agent_Population.query.filter_by(population_id=population.id).all()
        # get the agent details
        agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

        res = {"agents": []}
        for a in agents:
            res["agents"].append(
                {
                    "name": a.name,
                    "email": f"{a.name}@ysocial.it",
                    "password": f"{a.name}",
                    "age": a.age,
                    "type": a.ag_type,
                    "leaning": a.leaning,
                    "interests": [
                        [x.strip() for x in a.interests.split(",")],
                        [len([x for x in a.interests.split(",")])],
                    ] if a.interests else [[], 0],
                    "oe": a.oe,
                    "co": a.co,
                    "ex": a.ex,
                    "ag": a.ag,
                    "ne": a.ne,
                    "rec_sys": a.crecsys,
                    "frec_sys": a.frecsys,
                    "language": a.language,
                    "owner": exp.owner,
                    "education_level": a.education_level,
                    "round_actions": int(a.round_actions),
                    "gender": a.gender,
                    "nationality": a.nationality,
                    "toxicity": a.toxicity,
                    "is_page": 0,
                }
            )

        # get the pages associated with the population
        pages = Page_Population.query.filter_by(population_id=population.id).all()
        pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]

        for p in pages:
            res["agents"].append(
                {
                    "name": p.name,
                    "email": f"{p.name}@ysocial.it",
                    "password": f"{p.name}",
                    "age": 0,
                    "type": p.pg_type,
                    "leaning": "",
                    "interests": [[], 0],
                    "oe": "",
                    "co": "",
                    "ex": "",
                    "ag": "",
                    "ne": "",
                    "rec_sys": "",
                    "frec_sys": "",
                    "language": "english",
                    "owner": exp.owner,
                    "education_level": "",
                    "round_actions": 3,
                    "gender": "",
                    "nationality": "",
                    "toxicity": "none",
                    "is_page": 1,
                    "feed_url": p.feed,
                }
            )

        json.dump(res, open(filename, "w"), indent=4)

        # copy prompts.json into the experiment folder
        shutil.copyfile(f"{BASE_DIR}{os.sep}data_schema{os.sep}prompts.json".replace("/y_web/utils", ""), f"{data_base_path}prompts.json")

        # create a client execution object
        ce = Client_Execution(
            client_id=cli.id,
            elapsed_time=0,
            expected_duration_rounds=cli.days*24,
            last_active_hour=-1,
            last_active_day=-1
        )
        db.session.add(ce)
        db.session.commit()

    # add the network file if it is the first run (and the network is specified for the client)
    if first_run and cli.network_type is not None and cli.network_type != "":
        path = f"{cli.name}_network.csv"
        cl = YClientWeb(config_file, data_base_path, first_run=first_run, network=path)
    else:
        cl = YClientWeb(config_file, data_base_path, first_run=first_run)

    if resume:
        cl.days = ce.expected_duration_rounds - ce.elapsed_time
    cl.read_agents()
    run_simulation(cl, cli.id, filename)


def run_simulation(cl, cli_id, agent_file):
    """
    Run the simulation
    """

    for _ in range(int(cl.days)):
        daily_active = {}
        tid, _, _ = cl.sim_clock.get_current_slot()

        for _ in range(int(cl.slots)):
            tid, d, h = cl.sim_clock.get_current_slot()

            # get expected active users for this time slot (at least 1)
            expected_active_users = max(
                int(len(cl.agents.agents) * cl.hourly_activity[str(h)]), 1
            )
            sagents = random.sample(cl.agents.agents, expected_active_users)

            # available actions
            acts = [a for a, v in cl.actions_likelihood.items() if v > 0]

            # shuffle agents
            random.shuffle(sagents)
            for g in sagents:
                daily_active[g.name] = None

                for _ in range(int(g.round_actions)):
                    # sample two elements from a list with replacement
                    candidates = random.choices(
                        acts,
                        k=2,
                        weights=[cl.actions_likelihood[a] for a in acts],
                    )
                    candidates.append("NONE")

                    # reply to received mentions
                    if g not in cl.pages:
                        g.reply(tid=tid)

                    # select action to be performed
                    g.select_action(
                        tid=tid,
                        actions=candidates,
                        max_length_thread_reading=cl.max_length_thread_reading,
                    )
            # increment slot
            cl.sim_clock.increment_slot()

            # update client execution object
            ce = Client_Execution.query.filter_by(client_id=cli_id).first()
            ce.elapsed_time += 1
            ce.last_active_hour = h
            ce.last_active_day = d
            db.session.commit()

            # evaluate following (once per day, only for a random sample of daily active agents)
        da = [
            agent
            for agent in cl.agents.agents
            if agent.name in daily_active
            and agent not in cl.pages
            and random.random()
            < float(cl.config["agents"]["probability_of_daily_follow"])
        ]

        # Evaluating new friendship ties
        for agent in da:
            if agent not in cl.pages:
                agent.select_action(tid=tid, actions=["FOLLOW", "NONE"])

        # daily churn
        cl.churn(tid)

        # daily new agents
        if cl.percentage_new_agents_iteration > 0:
            for _ in range(
                max(
                    1,
                    int(len(daily_active) * cl.percentage_new_agents_iteration),
                )
            ):
                cl.add_agent()

        # saving "living" agents at the end of the day
        if (
            cl.percentage_removed_agents_iteration != 0
            or cl.percentage_removed_agents_iteration != 0
        ):
            cl.save_agents(agent_file)
