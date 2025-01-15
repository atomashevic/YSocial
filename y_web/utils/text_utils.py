import re
from html.parser import HTMLParser
from y_web.models import User_mgmt, Hashtags
from io import StringIO


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
        text = text.replace(m, f'<a href="/user_profile/{uid}"> {m} </a>')

    for h, hid in used_hastag.items():
        text = text.replace(h, f'<a href="/hashtag_posts/{hid}/1"> {h} </a>')

    return text


def extract_components(text, c_type="hashtags"):
    """
    Extract the components from the text.

    :param text: the text to extract the components from
    :param c_type: the component type
    :return: the extracted components
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
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()
