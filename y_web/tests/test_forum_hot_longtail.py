import math

from y_web.reddit.hot_rank import (
    base_hot_score,
    longtail_boost,
    rank_posts_longtail,
    stable_uniform_0_1,
)


class _Post:
    def __init__(self, post_id: int, post_round: int):
        self.id = post_id
        self.round = post_round


def test_stable_uniform_deterministic():
    a = stable_uniform_0_1(1, 2, 3)
    b = stable_uniform_0_1(1, 2, 3)
    c = stable_uniform_0_1(1, 2, 4)
    assert a == b
    assert 0.0 <= a < 1.0
    assert a != c


def test_longtail_boost_thresholds():
    # <=3 votes => [0, 0.45)
    u = 0.999
    b1 = longtail_boost(2, 0, u01=u)
    assert 0.0 <= b1 < 0.45

    # <=8 votes => [0, 0.20)
    b2 = longtail_boost(3, 2, u01=u)
    assert 0.0 <= b2 < 0.20

    # >8 votes => 0
    b3 = longtail_boost(9, 0, u01=u)
    assert b3 == 0.0


def test_base_hot_score_matches_expected():
    # net=0 => log10(1)=0, sign=0 => 0
    assert base_hot_score(0, 10) == 0.0

    # net=9 => log10(10)=1; sign=+1 => + round/12
    v = base_hot_score(9, 12, round_decay=12.0)
    assert math.isclose(v, 2.0, rel_tol=0, abs_tol=1e-9)

    # net=-9 => log10(10)=1; sign=-1 => - round/12
    v2 = base_hot_score(-9, 12, round_decay=12.0)
    assert math.isclose(v2, 0.0, rel_tol=0, abs_tol=1e-9)


def test_rank_posts_longtail_stable_and_local_shuffle():
    posts = [_Post(1, 100), _Post(2, 100), _Post(3, 100)]
    # All have zero votes => base hot tied; ranking comes from seeded longtail boost, tie-break by id.
    reactions = {1: (0, 0), 2: (0, 0), 3: (0, 0)}

    ranked1 = rank_posts_longtail(posts, reactions, viewer_id=7, current_round_id=42)
    ranked2 = rank_posts_longtail(posts, reactions, viewer_id=7, current_round_id=42)
    assert [p.id for p in ranked1] == [p.id for p in ranked2]

    ranked_other_viewer = rank_posts_longtail(
        posts, reactions, viewer_id=8, current_round_id=42
    )
    assert [p.id for p in ranked1] != [p.id for p in ranked_other_viewer]
