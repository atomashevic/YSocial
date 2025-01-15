import subprocess
import os
import sys
from requests import post
import json
import time


def terminate_process_on_port(port):
    """
    Terminate the process using the specified port

    :param port: the port number
    """
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


def start_server(exp):
    """
    Start the y_server in a detached screen

    :param exp: the experiment object
    """
    yserver_path = os.path.dirname(os.path.abspath(__file__)).split("y_web")[0]
    sys.path.append(f'{yserver_path}{os.sep}external{os.sep}YServer/')
    BASE_DIR = os.path.dirname(os.path.abspath(__file__)).split("utils")[0]
    config = f"{BASE_DIR}/{exp.db_name.split('database_server.db')[0]}config_server.json"
    exp_uid = exp.db_name.split(os.sep)[1]
    flask_command = f"python {yserver_path}external{os.sep}YServer{os.sep}y_server_run.py -c {config}"

    # Command to run in the detached screen
    screen_command = f"screen -dmS {exp_uid} {flask_command}"

    print(f"Starting server for experiment {exp_uid}...")
    subprocess.run(screen_command, shell=True, check=True)

    # Wait for the server to start
    time.sleep(5)
    print("Setup the database")
    data = {"path": f"{BASE_DIR[1:]}{exp.db_name}"}
    headers = {"Content-Type": "application/json"}
    ns = f"http://{exp.server}:{exp.port}/change_db"
    print(ns)
    print(data)
    post(f"{ns}", headers=headers, data=json.dumps(data))
