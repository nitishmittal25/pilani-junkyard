from google_play_scraper import app as gplay_app, reviews, Sort
from collections import Counter
from datetime import datetime, timezone
import json, re

# ── GENERIC issue/good signals — works for ANY app ──────────────────────────
# Instead of fixed keywords we extract the most frequent meaningful words
# from negative vs positive reviews and return them as themes.

STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "is","it","its","this","that","was","are","be","been","being","have",
    "has","had","do","does","did","will","would","could","should","may",
    "might","shall","can","not","no","so","if","as","by","from","up","out",
    "i","my","me","we","our","you","your","he","she","they","them","their",
    "app","apps","com","use","used","using","get","got","just","also","very",
    "good","great","nice","bad","worst","best","even","still","after","before",
    "when","than","more","most","all","some","one","two","time","way","make",
    "now","new","well","really","much","many","like","please","thank","thanks",
    "the","they","there","here","which","what","how","who","then","than",
}

def clean_tokens(text):
    text = text.lower()
    text = re.sub(r"[^a-z\s]", " ", text)
    tokens = text.split()
    return [t for t in tokens if len(t) > 3 and t not in STOPWORDS]

def extract_top_phrases(rv_list, star_range, top_n=10):
    """
    Extract the most frequently mentioned meaningful words
    from reviews in the given star range.
    Returns list of (word, count) tuples.
    """
    word_counts = Counter()
    subset = [r for r in rv_list if r.get("score") in star_range]
    for rv in subset:
        text = rv.get("content") or ""
        tokens = clean_tokens(text)
        # also count 2-word phrases
        for token in tokens:
            word_counts[token] += 1
        for i in range(len(tokens) - 1):
            phrase = tokens[i] + " " + tokens[i+1]
            word_counts[phrase] += 1
    return word_counts.most_common(top_n)

# ── TIME PERIOD BREAKDOWN ───────────────────────────────────────────────────

PERIODS = [7, 30, 60, 90, 120, 180, 270, 365]

def build_period_breakdown(rv_list):
    """
    For each period (7d, 30d, 60d … 365d and all-time),
    return count of 1★–5★ reviews and average rating.
    Only includes a period if at least one review falls in it.
    """
    now = datetime.now(timezone.utc)
    result = {}

    for days in PERIODS:
        cutoff = now.timestamp() - days * 86400
        subset = [r for r in rv_list if r["at"].timestamp() >= cutoff]
        if not subset:
            continue
        stars = {1:0, 2:0, 3:0, 4:0, 5:0}
        for r in subset:
            stars[r["score"]] += 1
        total = len(subset)
        avg   = sum(s * c for s, c in stars.items()) / total
        label = f"Last {days} Days"
        result[label] = {
            "days":    days,
            "total":   total,
            "avg":     round(avg, 2),
            "5star":   stars[5],
            "4star":   stars[4],
            "3star":   stars[3],
            "2star":   stars[2],
            "1star":   stars[1],
        }

    # All time
    if rv_list:
        stars = {1:0, 2:0, 3:0, 4:0, 5:0}
        for r in rv_list:
            stars[r["score"]] += 1
        total = len(rv_list)
        avg   = sum(s * c for s, c in stars.items()) / total
        result["All Time"] = {
            "days":    None,
            "total":   total,
            "avg":     round(avg, 2),
            "5star":   stars[5],
            "4star":   stars[4],
            "3star":   stars[3],
            "2star":   stars[2],
            "1star":   stars[1],
        }

    return result

# ── VERCEL HANDLER ──────────────────────────────────────────────────────────

def handler(request):
    headers = {
        "Access-Control-Allow-Origin":  "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Content-Type":                 "application/json",
    }

    if request.method == "OPTIONS":
        return Response("", 200, headers)

    app_id = request.args.get("appId", "").strip()
    count  = min(int(request.args.get("count", 300)), 1000)

    if not app_id:
        return Response(json.dumps({"error": "appId is required"}), 400, headers)

    try:
        # ── App metadata ──
        try:
            info = gplay_app(app_id, lang="en", country="in")
        except Exception:
            info = {}

        # ── Fetch reviews in batches ──
        all_rv, token = [], None
        while len(all_rv) < count:
            batch = min(200, count - len(all_rv))
            try:
                result, token = reviews(
                    app_id,
                    lang="en",
                    country="in",
                    sort=Sort.NEWEST,
                    count=batch,
                    continuation_token=token,
                )
            except Exception as e:
                return Response(json.dumps({"error": f"Review fetch failed: {str(e)}"}), 500, headers)

            if not result:
                break
            all_rv.extend(result)
            if not token:
                break

        if not all_rv:
            return Response(json.dumps({"error": f"No reviews found for {app_id}"}), 404, headers)

        # ── Sentiment counts ──
        pos   = sum(1 for r in all_rv if r["score"] >= 4)
        neg   = sum(1 for r in all_rv if r["score"] <= 2)
        total = len(all_rv)
        neu   = total - pos - neg

        sentiment = (
            "positive" if pos / total > 0.6 else
            "negative" if pos / total < 0.4 else
            "mixed"
        )

        # ── Dynamic theme extraction ──
        # Top words/phrases from negative reviews = issues
        # Top words/phrases from positive reviews = good points
        issue_phrases = extract_top_phrases(all_rv, star_range={1, 2}, top_n=10)
        good_phrases  = extract_top_phrases(all_rv, star_range={4, 5}, top_n=10)

        # ── Time period breakdown ──
        period_data = build_period_breakdown(all_rv)

        # ── Build payload ──
        payload = {
            "appId":      app_id,
            "appName":    info.get("title", app_id),
            "appIcon":    info.get("icon"),
            "appRating":  info.get("score"),
            "totalReviews": info.get("reviews"),
            "analysed":   total,
            "positive":   pos,
            "negative":   neg,
            "neutral":    neu,
            "sentiment":  sentiment,

            # Dynamic — words most mentioned in bad reviews
            "topIssues": [
                {"phrase": phrase, "count": cnt}
                for phrase, cnt in issue_phrases
            ],

            # Dynamic — words most mentioned in good reviews
            "topGood": [
                {"phrase": phrase, "count": cnt}
                for phrase, cnt in good_phrases
            ],

            # Period breakdown table
            "periodBreakdown": period_data,

            # Individual reviews
            "reviews": [
                {
                    "userName":  r.get("userName"),
                    "score":     r.get("score"),
                    "text":      r.get("content"),
                    "date":      r["at"].isoformat() if r.get("at") else None,
                    "thumbsUp":  r.get("thumbsUpCount", 0),
                    "version":   r.get("reviewCreatedVersion"),
                    "replyText": r.get("replyContent"),
                }
                for r in all_rv
            ],
        }

        return Response(json.dumps(payload, default=str), 200, headers)

    except Exception as e:
        return Response(json.dumps({"error": str(e)}), 500, headers)
