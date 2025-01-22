import feedparser


def get_feed(url):
    feed = feedparser.parse(url)

    res = []

    for entry in feed.entries:
        try:
            res.append(
                {"title": entry.title, "summary": entry.summary, "link": entry.link}
            )
        except:
            pass

    return res
