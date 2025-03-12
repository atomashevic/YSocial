from flask_login import UserMixin
from pygments.lexer import default

from . import db


class User_mgmt(UserMixin, db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(15), nullable=False, unique=True)
    email = db.Column(db.String(50), nullable=False, unique=True)
    password = db.Column(db.String(80), nullable=False)
    leaning = db.Column(db.String(10), default="neutral")
    user_type = db.Column(db.String(10), nullable=False, default="user")
    age = db.Column(db.Integer, default=0)
    oe = db.Column(db.String(50))
    co = db.Column(db.String(50))
    ex = db.Column(db.String(50))
    ag = db.Column(db.String(50))
    ne = db.Column(db.String(50))
    recsys_type = db.Column(db.String(50), default="default")
    frecsys_type = db.Column(db.String(50), default="default")
    language = db.Column(db.String(10), default="en")
    owner = db.Column(db.String(10), default=None)
    education_level = db.Column(db.String(10), default=None)
    joined_on = db.Column(db.Integer, nullable=False)
    gender = db.Column(db.String(10), default=None)
    nationality = db.Column(db.String(15), default=None)
    round_actions = db.Column(db.Integer, default=3)
    toxicity = db.Column(db.String(10), default="no")
    is_page = db.Column(db.Integer, default=0)
    left_on = db.Column(db.Integer, default=None)
    daily_activity_level = db.Column(db.Integer(), default=1)
    profession = db.Column(db.String(50), default="")

    posts = db.relationship("Post", backref="author", lazy=True)
    liked = db.relationship("Reactions", backref="liked_by", lazy=True)


class Post(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    tweet = db.Column(db.String(500), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    post_img = db.Column(db.String(20))
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    comment_to = db.Column(db.Integer, default=-1)
    thread_id = db.Column(db.Integer)
    news_id = db.Column(db.String(50), db.ForeignKey("articles.id"), default=None)
    image_id = db.Column(db.Integer(), db.ForeignKey("images.id"), default=None)
    shared_from = db.Column(db.Integer, default=-1)


class Hashtags(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    hashtag = db.Column(db.String(20), nullable=False)


class Emotions(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    emotion = db.Column(db.String(20), nullable=False)
    icon = db.Column(db.String(20), nullable=False)


class Post_emotions(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    emotion_id = db.Column(db.Integer, db.ForeignKey("emotions.id"), nullable=False)


class Post_hashtags(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    hashtag_id = db.Column(db.Integer, db.ForeignKey("hashtags.id"), nullable=False)


class Mentions(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    answered = db.Column(db.Integer, default=0)


class Reactions(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    round = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    type = db.Column(db.String(10), nullable=False)


class Follow(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    follower_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(10), nullable=False)


class Rounds(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Integer, nullable=False)
    hour = db.Column(db.Integer, nullable=False)


class Recommendations(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    post_ids = db.Column(db.String(500), nullable=False)
    round = db.Column(db.Integer, nullable=False)


class Articles(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    summary = db.Column(db.String(500), nullable=False)
    website_id = db.Column(db.Integer, db.ForeignKey("websites.id"), nullable=False)
    link = db.Column(db.String(200), nullable=False)
    fetched_on = db.Column(db.Integer, nullable=False)


class Websites(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    rss = db.Column(db.String(200), nullable=False)
    leaning = db.Column(db.String(10), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    last_fetched = db.Column(db.Integer, nullable=False)
    language = db.Column(db.String(10), nullable=False)
    country = db.Column(db.String(10), nullable=False)


class Voting(db.Model):
    __bind_key__ = "db_exp"
    vid = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    preference = db.Column(db.String(10), nullable=False)
    content_type = db.Column(db.String(10), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    round = db.Column(db.Integer, nullable=False)


class Interests(db.Model):
    __bind_key__ = "db_exp"
    iid = db.Column(db.Integer, primary_key=True)
    interest = db.Column(db.String(20), nullable=False)


class User_interest(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    interest_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)
    round_id = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)


class Post_topics(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)


class Images(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(200), nullable=True)
    description = db.Column(db.String(400), nullable=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=True)


class Article_topics(db.Model):
    __bind_key__ = "db_exp"
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("articles.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)


class Post_Sentiment(db.Model):
    __bind_key__ = "db_exp"
    __tablename__ = "post_sentiment"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_mgmt.id"), nullable=False)
    round = db.Column(db.Integer, db.ForeignKey("rounds.id"), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey("interests.iid"), nullable=False)
    is_post = db.Column(db.Integer, default=0)
    is_comment = db.Column(db.Integer, default=0)
    is_reaction = db.Column(db.Integer, default=0)
    neg = db.Column(db.REAL)
    neu = db.Column(db.REAL)
    pos = db.Column(db.REAL)
    compound = db.Column(db.REAL)
    sentiment_parent = db.Column(db.String(5), default="")


class Post_Toxicity(db.Model):
    __bind_key__ = "db_exp"
    __tablename__ = "post_toxicity"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("post.id"), nullable=False)
    toxicity = db.Column(db.REAL, default=0)
    severe_toxicity = db.Column(db.REAL, default=0)
    identity_attack = db.Column(db.REAL, default=0)
    insult = db.Column(db.REAL, default=0)
    profanity = db.Column(db.REAL, default=0)
    threat = db.Column(db.REAL, default=0)
    sexually_explicit = db.Column(db.REAL, default=0)
    flirtation = db.Column(db.REAL, default=0)


############################################################################################################


class Admin_users(UserMixin, db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "admin_users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(15), nullable=False, unique=True)
    email = db.Column(db.String(50), nullable=False, unique=True)
    password = db.Column(db.String(80), nullable=False)
    last_seen = db.Column(db.String(30), nullable=False)
    role = db.Column(db.String(10), nullable=False)
    llm = db.Column(db.String(50), default="")
    profile_pic = db.Column(db.String(400), default="")
    perspective_api = db.Column(db.String(300), default=None)


class Exps(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "exps"
    idexp = db.Column(db.Integer, primary_key=True)
    exp_name = db.Column(db.String(50), nullable=False)
    db_name = db.Column(db.String(50), nullable=False)
    owner = db.Column(db.String(50), nullable=False)
    exp_descr = db.Column(db.String(200), nullable=False)
    status = db.Column(db.Integer, nullable=False)
    running = db.Column(db.Integer, nullable=False, default=0)
    port = db.Column(db.Integer, nullable=False)
    server = db.Column(db.String(50), nullable=False, default="127.0.0.1")


class Exp_stats(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "exp_stats"
    id = db.Column(db.Integer, primary_key=True)
    exp_id = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)
    rounds = db.Column(db.Integer, nullable=False)
    agents = db.Column(db.Integer, nullable=False)
    posts = db.Column(db.Integer, nullable=False)
    reactions = db.Column(db.Integer, nullable=False)
    mentions = db.Column(db.Integer, nullable=False)


class Population(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "population"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    descr = db.Column(db.String(200), nullable=False)
    size = db.Column(db.Integer)
    llm = db.Column(db.String(50))
    age_min = db.Column(db.Integer)
    age_max = db.Column(db.Integer)
    education = db.Column(db.String(100))
    leanings = db.Column(db.String(200))
    nationalities = db.Column(db.String(200))
    interests = db.Column(db.String(300))
    toxicity = db.Column(db.String(50))
    languages = db.Column(db.String(100))
    crecsys = db.Column(db.String(50))
    frecsys = db.Column(db.String(50))


class Agent(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "agents"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    ag_type = db.Column(db.String(50), nullable=False)
    gender = db.Column(db.String(10))
    leaning = db.Column(db.String(50))
    age = db.Column(db.Integer)
    education_level = db.Column(db.String(50))
    interests = db.Column(db.String(200))
    oe = db.Column(db.String(50))
    co = db.Column(db.String(50))
    ex = db.Column(db.String(50))
    ag = db.Column(db.String(50))
    ne = db.Column(db.String(50))
    language = db.Column(db.String(10))
    toxicity = db.Column(db.String(50))
    round_actions = db.Column(db.String(50))
    nationality = db.Column(db.String(50))
    crecsys = db.Column(db.String(50))
    frecsys = db.Column(db.String(50))
    profile_pic = db.Column(db.String(400), default="")
    daily_activity_level = db.Column(db.Integer, default=1)
    profession = db.Column(db.String(50), default="")


class Agent_Population(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "agent_population"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=False)
    population_id = db.Column(
        db.Integer, db.ForeignKey("population.id"), nullable=False
    )


class Agent_Profile(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "agent_profile"
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agents.id"), nullable=False)
    profile = db.Column(db.String(300))


class Page(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "pages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    descr = db.Column(db.String(200))
    page_type = db.Column(db.String(50), nullable=False)
    feed = db.Column(db.String(200))
    keywords = db.Column(db.String(200))
    logo = db.Column(db.String(300))
    pg_type = db.Column(db.String(100))
    leaning = db.Column(db.String(50), default="")


class Population_Experiment(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "population_experiment"
    id = db.Column(db.Integer, primary_key=True)
    id_population = db.Column(
        db.Integer, db.ForeignKey("population.id"), nullable=False
    )
    id_exp = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)


class Page_Population(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "page_population"
    id = db.Column(db.Integer, primary_key=True)
    page_id = db.Column(db.Integer, db.ForeignKey("pages.id"), nullable=False)
    population_id = db.Column(
        db.Integer, db.ForeignKey("population.id"), nullable=False
    )


class User_Experiment(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "user_experiment"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("admin_users.id"), nullable=False)
    exp_id = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)


class Client(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "client"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    descr = db.Column(db.String(200))
    days = db.Column(db.Integer)
    percentage_new_agents_iteration = db.Column(db.REAL)
    percentage_removed_agents_iteration = db.Column(db.REAL)
    max_length_thread_reading = db.Column(db.Integer)
    reading_from_follower_ratio = db.Column(db.REAL)
    probability_of_daily_follow = db.Column(db.REAL)
    attention_window = db.Column(db.Integer)
    visibility_rounds = db.Column(db.Integer)
    post = db.Column(db.REAL)
    share = db.Column(db.REAL)
    image = db.Column(db.REAL)
    comment = db.Column(db.REAL)
    read = db.Column(db.REAL)
    news = db.Column(db.REAL)
    search = db.Column(db.REAL)
    vote = db.Column(db.REAL)
    llm = db.Column(db.String(100))
    llm_api_key = db.Column(db.String(300))
    llm_max_tokens = db.Column(db.Integer)
    llm_temperature = db.Column(db.REAL)
    llm_v_agent = db.Column(db.String(100))
    llm_v = db.Column(db.String(100))
    llm_v_api_key = db.Column(db.String(300))
    llm_v_max_tokens = db.Column(db.Integer)
    llm_v_temperature = db.Column(db.REAL)
    status = db.Column(db.Integer, nullable=False, default=0)
    id_exp = db.Column(db.Integer, db.ForeignKey("exps.idexp"), nullable=False)
    population_id = db.Column(
        db.Integer, db.ForeignKey("population.id"), nullable=False
    )
    network_type = db.Column(db.String(50), default="")


class Client_Execution(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "client_execution"
    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("client.id"), nullable=False)
    elapsed_time = db.Column(db.Integer, default=0)
    expected_duration_rounds = db.Column(db.Integer, default=0)
    last_active_hour = db.Column(db.Integer, default=-1)
    last_active_day = db.Column(db.Integer, default=-1)


class Ollama_Pull(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "ollama_pull"
    id = db.Column(db.Integer, primary_key=True)
    model_name = db.Column(db.String(50), nullable=False)
    status = db.Column(db.REAL, nullable=False, default=0)


class Profession(db.Model):
    __bind__ = "db_admin"
    __tablename__ = "professions"
    id = db.Column(db.Integer, primary_key=True)
    profession = db.Column(db.String(50), nullable=False)
    background = db.Column(db.String(200), nullable=False)


class Nationalities(db.Model):
    __bind__ = "db_admin"
    __tablename__ = "nationalities"
    id = db.Column(db.Integer, primary_key=True)
    nationality = db.Column(db.String(50), nullable=False)


class Education(db.Model):
    __bind__ = "db_admin"
    __tablename__ = "education"
    id = db.Column(db.Integer, primary_key=True)
    education_level = db.Column(db.String(50), nullable=False)


class Leanings(db.Model):
    __bind__ = "db_admin"
    __tablename__ = "leanings"
    id = db.Column(db.Integer, primary_key=True)
    leaning = db.Column(db.String(50), nullable=False)


class Languages(db.Model):
    __bind__ = "db_admin"
    __tablename__ = "languages"
    id = db.Column(db.Integer, primary_key=True)
    language = db.Column(db.String(50), nullable=False)


class Content_Recsys(db.Model):
    __bind__ = "db_admin"
    __tablename__ = "content_recsys"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(500), nullable=False)


class Follow_Recsys(db.Model):
    __bind__ = "db_admin"
    __tablename__ = "follow_recsys"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    value = db.Column(db.String(500), nullable=False)