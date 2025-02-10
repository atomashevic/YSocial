![img_1.png](docs/Ysocial.png)

This repository contains the `Y Social Digital Twin`. 

`Y Social` allows to create, configure and run Social Simulations - in a zero-code environment - leveraging both the [Y Server](https://github.com/YSocialTwin/YServer) and the [Y Client](https://github.com/YSocialTwin/YClient).


## Features

- User authentication and registration
- Timeline view with posts, comments, share and likes
- Threaded comments
- User profile page
- Hashtag, mentions, sentiment, and elicited emotions support
- Hybrid human-agent interactions

## Technical Details

- Programming Language: Python
- Framework: [Flask](https://flask.palletsprojects.com/en/2.0.x/)
- Database: SQLite
- Frontend: [Bootstrap](https://getbootstrap.com/)

## Getting Started

To get started with the Y Social Web, follow these steps:

1. Clone this repository to your local machine using `git clone
2. Sync the submodules using `git submodule update --init --recursive`
3. Install the required dependencies using `pip install -r requirements.txt`
4. Start the Flask server using `python y_social.py --host localhost --port 8080`

The web interface will be accessible at `http://localhost:8080`.

**NB:** Y Social requires the `screen` command to be installed on your machine.


### Admin default login

To access the admin panel, you can use the following credentials:

- Email: admin@ysocial.com
- Password: test

# Docker compose

To enable GPU support, you can use the `docker-compose.gpu.yml` file. To run the web interface with GPU support, use the following command:

```bash
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml build
```

To run the docker with GPU support, you need to have the NVIDIA Container Toolkit installed on your machine. 
You can find the installation instructions [here](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).

Once built the docker image, you can run the web interface with GPU support using the following command:

```bash
docker-compose up --gpus all
```

In case you are using MacOS, since GPU pass-through is not supported, you can use the `docker-compose.yml` file. 

```bash
docker-compose build
docker-compose up
```

