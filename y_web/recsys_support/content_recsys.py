"""
Content recommendation system algorithms.

Implements various content recommendation strategies for personalizing
the social media feed including reverse chronological, popularity-based,
follower-based, and random sampling approaches.
"""

from sqlalchemy import case, desc
from sqlalchemy import func as sql_func
from sqlalchemy.sql.expression import func

from y_web import db
from y_web.models import (
    Follow,
    Post,
    Reactions,
)


def get_suggested_posts(uid, mode, page=1, per_page=10, follower_ratio=0.6):
    """
    Get recommended posts for a user based on specified algorithm.

    Supports multiple recommendation strategies including chronological feeds,
    popularity-based ranking, follower-focused content, and random sampling.

    Args:
        uid: User ID to get recommendations for, or "all" for global feed
        mode: Recommendation algorithm - "ReverseChrono", "ReverseChronoPopularity",
              "ReverseChronoFollowers", or "Random"
        page: Page number for pagination
        per_page: Number of posts per page
        follower_ratio: Ratio of posts from followed users (for follower-based modes)

    Returns:
        Tuple of (posts, additional_posts) where posts is paginated query result
        and additional_posts may contain supplementary content
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

    elif mode == "TopRanking":
        # Reddit-style: sort by net score (likes - dislikes)
        like_count = (
            db.session.query(
                Reactions.post_id, sql_func.count(Reactions.id).label("likes")
            )
            .filter(Reactions.type == 1)
            .group_by(Reactions.post_id)
            .subquery()
        )
        dislike_count = (
            db.session.query(
                Reactions.post_id, sql_func.count(Reactions.id).label("dislikes")
            )
            .filter(Reactions.type == -1)
            .group_by(Reactions.post_id)
            .subquery()
        )
        score_expr = sql_func.coalesce(like_count.c.likes, 0) - sql_func.coalesce(
            dislike_count.c.dislikes, 0
        )
        posts = (
            db.session.query(Post)
            .filter(Post.user_id != uid, Post.comment_to == -1)
            .outerjoin(like_count, like_count.c.post_id == Post.id)
            .outerjoin(dislike_count, dislike_count.c.post_id == Post.id)
            .order_by(score_expr.desc(), desc(Post.id))
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    elif mode == "HotRanking":
        # Reddit-style hot with logarithmic scoring
        # Formula: log10(max(|score|, 1)) + sign(score) * round / round_decay
        # Every round_decay rounds, a post needs ~10x more votes to maintain position
        round_decay = 12

        like_count = (
            db.session.query(
                Reactions.post_id, sql_func.count(Reactions.id).label("likes")
            )
            .filter(Reactions.type == 1)
            .group_by(Reactions.post_id)
            .subquery()
        )
        dislike_count = (
            db.session.query(
                Reactions.post_id, sql_func.count(Reactions.id).label("dislikes")
            )
            .filter(Reactions.type == -1)
            .group_by(Reactions.post_id)
            .subquery()
        )

        # Net score
        net_score = sql_func.coalesce(like_count.c.likes, 0) - sql_func.coalesce(
            dislike_count.c.dislikes, 0
        )

        # Sign of score: 1 if positive, -1 if negative, 0 if zero
        sign_expr = case((net_score > 0, 1), (net_score < 0, -1), else_=0)

        # Logarithmic order: log10(max(abs(score), 1))
        # Using ln(x)/ln(10) for SQLite compatibility
        abs_score = sql_func.abs(net_score)
        max_score = case((abs_score >= 1, abs_score), else_=1)
        log_order = sql_func.log(max_score) / sql_func.log(10)

        # Hot score: logarithmic order + sign * time_boost
        hot_score = log_order + sign_expr * Post.round / round_decay

        posts = (
            db.session.query(Post)
            .filter(Post.user_id != uid, Post.comment_to == -1)
            .outerjoin(like_count, like_count.c.post_id == Post.id)
            .outerjoin(dislike_count, dislike_count.c.post_id == Post.id)
            .order_by(hot_score.desc(), desc(Post.id))
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    elif mode == "MostCommented":
        # Reddit-style: sort by comment count
        comment_count = (
            db.session.query(
                Post.thread_id, sql_func.count(Post.id).label("comment_count")
            )
            .filter(Post.comment_to != -1)
            .group_by(Post.thread_id)
            .subquery()
        )
        posts = (
            db.session.query(Post)
            .filter(Post.user_id != uid, Post.comment_to == -1)
            .outerjoin(comment_count, comment_count.c.thread_id == Post.id)
            .order_by(
                sql_func.coalesce(comment_count.c.comment_count, 0).desc(),
                desc(Post.id),
            )
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    else:
        # get posts in random order
        posts = (
            Post.query.filter(Post.user_id != uid, Post.comment_to == -1)
            .order_by(func.random())
            .paginate(page=page, per_page=per_page, error_out=False)
        )
        additional_posts = None

    return posts, additional_posts
