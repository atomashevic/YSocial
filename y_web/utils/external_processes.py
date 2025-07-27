import subprocess
import os
import re
import sys
from requests import post
import json
import time
import random
from multiprocessing import Process
import traceback
from y_web.models import (
    Client_Execution,
    Ollama_Pull
)

from flask import current_app
from y_web import db, client_processes
import requests
from ollama import Client as oclient
import concurrent
import numpy as np

import os
import sys
import subprocess
from pathlib import Path
import shutil


import os
import sys
import shutil
import subprocess
from pathlib import Path


def detect_env_handler():
    python_exe = sys.executable
    env_type = None
    env_name = None
    env_bin = None
    conda_sh = None

    # Check for conda
    conda_prefix = os.environ.get("CONDA_PREFIX")
    if conda_prefix:
        env_type = "conda"

        env_name = os.environ.get("CONDA_DEFAULT_ENV") or Path(conda_prefix).name
        env_bin = Path(conda_prefix) / "bin"

        # Use CONDA_PREFIX to locate the conda base
        conda_base = Path(conda_prefix).resolve().parent  # this goes one up to base

        # Handle cases like /Users/foo/miniforge3/envs/Y2
        if (conda_base / "etc" / "profile.d" / "conda.sh").exists():
            conda_sh = conda_base / "etc" / "profile.d" / "conda.sh"
        else:
            # fallback: check via `which conda`
            conda_exe = shutil.which("conda")
            if conda_exe:
                conda_base = Path(conda_exe).resolve().parent.parent
                maybe_sh = conda_base / "etc" / "profile.d" / "conda.sh"
                if maybe_sh.exists():
                    conda_sh = maybe_sh

        print(f"Detected conda environment: {env_name} at {env_bin}")

        return env_type, env_name, str(env_bin), str(conda_sh) if conda_sh else None
    # Check for pyenv
    pyenv_version = os.environ.get("PYENV_VERSION")
    pyenv_root_env = os.environ.get("PYENV_ROOT")
    if pyenv_version or pyenv_root_env or ".pyenv" in python_exe:
        env_type = "pyenv"
        # Determine pyenv root directory
        if pyenv_root_env:
            pyenv_root = Path(pyenv_root_env)
        else:
            parts = Path(python_exe).parts
            try:
                idx = parts.index(".pyenv")
                pyenv_root = Path(*parts[: idx + 1])
            except ValueError:
                pyenv_root = Path.home() / ".pyenv"
        # Determine environment/version name
        if pyenv_version:
            env_name = pyenv_version
        else:
            try:
                idx_vers = parts.index("versions")
                env_name = parts[idx_vers + 1] if len(parts) > idx_vers + 1 else None
            except (ValueError, NameError):
                env_name = None
        env_bin = pyenv_root
        print(f"Detected pyenv environment: {env_name} at {env_bin}")
        return env_type, env_name, str(env_bin), str(pyenv_root)

    # Check for pipenv
    if os.environ.get("PIPENV_ACTIVE"):
        env_type = "pipenv"
        env_name = os.path.basename(os.path.dirname(python_exe))
        env_bin = Path(python_exe).parent
        return env_type, env_name, str(env_bin), None

    # Check for venv
    venv_path = os.environ.get("VIRTUAL_ENV")
    if venv_path:
        env_type = "venv"
        env_name = os.path.basename(venv_path)
        env_bin = Path(venv_path) / "bin"
        return env_type, env_name, str(env_bin), None

    # System Python
    return "system", None, str(Path(python_exe).parent), None


def build_screen_command(script_path, config_path, screen_name=None):
    env_type, env_name, env_bin, conda_sh_or_pyenv_root = detect_env_handler()
    screen_name = screen_name or env_name or "experiment"

    if env_type == "conda" and conda_sh_or_pyenv_root:
        command = (
            f"screen -dmS {screen_name} bash -c "
            f"'source {conda_sh_or_pyenv_root} && conda activate {env_name} && "
            f"python {script_path} -c {config_path}'"
        )
    elif env_type in ("venv", "pipenv"):
        command = (
            f"screen -dmS {screen_name} bash -c "
            f"'source {env_bin}/activate && python {script_path} -c {config_path}'"
        )
    elif env_type == "pyenv":
        # env_bin is the pyenv root directory, conda_sh_or_pyenv_root is also pyenv_root
        pyenv_root = conda_sh_or_pyenv_root
        version_python = f"{pyenv_root}/versions/{env_name}/bin/python"
        command = (
            f"screen -dmS {screen_name} bash -lc "
            f"\"export PYENV_ROOT={pyenv_root} && "
            f"export PATH='{pyenv_root}/shims:$PATH' && "
            f"eval \\\"\\$(pyenv init -)\\\" && "
            f"pyenv shell {env_name} && "
            f"{version_python} {script_path} -c {config_path}\""
        )
    else:  # system
        command = f"screen -dmS {screen_name} python {script_path} -c {config_path}"

    return command


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

    if "database_server.db" in exp.db_name:
        config = f"{yserver_path}y_web{os.sep}{exp.db_name.split('database_server.db')[0]}config_server.json"
        exp_uid = exp.db_name.split(os.sep)[1]
    else:
        uid = exp.db_name.removeprefix('experiments_')
        exp_uid = f"{uid}{os.sep}"
        config = f"{yserver_path}y_web{os.sep}experiments{os.sep}{exp_uid}config_server.json"

    if exp.platform_type == "microblogging":
        screen_command = build_screen_command(
            script_path=f"{yserver_path}external{os.sep}YServer{os.sep}y_server_run.py",
            config_path=f"{config}",
            screen_name=f"{exp_uid.replace(f'{os.sep}', '')}"
        )

    elif exp.platform_type == "forum":
        screen_command = build_screen_command(
            script_path=f"{yserver_path}external{os.sep}YServerReddit{os.sep}y_server_run.py",
            config_path=f"{config}",
            screen_name=f"{exp_uid.replace(f'{os.sep}', '')}"
        )
        #subprocess.run(cmd, shell=True, check=True)
    else:
        raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

    # Command to run in the detached screen
    #screen_command = f"screen -dmS {exp_uid.replace(f'{os.sep}', '')} {flask_command}"
    print(screen_command)

    print(f"Starting server for experiment {exp_uid} ...")
    subprocess.run(screen_command, shell=True, check=True)

    # identify the db to be set
    db_uri_main = current_app.config["SQLALCHEMY_DATABASE_URI"]

    db_type = "sqlite"
    if db_uri_main.startswith("postgresql"):
        db_type = "postgresql"

    if db_type == "sqlite":
        db_uri = f"{BASE_DIR[1:]}{exp.db_name}"  # change this to the postgres URI
    elif db_type == "postgresql":
        old_db_name = db_uri_main.split("/")[-1]
        db_uri = db_uri_main.replace(old_db_name, exp.db_name)

    print(f"Database URI: {db_uri}")

    # Wait for the server to start
    time.sleep(20)
    data = {"path": f"{db_uri}"}
    headers = {"Content-Type": "application/json"}
    ns = f"http://{exp.server}:{exp.port}/change_db"
    post(f"{ns}", headers=headers, data=json.dumps(data))


def is_ollama_installed():
    # Step 1: Check if Ollama is installed
    try:
        subprocess.run(
            ["ollama", "--version"], capture_output=True, text=True, check=True
        )
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
            print(
                f"Ollama responded but not running correctly. Status: {response.status_code}"
            )
            return False
    except requests.ConnectionError:
        print("Ollama is not running or cannot be reached.")
        return False


def start_ollama_server():
    if is_ollama_installed():
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
        host="http://127.0.0.1:11434", headers={"x-some-header": "some-value"}
    )

    for progress in ol_client.pull(model_name, stream=True):
        model = Ollama_Pull.query.filter_by(model_name=model_name).first()
        if not model:
            model = Ollama_Pull(model_name=model_name, status=0)
            db.session.add(model)
            db.session.commit()

        total = progress.get("total")
        completed = progress.get("completed")
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
        host="http://0.0.0.0:11434", headers={"x-some-header": "some-value"}
    )

    # Extract all model values
    for i in ol_client.list():
        models = re.findall(pattern, str(i))

    models = [m for m in models if len(m) > 0]
    return models


def delete_ollama_model(model_name):
    ol_client = oclient(
        host="http://0.0.0.0:11434", headers={"x-some-header": "some-value"}
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
    #if not pause:
    #    ce = Client_Execution.query.filter_by(client_id=cli.id).first()
    #    ce.expected_duration_rounds = 0
    #    ce.elapsed_time = 0
    #    db.session.commit()


def start_client(exp, cli, population, resume=False):
    process = Process(
        target=start_client_process,
        args=(
            exp,
            cli,
            population,
            resume,
        ),
    )
    process.start()
    client_processes[cli.name] = process


def start_client_process(exp, cli, population, resume=False):
    from y_web import create_app, db
    from y_web.models import Client_Execution
    import os, sys, json

    app = create_app()  # create app instance for this subprocess

    with app.app_context():
        yclient_path = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]

        if exp.platform_type == "microblogging":
            sys.path.append(f"{yclient_path}{os.sep}external{os.sep}YClient/")
            from y_client.clients import YClientWeb
        elif exp.platform_type == "forum":
            sys.path.append(f"{yclient_path}{os.sep}external{os.sep}YClientReddit/")
            from y_client.clients import YClientWeb
        else:
            raise NotImplementedError(f"Unsupported platform {exp.platform_type}")

        # get experiment base path
        BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("utils")[0]

        # postgres
        if "experiments_" in exp.db_name:
            uid = exp.db_name.removeprefix('experiments_')
            filename = f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}{population.name.replace(' ', '')}.json".replace(
                "utils/", ""
            )
        else:
            uid = exp.db_name.split(os.sep)[1]
            filename = f"{BASE_DIR}{os.sep}{exp.db_name.split('database_server.db')[0]}{population.name.replace(' ', '')}.json".replace(
                "utils/", ""
            )

        data_base_path = f"{BASE_DIR}experiments{os.sep}{uid}{os.sep}"
        config_file = json.load(
            open(f"{data_base_path}client_{cli.name}-{population.name}.json")
        )

        # DB query requires app context
        ce = Client_Execution.query.filter_by(client_id=cli.id).first()
        if ce:
            if not resume:
                ce.elapsed_time = 0
                ce.expected_duration_rounds = cli.days * 24
            first_run = False
        else:
            first_run = True
            ce = Client_Execution(
                client_id=cli.id,
                elapsed_time=0,
                expected_duration_rounds=cli.days * 24,
                last_active_hour=-1,
                last_active_day=-1,
            )
            db.session.add(ce)
            db.session.commit()

        if first_run and cli.network_type:
            path = f"{cli.name}_network.csv"
            cl = YClientWeb(config_file, data_base_path, first_run=first_run, network=path)
        else:
            cl = YClientWeb(config_file, data_base_path, first_run=first_run)

        if resume:
            cl.days = int((ce.expected_duration_rounds - ce.elapsed_time) / 24)

        cl.read_agents()
        cl.add_feeds()

        if first_run and cli.network_type:
            cl.add_network()

        if not os.path.exists(filename):
            cl.save_agents(filename)

        run_simulation(cl, cli.id, filename, exp)


def run_simulation(cl, cli_id, agent_file, exp):
    """
    Run the simulation
    """
    platform_type = exp.platform_type

    total_days = int(cl.days)
    daily_slots = int(cl.slots)

    for d1 in range(total_days):
        daily_active = {}
        tid, _, _ = cl.sim_clock.get_current_slot()

        for _ in range(daily_slots):
            tid, d, h = cl.sim_clock.get_current_slot()

            # get expected active users for this time slot (at least 1)
            expected_active_users = max(
                int(len(cl.agents.agents) * cl.hourly_activity[str(h)]), 1
            )

            page_agents = [p for p in cl.agents.agents if p.is_page]

            if platform_type == "microblogging":
                # pages post at least a news each slot of the day (7-22), more if they were selected randomly
                for page in page_agents:
                    if h < 7 or h > 22:
                        continue
                    page.select_action(
                        tid=tid,
                        actions=[],
                        max_length_thread_reading=cl.max_length_thread_reading,
                    )

                # check whether there are agents left
            if len(cl.agents.agents) == 0:
                break

            # get the daily activities of each agent
            # @todo: simplifiy once the daily_activity_level is always set on YReddit
            try:
                weights = [a.daily_activity_level for a in cl.agents.agents]
                # normalize weights to sum to 1
                weights = [w / sum(weights) for w in weights]
                # sample agents
                sagents = np.random.choice(
                    cl.agents.agents, size=expected_active_users, p=weights, replace=False
                )
            except Exception as e:
                sagents = np.random.choice(
                    cl.agents.agents, size=expected_active_users, replace=False
                )

            # available actions
            # shuffle agents
            random.shuffle(sagents)

            ################# PARALLELIZED SECTION #################
            # def agent_task(g, tid):
            for g in sagents:
                acts = [a for a, v in cl.actions_likelihood.items() if v > 0]

                daily_active[g.name] = None

                # Get a random integer within g.round_actions.
                # If g.is_page == 1, then rounds = 0 (the page does not perform actions)
                if g.is_page == 1:
                    rounds = 0
                else:
                    rounds = random.randint(1, int(g.round_actions))

                for _ in range(rounds):
                    # sample two elements from a list with replacement

                    candidates = random.choices(
                        acts,
                        k=2,
                        weights=[cl.actions_likelihood[a] for a in acts],
                    )
                    candidates.append("NONE")

                    try:
                        # reply to received mentions
                        if g not in cl.pages:
                            g.reply(tid=tid)

                        # select action to be performed
                        g.select_action(
                            tid=tid,
                            actions=candidates,
                            max_length_thread_reading=cl.max_length_thread_reading,
                        )
                    except Exception as e:
                        print(f"Error ({g.name}): {e}")
                        print(traceback.format_exc())
                        pass

            # Run agent tasks in parallel
            # with concurrent.futures.ThreadPoolExecutor() as executor:
            #    executor.map(agent_task, sagents)
            ################# END OF PARALLELIZATION #################

            # increment slot
            cl.sim_clock.increment_slot()

            # update client execution object
            ce = Client_Execution.query.filter_by(client_id=cli_id).first()
            ce.elapsed_time += 1
            ce.last_active_hour = h
            ce.last_active_day = d
            db.session.commit()

        # evaluate follows (once per day, only for a random sample of daily active agents)
        if float(cl.config["agents"]["probability_of_daily_follow"]) > 0:
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

        # daily churn and new agents
        if len(daily_active) > 0:
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
        cl.save_agents(agent_file)
