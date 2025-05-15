from sqlalchemy import desc
from sqlalchemy.sql.expression import func
from y_web.models import (
    Post,
    Follow,
)
from y_web import db


def get_suggested_posts(uid, mode, page=1, per_page=10, follower_ratio=0.6):
    """
    Return a list of candidate posts for the user as filtered by the content recommendation system.

    :return: a json object with the post ids
    """

    if uid == "all":
        # get posts in reverse chrono for all users
        posts = (
            db.session.query(Post)
            .filter_by(comment_to=-1)
            .order_by(desc(Post.id))
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None
        return posts, additional_posts

    if mode == "ReverseChrono":
        # get posts in reverse chronological order
        posts = (
            db.session.query(Post)
            .filter(Post.user_id != uid, Post.comment_to == -1)
            .order_by(desc(Post.id))
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    elif mode == "ReverseChronoPopularity":
        # get posts ordered by likes in reverse chronological order

        posts = (
            db.session.query(Post)
            .filter(Post.user_id != uid, Post.comment_to == -1)
            .order_by(desc(Post.id), desc(Post.reaction_count))
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    elif mode == "ReverseChronoFollowers":
        # get followers
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        # get posts from followers in reverse chronological order

        posts = (
            Post.query.filter(Post.user_id.in_(follower_ids), Post.comment_to == -1)
            .order_by(desc(Post.id))
            .paginate(
                page=page, per_page=int(per_page * follower_ratio), error_out=False
            )
        )
        additional_posts = (
            Post.query.filter(Post.user_id != uid, Post.comment_to == -1)
            .order_by(desc(Post.id))
            .paginate(
                page=page,
                per_page=int(per_page * (1 - follower_ratio)),
                error_out=False,
            )
        )

    elif mode == "ReverseChronoFollowersPopularity":
        # get followers
        follower = Follow.query.filter_by(action="follow", user_id=uid)
        follower_ids = [f.follower_id for f in follower if f.follower_id != uid]

        # get posts from followers ordered by likes and reverse chronologically
        posts = (
            db.session.query(Post)
            .filter(Post.user_id.in_(follower_ids), Post.comment_to == -1)
            .order_by(desc(Post.id), desc(Post.reaction_count))
            .paginate(
                page=page, per_page=int(per_page * follower_ratio), error_out=False
            )
        )
        additional_posts = (
            Post.query.filter(Post.user_id != uid, Post.comment_to == -1)
            .order_by(desc(Post.id))
            .paginate(
                page=page,
                per_page=int(per_page * (1 - follower_ratio)),
                error_out=False,
            )
        )

    else:
        # get posts in random order
        posts = (
            Post.query.filter(Post.user_id != uid, Post.comment_to == -1)
            .order_by(func.random())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    return posts, additional_posts
