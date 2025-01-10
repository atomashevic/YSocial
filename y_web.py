from y_web import app

def start_app(debug=True, port=8080, host="localhost"):
    """
    Start the app

    :param debug: turn on debug mode
    :param port: the port to run the app on
    :param host: the host to run the app on
    """
    app.run(debug=debug, port=port, host=host)


if __name__ == "__main__":
    start_app()

