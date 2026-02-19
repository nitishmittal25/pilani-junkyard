// api/reviews.js — Vercel Serverless Function
// Uses the real `google-play-scraper` npm package to fetch live reviews.
//
// Endpoint: GET /api/reviews?appId=com.cred.club&count=50&rating=0&sort=2
//   appId  — Google Play package ID (required)
//   count  — number of reviews to fetch (default 40, max 200)
//   rating — filter: 0 = all, 1-5 = specific star rating
//   sort   — 1 = most relevant, 2 = newest, 3 = rating

const gplay = require('google-play-scraper');

module.exports = async (req, res) => {
  // ── CORS headers so the frontend (any origin) can call this ──
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const { appId, count = '40', rating = '0', sort = '2' } = req.query;

  if (!appId) {
    return res.status(400).json({ error: 'appId is required' });
  }

  const numCount  = Math.min(parseInt(count)  || 40, 200);
  const numRating = parseInt(rating) || 0;
  const numSort   = parseInt(sort)   || 2;

  try {
    // ── Fetch app metadata (name, icon, rating) ──
    let appInfo = null;
    try {
      appInfo = await gplay.app({ appId, lang: 'en', country: 'in' });
    } catch (_) {
      // non-fatal: proceed without metadata
    }

    // ── Fetch reviews ──
    const reviewOptions = {
      appId,
      lang:    'en',
      country: 'in',
      sort:    numSort,       // gplay.sort.NEWEST = 2
      num:     numCount,
    };

    // google-play-scraper filters by rating if you pass it
    if (numRating >= 1 && numRating <= 5) {
      reviewOptions.rating = numRating;
    }

    const { data: reviews } = await gplay.reviews(reviewOptions);

    const payload = {
      appId,
      appName:    appInfo?.title       || appId,
      appIcon:    appInfo?.icon        || null,
      appRating:  appInfo?.score       || null,
      totalReviews: appInfo?.reviews   || null,
      fetchedCount: reviews.length,
      reviews: reviews.map(r => ({
        id:        r.id,
        userName:  r.userName,
        userImage: r.userImage,
        date:      r.date,
        score:     r.score,
        text:      r.text,
        replyDate: r.replyDate || null,
        replyText: r.replyText || null,
        thumbsUp:  r.thumbsUpCount,
        version:   r.version || null,
      })),
    };

    return res.status(200).json(payload);

  } catch (err) {
    console.error('[reviews] error:', err.message);

    // Provide a helpful message for common errors
    if (err.message?.includes('404') || err.message?.includes('not found')) {
      return res.status(404).json({ error: `App "${appId}" not found on Google Play.` });
    }
    if (err.message?.includes('rate') || err.message?.includes('429')) {
      return res.status(429).json({ error: 'Google Play rate limit hit. Please wait a moment and try again.' });
    }

    return res.status(500).json({ error: 'Failed to fetch reviews. ' + err.message });
  }
};
