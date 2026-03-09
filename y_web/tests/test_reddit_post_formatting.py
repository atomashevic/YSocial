from y_web.utils.text_utils import normalize_punctuation_spacing, process_reddit_post


def test_process_reddit_post_splits_legacy_blank_line_title_body():
    title, body = process_reddit_post("My title\n\nThis is the body text.")
    assert title == "My title"
    assert body == "This is the body text."


def test_process_reddit_post_strips_leading_title_marker_from_body():
    title, body = process_reddit_post("TITLE: Hello\n\nTITLE: body starts here")
    assert title == "Hello"
    assert body == "body starts here"


def test_process_reddit_post_without_title_prefix_returns_body_only():
    title, body = process_reddit_post("Just one paragraph with no split.")
    assert title is None
    assert body == "Just one paragraph with no split."


def test_process_reddit_post_comment_mode_skips_legacy_blankline_split():
    title, body = process_reddit_post(
        "First paragraph.\n\nSecond paragraph.",
        allow_legacy_blankline_title=False,
    )
    assert title is None
    assert body == "First paragraph.\n\nSecond paragraph."


def test_normalize_punctuation_spacing_preserves_urls():
    text = "Hi!How are you?Fine,thanks. Visit https://example.com/a,b?x=1"
    normalized = normalize_punctuation_spacing(text)
    assert (
        normalized == "Hi! How are you? Fine, thanks. Visit https://example.com/a,b?x=1"
    )
