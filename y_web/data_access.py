from .models import (
    Post,
    Post_hashtags,
    Mentions,
    Emotions,
    Post_emotions,
    Reactions,
    Follow,
    Articles,
    Websites,
    Rounds,
    Interests,
    User_interest,
    Post_topics,
    Images,
    Page,
    Agent, Admin_users
)
from sqlalchemy.sql.expression import func
from sqlalchemy import desc
from y_web.utils.text_utils import *
from y_web import db


def get_user_recent_posts(user_id, page, per_page=10, mode="rf", current_user=None):
    """

    :param db:
    :param user_id:
    :param page:
    :param per_page:
    :param mode:
    :return:
    """

    if page < 1:
        page = 1

    username = User_mgmt.query.filter_by(id=int(user_id)).first().username
    if mode == "recent":
        posts = (
            Post.query.filter_by(user_id=int(user_id), comment_to=-1).order_by(
                desc(Post.id)
            )
        ).paginate(page=page, per_page=per_page, error_out=False)
    elif mode == "comments":
        posts = (
            Post.query.filter(
                Post.user_id == int(user_id), Post.comment_to != -1
            ).order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)

    elif mode == "liked":
        # get posts liked by the user
        posts = (
            Post.query.join(Reactions, Reactions.post_id == Post.id)
            .filter(Reactions.type == "like", Reactions.user_id == int(user_id))
            .order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)

    elif mode == "disliked":
        posts = (
            Post.query.join(Reactions, Reactions.post_id == Post.id)
            .filter(Reactions.type == "dislike", Reactions.user_id == int(user_id))
            .order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)

    elif mode == "shares":

        # get all posts of user_id having shared_from is not -1
        posts = (
            Post.query.filter(Post.user_id == int(user_id), Post.shared_from != -1)
            .order_by(desc(Post.id))
        ).paginate(page=page, per_page=per_page, error_out=False)

    else:
        # get the user posts with the most reactions
        posts = (
            Post.query.filter_by(user_id=int(user_id), comment_to=-1)
            .join(Reactions, Post.id == Reactions.post_id)
            .add_columns(func.count(Reactions.id).label("count"))
            .group_by(Post.id)
            .order_by(desc("count"))
        ).paginate(page=page, per_page=per_page, error_out=False)

    res = []

    for post in posts.items:
        if mode not in ["recent", "comments", "liked", "disliked", "shares"]:
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

            user = User_mgmt.query.filter_by(username=author).first()
            # is the agent a page?
            profile_pic = ""
            if user.is_page == 1:
                page = Page.query.filter_by(name=user.username).first()
                if page is not None:
                    profile_pic = page.logo
            else:
                ag = Agent.query.filter_by(name=user.username).first()
                profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else Admin_users.query.filter_by(username=user.username).first().profile_pic

            cms.append(
                {
                    "post_id": c.id,
                    "author": author,
                    "profile_pic": profile_pic,
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
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
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

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        # get elicited emotions names

        emotions = get_elicited_emotions(post.id)
        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        # is the agent a page?
        author = User_mgmt.query.filter_by(id=post.user_id).first()

        profile_pic = ""
        if author.is_page == 1:
            page = Page.query.filter_by(name=author.username).first()
            if page is not None:
                profile_pic = page.logo
        else:
            ag = Agent.query.filter_by(name=author.username).first()
            profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else Admin_users.query.filter_by(username=author.username).first().profile_pic

        res.append(
            {
                "article": art,
                "image": image,
                "thread_id": post.thread_id,
                "shared_from": -1 if post.shared_from == -1 else (post.shared_from, db.session.query(User_mgmt).join(Post, User_mgmt.id == Post.user_id).filter(Post.id == post.shared_from).first().username),
                "post_id": post.id,
                "profile_pic": profile_pic,
                "author": User_mgmt.query.filter_by(id=post.user_id).first().username,
                "author_id": int(post.user_id),
                "post": augment_text(post.tweet.split(":")[-1]),
                "round": post.round,
                "day": day,
                "hour": hour,
                "likes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="like").all())
                ),
                "dislikes": len(
                    list(
                        Reactions.query.filter_by(post_id=post.id, type="dislike").all()
                    )
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="dislike"
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


def augment_text(text):
    """
    Augment the text by adding links to the mentions and hashtags.

    :param text: the text to augment
    :return: the augmented text
    """
    text = text.split("(")[0]

    # Extract the mentions and hashtags
    mentions = extract_components(text, c_type="mentions")
    hashtags = extract_components(text, c_type="hashtags")

    # Define the dictionary to store the mentioned users and used hashtags
    mentioned_users = {}
    used_hastag = {}

    # Get the mentioned user id
    for m in mentions:
        try:
            mentioned_users[m] = User_mgmt.query.filter_by(username=m[1:]).first().id
        except:
            pass

    # Get the used hashtag id
    for h in hashtags:
        try:
            used_hastag[h] = Hashtags.query.filter_by(hashtag=h).first().id
        except:
            pass

    # Replace the mentions and hashtags with the links
    for m, uid in mentioned_users.items():
        text = text.replace(m, f'<a href="/profile/{uid}/recent/1"> {m} </a>')

    for h, hid in used_hastag.items():
        text = text.replace(h, f'<a href="/hashtag_posts/{hid}/1"> {h} </a>')

    return text


def get_mutual_friends(user_a, user_b, limit=10):
    """
    Get the mutual friends between two users.
    :param user_a:
    :param user_b:
    :param limit:
    :return:
    """
    # Get the friends of the two users
    friends_a = Follow.query.filter_by(user_id=user_a, action="follow").distinct()
    friends_b = Follow.query.filter_by(user_id=user_b, action="follow").distinct()

    # Get the mutual friends
    mutual_friends = []
    for f_a in friends_a:
        for f_b in friends_b:
            if f_a.follower_id == f_b.follower_id:
                mutual_friends.append(f_a.follower_id)

    res = []
    for uid in mutual_friends[:limit]:
        user = User_mgmt.query.filter_by(id=uid).first()
        res.append({"id": user.id, "username": user.username})

    return res


def get_top_user_hashtags(user_id, limit=10):
    """
    Get the top hashtags used by the user.
    :param user_id:
    :param limit:
    :return:
    """

    ht = (
        Post.query.filter_by(user_id=user_id)
        .join(Post_hashtags, Post.id == Post_hashtags.post_id)
        .join(Hashtags, Post_hashtags.hashtag_id == Hashtags.id)
        .add_columns(Hashtags.hashtag)
        .group_by(Hashtags.hashtag)
        .add_columns(func.count(Post_hashtags.hashtag_id))
        .order_by(desc(func.count(Post_hashtags.hashtag_id)))
        .limit(limit)
    ).all()

    ht = [
        {
            "hashtag": h[1],
            "count": h[2],
            "id": Hashtags.query.filter_by(hashtag=h[1]).first().id,
        }
        for h in ht
    ]

    return ht


def get_user_friends(user_id, limit=12, page=1):
    """
    Get the followers of the user.
    :param user_id:
    :param limit:
    :param page:
    :return:
    """

    if page < 1:
        page = 1

    # get number
    number_followees = len(
        list(
            Follow.query.filter(Follow.user_id==user_id, Follow.follower_id != user_id)
            .group_by(Follow.follower_id)
            .having(func.count(Follow.follower_id) % 2 == 1)
        )
    )
    number_followers = len(
        list(
            Follow.query.filter(Follow.follower_id==user_id, Follow.user_id != user_id)
            .group_by(Follow.user_id)
            .having(func.count(Follow.user_id) % 2 == 1)
        )
    )

    followee_list = []
    followers_list = []

    if (
        number_followers - page * limit < -limit
        and number_followees - page * limit < -limit
    ):
        return get_user_friends(user_id, limit=12, page=page - 1)

    if page * limit - number_followees < limit:
        followee = (
            Follow.query.filter(Follow.user_id==user_id, Follow.follower_id != user_id)
            .group_by(Follow.follower_id)
            .having(func.count(Follow.follower_id) % 2 == 1)
            .join(User_mgmt, Follow.follower_id == User_mgmt.id)
            .add_columns(User_mgmt.username, User_mgmt.id)
            .paginate(page=page, per_page=limit, error_out=False)
        )

        for f in followee.items:
            followee_list.append(
                {
                    "id": f.id,
                    "username": f.username,
                    "number_reactions": len(
                        list(Reactions.query.filter_by(user_id=f.id))
                    ),
                    "number_followers": len(
                        list(Follow.query.filter(Follow.follower_id == f.id, Follow.user_id != f.id).group_by(Follow.user_id).having(func.count(Follow.user_id) % 2 == 1))
                    ),
                    "number_followees": len(
                        list(Follow.query.filter(Follow.user_id == f.id, Follow.follower_id != f.id).group_by(Follow.follower_id).having(func.count(Follow.follower_id) % 2 == 1))
                    ),
                }
            )

    if number_followers - page * limit < limit:
        followers = (
            Follow.query.filter(Follow.follower_id==user_id, Follow.user_id != user_id)
            .group_by(Follow.user_id)
            .having(func.count(Follow.follower_id) % 2 == 1)
            .join(User_mgmt, Follow.user_id == User_mgmt.id)
            .add_columns(User_mgmt.username, User_mgmt.id)
            .paginate(page=page, per_page=limit, error_out=False)
        )

        for f in followers.items:
            followers_list.append(
                {
                    "id": f.id,
                    "username": f.username,
                    "number_reactions": len(
                        list(Reactions.query.filter_by(user_id=f.id))
                    ),
                    "number_followers": len(
                        list(Follow.query.filter(Follow.follower_id == f.id, Follow.user_id != f.id).group_by(Follow.user_id).having(func.count(Follow.user_id) % 2 == 1))
                    ),
                    "number_followees": len(
                        list(Follow.query.filter(Follow.user_id == f.id, Follow.follower_id != f.id).group_by(Follow.follower_id).having(func.count(Follow.follower_id) % 2 == 1))
                    ),
                }
            )

    return followers_list, followee_list, number_followers, number_followees


def get_trending_emotions(limit=10, window=24):
    """
    Get the trending emotions.
    :param limit:
    :return:
    """

    # get current round
    last_round = Rounds.query.order_by(desc(Rounds.id)).first()

    if last_round is not None:
        last_round = last_round.id
    else:
        last_round = 0

    # get the trending emotions
    em = (
        Post.query.join(Post_emotions, Post.id == Post_emotions.post_id)
        .filter(Post.round >= last_round - window)
        .join(Emotions, Post_emotions.emotion_id == Emotions.id)
        .add_columns(Emotions.emotion)
        .group_by(Emotions.emotion)
        .add_columns(func.count(Post_emotions.emotion_id))
        .add_columns(Emotions.id)
        .order_by(desc(func.count(Post_emotions.emotion_id)))
        .limit(limit)
    ).all()

    em = [{"emotion": e[1], "count": e[2], "id": e[3]} for e in em]

    return em


def get_trending_hashtags(limit=10, window=24):
    """
    Get the trending hashtags.
    :param limit:
    :return:
    """

    # get current round

    last_round = Rounds.query.order_by(desc(Rounds.id)).first()
    if last_round is not None:
        last_round = last_round.id
    else:
        last_round = 0

    ht = (
        Post.query.join(Post_hashtags, Post.id == Post_hashtags.post_id)
        .filter(Post.round >= last_round - window)
        .join(Hashtags, Post_hashtags.hashtag_id == Hashtags.id)
        .add_columns(Hashtags.hashtag)
        .group_by(Hashtags.hashtag)
        .add_columns(func.count(Post_hashtags.hashtag_id))
        .order_by(desc(func.count(Post_hashtags.hashtag_id)))
        .limit(limit)
    ).all()

    ht = [
        {
            "hashtag": h[1],
            "count": h[2],
            "id": Hashtags.query.filter_by(hashtag=h[1]).first().id,
        }
        for h in ht
    ]

    return ht


def get_trending_topics(limit=10, window=24):
    # get current round
    last_round = Rounds.query.order_by(desc(Rounds.id)).first()
    if last_round is not None:
        last_round = last_round.id
    else:
        last_round = 0

    # get the trending topics
    tp = (
        Post.query.join(Post_topics, Post.id == Post_topics.post_id)
        .filter(Post.round >= last_round - window)
        .join(Interests, Post_topics.topic_id == Interests.iid)
        .add_columns(Interests.interest)
        .group_by(Interests.interest)
        .add_columns(func.count(Post_topics.topic_id))
        .order_by(desc(func.count(Post_topics.topic_id)))
        .limit(limit)
    ).all()

    tp = [
        {
            "topic": t[1],
            "count": t[2],
            "id": Interests.query.filter_by(interest=t[1]).first().iid,
        }
        for t in tp
    ]

    # ht = [{"hashtag": h[1], "count": h[2], "id": Hashtags.query.filter_by(hashtag=h[1]).first().id} for h in ht]
    return tp


def get_posts_associated_to_hashtags(hashtag_id, page, per_page=10, current_user=None):
    """
    Get the posts associated to the given hashtag.

    :param hashtag_id:
    :param page:
    :param per_page:
    :return:
    """

    if page < 1:
        page = 1

    posts = (
        Post.query.join(Post_hashtags, Post.id == Post_hashtags.post_id)
        .filter(Post_hashtags.hashtag_id == hashtag_id)
        .order_by(desc(Post.id))
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    res = []
    for post in posts.items:
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

            # get author
            user = User_mgmt.query.filter_by(id=c.user_id).first()

            # is the agent a page?
            if user.is_page == 1:
                page = Page.query.filter_by(name=user.username).first()
                if page is not None:
                    profile_pic = page.logo
            else:
                ag = Agent.query.filter_by(name=user.username).first()
                profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else Admin_users.query.filter_by(username=user.username).first().profile_pic


            cms.append(
                {
                    "post_id": c.id,
                    "author": author,
                    "profile_pic": profile_pic,
                    "shared_from": -1 if c.shared_from == -1 else (c.shared_from, db.session.query(User_mgmt).join(Post, User_mgmt.id == Post.user_id).filter(Post.id == c.shared_from).first().username),
                    "author_id": int(c.user_id),
                    "post": augment_text(c.tweet.split(":")[-1]),
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
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
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

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        # get elicited emotions names

        emotions = get_elicited_emotions(post.id)

        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        # is the agent a page?
        author = User_mgmt.query.filter_by(id=post.user_id).first()

        if author.is_page == 1:
            page = Page.query.filter_by(name=author.username).first()
            if page is not None:
                profile_pic = page.logo
        else:
            # get agent profile pic
            ag = Agent.query.filter_by(name=author.username).first()
            profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else Admin_users.query.filter_by(username=author.username).first().profile_pic

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
                    list(Reactions.query.filter_by(post_id=post.id, type="like").all())
                ),
                "dislikes": len(
                    list(
                        Reactions.query.filter_by(post_id=post.id, type="dislike").all()
                    )
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="dislike"
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


def get_posts_associated_to_interest(interest_id, page, per_page=10, current_user=None):
    """
    Get the posts associated to the given interest.

    :param interest_id:
    :param page:
    :param per_page:
    :return:
    """

    if page < 1:
        page = 1

    # get posts associated to the topic
    posts = (
        Post.query.join(Post_topics, Post.id == Post_topics.post_id)
        .filter(Post_topics.topic_id == interest_id)
        .order_by(desc(Post.id))
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    res = []
    for post in posts.items:
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

            # is the agent a page?
            if c.is_page == 1:
                page = Page.query.filter_by(name=c.username).first()
                if page is not None:
                    profile_pic = page.logo
            else:
                ag = Agent.query.filter_by(name=c.username).first()
                profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else Admin_users.query.filter_by(username=c.username).first().profile_pic

            cms.append(
                {
                    "post_id": c.id,
                    "author": author,
                    "profile_pic": profile_pic,
                    "shared_from": -1 if c.shared_from == -1 else (c.shared_from, db.session.query(User_mgmt).join(Post, User_mgmt.id == Post.user_id).filter(Post.id == c.shared_from).first().username),
                    "author_id": int(c.user_id),
                    "post": augment_text(c.tweet.split(":")[-1]),
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
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
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

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        emotions = get_elicited_emotions(post.id)
        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        # is the agent a page?
        author = User_mgmt.query.filter_by(id=post.user_id).first()

        if author.is_page == 1:
            page = Page.query.filter_by(name=author.username).first()
            if page is not None:
                profile_pic = page.logo
        else:
            ag = Agent.query.filter_by(name=author.username).first()
            profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else Admin_users.query.filter_by(username=author.username).first().profile_pic

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
                    list(Reactions.query.filter_by(post_id=post.id, type="like").all())
                ),
                "dislikes": len(
                    list(
                        Reactions.query.filter_by(post_id=post.id, type="dislike").all()
                    )
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="dislike"
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


def get_posts_associated_to_emotion(emotion_id, page, per_page=10, current_user=None):
    """
    Get the posts associated to the given emotion.

    :param current_user:
    :param emotion_id:
    :param page:
    :param per_page:
    :return:
    """

    if page < 1:
        page = 1

    # get posts associated to the emotion
    posts = (
        Post.query.join(Post_emotions, Post.id == Post_emotions.post_id)
        .filter(Post_emotions.emotion_id == emotion_id)
        .order_by(desc(Post.id))
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    res = []
    for post in posts.items:
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

            user = User_mgmt.query.filter_by(username=author).first()

            # is the agent a page?
            if user.is_page == 1:
                page = Page.query.filter_by(name=user.username).first()
                if page is not None:
                    profile_pic = page.logo
            else:
                ag = Agent.query.filter_by(name=user.username).first()
                profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else Admin_users.query.filter_by(username=user.username).first().profile_pic

            cms.append(
                {
                    "post_id": c.id,
                    "author": author,
                    "profile_pic": profile_pic,
                    "shared_from": -1 if c.shared_from == -1 else (c.shared_from, db.session.query(User_mgmt).join(Post, User_mgmt.id == Post.user_id).filter(Post.id == c.shared_from).first().username),
                    "author_id": int(c.user_id),
                    "post": augment_text(c.tweet.split(":")[-1]),
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
                        post_id=c.id, user_id=current_user, type="like"
                    ).first()
                    is None,
                    "is_disliked": Reactions.query.filter_by(
                        post_id=c.id, user_id=current_user, type="dislike"
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

        c = Rounds.query.filter_by(id=post.round).first()
        if c is None:
            day = "None"
            hour = "00"
        else:
            day = c.day
            hour = c.hour

        emotions = get_elicited_emotions(post.id)
        image = Images.query.filter_by(id=post.image_id).first()
        if image is None:
            image = ""

        # is the agent a page?
        author = User_mgmt.query.filter_by(id=post.user_id).first()

        if author.is_page == 1:
            page = Page.query.filter_by(name=author.username).first()
            if page is not None:
                profile_pic = page.logo
        else:
            ag = Agent.query.filter_by(name=author.username).first()
            profile_pic = ag.profile_pic if ag is not None and ag.profile_pic is not None else Admin_users.query.filter_by(username=author.username).first().profile_pic

        res.append(
            {
                "article": art,
                "image": image,
                "thread_id": post.thread_id,
                "shared_from": -1 if post.shared_from == -1 else (post.shared_from, db.session.query(User_mgmt).join(Post, User_mgmt.id == Post.user_id).filter(Post.id == post.shared_from).first().username),
                "post_id": post.id,
                "profile_pic": profile_pic,
                "author": User_mgmt.query.filter_by(id=post.user_id).first().username,
                "author_id": int(post.user_id),
                "post": augment_text(post.tweet.split(":")[-1]),
                "round": post.round,
                "day": day,
                "hour": hour,
                "likes": len(
                    list(Reactions.query.filter_by(post_id=post.id, type="like").all())
                ),
                "dislikes": len(
                    list(
                        Reactions.query.filter_by(post_id=post.id, type="dislike").all()
                    )
                ),
                "is_liked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="like"
                ).first()
                is None,
                "is_disliked": Reactions.query.filter_by(
                    post_id=post.id, user_id=current_user, type="dislike"
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


def get_user_recent_interests(user_id, limit=5):
    """
    Get the recent interests of the user.
    :param user_id:
    :param limit:
    :return:
    """

    last_round = Rounds.query.order_by(desc(Rounds.id)).first()
    if last_round is not None:
        last_round = last_round.id
    else:
        last_round = 0
    # get the most recent interests of the user by frequency
    interests = (
        User_interest.query.filter_by(user_id=user_id)
        .join(User_interest, Interests.iid == User_interest.interest_id)
        .add_columns(Interests.interest)
        .filter(User_interest.round_id >= last_round - 36)
        .group_by(Interests.interest)
        .add_columns(func.count(User_interest.interest_id))
        .order_by(desc(func.count(User_interest.interest_id)))
        .limit(limit)
    ).all()

    res = [
        (interest[1], interest[0].interest_id, interest[2]) for interest in interests
    ]

    return res


def get_elicited_emotions(post_id):
    # get elicited emotions names
    emotions = (
        Post_emotions.query.filter_by(post_id=post_id)
        .join(Emotions, Post_emotions.emotion_id == Emotions.id)
        .add_columns(Emotions.emotion)
        .add_columns(Emotions.icon)
        .add_columns(Emotions.id)
    ).all()

    emotions = set([(e.emotion, e.icon, e.id) for e in emotions])
    return emotions


def get_topics(post_id):

    # get the topics of the post
    topics = (
        Post.query.filter_by(id=post_id)
        .join(Post_topics, Post.id == Post_topics.post_id)
        .join(Interests, Post_topics.topic_id == Interests.iid)
        .add_columns(Interests.interest)
        .add_columns(Interests.iid)
        .all()
    )

    topics = set([(iid, interest) for _, interest, iid in topics])
    return topics


def get_unanswered_mentions(user_id):
    """

    :param user_id:
    :return:
    """

    res = (
        Mentions.query.filter_by(user_id=user_id, answered=0)
        .join(Post, Post.id == Mentions.post_id)
        .join(User_mgmt, User_mgmt.id == Post.user_id)
        .add_columns(User_mgmt.username, Post.user_id, Post.tweet)
        .all()
    )

    return res
