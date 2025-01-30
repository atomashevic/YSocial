from flask import Blueprint, render_template, redirect
from flask_login import login_required, current_user
from .data_access import *
from .models import Admin_users, Images

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

    return render_template(
        "profile.html",
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

    if user_id == "all":
        # get the latest 20 posts paginated along with their comments
        if mode == "rf":
            posts = (
                Post.query.filter_by(comment_to=-1)
                .order_by(desc(Post.id))
                .paginate(page=page, per_page=5)
            )
        if mode == "rfp":
            posts = (
                Post.query.filter_by(comment_to=-1)
                .join(Reactions, Post.id == Reactions.post_id)
                .add_columns(func.count(Reactions.id).label("count"))
                .group_by(Post.id)
                .order_by(desc("count"))
            ).paginate(page=page, per_page=5)

        username = ""
    elif user_id != "all":
        if timeline == "timeline":
            username = User_mgmt.query.filter_by(id=int(user_id)).first().username
            if mode == "rf":
                posts = (
                    Post.query.filter_by(user_id=int(user_id), comment_to=-1)
                    .order_by(desc(Post.id))
                    .paginate(page=page, per_page=5)
                )
            # @todo: fix this
            if mode == "rfp":
                posts = (
                    Post.query.filter_by(user_id=int(user_id), comment_to=-1)
                    .join(Reactions, Post.id == Reactions.post_id)
                    .add_columns(func.count(Reactions.id).label("count"))
                    .group_by(Post.id)
                    .order_by(desc("count"))
                ).paginate(page=page, per_page=5)
        else:
            # get users' followees
            username = User_mgmt.query.filter_by(id=int(user_id)).first().username

            # only get the posts of the followees that were not unfollowed
            followers = list(
                Follow.query.filter_by(user_id=int(user_id))
                .group_by(Follow.follower_id)
                .having(func.count(Follow.follower_id) % 2 == 1)
            )
            users = [f.follower_id for f in followers]
            users.append(user_id)

            if mode == "rf":
                # get the posts of the followee

                posts = (
                    Post.query.filter(
                        Post.user_id.in_(users),
                        Post.comment_to == -1,
                    )
                    .order_by(desc(Post.id))
                    .paginate(page=page, per_page=5)
                )

            if mode == "rfp":
                # get posts from followee ordered by likes and reverse chronologically
                posts = (
                    Post.query.filter(
                        Post.user_id.in_(users),
                        Post.comment_to == -1,
                    )
                    .join(Reactions, Post.id == Reactions.post_id)
                    .add_columns(func.count(Reactions.post_id).label("count"))
                    .group_by(Post.id)
                    .order_by(desc("count"))
                    .paginate(page=page, per_page=5)
                )

    res = []

    for post in posts.items:
        if mode != "rf":
            post = post[0]

        comments = (
            Post.query.filter_by(thread_id=post.id)
            .join(User_mgmt, Post.user_id == User_mgmt.id)
            .add_columns(User_mgmt.username)
            .all()
        )

        cms = []
        idx = 0
        for c, author in comments:
            if idx == 0:
                idx = 1
                continue

            # get elicited emotions names
            emotions = get_elicited_emotions(c.id)

            if username == author:
                text = c.tweet.split(":")[-1].replace(f"@{username}", "")
            else:
                text = c.tweet.split(":")[-1]

            cms.append(
                {
                    "post_id": c.id,
                    "author": author,
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

        res.append(
            {
                "article": art,
                "image": image,
                "thread_id": post.thread_id,
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
                "comments": cms,
                "t_comments": len(cms),
                "emotions": emotions,
            }
        )

    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(current_user.id)

    return render_template(
        "feed.html",
        items=res,
        page=page,
        user_id=int(user_id),
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
    )


@main.get("/hashtag_posts/<int:hashtag_id>/<int:page>")
@login_required
def get_post_hashtags(hashtag_id, page=1):
    res = get_posts_associated_to_hashtags(
        hashtag_id, page, per_page=10, current_user=current_user.id
    )

    # get hashtag name
    hashtag = Hashtags.query.filter_by(id=hashtag_id).first().hashtag

    trending_ht = get_trending_hashtags()

    return render_template(
        "hashtag.html",
        items=res,
        page=page,
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

    # get topic name
    interest = Interests.query.filter_by(iid=interest_id).first().interest

    trending_tp = get_trending_topics()

    return render_template(
        "interest.html",
        items=res,
        page=page,
        username=current_user.username,
        user_id=int(current_user.id),
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_tp,
        logged_id=int(current_user.id),
        hashtag_id=interest_id,
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

    # get emotion name
    emotion = Emotions.query.filter_by(id=emotion_id).first()
    emotion = (emotion_id, emotion.emotion, emotion.icon)

    trending_tp = get_trending_emotions()

    return render_template(
        "emotions.html",
        items=res,
        page=page,
        username=current_user.username,
        user_id=int(current_user.id),
        enumerate=enumerate,
        len=len,
        logged_username=current_user.username,
        trending_ht=trending_tp,
        logged_id=int(current_user.id),
        hashtag_id=emotion_id,
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

    return render_template(
        "friends.html",
        followers=followers,
        followees=followees,
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
        "emotions": get_elicited_emotions(posts[0].id),
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
            "emotions": get_elicited_emotions(post.id),
        }

        parent = post.comment_to
        reverse_map[post.id] = parent

        post_to_child[parent].append(post.id)
        post_to_child[post.id] = []
        post_to_data[post.id] = data

    tree = __expand_tree(post_to_child, post_to_data)
    discussion_tree = tree[root]
    trending_ht = get_trending_hashtags()
    mentions = get_unanswered_mentions(current_user.id)

    return render_template(
        "thread.html",
        thread=discussion_tree,
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
