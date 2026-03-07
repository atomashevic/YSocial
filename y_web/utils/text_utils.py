"""
Text processing utilities for social media content.

Provides functions for sentiment analysis, toxicity detection, text augmentation
with hyperlinks, component extraction (hashtags, mentions), HTML tag stripping,
and Reddit-style post formatting.
"""

import re
from html.parser import HTMLParser
from io import StringIO

from y_web.models import Admin_users, Hashtags, Post_Toxicity, User_mgmt

# Optional imports
try:
    from nltk.sentiment import SentimentIntensityAnalyzer

    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

try:
    from perspective import PerspectiveAPI

    PERSPECTIVE_AVAILABLE = True
except ImportError:
    PERSPECTIVE_AVAILABLE = False


def vader_sentiment(text):
    """
    Calculate sentiment scores using VADER sentiment analysis.

    VADER (Valence Aware Dictionary and sEntiment Reasoner) is specifically
    tuned for social media text sentiment analysis.

    Args:
        text: Text content to analyze

    Returns:
        Dictionary with sentiment scores: {'neg', 'neu', 'pos', 'compound'}
    """
    if not NLTK_AVAILABLE:
        # Return mock sentiment if NLTK is not available
        return {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0}

    sia = SentimentIntensityAnalyzer()
    sentiment = sia.polarity_scores(text)
    return sentiment


def toxicity(text, username, post_id, db):
    """
    Calculate toxicity scores using Google's Perspective API.

    Analyzes text for various dimensions of toxicity including general toxicity,
    severe toxicity, identity attacks, insults, profanity, threats, sexually
    explicit content, and flirtation. Results are stored in the database.

    Args:
        text: Text content to analyze
        username: Username of the admin user (for API key lookup)
        post_id: ID of the post being analyzed
        db: Database session for storing results

    Returns:
        None (stores results in Post_Toxicity table)
    """
    if not PERSPECTIVE_AVAILABLE:
        # Return None if Perspective API is not available
        return None

    user = Admin_users.query.filter_by(username=username).first()

    if user is not None:
        api_key = user.perspective_api
        if api_key is not None:
            try:
                p = PerspectiveAPI(api_key)
                toxicity_score = p.score(
                    text,
                    tests=[
                        "TOXICITY",
                        "SEVERE_TOXICITY",
                        "IDENTITY_ATTACK",
                        "INSULT",
                        "PROFANITY",
                        "THREAT",
                        "SEXUALLY_EXPLICIT",
                        "FLIRTATION",
                    ],
                )
                post_toxicity = Post_Toxicity(
                    post_id=post_id,
                    toxicity=toxicity_score["TOXICITY"],
                    severe_toxicity=toxicity_score["SEVERE_TOXICITY"],
                    identity_attack=toxicity_score["IDENTITY_ATTACK"],
                    insult=toxicity_score["INSULT"],
                    profanity=toxicity_score["PROFANITY"],
                    threat=toxicity_score["THREAT"],
                    sexually_explicit=toxicity_score["SEXUALLY_EXPLICIT"],
                    flirtation=toxicity_score["FLIRTATION"],
                )

                db.session.add(post_toxicity)
                db.session.commit()

            except Exception as e:
                print(e)
                return


def augment_text(text, exp_id):
    """
    Augment text by converting mentions and hashtags to clickable links.

    Replaces @username mentions with links to user profiles and #hashtag
    with links to hashtag pages. Also capitalizes the first letter.

    Args:
        text: Raw text with mentions and hashtags
        exp_id: ID of the experiment

    Returns:
        HTML string with hyperlinked mentions and hashtags
    """
    # text = text.split("(")[0]

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
        text = text.replace(m, f'<a href="/{exp_id}/user_profile/{uid}"> {m} </a>')

    for h, hid in used_hastag.items():
        text = text.replace(h, f'<a href="/{exp_id}/hashtag_posts/{hid}/1"> {h} </a>')

    # remove first character it is a space
    if text[0] == " ":
        text = text[1:]

    # capitalize the first letter of the text
    text = text[0].upper() + text[1:]

    return text


def extract_components(text, c_type="hashtags"):
    """
    Extract hashtags or mentions from text using regex patterns.

    Args:
        text: Text to extract components from
        c_type: Component type - "hashtags" for #tags or "mentions" for @users

    Returns:
        List of extracted components (including # or @ prefix)
    """
    # Define the regex pattern
    if c_type == "hashtags":
        pattern = re.compile(r"#\w+")
    elif c_type == "mentions":
        pattern = re.compile(r"@\w+")
    else:
        return []
    # Find all matches in the input text
    hashtags = pattern.findall(text)
    return hashtags


class MLStripper(HTMLParser):
    """HTML parser subclass that strips all HTML tags from text."""

    def __init__(self):
        """Handle   init   operation."""
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        """Display handle data page."""
        self.text.write(d)

    def get_data(self):
        """
        Get extracted text data.

        Returns:
            String containing extracted text
        """
        return self.text.getvalue()


def strip_tags(html):
    """
    Remove all HTML tags from text content.

    Args:
        html: HTML string to strip tags from

    Returns:
        Plain text with all HTML tags removed
    """
    s = MLStripper()
    s.feed(html)
    return s.get_data()


def strip_markdown_artifacts(text):
    """
    Remove markdown headers and common article structure artifacts.

    Handles patterns like:
    - # Conclusion: Some text
    - # Call to Action
    - ## Summary
    - # Key Points:

    Args:
        text: Text content to clean

    Returns:
        Text with markdown artifacts removed
    """
    if not text:
        return text

    # Remove markdown headers with common article section names
    # Patterns: # Conclusion:, # Call to Action, # Key Points, etc.
    text = re.sub(
        r'^#+\s*(Conclusion|Call to Action|Key Points?|Summary|Overview|'
        r'Introduction|Background|TL;?DR|Final Thoughts?|Takeaway|'
        r'What\'s Next|Next Steps?|Resources?)[:\s]*',
        '', text, flags=re.MULTILINE | re.IGNORECASE
    )

    # Remove any isolated markdown header at the very start of text
    # (e.g., "# Some random header" at the beginning)
    text = re.sub(r'^#+\s+', '', text)

    # Clean up multiple consecutive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def calculate_text_similarity(text1, text2):
    """
    Calculate similarity between two texts using word overlap (Jaccard similarity).

    Args:
        text1: First text to compare
        text2: Second text to compare

    Returns:
        Float between 0 and 1 indicating similarity (1 = identical)
    """
    if not text1 or not text2:
        return 0.0

    # Normalize texts: lowercase and extract words
    words1 = set(re.findall(r'\b\w+\b', text1.lower()))
    words2 = set(re.findall(r'\b\w+\b', text2.lower()))

    if not words1 or not words2:
        return 0.0

    # Jaccard similarity: intersection / union
    intersection = len(words1 & words2)
    union = len(words1 | words2)

    return intersection / union if union > 0 else 0.0


def strip_reproduced_article_content(post_body, article_summary, similarity_threshold=0.6):
    """
    Detect and strip content that appears to be reproduced from the article summary.

    If the post body is too similar to the article summary, it indicates the LLM
    reproduced the article content instead of writing original commentary.

    Args:
        post_body: The generated post body text
        article_summary: The original article summary
        similarity_threshold: Similarity threshold above which content is considered reproduced (0-1)

    Returns:
        Tuple of (cleaned_body, was_modified) where was_modified indicates if content was stripped
    """
    if not post_body or not article_summary:
        return post_body, False

    # Normalize article summary for substring checking
    article_words = set(re.findall(r'\b\w+\b', article_summary.lower()))

    # Check overall similarity
    similarity = calculate_text_similarity(post_body, article_summary)

    if similarity >= similarity_threshold:
        # Content is too similar to article - try to find and remove the reproduced portion
        # Split into sentences and check each one
        sentences = re.split(r'(?<=[.!?])\s+', post_body)
        filtered_sentences = []

        # Use lower threshold for per-sentence matching since each sentence
        # only contains part of the article (so Jaccard similarity is lower)
        sentence_threshold = similarity_threshold * 0.6  # ~0.36 for default

        for sentence in sentences:
            sentence_similarity = calculate_text_similarity(sentence, article_summary)

            # Also check if sentence words are mostly from article
            sentence_words = set(re.findall(r'\b\w+\b', sentence.lower()))
            if sentence_words:
                # What percentage of sentence words appear in article?
                overlap_ratio = len(sentence_words & article_words) / len(sentence_words)
            else:
                overlap_ratio = 0

            # Keep sentences that are sufficiently different from the article
            # Both similarity and overlap ratio must be below thresholds
            if sentence_similarity < sentence_threshold and overlap_ratio < 0.7:
                filtered_sentences.append(sentence)

        if filtered_sentences:
            return ' '.join(filtered_sentences), True
        else:
            # All content was reproduced - return empty
            return "", True

    return post_body, False


def process_reddit_post(text, allow_legacy_blankline_title=True):
    """
    Process and format Reddit-style post text.

    Handles posts with "TITLE:" prefix (and variations/typos) by splitting
    into title and content. Also strips markdown artifacts from body.

    Supported title variations:
    - TITLE:, TITTLE:, TITEL: (typos)
    - title:, Title: (case variations)
    - TITLE: , TITLE:no_space (optional space after colon)

    Args:
        text: Raw post text to process
        allow_legacy_blankline_title: If True, infer title/body split from
            "title + blank line + body" legacy format when no TITLE prefix is present.

    Returns:
        Tuple of (title, content) where title is None if no TITLE prefix exists
    """
    if not text:
        return None, ""

    # Strip leading/trailing whitespace
    text = text.strip()

    # Match TITLE: prefix with variations (case-insensitive, typos, optional space)
    # Handles: TITLE:, TITTLE:, TITEL:, Title:, title:, etc.
    # Also handles markdown formatting: **TITLE:, *TITLE:, __TITLE:, _TITLE:
    title_match = re.match(r'^[\*_]{0,2}(TITLE|TITTLE|TITEL)\s*:\s*', text, re.IGNORECASE)

    if title_match:
        # Remove the matched prefix
        remaining = text[title_match.end():]

        # Split on first newline to separate title from body.
        # Some generations forget the newline after TITLE: and produce a single long line.
        # In that case, the whole post renders as a "title" (typically bold) in the Reddit UI.
        lines = remaining.split("\n", 1)
        title = lines[0].strip()

        # Strip trailing markdown bold/italic markers from title
        title = re.sub(r'[\*_]{1,2}$', '', title).strip()

        if len(lines) > 1:
            content = lines[1].lstrip()
        else:
            content = ""

            # Heuristic recovery: if TITLE has no newline and is extremely long,
            # treat the first sentence-ish chunk as the title and the rest as body.
            if len(title) >= 200:
                t = title

                # Prefer a sentence boundary early-ish; otherwise cut near a word boundary.
                # Keep the title reasonably short so the body isn't swallowed by bold title styling.
                min_idx, max_idx = 40, 160
                boundary_patterns = [r"\.\s+", r"!\s+", r"\?\s+", r"\.\.\.\s+"]
                split_at = None

                for pat in boundary_patterns:
                    m = re.search(pat, t)
                    if not m:
                        continue
                    idx = m.end()
                    if min_idx <= idx <= max_idx:
                        split_at = idx
                        break

                if split_at is None:
                    # Fall back to a whitespace cut before max_idx.
                    cut = t.rfind(" ", 0, max_idx)
                    if cut >= min_idx:
                        split_at = cut + 1

                if split_at is not None and split_at < len(t) - 1:
                    title = t[:split_at].strip()
                    content = t[split_at:].lstrip()
    else:
        title = None
        content = text.lstrip()

        if allow_legacy_blankline_title:
            # Human compose payloads historically used "title + blank line + body"
            # without a TITLE prefix. Treat that as a Reddit title/body split.
            blocks = re.split(r"\n\s*\n", text, maxsplit=1)
            if len(blocks) > 1:
                candidate_title = blocks[0].strip()
                candidate_body = blocks[1].lstrip()
                if (
                    candidate_title
                    and candidate_body
                    and len(candidate_title) <= 300
                ):
                    title = candidate_title
                    content = candidate_body

    # Strip markdown artifacts from body content
    content = strip_markdown_artifacts(content)

    # Guardrail: never leak TITLE markers in the rendered body.
    content = re.sub(
        r"^[\*_]{0,2}(TITLE|TITTLE|TITEL)\s*:\s*",
        "",
        content,
        flags=re.IGNORECASE,
    ).lstrip()

    return title, content


def normalize_punctuation_spacing(text):
    """
    Normalize missing spaces after punctuation for readability.

    This adds a single space after common punctuation marks when missing,
    while preserving URLs and common numeric patterns.
    """
    if not text:
        return text

    preserved = {}

    def _preserve(match):
        key = f"__URL_{len(preserved)}__"
        preserved[key] = match.group(0)
        return key

    normalized = re.sub(r"https?://\S+", _preserve, str(text))

    # Sentence punctuation spacing.
    normalized = re.sub(
        r"(?<!\d)([.!?;:])(?!\s|$)(?=[A-Za-z])",
        r"\1 ",
        normalized,
    )
    # Comma spacing, excluding thousands separators.
    normalized = re.sub(
        r"(?<!\d),(?!\s|$)(?=[A-Za-z])",
        ", ",
        normalized,
    )

    for key, url in preserved.items():
        normalized = normalized.replace(key, url)

    return normalized
