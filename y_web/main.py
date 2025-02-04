from flask import Blueprint, render_template, redirect, request, flash
from flask_login import login_required, current_user
from .data_access import *
from .models import Admin_users, Images, Page
from werkzeug.security import generate_password_hash
from y_web import db
from y_web.recsys_support import get_suggested_posts, get_suggested_users

main = Blueprint("main", __name__)


def is_admin(username):
    user = Admin_users.query.filter_by(username=username).first()
    if user.role != "admin":
        return False
    return True


@main.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(f"/feed/{current_user.id}/feed/rf/1")
    return render_template("login.html")


@main.get("/profile")
@login_required
def profile():
    user_id = current_user.id
    return redirect(f"/profile/{user_id}/rf/1")


@main.get("/profile/<int:user_id>/<string:mode>/<int:page>")
@login_required
def profile_logged(user_id, page=1, mode="recent"):
    user_id = int(user_id)
    user = User_mgmt.query.filter_by(id=user_id).first()

    # check if the logged user is following the user
    is_following = (
        Follow.query.filter_by(follower_id=user_id, user_id=current_user.id)
        .group_by(Follow.follower_id)
        .having(func.count(Follow.user_id) % 2 == 1)
    ).all()

    if len(is_following) == 0:
        is_following = False
    else:
        is_following = True

    # get user total number of posts
    total_posts = len(list(Post.query.filter_by(user_id=user_id, comment_to=-1)))

    # get user total number of comments
    total_comments = len(
        list(Post.query.filter_by(user_id=user_id).filter(Post.comment_to != -1))
    )

    # get user total number of likes
    total_likes = len(list(Reactions.query.filter_by(user_id=user_id, type="like")))

    # get user total number of dislikes
    total_dislikes = len(
        list(Reactions.query.filter_by(user_id=user_id, type="dislike"))
    )

    # get user total number of articles shared
    total_articles = len(
        list(Post.query.filter_by(user_id=user_id).filter(Post.news_id.isnot(None)))
    )

    # get the hashtag used by the user
    hashtags = (
        (
            (
                Post_hashtags.query.join(
                    Hashtags, Post_hashtags.hashtag_id == Hashtags.id
                )
            )
            .join(Post, Post_hashtags.post_id == Post.id)
            .filter_by(user_id=user_id)
            .add_columns(Hashtags.hashtag)
        )
        .add_columns(func.count(Post_hashtags.hashtag_id).label("count"))
        .group_by(Hashtags.id)
        .order_by(desc("count"))
        .limit(10)
    ).all()

    most_used_hashtags = [(h[0].hashtag_id, h[1], h[2]) for h in hashtags]

    emotions = (
        (
            (
                Post_emotions.query.join(
                    Emotions, Post_emotions.emotion_id == Emotions.id
                )
            )
            .join(Post, Post_emotions.post_id == Post.id)
            .filter_by(user_id=user_id)
            .add_columns(Emotions.emotion)
        )
        .add_columns(func.count(Post_emotions.emotion_id).label("count"))
        .group_by(Emotions.id)
        .order_by(desc("count"))
        .limit(10)
        .all()
    )

    most_used_emotions = [(h[0].emotion_id, h[1], h[2]) for h in emotions]

    # get user total number of followers
    total_followee = len(
        list(
            Follow.query.filter_by(user_id=user_id)
            .group_by(Follow.follower_id)
            .having(func.count(Follow.follower_id) % 2 == 1)
        )
    )

    # get user total followee
    total_followers = len(
        list(
            Follow.query.filter_by(follower_id=user_id)
            .group_by(Follow.user_id)
            .having(func.count(Follow.user_id) % 2 == 1)
        )
    )

    res = {
        "user_data": user,
        "total_posts": total_posts,
        "total_comments": total_comments,
        "total_likes": total_likes,
        "total_dislikes": total_dislikes,
        "total_articles": total_articles,
        "most_used_hashtags": most_used_hashtags,
        "most_used_emotions": most_used_emotions,
        "total_followers": total_followers,
        "total_followee": total_followee,
    }

    rp = get_user_recent_posts(user_id, page, 10, mode, current_user.id)
    mutual_friends = get_mutual_friends(user_id, current_user.id)
    hashtags = get_top_user_hashtags(user_id, 5)
    interests = get_user_recent_interests(user_id, 5)

    mentions = get_unanswered_mentions(current_user.id)

    profile_pic = ""

    # is the agent a page?
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if page is not None:
            profile_pic = pg.logo
    else:
        ag = Agent.query.filter_by(name=user.username).first()
        profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""

    return render_template(
        "profile.html",
        profile_pic=profile_pic,
        is_page=user.is_page,
        user=res,
        enumerate=enumerate,
        username=user.username,
        items=rp,
        len=len,
        mutual=mutual_friends,
        page=page,
        mode=mode,
        user_id=int(user_id),
        logged_username=current_user.username,
        hashtags=hashtags,
        str=str,
        logged_id=current_user.id,
        is_following=is_following,
        interests=interests,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
    )


@main.get("/edit_profile/<int:user_id>")
@login_required
def edit_profile(user_id):
    user = User_mgmt.query.filter_by(id=user_id).first()

    profile_pic = ""

    # is the agent a page?
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        ag = Agent.query.filter_by(name=user.username).first()
        profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""

    return render_template(
        "edit_profile.html",
        user=user,
        profile_pic=profile_pic,
        is_page=user.is_page,
        enumerate=enumerate,
        username=user.username,
        len=len,
        user_id=int(user_id),
        logged_username=current_user.username,
        str=str,
        logged_id=current_user.id,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.route("/update_profile_data/<int:user_id>", methods=["POST"])
@login_required
def update_profile_data(user_id):
    user = User_mgmt.query.filter_by(id=user_id).first()

    user.email = request.form.get("email")
    user.gender = request.form.get("gender")
    user.nationality = request.form.get("nationality")
    user.language = request.form.get("language")
    user.leaning = request.form.get("leaning")
    user.education_level = request.form.get("education_level")
    user.recsys_type = request.form.get("recsys_type")
    user.frecsys_type = request.form.get("frecsys_type")
    user.age = int(request.form.get("age"))
    # profile_pic = request.form.get("profile_pic")

    db.session.commit()

    return redirect(request.referrer)


@main.route("/update_password/<int:user_id>", methods=["POST"])
@login_required
def update_password(user_id):
    user = User_mgmt.query.filter_by(id=user_id).first()

    npassword = request.form.get("new_password")
    npassword2 = request.form.get("new_password2")

    if npassword != npassword2:
        # return an error message
        flash("The provided passwords do not match.")
        return redirect(request.referrer)

    pwd = generate_password_hash(npassword, method="pbkdf2:sha256")
    user.password = pwd
    db.session.commit()

    return redirect(request.referrer)


@main.get("/feed")
@login_required
def feeed_logged():
    user_id = current_user.id
    return redirect(f"/feed/{user_id}/feed/rf/1")


@main.get("/feed/<string:user_id>/<string:timeline>/<string:mode>/<int:page>")
@login_required
def feed(user_id="all", timeline="timeline", mode="rf", page=1):
    if page < 1:
        page = 1

    max_post_per_page = 10
    username = ""
    posts, additional = None, None

    if user_id == "all":
        posts, additional = get_suggested_posts("all", "", page, max_post_per_page)

    elif user_id != "all":

        user = User_mgmt.query.filter_by(id=int(user_id)).first()
        recsys = user.recsys_type

        posts, additional = get_suggested_posts(user_id, recsys, page, max_post_per_page)
        username = user.username

    res, res_additional = [], []

    if posts is not None:
        res = __get_discussions(posts, username, page)
    if additional is not None:
        res_additional = __get_discussions(additional, username, page)

    # combine the posts and additional posts
    if len(res_additional) > 0:
        for add in res_additional:
            res.append(add)

    # not enough posts to display
    if len(res) == 0 and page > 1:
        return redirect(f"/feed/{user_id}/{timeline}/{mode}/{page - 1}")

    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(current_user.id)
    sfollow = get_suggested_users(user_id)

    # get user profile pic
    if user_id != "all":
        user = User_mgmt.query.filter_by(id=user_id).first()
    else:
        user = User_mgmt.query.filter_by(id=current_user.id).first()

    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""
        except:
            profile_pic = ""

    return render_template(
        "feed.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        user_id=user_id,
        timeline=timeline,
        username=username,
        mode=mode,
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        logged_id=current_user.id,
        trending_ht=trending_ht,
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
        sfollow=sfollow,
    )


@main.get("/hashtag_posts/<int:hashtag_id>/<int:page>")
@login_required
def get_post_hashtags(hashtag_id, page=1):
    res = get_posts_associated_to_hashtags(
        hashtag_id, page, per_page=10, current_user=current_user.id
    )

    if len(res) == 0:
        return redirect(f"/hashtag_posts/{hashtag_id}/{page - 1}")

    # get hashtag name
    hashtag = Hashtags.query.filter_by(id=hashtag_id).first().hashtag

    trending_ht = get_trending_hashtags()

    # get user profile pic
    user = User_mgmt.query.filter_by(id=current_user.id).first()
    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""
        except:
            profile_pic = ""

    return render_template(
        "hashtag.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        username=current_user.username,
        user_id=int(current_user.id),
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_ht,
        logged_id=int(current_user.id),
        hashtag_id=hashtag_id,
        current_hashtag=hashtag,
        str=str,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.get("/interest/<int:interest_id>/<int:page>")
@login_required
def get_post_interest(interest_id, page=1):
    res = get_posts_associated_to_interest(
        interest_id, page, per_page=10, current_user=current_user.id
    )

    if len(res) == 0:
        return redirect(f"/interest/{interest_id}/{page - 1}")

    # get topic name
    interest = Interests.query.filter_by(iid=interest_id).first().interest

    trending_tp = get_trending_topics()

    # get user profile pic
    user = User_mgmt.query.filter_by(id=current_user.id).first()
    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""
        except:
            profile_pic = ""

    return render_template(
        "interest.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        username=current_user.username,
        user_id=int(current_user.id),
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_tp,
        logged_id=int(current_user.id),
        interest_id=interest_id,
        current_interest=interest,
        str=str,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.get("/emotion/<int:emotion_id>/<int:page>")
@login_required
def get_post_emotion(emotion_id, page=1):
    res = get_posts_associated_to_emotion(
        emotion_id, page, per_page=10, current_user=current_user.id
    )

    if len(res) == 0:
        return redirect(f"/emotion/{emotion_id}/{page - 1}")

    # get emotion name
    emotion = Emotions.query.filter_by(id=emotion_id).first()
    emotion = (emotion_id, emotion.emotion, emotion.icon)

    trending_tp = get_trending_emotions()

    # get user profile pic
    user = User_mgmt.query.filter_by(id=current_user.id).first()
    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""
        except:
            profile_pic = ""

    return render_template(
        "emotions.html",
        items=res,
        page=page,
        profile_pic=profile_pic,
        username=current_user.username,
        user_id=int(current_user.id),
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_tp,
        logged_id=int(current_user.id),
        emotion_id=emotion_id,
        current_emotion=emotion,
        str=str,
        bool=bool,
        is_admin=is_admin(current_user.username),
    )


@main.get("/friends/<int:user_id>/<int:page>")
@login_required
def get_friends(user_id, page=1):
    followers, followees, number_followers, number_followees = get_user_friends(
        user_id, limit=12, page=page
    )
    mentions = get_unanswered_mentions(current_user.id)

    profile_pic_follower = {}

    for f in followers:
        u = User_mgmt.query.filter_by(id=f['id']).first()

        if u.is_page == 1:
            pg = Page.query.filter_by(name=f['username']).first()
            if pg is not None:
                profile_pic_follower[f['id']] = pg.logo
        else:
            try:
                ag = Agent.query.filter_by(name=f['username']).first()
                profile_pic_follower[f['id']] = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""
            except:
                profile_pic_follower[f['id']] = ""

    profile_pic_followee = {}

    for f in followees:

        u = User_mgmt.query.filter_by(id=f['id']).first()

        if u.is_page == 1:
            pg = Page.query.filter_by(name=f['username']).first()
            if pg is not None:
                profile_pic_followee[f['id']] = pg.logo
        else:
            try:
                ag = Agent.query.filter_by(name=f['username']).first()
                profile_pic_followee[f['id']] = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""
            except:
                profile_pic_followee[f['id']] = ""

    return render_template(
        "friends.html",
        followers=followers,
        profile_pic_follower=profile_pic_follower,
        followees=followees,
        profile_pic_followee=profile_pic_followee,
        page=page,
        username=current_user.username,
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        logged_id=int(current_user.id),
        user_id=user_id,
        number_followers=number_followers,
        number_followees=number_followees,
        str=str,
        bool=bool,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
    )


@main.get("/thread/<int:post_id>")
@login_required
def get_thread(post_id):
    # get thread_id for post_id
    thread_id = Post.query.filter_by(id=post_id).first().thread_id

    # get all posts with the specified thread id
    posts = Post.query.filter_by(thread_id=thread_id).order_by(Post.id.asc()).all()

    root = posts[0].id

    c = Rounds.query.filter_by(id=posts[0].round).first()
    if c is None:
        day = "None"
        hour = "00"
    else:
        day = c.day
        hour = c.hour

    image = Images.query.filter_by(id=posts[0].image_id).first()

    discussion_tree = {
        "post": augment_text(posts[0].tweet),
        "image": image,
        "shared_from": -1 if posts[0].shared_from == -1 else (posts[0].shared_from, db.session.query(User_mgmt).join(Post, User_mgmt.id == Post.user_id).filter(Post.id == posts[0].shared_from).first().username),

        "post_id": posts[0].id,
        "author": User_mgmt.query.filter_by(id=posts[0].user_id).first().username,
        "author_id": posts[0].user_id,
        "day": day,
        "hour": hour,
        posts[0].id: None,
        "children": [],
        "likes": len(
            list(Reactions.query.filter_by(post_id=posts[0].id, type="like").all())
        ),
        "dislikes": len(
            list(Reactions.query.filter_by(post_id=posts[0].id, type="dislike").all())
        ),
        "is_liked": Reactions.query.filter_by(
            post_id=posts[0].id, user_id=current_user.id, type="like"
        ).first()
        is None,
        "is_disliked": Reactions.query.filter_by(
            post_id=posts[0].id, user_id=current_user.id, type="dislike"
        ).first()
        is None,
        "is_shared": len(Post.query.filter_by(shared_from=posts[0].id).all()),
        "emotions": get_elicited_emotions(posts[0].id),
        "topics": get_topics(posts[0].id)
    }

    reverse_map = {posts[0].id: None}
    post_to_child = {posts[0].id: []}
    post_to_data = {posts[0].id: discussion_tree}

    for post in posts[1:]:
        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        data = {
            "post": augment_text(post.tweet),
            "post_id": post.id,
            "author": User_mgmt.query.filter_by(id=post.user_id).first().username,
            "author_id": post.user_id,
            post.id: None,
            "day": day,
            "hour": hour,
            "children": [],
            "likes": len(
                list(Reactions.query.filter_by(post_id=post.id, type="like").all())
            ),
            "dislikes": len(
                list(Reactions.query.filter_by(post_id=post.id, type="dislike").all())
            ),
            "is_liked": Reactions.query.filter_by(
                post_id=post.id, user_id=current_user.id, type="like"
            ).first()
            is None,
            "is_disliked": Reactions.query.filter_by(
                post_id=post.id, user_id=current_user.id, type="dislike"
            ).first()
            is None,
            "is_shared": len(Post.query.filter_by(shared_from=post.id).all()),
            "emotions": get_elicited_emotions(post.id),
            "topics": get_topics(post.id)
        }

        parent = post.comment_to
        reverse_map[post.id] = parent

        if parent != -1:
            if parent in post_to_child:
                post_to_child[parent].append(post.id)
                post_to_child[post.id] = []
                post_to_data[post.id] = data

    tree = __expand_tree(post_to_child, post_to_data)
    discussion_tree = tree[root]
    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(current_user.id)

    # get user profile pic
    user = User_mgmt.query.filter_by(id=current_user.id).first()
    profile_pic = ""
    if user.is_page == 1:
        pg = Page.query.filter_by(name=user.username).first()
        if pg is not None:
            profile_pic = pg.logo
    else:
        try:
            ag = Agent.query.filter_by(name=user.username).first()
            profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""
        except:
            profile_pic = ""

    return render_template(
        "thread.html",
        thread=discussion_tree,
        profile_pic=profile_pic,
        user_id= current_user.id,
        username=current_user.username,
        logged_username=current_user.username,
        logged_id=int(current_user.id),
        str=str,
        bool=bool,
        enumerate=enumerate,
        trending_ht=trending_ht,
        len=len,
        mentions=mentions,
        is_admin=is_admin(current_user.username),
    )


def __expand_tree(post_to_child, post_to_data):
    for pid, clds in post_to_child.items():
        for cl in clds:
            post_to_data[pid]["children"].append(post_to_data[cl])

    return post_to_data


def recursive_visit(data):
    if len(data["children"]) == 0:
        return data["post"]
    else:
        for c in data["children"]:
            return recursive_visit(c)


def __get_discussions(posts, username, page):

    res = []

    for post in posts.items:

        try:
            post = post[0]
        except:
            pass

        comments = (
            Post.query.filter(Post.thread_id == post.id, Post.id != post.id)
            .join(User_mgmt, Post.user_id == User_mgmt.id)
            .add_columns(User_mgmt.username)
            .all()
        )

        cms = []
        for c, author in comments:
            # get elicited emotions names
            emotions = get_elicited_emotions(c.id)

            if username == author:
                text = c.tweet.split(":")[-1].replace(f"@{username}", "")
            else:
                text = c.tweet.split(":")[-1]

            profile_pic = ""

            user = User_mgmt.query.filter_by(id=c.user_id).first()

            if user.is_page == 1:
                pg = Page.query.filter_by(name=user.username).first()
                if page is not None:
                    profile_pic = pg.logo
            else:
                ag = Agent.query.filter_by(name=user.username).first()
                profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else ""

            cms.append(
                {
                    "post_id": c.id,
                    "profile_pic": profile_pic,
                    "author": author,
                    "shared_from": -1 if c.shared_from == -1 else (c.shared_from, db.session.query(User_mgmt).join(Post, User_mgmt.id == Post.user_id).filter(Post.id == c.shared_from).first().username),
                    "author_id": int(c.user_id),
                    "post": augment_text(text),
                    "round": c.round,
                    "day": Rounds.query.filter_by(id=c.round).first().day,
                    "hour": Rounds.query.filter_by(id=c.round).first().hour,
                    "likes": len(
                        list(Reactions.query.filter_by(post_id=c.id, type="like"))
                    ),
                    "dislikes": len(
                        list(Reactions.query.filter_by(post_id=c.id, type="dislike"))
                    ),
                    "is_liked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user.id, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user.id, type="dislike"
                    ).first()
                    is None,
                    "is_shared": len(Post.query.filter_by(shared_from=c.id).all()),
                    "emotions": emotions,
                }
            )

        article = Articles.query.filter_by(id=post.news_id).first()
        if article is None:
            art = 0
        else:
            art = {
                "title": article.title,
                "summary": strip_tags(article.summary),
                "url": article.link,
                "source": Websites.query.filter_by(id=article.website_id).first().name,
            }

        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        # get elicited emotions names
        emotions = get_elicited_emotions(post.id)

        aa = User_mgmt.query.filter_by(id=post.user_id).first()
        profile_pic = ""
        if aa.is_page == 1:
            pg = Page.query.filter_by(name=aa.username).first()
            if pg is not None:
                profile_pic = pg.logo
        else:
            try:
                ag = Agent.query.filter_by(name=aa.username).first()
                profile_pic = ag.profile_pic if ag.profile_pic is not None else ""
            except:
                profile_pic = ""

        # get the post.shared_from

        res.append(
            {
                "article": art,
                "image": image,
                "profile_pic": profile_pic,
                "thread_id": post.thread_id,
                "shared_from": -1 if post.shared_from == -1 else (post.shared_from, db.session.query(User_mgmt).join(Post, User_mgmt.id == Post.user_id).filter(Post.id == post.shared_from).first().username),
                "post_id": post.id,
                "author": User_mgmt.query.filter_by(id=post.user_id).first().username,
                "author_id": int(post.user_id),
                "post": augment_text(post.tweet.split(":")[-1]),
                "round": post.round,
                "day": day,
                "hour": hour,
                "likes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="like"))
                ),
                "dislikes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="dislike"))
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user.id, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user.id, type="dislike"
                ).first()
                is None,
                "is_shared": len(Post.query.filter_by(shared_from=post.id).all()),
                "comments": cms,
                "t_comments": len(cms),
                "emotions": emotions,
                "topics": get_topics(post.id)
            }
        )

    return res