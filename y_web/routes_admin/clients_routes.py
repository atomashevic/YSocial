"""
Client simulation management routes.

Administrative routes for configuring and managing simulation clients,
including behavior parameters, LLM settings, network topology, and
client execution control (start/pause/resume/terminate).
"""

import json
import os
import shutil
import traceback

import faker
import networkx as nx
from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
)
from flask_login import current_user, login_required

from y_web import db
from y_web.models import (
    ActivityProfile,
    Agent,
    Agent_Population,
    Agent_Profile,
    Client,
    Client_Execution,
    Content_Recsys,
    Exp_Topic,
    Exps,
    Follow_Recsys,
    Page,
    Page_Population,
    Population,
    Population_Experiment,
    PopulationActivityProfile,
    Topic_List,
    User_mgmt,
)
from y_web.utils import (
    get_db_type,
    get_llm_models,
    get_ollama_models,
    start_client,
    terminate_client,
)
from y_web.utils.desktop_file_handler import send_file_desktop
from y_web.utils.experiment_clock import (
    apply_clock_to_client_simulation,
    current_local_time,
    ensure_experiment_clock,
    validate_clock_mode,
    validate_feed_refresh,
    validate_timezone,
)
from y_web.utils.experiment_helpers import get_experiment_uid_from_db_name
from y_web.utils.memory_run_id import (
    build_memory_run_seed,
    normalize_memory_run_id,
)
from y_web.utils.miscellanea import check_privileges, llm_backend_status, ollama_status
from y_web.utils.path_utils import get_resource_path, get_writable_path

clientsr = Blueprint("clientsr", __name__)

# Defaults for context-heavy prompts.
DEFAULT_OLLAMA_MAX_TOKENS = 768
DEFAULT_MAX_THREAD_CONTEXT_CHARS = 3200
MAX_MAX_THREAD_CONTEXT_CHARS = 4800
DEFAULT_MEMORY_PROMPT_MAX_CHARS = 1600
MAX_MEMORY_PROMPT_MAX_CHARS = 3200
DEFAULT_MEMORY_SEARCH_MAX_CHARS = 900
MAX_MEMORY_SEARCH_MAX_CHARS = 1800
DEFAULT_MEMORY_TIER_A_MAX_CHARS = 350
MAX_MEMORY_TIER_A_MAX_CHARS = 2000
DEFAULT_MEMORY_TIER_B_MAX_CHARS = 900
DEFAULT_MEMORY_TIER_C_MAX_CHARS = 900
MAX_MEMORY_TIER_BC_MAX_CHARS = 3200
DEFAULT_MEMORY_TOTAL_MAX_CHARS = 2200
MAX_MEMORY_TOTAL_MAX_CHARS = 5000


def _normalize_llm_max_tokens(raw_value):
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_OLLAMA_MAX_TOKENS
    if parsed <= 0:
        return DEFAULT_OLLAMA_MAX_TOKENS
    return parsed


@clientsr.route("/admin/reset_client/<int:uid>")
@login_required
def reset_client(uid):
    """Handle reset client operation."""
    check_privileges(current_user.username)

    from y_web.utils.path_utils import get_writable_path

    BASE_DIR = get_writable_path()

    # delete experiment json files
    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    # Extract experiment folder using helper function
    exp_folder = get_experiment_uid_from_db_name(exp.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return redirect(request.referrer or "/admin/experiments")

    population = Population.query.filter_by(id=client.population_id).first()
    path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{population.name.replace(' ', '')}.json"
    if os.path.exists(path):
        os.remove(path)

    path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}prompts.json"
    if os.path.exists(path):
        os.remove(path)

    # copy the original prompts.json file
    if exp.platform_type == "microblogging":
        prompts_src = get_resource_path(os.path.join("data_schema", "prompts.json"))
        shutil.copy(
            prompts_src,
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}prompts.json",
        )
    elif exp.platform_type == "forum":
        prompts_src = get_resource_path(
            os.path.join("data_schema", "prompts_forum.json")
        )
        shutil.copy(
            prompts_src,
            f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}prompts.json",
        )
    else:
        raise Exception(f"unsupported platform: {exp.platform_type}")

    # delete client execution
    db.session.query(Client_Execution).filter_by(client_id=uid).delete()
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/extend_simulation/<int:id_client>", methods=["POST", "GET"])
@login_required
def extend_simulation(id_client):
    """Handle extend simulation operation."""
    check_privileges(current_user.username)

    # check if the client exists
    client = Client.query.filter_by(id=id_client).first()
    if client is None:
        flash("Client not found.", "error")
        return redirect(request.referrer)

    # get the days from the form
    days = request.form.get("days")

    # get the client execution
    client_execution = Client_Execution.query.filter_by(client_id=id_client).first()

    # extend the simulation
    client_execution.expected_duration_rounds += int(days) * 24

    db.session.commit()

    # update the client days field
    client = db.session.query(Client).filter_by(id=id_client).first()
    client.days = int(client.days) + int(days)
    db.session.commit()

    # Check if the experiment was completed, and reset to stopped if so
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if exp and exp.exp_status == "completed":
        exp.exp_status = "stopped"
        db.session.commit()
        flash(
            f"Experiment '{exp.exp_name}' moved from completed to stopped (client duration extended).",
            "info",
        )

    return redirect(request.referrer)


@clientsr.route("/admin/run_client/<int:uid>/<int:idexp>")
@login_required
def run_client(uid, idexp):
    """Handle run client operation."""
    from .experiments_routes import experiment_details

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

    return experiment_details(idexp)


@clientsr.route("/admin/resume_client/<int:uid>/<int:idexp>")
@login_required
def resume_client(uid, idexp):
    """Handle resume client operation."""
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
    """Handle pause client operation."""
    from .experiments_routes import experiment_details

    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client
    client = Client.query.filter_by(id=uid).first()
    terminate_client(client, pause=True)

    return experiment_details(idexp)  # redirect(request.referrer)


@clientsr.route("/admin/stop_client/<int:uid>/<int:idexp>")
@login_required
def stop_client(uid, idexp):
    """Handle stop client operation."""
    from .experiments_routes import experiment_details

    check_privileges(current_user.username)

    # get population_experiment and update the client_running status
    db.session.query(Client).filter_by(id=uid).update({Client.status: 0})
    db.session.commit()

    # get client
    client = Client.query.filter_by(id=uid).first()
    terminate_client(client, pause=False)

    return experiment_details(idexp)  # redirect(request.referrer)


@clientsr.route("/admin/clients/<idexp>")
@login_required
def clients(idexp):
    """Handle clients operation."""
    check_privileges(current_user.username)

    # get experiment
    exp = Exps.query.filter_by(idexp=idexp).first()

    # get only populations already associated with this experiment
    pop_exp_associations = Population_Experiment.query.filter_by(id_exp=idexp).all()
    population_ids = [pe.id_population for pe in pop_exp_associations]

    # get only populations  that are not associated with this experiment
    pops = (
        Population.query.filter(~Population.id.in_(population_ids)).all()
        if population_ids
        else Population.query.all()
    )

    # Only allow populations compatible with this experiment's platform type.
    # Default to microblogging for legacy populations without username_type.
    pops = [
        p
        for p in pops
        if (getattr(p, "username_type", "microblogging") or "microblogging")
        == exp.platform_type
    ]

    crecsys = Content_Recsys.query.all()
    frecsys = Follow_Recsys.query.all()

    # Check if LLM agents are enabled for this experiment
    llm_agents_enabled = (
        exp.llm_agents_enabled if hasattr(exp, "llm_agents_enabled") else True
    )

    # Get experiment-wide LLM defaults
    exp_llm_defaults = {
        "llm": getattr(exp, "llm_default", None) or "http://127.0.0.1:11434/v1",
        "llm_api_key": getattr(exp, "llm_api_key_default", None) or "NULL",
        "llm_max_tokens": _normalize_llm_max_tokens(
            getattr(exp, "llm_max_tokens_default", None)
        ),
        "llm_temperature": getattr(exp, "llm_temperature_default", None) or 1.5,
        "llm_v": getattr(exp, "llm_v_default", None) or "http://127.0.0.1:11434/v1",
        "llm_v_api_key": getattr(exp, "llm_v_api_key_default", None) or "NULL",
        "llm_v_max_tokens": getattr(exp, "llm_v_max_tokens_default", None) or 300,
        "llm_v_temperature": getattr(exp, "llm_v_temperature_default", None) or 0.5,
    }

    experiment_clock = {}
    try:
        exp_uid = get_experiment_uid_from_db_name(exp.db_name)
        if exp_uid:
            base_dir = get_writable_path()
            config_path = os.path.join(
                base_dir,
                "y_web",
                "experiments",
                exp_uid,
                "config_server.json",
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as config_file:
                    config_payload = json.load(config_file)
                experiment_clock = ensure_experiment_clock(config_payload)
    except Exception:
        experiment_clock = {}

    return render_template(
        "admin/clients.html",
        experiment=exp,
        populations=pops,
        crecsys=crecsys,
        frecsys=frecsys,
        llm_agents_enabled=llm_agents_enabled,
        exp_llm_defaults=exp_llm_defaults,
        experiment_clock=experiment_clock,
    )


@clientsr.route("/admin/create_client", methods=["POST"])
@login_required
def create_client():
    """Create client."""
    check_privileges(current_user.username)

    name = request.form.get("name")
    descr = request.form.get("descr")
    exp_id = request.form.get("id_exp")
    population_id = request.form.get("population_id")
    initial_agents = request.form.get("initial_agents")
    days = request.form.get("days")
    percentage_new_agents_iteration = request.form.get(
        "percentage_new_agents_iteration"
    )
    percentage_removed_agents_iteration = request.form.get(
        "percentage_removed_agents_iteration"
    )
    max_length_thread_reading = request.form.get("max_length_thread_reading")
    max_thread_context_chars = request.form.get(
        "max_thread_context_chars", DEFAULT_MAX_THREAD_CONTEXT_CHARS
    )
    reading_from_follower_ratio = request.form.get("reading_from_follower_ratio")
    probability_of_daily_follow = request.form.get("probability_of_daily_follow")
    probability_of_secondary_follow = request.form.get(
        "probability_of_secondary_follow"
    )
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
    share_link = request.form.get("share_link")
    share_image = request.form.get("share_image")
    clock_mode = request.form.get("clock_mode")
    clock_timezone = request.form.get("clock_timezone")
    clock_feed_refresh = request.form.get("clock_feed_refresh", "hourly")

    # Reply behavior controls (guardrails)
    max_replies_per_round = request.form.get("max_replies_per_round", 2)
    reply_cooldown_rounds = request.form.get("reply_cooldown_rounds", 2)

    # Run-scoped agent memory controls (hybrid storage + LLM-on-write + decay)
    # Checkbox fields are absent when unchecked, so treat missing as the feature default (enabled).
    memory_enabled_raw = request.form.get("memory_enabled")
    if memory_enabled_raw is None:
        memory_enabled = True
    else:
        memory_enabled = str(memory_enabled_raw).strip().lower() in {
            "1",
            "true",
            "on",
            "yes",
        }

    memory_pair_limit = request.form.get("memory_pair_limit", 5)
    memory_prompt_max_chars = request.form.get(
        "memory_prompt_max_chars", DEFAULT_MEMORY_PROMPT_MAX_CHARS
    )
    memory_social_decay_lambda = request.form.get("memory_social_decay_lambda", 0.05)
    memory_social_corruption_rate = request.form.get(
        "memory_social_corruption_rate", 0.02
    )
    memory_social_resummarize_every_events = request.form.get(
        "memory_social_resummarize_every_events", 4
    )
    memory_thread_decay_lambda = request.form.get("memory_thread_decay_lambda", 0.03)
    memory_thread_corruption_rate = request.form.get(
        "memory_thread_corruption_rate", 0.01
    )
    memory_thread_resummarize_every_events = request.form.get(
        "memory_thread_resummarize_every_events", 4
    )
    memory_evidence_tail_max = request.form.get("memory_evidence_tail_max", 8)
    memory_digest_update_cadence_rounds = request.form.get(
        "memory_digest_update_cadence_rounds", 3
    )
    memory_digest_events_limit = request.form.get("memory_digest_events_limit", 80)
    memory_cold_start_window = request.form.get("memory_cold_start_window", 5)
    memory_semantic_enabled_raw = request.form.get("memory_semantic_enabled")
    if memory_semantic_enabled_raw is None:
        memory_semantic_enabled = True
    else:
        memory_semantic_enabled = str(memory_semantic_enabled_raw).strip().lower() in {
            "1",
            "true",
            "on",
            "yes",
        }
    memory_search_k = request.form.get("memory_search_k", 8)
    memory_search_max_chars = request.form.get(
        "memory_search_max_chars", DEFAULT_MEMORY_SEARCH_MAX_CHARS
    )
    memory_search_time_window_rounds = request.form.get(
        "memory_search_time_window_rounds", 40
    )
    memory_tier_a_max_chars = request.form.get(
        "memory_tier_a_max_chars", DEFAULT_MEMORY_TIER_A_MAX_CHARS
    )
    memory_tier_b_max_chars = request.form.get(
        "memory_tier_b_max_chars", DEFAULT_MEMORY_TIER_B_MAX_CHARS
    )
    memory_tier_c_max_chars = request.form.get(
        "memory_tier_c_max_chars", DEFAULT_MEMORY_TIER_C_MAX_CHARS
    )
    memory_total_max_chars = request.form.get(
        "memory_total_max_chars", DEFAULT_MEMORY_TOTAL_MAX_CHARS
    )
    memory_tier_c_uncertainty_threshold = request.form.get(
        "memory_tier_c_uncertainty_threshold", 0.45
    )
    memory_reflection_cadence_rounds = request.form.get(
        "memory_reflection_cadence_rounds", 3
    )
    memory_reflection_min_events = request.form.get("memory_reflection_min_events", 12)
    memory_reflection_trigger_importance_sum = request.form.get(
        "memory_reflection_trigger_importance_sum", 3.5
    )
    memory_reflection_max_items_per_run = request.form.get(
        "memory_reflection_max_items_per_run", 60
    )
    memory_embedding_model = request.form.get("memory_embedding_model", "BAAI/bge-m3")
    memory_embedding_async_raw = request.form.get("memory_embedding_async")
    if memory_embedding_async_raw is None:
        memory_embedding_async = True
    else:
        memory_embedding_async = str(memory_embedding_async_raw).strip().lower() in {
            "1",
            "true",
            "on",
            "yes",
        }
    memory_importance_mode = request.form.get(
        "memory_importance_mode", "heuristic_then_batch_llm"
    )

    # Normalize required foreign keys early to avoid DB type errors (e.g., PostgreSQL int vs "")
    try:
        exp_id = int(exp_id)
    except (TypeError, ValueError):
        flash("Invalid experiment ID.", "error")
        return redirect(request.referrer or "/admin/experiments")

    try:
        population_id = int(population_id)
    except (TypeError, ValueError):
        flash("Please select a valid population.", "error")
        return redirect(request.referrer or f"/admin/clients/{exp_id}")

    # Check if LLM agents are enabled for this experiment
    exp = Exps.query.filter_by(idexp=exp_id).first()
    llm_agents_enabled = (
        exp.llm_agents_enabled if (exp and hasattr(exp, "llm_agents_enabled")) else True
    )

    # Get LLM parameters from form, or use defaults if LLM agents are disabled
    if llm_agents_enabled:
        llm = request.form.get("llm")
        llm_api_key = request.form.get("llm_api_key")
        llm_max_tokens = request.form.get("llm_max_tokens")
        llm_temperature = request.form.get("llm_temperature")
        llm_v_agent = request.form.get("llm_v_agent")
        llm_v = request.form.get("llm_v")
        llm_v_api_key = request.form.get("llm_v_api_key")
        llm_v_max_tokens = request.form.get("llm_v_max_tokens")
        llm_v_temperature = request.form.get("llm_v_temperature")
        user_type = request.form.get("user_type")
    else:
        # Use default values when LLM agents are disabled
        llm = "http://127.0.0.1:11434/v1"
        llm_api_key = "NULL"
        llm_max_tokens = str(DEFAULT_OLLAMA_MAX_TOKENS)
        llm_temperature = "1.5"
        llm_v_agent = "minicpm-v"
        llm_v = "http://127.0.0.1:11434/v1"
        llm_v_api_key = "NULL"
        llm_v_max_tokens = "300"
        llm_v_temperature = "0.5"
        user_type = ""

    crecsys = request.form.get("recsys_type")
    frecsys = request.form.get("frecsys_type")

    # Validate simulation parameters
    errors = []
    # Validate numeric fields
    try:
        days = int(days)
        # days = -1 means infinite/run-until-stopped
        if days != -1 and days < 1:
            errors.append(
                "Days must be at least 1, or use -1 for infinite duration (run until stopped)"
            )
    except (ValueError, TypeError):
        errors.append("Days must be a valid integer")
    try:
        max_length_thread_reading = int(max_length_thread_reading)
    except (ValueError, TypeError):
        errors.append("Max Length Thread Reading must be a valid integer")
    try:
        max_thread_context_chars = int(max_thread_context_chars)
        if max_thread_context_chars < 200:
            errors.append("Max Thread Context Chars must be at least 200")
        if max_thread_context_chars > MAX_MAX_THREAD_CONTEXT_CHARS:
            errors.append(
                f"Max Thread Context Chars must be <= {MAX_MAX_THREAD_CONTEXT_CHARS}"
            )
    except (ValueError, TypeError):
        errors.append("Max Thread Context Chars must be a valid integer")
    try:
        attention_window = int(attention_window)
    except (ValueError, TypeError):
        errors.append("Attention Window must be a valid integer")
    try:
        visibility_rounds = int(visibility_rounds)
    except (ValueError, TypeError):
        errors.append("Visibility Rounds must be a valid integer")
    try:
        clock_mode = validate_clock_mode(clock_mode)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        clock_timezone = validate_timezone(clock_timezone)
    except ValueError as exc:
        errors.append(str(exc))
    try:
        clock_feed_refresh = validate_feed_refresh(clock_feed_refresh)
    except ValueError as exc:
        errors.append(str(exc))

    # Validate agent memory fields
    try:
        memory_pair_limit = int(memory_pair_limit)
        if memory_pair_limit < 1:
            errors.append("Memory Pair Limit must be at least 1")
    except (ValueError, TypeError):
        errors.append("Memory Pair Limit must be a valid integer")

    try:
        memory_prompt_max_chars = int(memory_prompt_max_chars)
        if memory_prompt_max_chars < 200:
            errors.append("Memory Prompt Max Chars must be at least 200")
        if memory_prompt_max_chars > MAX_MEMORY_PROMPT_MAX_CHARS:
            errors.append(
                f"Memory Prompt Max Chars must be <= {MAX_MEMORY_PROMPT_MAX_CHARS}"
            )
    except (ValueError, TypeError):
        errors.append("Memory Prompt Max Chars must be a valid integer")

    try:
        memory_social_decay_lambda = float(memory_social_decay_lambda)
        if memory_social_decay_lambda < 0:
            errors.append("Memory Social Decay (lambda) must be >= 0")
    except (ValueError, TypeError):
        errors.append("Memory Social Decay (lambda) must be a valid number")

    try:
        memory_thread_decay_lambda = float(memory_thread_decay_lambda)
        if memory_thread_decay_lambda < 0:
            errors.append("Memory Thread Decay (lambda) must be >= 0")
    except (ValueError, TypeError):
        errors.append("Memory Thread Decay (lambda) must be a valid number")

    try:
        memory_social_corruption_rate = float(memory_social_corruption_rate)
        if not (0 <= memory_social_corruption_rate <= 1):
            errors.append("Memory Social Corruption Rate must be between 0 and 1")
    except (ValueError, TypeError):
        errors.append("Memory Social Corruption Rate must be a valid number")

    try:
        memory_thread_corruption_rate = float(memory_thread_corruption_rate)
        if not (0 <= memory_thread_corruption_rate <= 1):
            errors.append("Memory Thread Corruption Rate must be between 0 and 1")
    except (ValueError, TypeError):
        errors.append("Memory Thread Corruption Rate must be a valid number")

    try:
        memory_social_resummarize_every_events = int(
            memory_social_resummarize_every_events
        )
        if memory_social_resummarize_every_events < 1:
            errors.append("Memory Social Resummarize Every (events) must be at least 1")
    except (ValueError, TypeError):
        errors.append(
            "Memory Social Resummarize Every (events) must be a valid integer"
        )

    try:
        memory_thread_resummarize_every_events = int(
            memory_thread_resummarize_every_events
        )
        if memory_thread_resummarize_every_events < 1:
            errors.append("Memory Thread Resummarize Every (events) must be at least 1")
    except (ValueError, TypeError):
        errors.append(
            "Memory Thread Resummarize Every (events) must be a valid integer"
        )

    try:
        memory_evidence_tail_max = int(memory_evidence_tail_max)
        if memory_evidence_tail_max < 0:
            errors.append("Memory Evidence Tail Max must be >= 0")
    except (ValueError, TypeError):
        errors.append("Memory Evidence Tail Max must be a valid integer")

    try:
        memory_digest_update_cadence_rounds = int(memory_digest_update_cadence_rounds)
        if memory_digest_update_cadence_rounds < 1:
            errors.append("Memory Digest Update Cadence (rounds) must be at least 1")
    except (ValueError, TypeError):
        errors.append("Memory Digest Update Cadence (rounds) must be a valid integer")

    try:
        memory_digest_events_limit = int(memory_digest_events_limit)
        if memory_digest_events_limit < 10:
            errors.append("Memory Digest Events Limit must be at least 10")
    except (ValueError, TypeError):
        errors.append("Memory Digest Events Limit must be a valid integer")

    try:
        memory_cold_start_window = int(memory_cold_start_window)
        if memory_cold_start_window < 1:
            errors.append("Memory Cold-Start Window must be at least 1")
        if memory_cold_start_window > 1000:
            errors.append("Memory Cold-Start Window must be <= 1000")
    except (ValueError, TypeError):
        errors.append("Memory Cold-Start Window must be a valid integer")

    try:
        memory_search_k = int(memory_search_k)
        if memory_search_k < 1:
            errors.append("Memory Search K must be at least 1")
    except (ValueError, TypeError):
        errors.append("Memory Search K must be a valid integer")

    try:
        memory_search_max_chars = int(memory_search_max_chars)
        if memory_search_max_chars < 300:
            errors.append("Memory Search Max Chars must be at least 300")
        if memory_search_max_chars > MAX_MEMORY_SEARCH_MAX_CHARS:
            errors.append(
                f"Memory Search Max Chars must be <= {MAX_MEMORY_SEARCH_MAX_CHARS}"
            )
    except (ValueError, TypeError):
        errors.append("Memory Search Max Chars must be a valid integer")

    try:
        memory_search_time_window_rounds = int(memory_search_time_window_rounds)
        if memory_search_time_window_rounds < 0:
            errors.append("Memory Search Window (rounds) must be >= 0")
    except (ValueError, TypeError):
        errors.append("Memory Search Window (rounds) must be a valid integer")

    try:
        memory_tier_a_max_chars = int(memory_tier_a_max_chars)
        if memory_tier_a_max_chars < 100:
            errors.append("Memory Tier A Max Chars must be at least 100")
        if memory_tier_a_max_chars > MAX_MEMORY_TIER_A_MAX_CHARS:
            errors.append(
                f"Memory Tier A Max Chars must be <= {MAX_MEMORY_TIER_A_MAX_CHARS}"
            )
    except (ValueError, TypeError):
        errors.append("Memory Tier A Max Chars must be a valid integer")

    try:
        memory_tier_b_max_chars = int(memory_tier_b_max_chars)
        if memory_tier_b_max_chars < 400:
            errors.append("Memory Tier B Max Chars must be at least 400")
        if memory_tier_b_max_chars > MAX_MEMORY_TIER_BC_MAX_CHARS:
            errors.append(
                f"Memory Tier B Max Chars must be <= {MAX_MEMORY_TIER_BC_MAX_CHARS}"
            )
    except (ValueError, TypeError):
        errors.append("Memory Tier B Max Chars must be a valid integer")

    try:
        memory_tier_c_max_chars = int(memory_tier_c_max_chars)
        if memory_tier_c_max_chars < 400:
            errors.append("Memory Tier C Max Chars must be at least 400")
        if memory_tier_c_max_chars > MAX_MEMORY_TIER_BC_MAX_CHARS:
            errors.append(
                f"Memory Tier C Max Chars must be <= {MAX_MEMORY_TIER_BC_MAX_CHARS}"
            )
    except (ValueError, TypeError):
        errors.append("Memory Tier C Max Chars must be a valid integer")

    try:
        memory_total_max_chars = int(memory_total_max_chars)
        if memory_total_max_chars < 800:
            errors.append("Memory Total Max Chars must be at least 800")
        if memory_total_max_chars > MAX_MEMORY_TOTAL_MAX_CHARS:
            errors.append(
                f"Memory Total Max Chars must be <= {MAX_MEMORY_TOTAL_MAX_CHARS}"
            )
    except (ValueError, TypeError):
        errors.append("Memory Total Max Chars must be a valid integer")

    if all(
        isinstance(v, int)
        for v in (
            memory_tier_a_max_chars,
            memory_tier_b_max_chars,
            memory_tier_c_max_chars,
            memory_total_max_chars,
        )
    ):
        tiers_total = (
            memory_tier_a_max_chars + memory_tier_b_max_chars + memory_tier_c_max_chars
        )
        if tiers_total > memory_total_max_chars:
            errors.append(
                "Memory tier budgets must fit within Memory Total Max Chars "
                f"(tier sum {tiers_total} > total {memory_total_max_chars})."
            )

    llm_max_tokens = _normalize_llm_max_tokens(llm_max_tokens)

    try:
        memory_tier_c_uncertainty_threshold = float(memory_tier_c_uncertainty_threshold)
        if not (0 <= memory_tier_c_uncertainty_threshold <= 1):
            errors.append("Memory Tier C Uncertainty must be between 0 and 1")
    except (ValueError, TypeError):
        errors.append("Memory Tier C Uncertainty must be a valid number")

    try:
        memory_reflection_cadence_rounds = int(memory_reflection_cadence_rounds)
        if memory_reflection_cadence_rounds < 1:
            errors.append("Memory Reflection Cadence must be at least 1")
    except (ValueError, TypeError):
        errors.append("Memory Reflection Cadence must be a valid integer")

    try:
        memory_reflection_min_events = int(memory_reflection_min_events)
        if memory_reflection_min_events < 1:
            errors.append("Memory Reflection Min Events must be at least 1")
    except (ValueError, TypeError):
        errors.append("Memory Reflection Min Events must be a valid integer")

    try:
        memory_reflection_trigger_importance_sum = float(
            memory_reflection_trigger_importance_sum
        )
        if memory_reflection_trigger_importance_sum < 0:
            errors.append("Memory Reflection Trigger Sum must be >= 0")
    except (ValueError, TypeError):
        errors.append("Memory Reflection Trigger Sum must be a valid number")

    try:
        memory_reflection_max_items_per_run = int(memory_reflection_max_items_per_run)
        if memory_reflection_max_items_per_run < 1:
            errors.append("Memory Reflection Max Items must be at least 1")
    except (ValueError, TypeError):
        errors.append("Memory Reflection Max Items must be a valid integer")

    try:
        memory_embedding_model = str(memory_embedding_model).strip()
        if len(memory_embedding_model) == 0:
            errors.append("Memory Embedding Model cannot be empty")
    except Exception:
        errors.append("Memory Embedding Model must be a valid string")

    try:
        memory_importance_mode = str(memory_importance_mode).strip()
        if len(memory_importance_mode) == 0:
            errors.append("Memory Importance Mode cannot be empty")
    except Exception:
        errors.append("Memory Importance Mode must be a valid string")

    # Validate probability fields (must be float in [0, 1])
    try:
        percentage_new_agents_iteration = float(percentage_new_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% New Agents (daily) must be a valid number")
        percentage_new_agents_iteration = None
    try:
        percentage_removed_agents_iteration = float(percentage_removed_agents_iteration)
    except (ValueError, TypeError):
        errors.append("% Daily Churn must be a valid number")
        percentage_removed_agents_iteration = None
    try:
        reading_from_follower_ratio = float(reading_from_follower_ratio)
    except (ValueError, TypeError):
        errors.append("Timeline Follower Ratio must be a valid number")
        reading_from_follower_ratio = None
    try:
        probability_of_daily_follow = float(probability_of_daily_follow)
    except (ValueError, TypeError):
        errors.append("Probability Daily Follow must be a valid number")
        probability_of_daily_follow = None
    try:
        probability_of_secondary_follow = float(probability_of_secondary_follow)
    except (ValueError, TypeError):
        errors.append("Probability Secondary Follow must be a valid number")
        probability_of_secondary_follow = None

    # Check probability ranges
    probabilities = {
        "% New Agents (daily)": percentage_new_agents_iteration,
        "% Daily Churn": percentage_removed_agents_iteration,
        "Timeline Follower Ratio": reading_from_follower_ratio,
        "Probability Daily Follow": probability_of_daily_follow,
        "Probability Secondary Follow": probability_of_secondary_follow,
    }
    for field_name, value in probabilities.items():
        if value is not None and not (0 <= value <= 1):
            errors.append(f"{field_name} must be between 0 and 1")

    if errors:
        for error in errors:
            flash(error)
        return redirect(request.referrer)

    # Fetch optional network configuration
    network_model = request.form.get("network_model")
    network_p = request.form.get("network_p")
    network_m = request.form.get("network_m")
    network_file = request.files.get("network_file")

    # Fetch optional hourly activity rates
    hourly_activity_custom = {}
    for hour in range(24):
        hourly_val = request.form.get(f"hourly_{hour}")
        if hourly_val and hourly_val.strip():
            try:
                hourly_activity_custom[str(hour)] = float(hourly_val)
            except ValueError:
                pass  # Ignore invalid values, use defaults

    # get experiment topics
    topics = Exp_Topic.query.filter_by(exp_id=exp_id).all()
    topics_ids = [t.topic_id for t in topics]
    # get the topics names from the Topic_list table
    topics = db.session.query(Topic_List).filter(Topic_List.id.in_(topics_ids)).all()
    topics = [t.name for t in topics]

    # if name already exists, return to the previous page
    if Client.query.filter_by(name=name).first():
        flash("Client name already exists.", "error")
        return redirect(request.referrer)

    exp = Exps.query.filter_by(idexp=exp_id).first()

    # get population
    population = Population.query.filter_by(id=population_id).first()

    if population is None:
        flash("Population not found.", "error")
        return redirect(request.referrer)

    pop_type = getattr(population, "username_type", "microblogging") or "microblogging"
    if pop_type != exp.platform_type:
        flash(
            f"Population Username Type '{pop_type}' is incompatible with experiment platform '{exp.platform_type}'.",
            "error",
        )
        return redirect(request.referrer)

    # check if the population is already assigned to the experiment
    # if not, add it
    pop_exp = Population_Experiment.query.filter_by(
        id_population=population_id, id_exp=exp_id
    ).first()
    if not pop_exp:
        pop_exp = Population_Experiment(id_population=population_id, id_exp=exp_id)
        db.session.add(pop_exp)
        db.session.commit()

    # Enforce action restrictions per platform type
    if exp.platform_type == "forum":
        news = 0  # Forum mode doesn't use news
        share = 0  # Forum mode doesn't use share
        # share_link is KEPT for forum mode - it's the key action for Reddit-style link sharing
    elif exp.platform_type == "microblogging":
        share_link = 0  # Microblogging doesn't use share_link

    # Parse initial_agents (can be empty/None)
    initial_agents_int = None
    if initial_agents and initial_agents.strip():
        try:
            initial_agents_int = int(initial_agents)
            if initial_agents_int < 1:
                initial_agents_int = None
        except (ValueError, TypeError):
            initial_agents_int = None

    # create the Client object
    client = Client(
        name=name,
        descr=descr,
        id_exp=exp_id,
        population_id=population_id,
        initial_agents=initial_agents_int,
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
        share_link=share_link,
        llm=llm,
        llm_api_key=llm_api_key,
        llm_max_tokens=llm_max_tokens,
        llm_temperature=llm_temperature,
        llm_v_agent=llm_v_agent,
        llm_v=llm_v,
        llm_v_api_key=llm_v_api_key,
        llm_v_max_tokens=llm_v_max_tokens,
        llm_v_temperature=llm_v_temperature,
        probability_of_secondary_follow=probability_of_secondary_follow,
        crecsys=crecsys,
        frecsys=frecsys,
        max_replies_per_round=int(max_replies_per_round),
        reply_cooldown_rounds=int(reply_cooldown_rounds),
        status=0,
    )

    db.session.add(client)
    db.session.commit()

    # If experiment was completed, reset status to stopped since a new client was added
    if exp.exp_status == "completed":
        exp.exp_status = "stopped"
        db.session.commit()

    # Get LLM URL from environment (set by y_social.py)
    import os

    # get population activity profiles
    activity_profiles = (
        db.session.query(PopulationActivityProfile)
        .filter(PopulationActivityProfile.population == population_id)
        .all()
    )

    activity_profiles = [a.activity_profile for a in activity_profiles]

    # get all activity profiles from the db where id in activity_profiles
    activity_profiles = (
        db.session.query(ActivityProfile)
        .filter(ActivityProfile.id.in_([a for a in activity_profiles]))
        .all()
    )

    profiles = {ap.name: ap.hours for ap in activity_profiles}

    annotations = exp.annotations.split(",")
    emotion_annotation = "emotion" in annotations

    default_hourly_activity = {
        "0": 0.023,
        "1": 0.021,
        "2": 0.020,
        "3": 0.020,
        "4": 0.018,
        "5": 0.017,
        "6": 0.017,
        "7": 0.018,
        "8": 0.020,
        "9": 0.020,
        "10": 0.021,
        "11": 0.022,
        "12": 0.024,
        "13": 0.027,
        "14": 0.030,
        "15": 0.032,
        "16": 0.032,
        "17": 0.032,
        "18": 0.032,
        "19": 0.031,
        "20": 0.030,
        "21": 0.029,
        "22": 0.027,
        "23": 0.025,
    }

    hourly_activity = {
        str(h): (
            hourly_activity_custom.get(str(h), default_hourly_activity[str(h)])
            if hourly_activity_custom
            else default_hourly_activity[str(h)]
        )
        for h in range(24)
    }

    # Extract experiment folder using helper function.
    uid = get_experiment_uid_from_db_name(exp.db_name)
    if not uid:
        flash("Invalid experiment database configuration", "error")
        return redirect(request.referrer or "/admin/experiments")

    BASE_DIR = get_writable_path()
    client_config_path = (
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"
        f"client_{name}-{population.name}.json"
    )
    experiment_config_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}config_server.json"

    resolved_clock = {
        "mode": clock_mode,
        "timezone": clock_timezone,
        "feed_refresh": clock_feed_refresh,
    }
    experiment_clock_updated = False
    clock_sync_applied = False

    try:
        if os.path.exists(experiment_config_path):
            with open(experiment_config_path, "r") as config_file:
                experiment_config = json.load(config_file)
        else:
            experiment_config = {}

        existing_clock = ensure_experiment_clock(experiment_config)
        if (
            existing_clock["mode"] != resolved_clock["mode"]
            or existing_clock["timezone"] != resolved_clock["timezone"]
            or existing_clock["feed_refresh"] != resolved_clock["feed_refresh"]
        ):
            experiment_clock_updated = True

        experiment_config["clock"] = {
            "mode": resolved_clock["mode"],
            "timezone": resolved_clock["timezone"],
            "feed_refresh": resolved_clock["feed_refresh"],
        }

        if (
            resolved_clock["mode"] == "real_time"
            and "anchor_date" not in experiment_config["clock"]
        ):
            experiment_config["clock"]["anchor_date"] = (
                current_local_time(resolved_clock["timezone"]).date().isoformat()
            )

        resolved_clock = ensure_experiment_clock(experiment_config)

        with open(experiment_config_path, "w") as config_file:
            json.dump(experiment_config, config_file, indent=4)

        if experiment_clock_updated:
            exp_dir = os.path.dirname(experiment_config_path)
            for item in os.listdir(exp_dir):
                if not (item.startswith("client_") and item.endswith(".json")):
                    continue
                client_path = os.path.join(exp_dir, item)
                try:
                    with open(client_path, "r") as existing_client_file:
                        existing_client_config = json.load(existing_client_file)
                    if isinstance(existing_client_config.get("simulation"), dict):
                        apply_clock_to_client_simulation(
                            existing_client_config["simulation"], resolved_clock
                        )
                        with open(client_path, "w") as existing_client_file:
                            json.dump(
                                existing_client_config, existing_client_file, indent=4
                            )
                        clock_sync_applied = True
                except Exception:
                    continue
    except Exception:
        # Keep client creation resilient if experiment config is unavailable.
        pass

    existing_memory_run_key = None
    if os.path.exists(client_config_path):
        try:
            with open(client_config_path, "r") as existing_file:
                existing_cfg = json.load(existing_file)
            existing_memory_run_key = str(
                (existing_cfg.get("agents", {}) or {}).get("memory_run_id") or ""
            ).strip()
        except Exception:
            existing_memory_run_key = None

    # Keep run_id stable across client config edits and enforce DB-safe length.
    memory_run_key = normalize_memory_run_id(existing_memory_run_key)
    if not memory_run_key:
        seeded_run_key = build_memory_run_seed(
            uid,
            str(name),
            str(population.name),
        )
        memory_run_key = normalize_memory_run_id(seeded_run_key)

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
            "population": population.name.replace(" ", ""),
            "client": "YClientWeb",
            "days": int(days),
            "slots": 24,
            "initial_agents": initial_agents_int,
            "percentage_new_agents_iteration": float(percentage_new_agents_iteration),
            "percentage_removed_agents_iteration": float(
                percentage_removed_agents_iteration
            ),
            "activity_profiles": profiles,
            "hourly_activity": hourly_activity,
            "actions_likelihood": {
                "post": float(post),
                "image": float(image) if image is not None else 0,
                # Enforce action restrictions per platform type
                "news": (
                    0.0
                    if exp.platform_type == "forum"
                    else (float(news) if news is not None else 0)
                ),
                "comment": float(comment) if comment is not None else 0,
                "read": float(read) if read is not None else 0,
                "share": (
                    0.0
                    if exp.platform_type == "forum"
                    else (float(share) if share is not None else 0)
                ),
                "search": float(search) if search is not None else 0,
                "cast": float(vote) if vote is not None else 0,
                "share_link": (
                    0.0
                    if exp.platform_type == "microblogging"
                    else (float(share_link) if share_link is not None else 0)
                ),
                "share_image": (
                    0.0
                    if exp.platform_type == "microblogging"
                    else (float(share_image) if share_image is not None else 0)
                ),
            },
            "emotion_annotation": emotion_annotation,
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
            "llm_v_agent": "minicpm-v",
            "username_type": pop_type,
            "reading_from_follower_ratio": float(reading_from_follower_ratio),
            "max_length_thread_reading": int(max_length_thread_reading),
            "max_thread_context_chars": int(max_thread_context_chars),
            "attention_window": int(attention_window),
            "probability_of_daily_follow": float(probability_of_daily_follow),
            "probability_of_secondary_follow": float(probability_of_secondary_follow),
            "age": {"min": 18, "max": 65},
            "political_leaning": [],
            "toxicity_levels": [],
            "languages": [],
            "llm_agents": [],
            "education_levels": [],
            "round_actions": {"min": 1, "max": 3},
            "n_interests": {"min": 1, "max": 5},
            "interests": [],
            "big_five": {
                "oe": ["inventive/curious", "consistent/cautious"],
                "co": ["extravagant/careless", "efficient/organized"],
                "ex": ["outgoing/energetic", "solitary/reserved"],
                "ag": ["critical/judgmental", "friendly/compassionate"],
                "ne": ["resilient/confident", "sensitive/nervous"],
            },
            "max_replies_per_round": int(max_replies_per_round),
            "reply_cooldown_rounds": int(reply_cooldown_rounds),
            # Forum agents: sequential thread browsing before commenting
            "thread_browse_mode": "llm",
            "thread_browse_order": "tree_dfs",
            "thread_browse_max_nodes": 400,
            "thread_browse_chunk_size": 20,
            "thread_browse_top_k": 6,
            "thread_browse_max_llm_steps": 3,
            "thread_browse_snippet_chars": 220,
            "thread_browse_context_window": 30,
            # Run-scoped agent memory (hybrid storage, LLM-on-write + decay)
            "memory_enabled": bool(memory_enabled),
            "memory_pair_limit": int(memory_pair_limit),
            "memory_prompt_max_chars": int(memory_prompt_max_chars),
            "memory_social_decay_lambda": float(memory_social_decay_lambda),
            "memory_social_corruption_rate": float(memory_social_corruption_rate),
            "memory_social_resummarize_every_events": int(
                memory_social_resummarize_every_events
            ),
            "memory_thread_decay_lambda": float(memory_thread_decay_lambda),
            "memory_thread_corruption_rate": float(memory_thread_corruption_rate),
            "memory_thread_resummarize_every_events": int(
                memory_thread_resummarize_every_events
            ),
            "memory_evidence_tail_max": int(memory_evidence_tail_max),
            "memory_digest_update_cadence_rounds": int(
                memory_digest_update_cadence_rounds
            ),
            "memory_digest_events_limit": int(memory_digest_events_limit),
            "memory_cold_start_window": int(memory_cold_start_window),
            "memory_semantic_enabled": bool(memory_semantic_enabled),
            "memory_search_k": int(memory_search_k),
            "memory_search_max_chars": int(memory_search_max_chars),
            "memory_search_time_window_rounds": int(memory_search_time_window_rounds),
            "memory_tier_a_max_chars": int(memory_tier_a_max_chars),
            "memory_tier_b_max_chars": int(memory_tier_b_max_chars),
            "memory_tier_c_max_chars": int(memory_tier_c_max_chars),
            "memory_total_max_chars": int(memory_total_max_chars),
            "memory_tier_c_uncertainty_threshold": float(
                memory_tier_c_uncertainty_threshold
            ),
            "memory_reflection_cadence_rounds": int(memory_reflection_cadence_rounds),
            "memory_reflection_min_events": int(memory_reflection_min_events),
            "memory_reflection_trigger_importance_sum": float(
                memory_reflection_trigger_importance_sum
            ),
            "memory_reflection_max_items_per_run": int(
                memory_reflection_max_items_per_run
            ),
            "memory_embedding_model": str(memory_embedding_model).strip(),
            "memory_embedding_async": bool(memory_embedding_async),
            "memory_importance_mode": str(memory_importance_mode).strip(),
            "memory_run_id": memory_run_key,
            "memory_reset_on_start": False,
            "memory_high_affect_enabled": False,
            "memory_nuance_planner_enabled": False,
            "memory_prompt_mode": "subtle_forum",
            "memory_reply_context_max_chars": 280,
            "memory_vote_signal_only": True,
            "forum_post_structure_strict": True,
            "memory_cross_thread_callback_min_score": 0.8,
        },
    }
    apply_clock_to_client_simulation(config["simulation"], resolved_clock)

    if experiment_clock_updated:
        flash(
            "Experiment clock settings were updated and applied experiment-wide.",
            "info",
        )
        if clock_sync_applied:
            flash(
                "Existing client configuration files were synchronized with the new clock settings.",
                "info",
            )

    # get population agents
    agents = Agent_Population.query.filter_by(population_id=population_id).all()
    # get agents political leaning
    political_leaning = set(
        [Agent.query.filter_by(id=a.agent_id).first().leaning for a in agents]
    )
    # get agents' age
    age = set([Agent.query.filter_by(id=a.agent_id).first().age for a in agents])
    # get agents toxicity levels
    toxicity = set(
        [Agent.query.filter_by(id=a.agent_id).first().toxicity for a in agents]
    )
    # get agents' language
    language = set(
        [Agent.query.filter_by(id=a.agent_id).first().language for a in agents]
    )
    # get agents' type
    ag_type = set(
        [Agent.query.filter_by(id=a.agent_id).first().ag_type for a in agents]
    )
    # get agents' education level
    education_level = set(
        [Agent.query.filter_by(id=a.agent_id).first().education_level for a in agents]
    )

    config["agents"]["political_leanings"] = list(political_leaning)
    config["agents"]["age"]["min"] = min(age)
    config["agents"]["age"]["max"] = max(age)
    config["agents"]["toxicity_levels"] = list(toxicity)
    config["agents"]["languages"] = list(language)
    config["agents"]["llm_agents"] = list(ag_type)
    config["agents"]["education_levels"] = list(education_level)
    config["agents"]["round_actions"] = {"min": 1, "max": 3}
    config["agents"]["n_interests"] = {"min": 1, "max": 5}

    with open(
        f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}client_{name}-{population.name}.json",
        "w",
    ) as f:
        json.dump(config, f, indent=4)

    data_base_path = f"{BASE_DIR}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}"
    # copy prompts.json into the experiment folder

    if exp.platform_type == "microblogging":
        prompts_src = get_resource_path(os.path.join("data_schema", "prompts.json"))
        shutil.copyfile(
            prompts_src,
            f"{data_base_path}prompts.json",
        )

    elif exp.platform_type == "forum":
        prompts_src = get_resource_path(
            os.path.join("data_schema", "prompts_forum.json")
        )
        shutil.copyfile(
            prompts_src,
            f"{data_base_path}prompts.json",
        )
    else:
        raise Exception(f"unsupported platform: {exp.platform_type}")

    # Create agent population file
    writable_base = get_writable_path()

    # Use the already-extracted uid from above
    filename = os.path.join(
        writable_base,
        "y_web",
        "experiments",
        uid,
        f"{population.name.replace(' ', '')}.json",
    )

    agents = Agent_Population.query.filter_by(population_id=population.id).all()
    # get the agent details
    agents = [Agent.query.filter_by(id=a.agent_id).first() for a in agents]

    res = {"agents": []}
    for a in agents:
        custom_prompt = Agent_Profile.query.filter_by(agent_id=a.id).first()

        if custom_prompt:
            custom_prompt = custom_prompt.profile

        # randomly select from 1 to 5 topics without replacement and save as interests
        fake = faker.Faker()

        interests = list(
            set(
                fake.random_elements(
                    elements=set(topics),
                    length=fake.random_int(
                        min=1,
                        max=5,
                    ),
                )
            )
        )

        ints = [interests, len(interests)]

        activity_profile_obj = (
            db.session.query(ActivityProfile).filter_by(id=a.activity_profile).first()
        )
        activity_profile_name = (
            activity_profile_obj.name if activity_profile_obj else "Always On"
        )

        res["agents"].append(
            {
                "name": a.name,
                "email": f"{a.name}@ysocial.it",
                "password": f"{a.name}",
                "age": a.age,
                "type": user_type,  # ,a.ag_type,
                "leaning": a.leaning,
                "interests": ints,
                "oe": a.oe,
                "co": a.co,
                "ex": a.ex,
                "ag": a.ag,
                "ne": a.ne,
                "rec_sys": crecsys,
                "frec_sys": frecsys,
                "language": a.language,
                "owner": exp.owner,
                "education_level": a.education_level,
                "round_actions": int(a.round_actions),
                "gender": a.gender,
                "nationality": a.nationality,
                "toxicity": a.toxicity,
                "is_page": 0,
                "prompts": custom_prompt if custom_prompt else None,
                "daily_activity_level": a.daily_activity_level,
                "profession": a.profession,
                "activity_profile": activity_profile_name,
            }
        )

    # Forum simulations: disable page accounts (news org pages).
    if exp.platform_type != "forum":
        # get the pages associated with the population
        pages = Page_Population.query.filter_by(population_id=population.id).all()
        pages = [Page.query.filter_by(id=p.page_id).first() for p in pages]

        for p in pages:
            # get pages topics
            page_topics = (
                db.session.query(Exp_Topic, Topic_List)
                .join(Topic_List)
                .filter(Exp_Topic.exp_id == exp_id, Exp_Topic.topic_id == Topic_List.id)
                .all()
            )
            page_topics = [t[1].name for t in page_topics]
            page_topics = list(set(page_topics) & set(topics))

            activity_profile_obj = (
                db.session.query(ActivityProfile)
                .filter_by(id=p.activity_profile)
                .first()
            )
            activity_profile_name = (
                activity_profile_obj.name if activity_profile_obj else "Always On"
            )

            res["agents"].append(
                {
                    "name": p.name,
                    "email": f"{p.name}@ysocial.it",
                    "password": f"{p.name}",
                    "age": 0,
                    "type": user_type,
                    "leaning": p.leaning,
                    "interests": [page_topics, len(page_topics)],
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
                    "activity_profile": activity_profile_name,
                }
            )

    print(f"Saving agents to {filename}")
    json.dump(res, open(filename, "w"), indent=4)

    # Handle optional network configuration
    if network_model or network_file:
        # get populations for client
        populations = Population.query.filter_by(id=client.population_id).all()
        # get agents for the populations
        agents = Agent_Population.query.filter(
            Agent_Population.population_id.in_([p.id for p in populations])
        ).all()
        # get agent ids for all agents in populations
        agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]

        BASE = get_writable_path()
        # Use the already-extracted uid from above
        network_path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{uid}{os.sep}{client.name}_network.csv"

        if network_file and network_file.filename:
            # Handle uploaded network file
            temp_path = network_path.replace("_network.csv", "_network_temp.csv")
            network_file.save(temp_path)

            try:
                with open(network_path, "w") as o:
                    error, error2 = False, False
                    with open(temp_path, "r") as f:
                        for l in f:
                            l = l.rstrip().split(",")
                            if len(l) < 2:
                                continue

                            agent_1 = Agent.query.filter_by(name=l[0]).all()
                            aids = [a.id for a in agent_1]

                            if agent_1 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error = len(test) == 0
                            else:
                                agent_1 = Page.query.filter_by(name=l[0]).all()
                                aids = [a.id for a in agent_1]

                                if agent_1 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error = len(test) == 0
                                if agent_1 is None:
                                    error = True

                            agent_2 = Agent.query.filter_by(name=l[1]).all()
                            aids = [a.id for a in agent_2]

                            if agent_2 is not None:
                                test = Agent_Population.query.filter(
                                    Agent_Population.agent_id.in_(aids),
                                    Agent_Population.population_id
                                    == client.population_id,
                                ).all()
                                error2 = len(test) == 0
                            else:
                                agent_2 = Page.query.filter_by(name=l[1]).all()
                                aids = [a.id for a in agent_2]

                                if agent_2 is not None:
                                    test = Page_Population.query.filter(
                                        Page_Population.page_id.in_(aids),
                                        Page_Population.population_id
                                        == client.population_id,
                                    ).all()
                                    error2 = len(test) == 0

                                if agent_2 is None:
                                    error2 = True

                            if not error and not error2:
                                o.write(f"{l[0]},{l[1]}\n")
                            else:
                                flash(
                                    f"Agent {l[0]} or {l[1]} not found in network file.",
                                    "warning",
                                )

                os.remove(temp_path)
                client.network_type = "Custom Network"
                db.session.commit()
            except Exception as e:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                if os.path.exists(network_path):
                    os.remove(network_path)
                flash(
                    "Network file format error: provide a csv file containing two columns with agent names. No header required.",
                    "error",
                )

        elif network_model:
            # Handle synthetic network generation
            m = int(network_m) if network_m else 2
            p = float(network_p) if network_p else 0.1

            if network_model == "BA":
                g = nx.barabasi_albert_graph(len(agent_ids), m=m)
            elif network_model == "ER":
                g = nx.erdos_renyi_graph(len(agent_ids), p=p)
            else:
                g = None

            if g:
                # since the network is undirected and Y assume directed relations we need to write the edges in both directions
                with open(network_path, "w") as f:
                    for n in g.edges:
                        f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
                        f.write(f"{agent_ids[n[1]]},{agent_ids[n[0]]}\n")
                    f.flush()

                client.network_type = network_model
                db.session.commit()

    from y_web.telemetry import Telemetry

    telemetry = Telemetry(user=current_user)
    telemetry.log_event(
        data={
            "action": "create_client",
            "data": {
                "llm_agents_enabled": llm_agents_enabled,
                "days": days,
                "percentage_new_agents_iteration": percentage_new_agents_iteration,
                "percentage_removed_agents_iteration": percentage_removed_agents_iteration,
                "max_length_thread_reading": max_length_thread_reading,
                "reading_from_follower_ratio": reading_from_follower_ratio,
                "probability_of_daily_follow": probability_of_daily_follow,
                "attention_window": attention_window,
                "visibility_rounds": visibility_rounds,
                "actions": {
                    "post": post,
                    "share": share,
                    "image": image,
                    "comment": comment,
                    "read": read,
                    "news": news,
                    "search": search,
                    "vote": vote,
                    "share_link": share_link,
                },
                "llm": user_type,
                "probability_of_secondary_follow": probability_of_secondary_follow,
                "crecsys": crecsys,
                "frecsys": frecsys,
            },
        }
    )

    # load experiment_details page
    from .experiments_routes import experiment_details

    return experiment_details(int(exp_id))


@clientsr.route("/admin/delete_client/<int:uid>")
@login_required
def delete_client(uid):
    """Delete client."""
    check_privileges(current_user.username)

    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found.", "error")
        return redirect(request.referrer or "/admin/experiments")

    exp_id = client.id_exp
    pop_id = client.population_id

    # If the client process is still running, terminate it before deleting the DB row.
    if client.pid:
        try:
            terminate_client(client, pause=False)
        except Exception:
            traceback.print_exc()

    Client_Execution.query.filter_by(client_id=uid).delete()
    db.session.commit()

    db.session.delete(client)
    db.session.commit()

    # Delete association of population and experiment if no other client uses it.
    # Important: only delete for this experiment, not globally for the population.
    remaining_clients = Client.query.filter_by(
        id_exp=exp_id, population_id=pop_id
    ).count()
    if remaining_clients == 0:
        Population_Experiment.query.filter_by(
            id_population=pop_id, id_exp=exp_id
        ).delete()
        db.session.commit()

    from y_web.utils.path_utils import get_writable_path

    # remove the db file on the client
    BASE_PATH = get_writable_path()
    path = f"{BASE_PATH}{os.sep}external{os.sep}YClient{os.sep}experiments{os.sep}{client.name}.db"
    if os.path.exists(path):
        os.remove(path)
    else:
        print(f"File {path} does not exist.")

    from .experiments_routes import experiment_details

    return experiment_details(exp_id)


@clientsr.route("/admin/client_details/<int:uid>")
@login_required
def client_details(uid):
    """Handle client details operation."""
    check_privileges(current_user.username)

    # get client details
    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    if not experiment:
        flash("Experiment not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    # get population for the client
    population = Population.query.filter_by(id=client.population_id).first()
    # get the pages included to the population
    pages = (
        db.session.query(Page, Page_Population)
        .join(Page_Population)
        .filter(Page_Population.population_id == client.population_id)
        .all()
    )

    # get the client configuration file
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    # Extract experiment folder using helper function
    exp_folder = get_experiment_uid_from_db_name(experiment.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return redirect(request.referrer or "/admin/experiments")

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
    else:
        config = None

    # Optional cap for how much thread text we feed to the LLM (forum + microblogging).
    max_thread_context_chars = DEFAULT_MAX_THREAD_CONTEXT_CHARS
    try:
        if isinstance(config, dict):
            max_thread_context_chars = int(
                config.get("agents", {}).get(
                    "max_thread_context_chars", DEFAULT_MAX_THREAD_CONTEXT_CHARS
                )
                or DEFAULT_MAX_THREAD_CONTEXT_CHARS
            )
    except (ValueError, TypeError):
        max_thread_context_chars = DEFAULT_MAX_THREAD_CONTEXT_CHARS

    # open the agent population file to get the number of agents
    path_agents = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{population.name.replace(' ', '')}.json"

    if os.path.exists(path_agents):
        with open(path_agents, "r") as f:
            agents = json.load(f)
    else:
        agents = None

    llms = []
    if agents is not None:
        for agent in agents["agents"]:
            llms.append(agent["type"])

    llms = ",".join(list(set(llms)))

    models = get_llm_models()  # Use generic function for any LLM server

    llm_backend = llm_backend_status()

    frecsys = Follow_Recsys.query.all()
    crecsys = Content_Recsys.query.all()

    return render_template(
        "admin/client_details.html",
        client=client,
        experiment=experiment,
        population=population,
        pages=pages,
        models=models,
        llm_backend=llm_backend,
        frecsys=frecsys,
        crecsys=crecsys,
        llms=llms,
        max_thread_context_chars=max_thread_context_chars,
    )


@clientsr.route("/admin/progress/<int:client_id>")
def get_progress(client_id):
    """Return the current progress as JSON.

    For finite clients: returns progress percentage (0-100)
    For infinite clients (expected_duration_rounds = -1): returns elapsed time info
    Also includes process health status and error detection.
    """
    import psutil

    from y_web.utils.path_utils import get_writable_path

    # get client and experiment info for log path
    client = Client.query.filter_by(id=client_id).first()
    exp = Exps.query.filter_by(idexp=client.id_exp).first() if client else None

    # get client_execution
    client_execution = Client_Execution.query.filter_by(client_id=client_id).first()

    # Check if process is actually running
    process_alive = False
    if client and client.pid:
        try:
            process = psutil.Process(client.pid)
            process_alive = (
                process.is_running() and process.status() != psutil.STATUS_ZOMBIE
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            process_alive = False

    # Check stderr log for recent errors
    has_error = False
    last_error = None
    if client and exp:
        try:
            writable_base = get_writable_path()
            # Extract experiment folder using helper function
            exp_folder = get_experiment_uid_from_db_name(exp.db_name)
            if exp_folder:
                log_dir = os.path.join(
                    writable_base, "y_web", "experiments", exp_folder
                )
            else:
                log_dir = None
            if not log_dir:
                raise ValueError("Could not determine experiment folder")
            stderr_log = os.path.join(log_dir, f"{client.name}_client_stderr.log")
            if os.path.exists(stderr_log):
                with open(stderr_log, "r") as f:
                    # Read last 50 lines to check for recent errors
                    lines = f.readlines()[-50:]
                    for line in reversed(lines):
                        if "ERROR in client process:" in line:
                            has_error = True
                            # Get the error message (next line after ERROR)
                            idx = lines.index(line)
                            if idx + 1 < len(lines):
                                last_error = (
                                    lines[idx].strip() + " " + lines[idx + 1].strip()
                                )
                            else:
                                last_error = line.strip()
                            break
        except Exception:
            pass  # Ignore log reading errors

    if client_execution is None:
        return json.dumps(
            {
                "progress": 0,
                "infinite": False,
                "process_alive": process_alive,
                "has_error": has_error,
                "last_error": last_error,
            }
        )

    # Check if this is an infinite client (expected_duration_rounds = -1)
    if client_execution.expected_duration_rounds == -1:
        # Return elapsed time info for infinite clients
        elapsed_hours = client_execution.elapsed_time
        elapsed_days = elapsed_hours // 24
        remaining_hours = elapsed_hours % 24
        return json.dumps(
            {
                "progress": -1,
                "infinite": True,
                "elapsed_time": client_execution.elapsed_time,
                "elapsed_days": elapsed_days,
                "elapsed_hours": remaining_hours,
                "last_active_day": client_execution.last_active_day,
                "last_active_hour": client_execution.last_active_hour,
                "process_alive": process_alive,
                "has_error": has_error,
                "last_error": last_error,
            }
        )

    # Calculate progress and cap at 100%
    if client_execution.expected_duration_rounds > 0:
        progress = int(
            100
            * float(client_execution.elapsed_time)
            / float(client_execution.expected_duration_rounds)
        )
        # Cap progress at 100% to prevent overflow
        progress = min(100, max(0, progress))
    else:
        progress = 0

    return json.dumps(
        {
            "progress": progress,
            "infinite": False,
            "process_alive": process_alive,
            "has_error": has_error,
            "last_error": last_error,
        }
    )


@clientsr.route("/admin/set_network/<int:uid>", methods=["POST"])
@login_required
def set_network(uid):
    """Handle set network operation."""
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()

    # get populations for client uid
    populations = Population.query.filter_by(id=client.population_id).all()
    # get agents for the populations
    agents = Agent_Population.query.filter(
        Agent_Population.population_id.in_([p.id for p in populations])
    ).all()
    # get agent ids for all agents in populations
    agent_ids = [Agent.query.filter_by(id=a.agent_id).first().name for a in agents]

    # get data from form
    network = request.form.get("network_model")

    m = int(request.form.get("m"))
    p = float(request.form.get("p"))

    if network == "BA":
        g = nx.barabasi_albert_graph(len(agent_ids), m=m)
    else:
        g = nx.erdos_renyi_graph(len(agent_ids), p=p)

    # get the client experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    # get the experiment folder
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    # Extract experiment folder using helper function
    exp_folder = get_experiment_uid_from_db_name(exp.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return redirect(request.referrer or "/admin/experiments")

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network.csv"

    # since the network is undirected and Y assume directed relations we need to write the edges in both directions
    with open(path, "w") as f:
        for n in g.edges:
            f.write(f"{agent_ids[n[0]]},{agent_ids[n[1]]}\n")
            f.write(f"{agent_ids[n[1]]},{agent_ids[n[0]]}\n")
        f.flush()

    client.network_type = network
    db.session.commit()

    return redirect(request.referrer)


@clientsr.route("/admin/upload_network/<int:uid>", methods=["POST"])
@login_required
def upload_network(uid):
    """Upload network."""
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    # get the client experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    # get the experiment folder
    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    # Extract experiment folder using helper function
    exp_folder = get_experiment_uid_from_db_name(exp.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return redirect(request.referrer or "/admin/experiments")

    network = request.files["network_file"]
    network.save(
        f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_network_temp.csv"
    )

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}"

    try:
        with open(f"{path}_network.csv", "w") as o:
            error, error2 = False, False
            with open(f"{path}_network_temp.csv", "r") as f:
                for l in f:
                    l = l.rstrip().split(",")

                    agent_1 = Agent.query.filter_by(name=l[0]).all()
                    aids = [a.id for a in agent_1]

                    if agent_1 is not None:
                        # check if in population
                        test = Agent_Population.query.filter(
                            Agent_Population.agent_id.in_(aids),
                            Agent_Population.population_id == client.population_id,
                        ).all()
                        error = len(test) == 0
                    else:
                        agent_1 = Page.query.filter_by(name=l[0]).all()
                        aids = [a.id for a in agent_1]

                        if agent_1 is not None:
                            # check if in population
                            test = Page_Population.query.filter(
                                Page_Population.page_id.in_(aids),
                                Page_Population.population_id == client.population_id,
                            ).all()
                            error = len(test) == 0
                        if agent_1 is None:
                            error = True

                    agent_2 = Agent.query.filter_by(name=l[1]).all()
                    aids = [a.id for a in agent_2]

                    if agent_2 is not None:
                        # check if in population
                        test = Agent_Population.query.filter(
                            Agent_Population.agent_id.in_(aids),
                            Agent_Population.population_id == client.population_id,
                        ).all()
                        error2 = len(test) == 0
                    else:
                        agent_2 = Page.query.filter_by(name=l[1]).all()
                        aids = [a.id for a in agent_2]

                        if agent_2 is not None:
                            # check if in population
                            test = Page_Population.query.filter(
                                Page_Population.page_id.in_(aids),
                                Page_Population.population_id == client.population_id,
                            ).all()
                            error2 = len(test) == 0

                        if agent_2 is None:
                            error2 = True

                    if not error and not error2:
                        o.write(f"{l[0]},{l[1]}\n")
                    else:
                        flash(f"Agent {l[0]} or {l[1]} not found.", "error")
                        os.remove(f"{path}_network_temp.csv")
                        os.remove(f"{path}_network.csv")
                        return redirect(request.referrer)
    except:
        flash(
            "File format error: provide a csv file containing two columns with agent names. No header required.",
            "error",
        )
        os.remove(f"{path}_network_temp.csv")
        os.remove(f"{path}_network.csv")
        return redirect(request.referrer)

    # delete the temp file
    os.remove(f"{path}_network_temp.csv")

    client.network_type = "Custom Network"
    db.session.commit()
    return redirect(request.referrer)


@clientsr.route("/admin/download_agent_list/<int:uid>")
@login_required
def download_agent_list(uid):
    """Download agent list."""
    check_privileges(current_user.username)

    # get client
    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    # get populations associated to the client
    populations = Population_Experiment.query.filter_by(id_exp=client.id_exp).all()

    # get agents in the populations
    agents = Agent_Population.query.filter(
        Agent_Population.population_id.in_([p.id_population for p in populations])
    ).all()

    # get the experiment
    exp = Exps.query.filter_by(idexp=client.id_exp).first()
    if not exp:
        flash("Experiment not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    from y_web.utils.path_utils import get_writable_path

    # get the experiment folder
    BASE = get_writable_path()

    # Extract experiment folder using helper function
    exp_folder = get_experiment_uid_from_db_name(exp.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return redirect(request.referrer or "/admin/experiments")

    with open(
        f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv",
        "w",
    ) as f:
        for a in agents:
            agent = Agent.query.filter_by(id=a.agent_id).first()
            f.write(f"{agent.name}\n")
        f.flush()

    return send_file_desktop(
        f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}{client.name}_agent_list.csv",
        as_attachment=True,
    )


@clientsr.route("/admin/update_agents_activity/<int:uid>", methods=["POST"])
@login_required
def update_agents_activity(uid):
    """Update agents activity."""
    check_privileges(current_user.username)

    # get data from form
    activity = {}
    for x in request.form:
        activity[str(x)] = float(request.form.get(str(x)))

    # get client details
    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    if not experiment:
        flash("Experiment not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    population = Population.query.filter_by(id=client.population_id).first()

    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    # Extract experiment folder using helper function
    exp_folder = get_experiment_uid_from_db_name(experiment.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return redirect(request.referrer or "/admin/experiments")

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
            config["simulation"]["hourly_activity"] = activity
            # save the new configuration
            json.dump(config, open(path, "w"), indent=4)
    else:
        flash("Configuration file not found.", "error")

    return redirect(request.referrer)


@clientsr.route("/admin/reset_agents_activity/<int:uid>")
@login_required
def reset_agents_activity(uid):
    """Handle reset agents activity operation."""
    check_privileges(current_user.username)

    # get client details
    client = Client.query.filter_by(id=uid).first()
    if not client:
        flash("Client not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    experiment = Exps.query.filter_by(idexp=client.id_exp).first()
    if not experiment:
        flash("Experiment not found", "error")
        return redirect(request.referrer or "/admin/experiments")

    population = Population.query.filter_by(id=client.population_id).first()

    from y_web.utils.path_utils import get_writable_path

    BASE = get_writable_path()

    # Extract experiment folder using helper function
    exp_folder = get_experiment_uid_from_db_name(experiment.db_name)
    if not exp_folder:
        flash("Invalid experiment database configuration", "error")
        return redirect(request.referrer or "/admin/experiments")

    path = f"{BASE}{os.sep}y_web{os.sep}experiments{os.sep}{exp_folder}{os.sep}client_{client.name}-{population.name}.json"

    if os.path.exists(path):
        with open(path, "r") as f:
            config = json.load(f)
            config["simulation"]["hourly_activity"] = {
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
            }
            # save the new configuration
            json.dump(config, open(path, "w"), indent=4)
    else:
        flash("Configuration file not found.", "error")

    return redirect(request.referrer)


@clientsr.route("/admin/update_recsys/<int:uid>", methods=["POST"])
@login_required
def update_recsys(uid):
    """Update recsys."""
    check_privileges(current_user.username)

    recsys_type = request.form.get("recsys_type")
    frecsys_type = request.form.get("frecsys_type")

    client = Client.query.filter_by(id=uid).first()

    # Update client's recsys settings
    client.crecsys = recsys_type
    client.frecsys = frecsys_type

    # get populations for client uid
    population = Population.query.filter_by(id=client.population_id).first()
    # get agents for the populations
    agents = Agent_Population.query.filter_by(population_id=population.id).all()

    # updating the recommenders of the agents in the specific simulation instance (not in the population)
    for agent in agents:
        try:
            a = Agent.query.filter_by(id=agent.agent_id).first()
            user = (User_mgmt.query.filter_by(username=a.name)).first()
            user.frecsys_type = frecsys_type
            user.recsys_type = recsys_type
            db.session.commit()
        except:
            flash("The experiment needs to be activated first.", "error")
            return redirect(request.referrer)

    db.session.commit()
    return redirect(request.referrer)


@clientsr.route("/admin/update_client_llm/<int:uid>", methods=["POST"])
@login_required
def update_llm(uid):
    """Update llm."""
    check_privileges(current_user.username)

    user_type = request.form.get("user_type")

    client = Client.query.filter_by(id=uid).first()

    # get populations for client uid
    population = Population.query.filter_by(id=client.population_id).first()
    # get agents for the populations
    agents = Agent_Population.query.filter_by(population_id=population.id).all()

    for agent in agents:
        try:
            a = Agent.query.filter_by(id=agent.agent_id).first()
            user = (User_mgmt.query.filter_by(username=a.name)).first()
            user.user_type = user_type
            db.session.commit()
        except:
            flash("The experiment needs to be activated first.", "error")
            return redirect(request.referrer)

    population.llm = user_type

    db.session.commit()
    return redirect(request.referrer)
