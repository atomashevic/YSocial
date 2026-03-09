"""
Experiment Context Management.

This module handles dynamic database binding for multiple active experiments.
It provides utilities to register, access, and switch between experiment databases.
"""

import os

from flask import current_app, g, request

from y_web import db


def get_db_bind_key_for_exp(exp_id):
    """
    Get the database bind key for a specific experiment.

    Args:
        exp_id: Experiment ID

    Returns:
        Database bind key string (e.g., 'db_exp_5')
    """
    if exp_id is None:
        return "db_exp"  # Fallback to legacy single experiment bind
    return f"db_exp_{exp_id}"


def register_experiment_database(app, exp_id, db_name):
    """
    Register an experiment database in the app's SQLALCHEMY_BINDS.

    Args:
        app: Flask application instance
        exp_id: Experiment ID
        db_name: Database name or path (e.g., "experiments/uid/database_server.db")
    """
    bind_key = get_db_bind_key_for_exp(exp_id)

    # Use get_writable_path to handle both development and PyInstaller modes
    from y_web.utils.path_utils import get_writable_path

    # Check database type
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql"):
        # PostgreSQL: construct full URI
        base_uri = app.config["SQLALCHEMY_DATABASE_URI"].rsplit("/", 1)[0]
        db_uri = f"{base_uri}/{db_name}"
    elif app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        # SQLite: construct file path
        # db_name is stored as "experiments/uid/database_server.db"
        # but actual file is in "y_web/experiments/uid/database_server.db"
        # Prepend y_web/ to match actual file location
        db_path = get_writable_path(os.path.join("y_web", db_name))
        db_uri = f"sqlite:///{db_path}"
    else:
        raise ValueError("Unsupported database type")

    # Add to binds with experiment-specific key
    app.config["SQLALCHEMY_BINDS"][bind_key] = db_uri


def get_active_experiments():
    """
    Get all currently active experiments.

    Returns:
        List of Exps objects with status=1
    """
    from y_web.models import Exps

    return Exps.query.filter_by(status=1).all()


def setup_experiment_context():
    """
    Setup experiment context from the current request URL.

    This should be called in a before_request handler to extract
    the exp_id from the URL and set up the appropriate database binding.

    Dynamically routes queries to the correct experiment database by
    temporarily overriding the db_exp bind for this request.
    """
    # Admin endpoints manage experiment DB access explicitly and should not
    # implicitly override the db_exp bind in this global hook.
    if request.path.startswith("/admin/"):
        g.current_exp_id = None
        g.current_db_bind = "db_exp"
        return

    # Extract exp_id from URL if present
    exp_id = request.view_args.get("exp_id") if request.view_args else None

    if exp_id:
        g.current_exp_id = exp_id
        bind_key = get_db_bind_key_for_exp(exp_id)

        # Verify the bind exists
        if bind_key not in current_app.config["SQLALCHEMY_BINDS"]:
            # Bind doesn't exist, need to register it
            from y_web.models import Exps

            # Don't gate DB binding on Exps.status. "status" is used as an admin toggle,
            # but experiments can still be running/inspectable when status=0.
            exp = Exps.query.filter_by(idexp=exp_id).first()
            if exp:
                register_experiment_database(current_app, exp_id, exp.db_name)
                # Ensure any new db_exp tables exist for this experiment DB.
                # This runs only on first access per process, so the overhead is acceptable.
                exp_uri = current_app.config["SQLALCHEMY_BINDS"].get(bind_key)
                if exp_uri:
                    original_db_exp = current_app.config["SQLALCHEMY_BINDS"].get(
                        "db_exp"
                    )
                    current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = exp_uri
                    try:
                        db.create_all(bind="db_exp")
                    finally:
                        if original_db_exp is not None:
                            current_app.config["SQLALCHEMY_BINDS"][
                                "db_exp"
                            ] = original_db_exp

                    # For SQLite experiment DBs, run local schema migrations for post columns.
                    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith(
                        "sqlite"
                    ) and exp_uri.startswith("sqlite:///"):
                        try:
                            from y_web.migrations.add_comment_dedupe_columns import (
                                migrate_sqlite_comment_dedupe_columns,
                            )
                            from y_web.migrations.add_post_created_at_column import (
                                migrate_sqlite_experiment_db,
                            )

                            migrate_sqlite_experiment_db(exp_uri)
                            migrate_sqlite_comment_dedupe_columns(exp_uri)
                        except Exception as e:
                            print(
                                f"Warning: SQLite post schema migration failed for experiment {exp.idexp}: {e}"
                            )

                    # For PostgreSQL experiment DBs, ensure server schema columns/indexes exist.
                    if current_app.config["SQLALCHEMY_DATABASE_URI"].startswith(
                        "postgresql"
                    ):
                        try:
                            from urllib.parse import urlparse

                            from y_web.migrations.ensure_postgresql_schema import (
                                migrate_server_db,
                            )

                            parsed_uri = urlparse(
                                current_app.config["SQLALCHEMY_DATABASE_URI"]
                            )
                            pg_host = parsed_uri.hostname or "localhost"
                            pg_port = str(parsed_uri.port or 5432)
                            pg_user = parsed_uri.username or "postgres"
                            pg_password = parsed_uri.password or ""

                            if pg_password:
                                migrate_server_db(
                                    pg_host,
                                    pg_port,
                                    exp.db_name,
                                    pg_user,
                                    pg_password,
                                )
                        except Exception as e:
                            print(
                                f"Warning: PostgreSQL schema migration failed for experiment {exp.idexp}: {e}"
                            )

        g.current_db_bind = bind_key

        # Store the original db_exp bind so we can restore it later
        if not hasattr(g, "original_db_exp_bind"):
            g.original_db_exp_bind = current_app.config["SQLALCHEMY_BINDS"].get(
                "db_exp"
            )

        # Dynamically override db_exp bind to point to this experiment's database
        # This ensures all queries using __bind_key__ = "db_exp" route to the correct database
        if bind_key in current_app.config["SQLALCHEMY_BINDS"]:
            current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = current_app.config[
                "SQLALCHEMY_BINDS"
            ][bind_key]
    else:
        # No exp_id in URL, fall back to legacy behavior
        g.current_exp_id = None
        g.current_db_bind = "db_exp"


def get_current_experiment_bind():
    """
    Get the database bind key for the current request context.

    Returns:
        Database bind key string
    """
    return getattr(g, "current_db_bind", "db_exp")


def get_current_experiment_id():
    """
    Get the experiment ID for the current request context.

    Returns:
        Experiment ID or None
    """
    return getattr(g, "current_exp_id", None)


def teardown_experiment_context(exception=None):
    """
    Restore the original db_exp bind after the request completes.

    This should be called in a teardown_request handler to ensure
    the db_exp bind is restored to its original state after each request.

    Args:
        exception: Exception that occurred during request processing, if any
    """
    # Restore original db_exp bind if it was modified
    if hasattr(g, "original_db_exp_bind") and g.original_db_exp_bind is not None:
        current_app.config["SQLALCHEMY_BINDS"]["db_exp"] = g.original_db_exp_bind


def initialize_active_experiment_databases(app):
    """
    Initialize database bindings for all currently active experiments.

    This should be called during application startup to register
    all active experiment databases. For PostgreSQL databases, it also
    runs schema migrations to ensure all required columns exist.

    Args:
        app: Flask application instance
    """
    with app.app_context():
        from y_web.models import Exps

        active_experiments = Exps.query.filter_by(status=1).all()

        # Check if we're using PostgreSQL
        is_postgresql = app.config["SQLALCHEMY_DATABASE_URI"].startswith("postgresql")

        for exp in active_experiments:
            register_experiment_database(app, exp.idexp, exp.db_name)
            bind_key = get_db_bind_key_for_exp(exp.idexp)

            # Ensure any new db_exp tables exist in the experiment DB.
            exp_uri = app.config["SQLALCHEMY_BINDS"].get(bind_key)
            if exp_uri:
                original_db_exp = app.config["SQLALCHEMY_BINDS"].get("db_exp")
                app.config["SQLALCHEMY_BINDS"]["db_exp"] = exp_uri
                try:
                    db.create_all(bind="db_exp")
                finally:
                    if original_db_exp is not None:
                        app.config["SQLALCHEMY_BINDS"]["db_exp"] = original_db_exp

                # For SQLite experiment DBs, run local schema migration for post.created_at.
                if not is_postgresql and exp_uri.startswith("sqlite:///"):
                    try:
                        from y_web.migrations.add_comment_dedupe_columns import (
                            migrate_sqlite_comment_dedupe_columns,
                        )
                        from y_web.migrations.add_post_created_at_column import (
                            migrate_sqlite_experiment_db,
                        )

                        migrate_sqlite_experiment_db(exp_uri)
                        migrate_sqlite_comment_dedupe_columns(exp_uri)
                    except Exception as e:
                        print(
                            f"Warning: SQLite post schema migration failed for experiment {exp.idexp}: {e}"
                        )

            # For PostgreSQL, run schema migration to ensure all columns exist
            if is_postgresql:
                try:
                    from urllib.parse import urlparse

                    from y_web.migrations.ensure_postgresql_schema import (
                        migrate_server_db,
                    )

                    parsed_uri = urlparse(app.config["SQLALCHEMY_DATABASE_URI"])
                    pg_host = parsed_uri.hostname or "localhost"
                    pg_port = str(parsed_uri.port or 5432)
                    pg_user = parsed_uri.username or "postgres"
                    pg_password = parsed_uri.password or ""

                    if pg_password:
                        migrate_server_db(
                            pg_host, pg_port, exp.db_name, pg_user, pg_password
                        )
                except Exception as e:
                    print(
                        f"Warning: PostgreSQL schema migration failed for experiment {exp.idexp}: {e}"
                    )
