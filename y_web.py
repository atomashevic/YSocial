from y_web import app, db


def start_app(debug=False, port=8080, host="localhost"):
    """
    Start the app

    :param debug: turn on debug mode
    :param port: the port to run the app on
    :param host: the host to run the app on
    """

    # unload all experiments
    from y_web.models import Exps
    # select all loaded experiments
    exps = Exps.query.filter_by(status=1).all()
    # stop all the experiments
    for exp in exps:
        exp.status = 0
    db.session.commit()



    app.run(debug=debug, port=port, host=host)


if __name__ == "__main__":
    start_app()
