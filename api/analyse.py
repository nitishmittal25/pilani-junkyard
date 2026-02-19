from google_play_scraper import app as gplay_app, reviews, Sort
from collections import Counter
from datetime import datetime, timedelta
import json

ISSUE_KEYWORDS = {
    "App crashes / freezes":    ["crash","freeze","frozen","hang","stuck","not opening","force close","black screen"],
    "Login / OTP problems":     ["otp","login","sign in","can't log","logout","logged out","verify"],
    "Payment failures":         ["payment","failed","deducted","charged","refund","money","transaction"],
    "Slow / laggy":             ["slow","lag","lagging","loading","takes forever","buffer"],
    "Order / delivery issues":  ["order","deliver","late","delayed","wrong product","return"],
    "Customer support":         ["support","customer care","no response","ignored","useless","not helpful"],
    "Bugs / errors":            ["bug","error","glitch","broken","not working","doesn't work"],
    "Too many ads":             ["ad","ads","advertisement","popup","spam","notification"],
    "Poor UI / UX":             ["confusing","complicated","bad design","ugly","layout"],
}

GOOD_KEYWORDS = {
    "Easy to use":              ["easy","simple","smooth","user friendly","intuitive","clean"],
    "Fast & reliable":          ["fast","quick","instant","reliable","stable","works great"],
    "Good offers / cashback":   ["cashback","offer","discount","reward","deal","savings"],
    "Great customer support":   ["support","helpful","resolved","quick response","great service"],
    "Seamless payments":        ["seamless","easy payment","quick pay","smooth transaction"],
    "Trustworthy / secure":     ["safe","secure","trust","genuine","authentic"],
    "Value for money":          ["value","worth","affordable","cheap","cost effective"],
    "Overall love it":          ["love","amazing","excellent","fantastic","best app","perfect"],
}

def detect_themes(rv_list, star_range, keyword_bank):
    counts = Counter()
    for rv in rv_list:
        if rv.get("score") not in star_range:
            continue
        text = (rv.get("content") or "").lower()
        for theme, kws in keyword_bank.items():
            if any(kw in text for kw in kws):
                counts[theme] += 1
    return counts

def handler(request):
    # CORS
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Content-Type": "application/json",
    }

    if request.method == "OPTIONS":
        return Response("", 200, headers)

    app_id = request.args.get("appId")
    count  = min(int(request.args.get("count", 200)), 500)

    if not app_id:
        return Response(json.dumps({"error": "appId required"}), 400, headers)

    try:
        info = gplay_app(app_id, lang="en", country="in")

        all_rv, token = [], None
        while len(all_rv) < count:
            batch = min(200, count - len(all_rv))
            result, token = reviews(
                app_id, lang="en", country="in",
                sort=Sort.NEWEST, count=batch,
                continuation_token=token
            )
            if not result: break
            all_rv.extend(result)
            if not token: break

        issue_counts = detect_themes(all_rv, {1, 2}, ISSUE_KEYWORDS)
        good_counts  = detect_themes(all_rv, {4, 5}, GOOD_KEYWORDS)

        pos = sum(1 for r in all_rv if r["score"] >= 4)
        neg = sum(1 for r in all_rv if r["score"] <= 2)
        total = len(all_rv)

        payload = {
            "appName":    info.get("title", app_id),
            "appIcon":    info.get("icon"),
            "appRating":  info.get("score"),
            "analysed":   total,
            "positive":   pos,
            "negative":   neg,
            "neutral":    total - pos - neg,
            "sentiment":  "positive" if pos/total > 0.6 else "negative" if pos/total < 0.4 else "mixed" if total else "mixed",
            "topIssues":  dict(issue_counts.most_common(8)),
            "topGood":    dict(good_counts.most_common(8)),
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

        return Response(json.dumps(payload), 200, headers)

    except Exception as e:
        return Response(json.dumps({"error": str(e)}), 500, headers)
```

### Step 2 — Create `requirements.txt` in your repo root
```
google-play-scraper==1.2.7
