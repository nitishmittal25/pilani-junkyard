const gplay = require('google-play-scraper');

const STOPWORDS = new Set([
  'the','a','an','and','or','but','in','on','at','to','for','of','with',
  'is','it','its','this','that','was','are','be','been','have','has','had',
  'do','does','did','will','would','could','should','not','no','so','if',
  'i','my','me','we','you','your','they','them','app','use','get','just',
  'also','very','good','great','nice','bad','even','still','after','before',
  'when','than','more','all','some','one','time','way','make','now','new',
  'well','really','much','many','like','please','thank','thanks','this',
]);

function extractPhrases(reviews, starRange, topN = 10) {
  const counts = {};
  reviews.filter(r => starRange.includes(r.score)).forEach(r => {
    const text = (r.content || '').toLowerCase().replace(/[^a-z\s]/g, ' ');
    const tokens = text.split(/\s+/).filter(t => t.length > 3 && !STOPWORDS.has(t));
    tokens.forEach(t => { counts[t] = (counts[t] || 0) + 1; });
    for (let i = 0; i < tokens.length - 1; i++) {
      const phrase = tokens[i] + ' ' + tokens[i+1];
      counts[phrase] = (counts[phrase] || 0) + 1;
    }
  });
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map(([phrase, count]) => ({ phrase, count }));
}

function buildPeriodBreakdown(reviews) {
  const now = Date.now();
  const PERIODS = [7, 30, 60, 90, 120, 180, 270, 365];
  // Only include periods up to how far back the reviews actually go
  const oldestDate = Math.min(...reviews.map(r => new Date(r.at).getTime()));
  const actualDays = Math.ceil((now - oldestDate) / (86400 * 1000));

  const result = {};

  PERIODS.filter(d => d <= actualDays + 7).forEach(days => {
    const cutoff = now - days * 86400 * 1000;
    const fromDate = new Date(cutoff).toLocaleDateString('en-IN', {day:'numeric',month:'short',year:'numeric'});
    const toDate   = new Date(now).toLocaleDateString('en-IN', {day:'numeric',month:'short',year:'numeric'});
    const subset   = reviews.filter(r => { const d = new Date(r.at); return !isNaN(d.getTime()) && d.getTime() >= cutoff; });
    if (!subset.length) return;

    const stars = {1:0,2:0,3:0,4:0,5:0};
    subset.forEach(r => stars[r.score]++);
    const avg = subset.reduce((s, r) => s + r.score, 0) / subset.length;

    result[`Last ${days} Days`] = {
      days,
      dateRange: `${fromDate} → ${toDate}`,
      total: subset.length,
      avg: Math.round(avg * 100) / 100,
      '5star': stars[5], '4star': stars[4],
      '3star': stars[3], '2star': stars[2], '1star': stars[1],
    };
  });

  // All fetched reviews period
  if (reviews.length) {
    const stars = {1:0,2:0,3:0,4:0,5:0};
    reviews.forEach(r => stars[r.score]++);
    const avg = reviews.reduce((s, r) => s + r.score, 0) / reviews.length;
    const fromDate = new Date(oldestDate).toLocaleDateString('en-IN', {day:'numeric',month:'short',year:'numeric'});
    const toDate   = new Date(now).toLocaleDateString('en-IN', {day:'numeric',month:'short',year:'numeric'});

    result[`All Fetched (${reviews.length} reviews)`] = {
      days: null,
      dateRange: `${fromDate} → ${toDate}`,
      total: reviews.length,
      avg: Math.round(avg * 100) / 100,
      '5star': stars[5], '4star': stars[4],
      '3star': stars[3], '2star': stars[2], '1star': stars[1],
    };
  }

  return result;
}
  
module.exports = async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Content-Type', 'application/json');

  if (req.method === 'OPTIONS') return res.status(200).end();

  const { appId, count = '150' } = req.query;
  if (!appId) return res.status(400).json({ error: 'appId is required' });

  const numCount = Math.min(parseInt(count) || 150, 200000);

  try {
    // App info
    let info = {};
    try { info = await gplay.app({ appId, lang: 'en', country: 'in' }); } catch(_) {}

    // Fetch reviews in batches
    let allReviews = [], token = null;
    while (allReviews.length < numCount) {
      const batch = Math.min(200, numCount - allReviews.length);
      const reviewResult = await gplay.reviews({
        appId, lang: 'en', country: 'in',
        sort: gplay.sort.NEWEST,
        count: batch,
        continuationToken: token,
      });
    const result = reviewResult.data;
    token = reviewResult.nextPaginationToken;
      if (!result || !result.length) break;
      allReviews = allReviews.concat(result);
      if (!token) break;
    }

    if (!allReviews.length) {
      return res.status(404).json({ error: `No reviews found for ${appId}` });
    }

    const pos = allReviews.filter(r => r.score >= 4).length;
    const neg = allReviews.filter(r => r.score <= 2).length;
    const total = allReviews.length;

    const sentiment = pos / total > 0.6 ? 'positive'
                    : pos / total < 0.4 ? 'negative'
                    : 'mixed';

    return res.status(200).json({
      appId,
      appName:      info.title      || appId,
      appIcon:      info.icon       || null,
      appRating:    info.score      || null,
      totalReviews: info.reviews    || null,
      analysed:     total,
      positive:     pos,
      negative:     neg,
      neutral:      total - pos - neg,
      sentiment,
      lastReviewDate:   allReviews.length ? new Date(Math.max(...allReviews.map(r => new Date(r.at).getTime()))).toLocaleDateString('en-IN', {day:'numeric',month:'short',year:'numeric'}) : null,
      oldestReviewDate: allReviews.length ? new Date(Math.min(...allReviews.map(r => new Date(r.at).getTime()))).toLocaleDateString('en-IN', {day:'numeric',month:'short',year:'numeric'}) : null,
      topIssues:    extractPhrases(allReviews, [1, 2], 10),
      topGood:      extractPhrases(allReviews, [4, 5], 10),
      issueSummary: (() => { const p = extractPhrases(allReviews, [1,2], 5); return p.length ? `Users most commonly mention issues around: ${p.map(x=>x.phrase).join(', ')}. These appear repeatedly across 1★–2★ reviews.` : null; })(),
      goodSummary:  (() => { const p = extractPhrases(allReviews, [4,5], 5); return p.length ? `Users frequently praise: ${p.map(x=>x.phrase).join(', ')}. These themes dominate 4★–5★ reviews.` : null; })(),
      periodBreakdown: buildPeriodBreakdown(allReviews),
      reviews: allReviews.map(r => ({
        userName:  r.userName || 'Anonymous',
        score:     r.score,
        text:      r.content  || '',
        date:      r.at ? new Date(r.at).toISOString() : null,
        thumbsUp:  r.thumbsUpCount || '',
        version:   r.reviewCreatedVersion || '',
        replyText: r.replyContent || '',
        replyDate: r.repliedAt ? new Date(r.repliedAt).toISOString() : '',
      })),
    });

  } catch (err) {
    return res.status(500).json({ error: err.message });
  }
};
