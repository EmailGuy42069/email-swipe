#!/usr/bin/env python3
"""Intent-based folder routing signals — soft matching, not literal keywords."""

from __future__ import annotations

import re
from typing import Any

INTENT_DEFINITIONS: dict[str, dict[str, Any]] = {
    'promotions': {
        'label': 'Promotions & sales',
        'description': 'Marketing, deals, and sales blasts — even when the word "promo" is missing',
        'keywords': (
            'sale', 'sales', '% off', 'percent off', 'deal', 'deals', 'discount', 'save ',
            'limited time', 'shop now', 'buy now', 'free shipping', 'coupon', 'offer',
            'flash sale', 'clearance', 'exclusive offer', 'act now', 'don\'t miss',
            'special offer', 'lowest price', 'mega sale', 'today only',
            'new collection', 'new arrivals', 'just dropped', 'introducing', 'discover',
            'you\'ll love', 'styles', 'curated for you', 'picked for you', 'don\'t miss out',
        ),
        'sender_hints': (
            'promo', 'promotions', 'marketing', 'deals', 'offers', 'news@', 'email@',
            'mail@', 'info@', 'store@', 'shop@',
        ),
        'negative_keywords': (
            'receipt', 'invoice', 'order confirmed', 'payment received', 'your order',
            'shipped', 'delivery', 'tracking number', 'paid', 'statement',
        ),
        'newsletter_bonus': 0.12,
        'unsubscribe_bonus': 0.08,
    },
    'newsletters': {
        'label': 'Newsletters & digests',
        'description': 'Digests, list mail, and recurring content — often has unsubscribe',
        'keywords': (
            'newsletter', 'digest', 'weekly roundup', 'daily briefing', 'edition',
            'this week in', 'your update', 'substack', 'read online', 'view in browser',
        ),
        'sender_hints': ('newsletter', 'digest', 'substack', 'mailchi', 'campaign'),
        'negative_keywords': ('receipt', 'invoice', 'security alert', 'password reset'),
        'newsletter_bonus': 0.35,
        'unsubscribe_bonus': 0.25,
    },
    'receipts': {
        'label': 'Receipts & orders',
        'description': 'Purchases, payments, invoices, and shipping updates',
        'keywords': (
            'receipt', 'invoice', 'order confirmed', 'order #', 'payment received',
            'your purchase', 'transaction', 'billing', 'statement', 'shipped',
            'tracking', 'delivered', 'paid', 'amount charged',
        ),
        'sender_hints': (
            'receipt', 'billing', 'invoice', 'orders', 'payments', 'noreply@stripe',
            'paypal', 'shopify', 'amazon',
        ),
        'negative_keywords': ('% off', 'sale ends', 'limited time offer', 'unsubscribe'),
        'newsletter_bonus': 0.0,
        'unsubscribe_bonus': -0.15,
    },
    'notifications': {
        'label': 'Notifications & alerts',
        'description': 'Automated alerts, security, and system messages',
        'keywords': (
            'notification', 'alert', 'security alert', 'sign-in', 'login attempt',
            'verify', 'verification', 'password', '2fa', 'activity on your account',
            'new comment', 'mentioned you', 'assigned to you',
        ),
        'sender_hints': (
            'noreply', 'no-reply', 'notifications', 'alerts', 'security', 'accounts',
        ),
        'negative_keywords': ('unsubscribe', '% off', 'newsletter'),
        'newsletter_bonus': 0.0,
        'unsubscribe_bonus': -0.05,
    },
    'social': {
        'label': 'Social networks',
        'description': 'LinkedIn, X, Facebook, and similar social notifications',
        'keywords': (
            'connection request', 'viewed your profile', 'mentioned you', 'new follower',
            'liked your', 'commented on', 'invited you', 'people you may know',
        ),
        'sender_hints': (
            'linkedin', 'facebook', 'twitter', 'x.com', 'instagram', 'tiktok',
        ),
        'negative_keywords': (),
        'newsletter_bonus': 0.05,
        'unsubscribe_bonus': 0.05,
    },
}


def _email_text(email: dict) -> str:
    return f'{email.get("subject", "")} {email.get("snippet", "")}'.lower()


def _sender(email: dict) -> str:
    return (email.get('from') or email.get('sender', '')).lower()


def _domain(email: dict) -> str:
    s = _sender(email)
    return s.split('@')[1] if '@' in s else ''


def score_intent(email: dict, intent_id: str) -> tuple[float, str]:
    """Return (score 0–1, human reason) for routing suggestion."""
    spec = INTENT_DEFINITIONS.get(intent_id)
    if not spec:
        return 0.0, ''

    text = _email_text(email)
    sender = _sender(email)
    domain = _domain(email)
    score = 0.0
    reasons: list[str] = []

    for neg in spec.get('negative_keywords', ()):
        if neg in text:
            return 0.05, 'looks transactional, not promotional'

    kw_hits = [kw for kw in spec['keywords'] if kw in text]
    if kw_hits:
        score += min(0.55, 0.18 + len(kw_hits) * 0.12)
        reasons.append(kw_hits[0])

    for hint in spec.get('sender_hints', ()):
        if hint in sender or hint in domain:
            score += 0.22
            reasons.append(f'sender pattern ({hint})')
            break

    if email.get('isNewsletter'):
        score += spec.get('newsletter_bonus', 0.0)
        if spec.get('newsletter_bonus', 0) > 0.1:
            reasons.append('newsletter pattern')

    if 'unsubscribe' in text:
        score += spec.get('unsubscribe_bonus', 0.0)
        if spec.get('unsubscribe_bonus', 0) > 0.1:
            reasons.append('list mail')

    if re.search(r'\d{1,3}\s*%', text) and intent_id == 'promotions':
        score += 0.2
        reasons.append('discount %')

    if email.get('folderIntent') == intent_id:
        score = max(score, 0.85)
        reasons.append('agent tagged')

    hints = email.get('folderHints') or []
    if intent_id in hints:
        score = max(score, 0.75)
        reasons.append('agent hint')

    score = min(1.0, max(0.0, score))
    if score < 0.2:
        return score, ''

    reason_map = {
        'promotions': 'looks promotional',
        'newsletters': 'looks like a newsletter',
        'receipts': 'looks like a receipt or order',
        'notifications': 'looks like an alert',
        'social': 'looks like social mail',
    }
    primary = reason_map.get(intent_id, 'matches category')
    if reasons:
        primary = f'{primary} ({reasons[0]})'
    return round(score, 2), primary


def score_descriptor(email: dict, route: dict) -> tuple[float, str]:
    """AI-rule route: agent judgment first, then soft descriptor heuristics."""
    route_id = route.get('id', '')
    for judgment in email.get('folderJudgments') or email.get('aiFolderMatches') or []:
        if judgment.get('routeId') == route_id or judgment.get('folderRouteId') == route_id:
            conf = float(judgment.get('confidence', 0.85))
            return min(1.0, max(0.0, conf)), judgment.get('reason') or 'agent judged'

    if email.get('aiSuggestedFolderRouteId') == route_id:
        conf = float(email.get('aiSuggestedFolderConfidence', 0.8))
        return conf, email.get('aiSuggestedFolderReason') or 'agent suggested'

    rule = (route.get('aiRule') or route.get('description') or '').lower()
    text = _email_text(email)
    sender = _sender(email)
    stop = {'all', 'the', 'and', 'for', 'put', 'this', 'that', 'with', 'from', 'into', 'your', 'mail', 'email', 'folder'}
    tokens = [t for t in re.split(r'[^a-z0-9%]+', rule) if len(t) > 3 and t not in stop]
    hits = [t for t in tokens if t in text or t in sender]
    score = min(0.45, 0.12 + len(hits) * 0.08) if hits else 0.0

    intent_bridge = {
        'promotion': 'promotions', 'promotional': 'promotions', 'promo': 'promotions',
        'sale': 'promotions', 'marketing': 'promotions', 'newsletter': 'newsletters',
        'receipt': 'receipts', 'invoice': 'receipts', 'alert': 'notifications',
    }
    reason = f'rule hint ({hits[0]})' if hits else ''
    for word, intent_id in intent_bridge.items():
        if word in rule:
            s, r = score_intent(email, intent_id)
            if s > 0.25:
                score = max(score, s * 0.9)
                reason = r or reason

    if score < 0.2:
        return score, 'needs agent judgment' if rule else ''
    return round(min(1.0, score), 2), reason or 'matches your description'


def score_route(email: dict, route: dict) -> tuple[float, str]:
    """Score a folder route against an email."""
    match_type = route.get('matchType', 'keyword')
    match_value = (route.get('matchValue') or '').lower()
    text = _email_text(email)
    sender = _sender(email)
    domain = _domain(email)

    if match_type == 'descriptor':
        return score_descriptor(email, route)

    if match_type == 'intent':
        return score_intent(email, match_value or route.get('intent', 'promotions'))

    if match_type == 'keyword' and match_value and match_value in text:
        return 1.0, f'contains "{match_value}"'
    if match_type == 'domain' and match_value and domain == match_value:
        return 1.0, f'domain {match_value}'
    if match_type == 'sender' and match_value and sender == match_value:
        return 1.0, 'sender match'

    return 0.0, ''


def best_route(email: dict, routes: list[dict], min_score: float = 0.32) -> tuple[dict | None, float, str]:
    best = None
    best_score = 0.0
    best_reason = ''
    for route in routes:
        s, reason = score_route(email, route)
        if s > best_score:
            best_score = s
            best = route
            best_reason = reason
    if best_score < min_score:
        return None, best_score, best_reason
    return best, best_score, best_reason


def intent_options() -> list[dict]:
    return [
        {'id': k, 'label': v['label'], 'description': v['description']}
        for k, v in INTENT_DEFINITIONS.items()
    ]
