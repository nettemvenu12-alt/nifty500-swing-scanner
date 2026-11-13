"""Recent news headlines (Google News RSS) + simple finance sentiment."""
import re
import urllib.parse

import feedparser

POS = {"surge", "surges", "jump", "jumps", "soar", "soars", "rally", "rallies", "gain", "gains",
       "record", "high", "beat", "beats", "strong", "profit", "growth", "upgrade", "upgrades",
       "buy", "order", "orders", "wins", "win", "bags", "contract", "expansion", "approval",
       "approves", "dividend", "bonus", "buyback", "outperform", "bullish", "rises", "rise",
       "up", "boost", "robust", "acquire", "acquisition", "launch", "target", "raises", "upside"}
NEG = {"fall", "falls", "drop", "drops", "plunge", "plunges", "slump", "crash", "loss", "losses",
       "miss", "misses", "weak", "downgrade", "downgrades", "sell", "fraud", "probe", "raid",
       "penalty", "fine", "ban", "default", "resigns", "resignation", "decline", "declines",
       "slips", "bearish", "cut", "cuts", "lower", "down", "pledge", "sebi", "lawsuit",
       "underperform", "warning", "concern", "tumbles", "sinks", "exits", "slashes"}


def _clean(name):
    return re.sub(r"\b(ltd|limited|ltd\.|india)\b\.?", "", name, flags=re.I).strip(" .")


def headlines(name, symbol, n=5):
    q = urllib.parse.quote(f'"{_clean(name)}" OR {symbol} share when:7d')
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        feed = feedparser.parse(url)
        return [{"title": e.title, "link": e.link, "date": e.get("published", "")}
                for e in feed.entries[:n]]
    except Exception:
        return []


def sentiment(items):
    """-1 .. +1"""
    if not items:
        return 0.0
    total = 0
    for it in items:
        words = set(re.findall(r"[a-z]+", it["title"].lower()))
        total += len(words & POS) - len(words & NEG)
    return max(-1.0, min(1.0, total / (2 * len(items))))


def score(sent):
    """0-5 points; neutral news = 2.5."""
    return round(2.5 + 2.5 * sent, 1)
