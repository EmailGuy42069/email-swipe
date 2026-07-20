/**
 * Intent-based folder routing (mirrors scripts/folder_intent.py heuristics).
 */
const FOLDER_INTENTS = {
  promotions: {
    label: 'Promotions & sales',
    description: 'Marketing and deals — even without the word "promo"',
    keywords: [
      'sale', 'sales', '% off', 'percent off', 'deal', 'deals', 'discount', 'save ',
      'limited time', 'shop now', 'buy now', 'free shipping', 'coupon', 'offer',
      'flash sale', 'clearance', 'exclusive offer', 'act now', "don't miss",
      'special offer', 'lowest price', 'mega sale', 'today only',
      'new collection', 'new arrivals', 'just dropped', 'introducing', 'discover',
      "you'll love", 'styles', 'curated for you', 'picked for you',
    ],
    senderHints: ['promo', 'promotions', 'marketing', 'deals', 'offers', 'news@', 'store@', 'shop@'],
    negativeKeywords: ['receipt', 'invoice', 'order confirmed', 'payment received', 'your order', 'shipped', 'tracking', 'paid'],
    newsletterBonus: 0.12,
    unsubscribeBonus: 0.08,
    reason: 'looks promotional',
  },
  newsletters: {
    label: 'Newsletters & digests',
    keywords: ['newsletter', 'digest', 'weekly roundup', 'daily briefing', 'edition', 'substack', 'view in browser'],
    senderHints: ['newsletter', 'digest', 'substack', 'mailchi', 'campaign'],
    negativeKeywords: ['receipt', 'invoice', 'security alert'],
    newsletterBonus: 0.35,
    unsubscribeBonus: 0.25,
    reason: 'looks like a newsletter',
  },
  receipts: {
    label: 'Receipts & orders',
    keywords: ['receipt', 'invoice', 'order confirmed', 'order #', 'payment received', 'shipped', 'tracking', 'delivered', 'paid'],
    senderHints: ['receipt', 'billing', 'invoice', 'orders', 'payments', 'stripe', 'paypal'],
    negativeKeywords: ['% off', 'sale ends', 'limited time offer', 'unsubscribe'],
    newsletterBonus: 0,
    unsubscribeBonus: -0.15,
    reason: 'looks like a receipt or order',
  },
  notifications: {
    label: 'Notifications & alerts',
    keywords: ['notification', 'alert', 'security alert', 'sign-in', 'verify', 'password', '2fa', 'assigned to you'],
    senderHints: ['noreply', 'no-reply', 'notifications', 'alerts', 'security'],
    negativeKeywords: ['unsubscribe', '% off'],
    newsletterBonus: 0,
    unsubscribeBonus: -0.05,
    reason: 'looks like an alert',
  },
  social: {
    label: 'Social networks',
    keywords: ['connection request', 'viewed your profile', 'new follower', 'people you may know', 'mentioned you'],
    senderHints: ['linkedin', 'facebook', 'twitter', 'x.com', 'instagram'],
    negativeKeywords: [],
    newsletterBonus: 0.05,
    unsubscribeBonus: 0.05,
    reason: 'looks like social mail',
  },
};

const INTENT_MATCH_THRESHOLD = 0.32;
const DESCRIPTOR_STOP_WORDS = new Set(
  'all the and for put this that with from into your mail email folder route files'.split(' '),
);

function routeMatchMode(route) {
  if (route.matchMode) return route.matchMode;
  if (route.matchType === 'descriptor') return 'ai';
  if (route.matchType === 'intent') return 'smart';
  return 'strict';
}

function emailRoutingText(email) {
  return `${email.subject || ''} ${email.snippet || ''}`.toLowerCase();
}

function getAgentJudgment(email, routeId) {
  const judgments = email.folderJudgments || email.aiFolderMatches || [];
  return judgments.find((j) => j.routeId === routeId || j.folderRouteId === routeId);
}

function scoreDescriptorRoute(email, route) {
  const judgment = getAgentJudgment(email, route.id);
  if (judgment) {
    const conf = Math.min(1, Math.max(0, judgment.confidence ?? 0.85));
    return {
      score: conf,
      reason: judgment.reason || 'agent judged',
      judgmentSource: 'agent',
    };
  }

  if (email.aiSuggestedFolderRouteId === route.id) {
    return {
      score: email.aiSuggestedFolderConfidence ?? 0.8,
      reason: email.aiSuggestedFolderReason || 'agent suggested',
      judgmentSource: 'agent',
    };
  }

  const rule = (route.aiRule || route.description || '').toLowerCase();
  const text = emailRoutingText(email);
  const sender = (email.from || email.sender || '').toLowerCase();
  let score = 0;
  const reasons = [];

  const tokens = rule.split(/[^a-z0-9%]+/).filter((t) => t.length > 3 && !DESCRIPTOR_STOP_WORDS.has(t));
  const tokenHits = tokens.filter((t) => text.includes(t) || sender.includes(t));
  if (tokenHits.length) {
    score += Math.min(0.45, 0.12 + tokenHits.length * 0.08);
    reasons.push(`rule hint (${tokenHits[0]})`);
  }

  const intentHints = {
    promotion: 'promotions',
    promotional: 'promotions',
    promo: 'promotions',
    sale: 'promotions',
    marketing: 'promotions',
    newsletter: 'newsletters',
    digest: 'newsletters',
    receipt: 'receipts',
    invoice: 'receipts',
    order: 'receipts',
    alert: 'notifications',
    notification: 'notifications',
    linkedin: 'social',
    social: 'social',
  };
  for (const [word, intentId] of Object.entries(intentHints)) {
    if (rule.includes(word)) {
      const intentScore = scoreFolderIntent(email, intentId);
      if (intentScore.score > 0.25) {
        score = Math.max(score, intentScore.score * 0.9);
        reasons.push(intentScore.reason || `fits ${word}`);
      }
    }
  }

  score = Math.min(1, Math.max(0, score));
  if (score < 0.2) {
    return { score, reason: route.aiRule ? 'needs agent judgment' : '', judgmentSource: 'heuristic' };
  }
  return {
    score,
    reason: reasons[0] || 'matches your description',
    judgmentSource: 'heuristic',
  };
}

function scoreFolderIntent(email, intentId) {
  const spec = FOLDER_INTENTS[intentId];
  if (!spec) return { score: 0, reason: '' };

  const text = emailRoutingText(email);
  const sender = (email.from || email.sender || '').toLowerCase();
  const domain = sender.includes('@') ? sender.split('@')[1] : '';

  for (const neg of spec.negativeKeywords || []) {
    if (text.includes(neg)) return { score: 0.05, reason: 'looks transactional' };
  }

  let score = 0;
  const hits = (spec.keywords || []).filter((kw) => text.includes(kw));
  if (hits.length) score += Math.min(0.55, 0.18 + hits.length * 0.12);

  for (const hint of spec.senderHints || []) {
    if (sender.includes(hint) || domain.includes(hint)) {
      score += 0.22;
      break;
    }
  }

  if (email.isNewsletter) score += spec.newsletterBonus || 0;
  if (text.includes('unsubscribe')) score += spec.unsubscribeBonus || 0;
  if (/\d{1,3}\s*%/.test(text) && intentId === 'promotions') score += 0.2;

  if (email.folderIntent === intentId) score = Math.max(score, 0.85);
  if ((email.folderHints || []).includes(intentId)) score = Math.max(score, 0.75);

  score = Math.min(1, Math.max(0, score));
  if (score < 0.2) return { score, reason: '' };
  return { score, reason: spec.reason || 'matches category' };
}

function scoreRouteForEmail(email, route) {
  const type = route.matchType || 'keyword';
  const value = (route.matchValue || route.intent || '').toLowerCase();
  const text = emailRoutingText(email);
  const sender = (email.from || email.sender || '').toLowerCase();
  const domain = sender.includes('@') ? sender.split('@')[1] : '';

  if (type === 'descriptor') {
    return scoreDescriptorRoute(email, route);
  }
  if (type === 'intent') {
    const result = scoreFolderIntent(email, value || 'promotions');
    return { ...result, judgmentSource: result.score >= 0.75 ? 'agent' : 'heuristic' };
  }
  if (type === 'keyword' && value && text.includes(value)) {
    return { score: 1, reason: `strict: contains "${value}"`, judgmentSource: 'strict' };
  }
  if (type === 'domain' && value && domain === value) {
    return { score: 1, reason: `strict: domain ${value}`, judgmentSource: 'strict' };
  }
  if (type === 'sender' && value && sender === value) {
    return { score: 1, reason: 'strict: sender match', judgmentSource: 'strict' };
  }
  return { score: 0, reason: '', judgmentSource: 'none' };
}

function suggestRouteForEmail(email) {
  let best = null;
  let bestScore = 0;
  let bestReason = '';
  let bestSource = 'none';
  for (const route of getFolderRoutes()) {
    const { score, reason, judgmentSource } = scoreRouteForEmail(email, route);
    if (score > bestScore) {
      bestScore = score;
      best = route;
      bestReason = reason;
      bestSource = judgmentSource || 'none';
    }
  }
  if (!best || bestScore < INTENT_MATCH_THRESHOLD) return null;
  return { route: best, score: bestScore, reason: bestReason, judgmentSource: bestSource };
}
