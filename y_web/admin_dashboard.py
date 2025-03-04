from flask import (
    Blueprint,
    render_template,
)
from flask_login import login_required, current_user

from .models import Exps, Client, Client_Execution, Ollama_Pull
from y_web.utils import (
    is_ollama_running,
    is_ollama_installed,
    get_ollama_models,
)

from .utils import check_privileges


admin = Blueprint("admin", __name__)


def ollama_status():
    return {
        "status": is_ollama_running(),
        "installed": is_ollama_installed(),
    }


@admin.route("/admin/dashboard")
@login_required
def dashboard():
    check_privileges(current_user.username)
    ollamas = ollama_status()

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

    # get installed ollama models, if any
    models = []
    try:
        models = get_ollama_models()
    except:
        pass

    # get all ollama pulls
    ollama_pulls = Ollama_Pull.query.all()
    ollama_pulls = [(pull.model_name, float(pull.status)) for pull in ollama_pulls]

    return render_template(
        "admin/dashboard.html",
        experiments=res,
        ollamas=ollamas,
        models=models,
        active_pulls=ollama_pulls,
        len=len,
    )


@admin.route("/admin/about")
@login_required
def about():
    check_privileges(current_user.username)
    return render_template("admin/about.html")
