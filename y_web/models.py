from flask_login import UserMixin
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


class Exps(db.Model):
    __bind_key__ = "db_admin"
    __tablename__ = "exps"
    idexp = db.Column(db.Integer, primary_key=True)
    exp_name = db.Column(db.String(50), nullable=False)
    db_name = db.Column(db.String(50), nullable=False)
    owner = db.Column(db.String(50), nullable=False)
    exp_descr = db.Column(db.String(200), nullable=False)
    status = db.Column(db.Integer, nullable=False)


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

