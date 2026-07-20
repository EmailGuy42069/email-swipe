/**
 * Baseline Predictions Module for Email Swipe
 * Makes predictions from email #1 using heuristics + agent knowledge
 */

const BaselinePredictor = (function() {
  'use strict';

  // ============================================================
  // HEURISTIC RULES
  // ============================================================

  const SPAM_INDICATORS = {
    // Subject line patterns
    subjectPatterns: [
      { pattern: /\b(unsubscribe|opt-out|manage preferences)\b/i, weight: 0.6, reason: 'Newsletter/marketing language' },
      { pattern: /\b(sale|discount|% off|limited time|offer ends)\b/i, weight: 0.5, reason: 'Promotional content' },
      { pattern: /\b(act now|urgent|don'?t miss|last chance)\b/i, weight: 0.55, reason: 'Urgency marketing' },
      { pattern: /\b(webinar|free download|whitepaper|ebook)\b/i, weight: 0.4, reason: 'Lead generation' },
      { pattern: /\b(monthly|weekly|daily)\s+(newsletter|digest|update)\b/i, weight: 0.45, reason: 'Bulk newsletter' },
      { pattern: /^re:\s*$/i, weight: 0.3, reason: 'Empty reply (suspicious)' },
    ],
    // Sender patterns
    senderPatterns: [
      { pattern: /^no-?reply@/i, weight: 0.35, reason: 'Automated sender' },
      { pattern: /marketing@/i, weight: 0.5, reason: 'Marketing department' },
      { pattern: /newsletter@/i, weight: 0.5, reason: 'Newsletter sender' },
      { pattern: /notifications@/i, weight: 0.25, reason: 'Notification bot' },
      { pattern: /(mailchimp|sendgrid|constantcontact|klaviyo)/i, weight: 0.4, reason: 'Email marketing platform' },
    ],
    // Body snippet patterns
    bodyPatterns: [
      { pattern: /\b(unsubscribe|opt out|update preferences)\b/i, weight: 0.5, reason: 'Contains unsubscribe footer' },
      { pattern: /\b(privacy policy|terms of service)\b.*\b(unsubscribe|opt out)\b/i, weight: 0.55, reason: 'Standard marketing footer' },
      { pattern: /\b(promotional|marketing)\s+(emails|messages|communications)\b/i, weight: 0.5, reason: 'Marketing classification' },
    ],
  };

  const IMPORTANT_INDICATORS = {
    subjectPatterns: [
      { pattern: /\b(invoice|payment received|receipt|order confirmed)\b/i, weight: 0.6, reason: 'Transaction confirmation' },
      { pattern: /\b(your\s+(order|shipment|delivery))\b/i, weight: 0.55, reason: 'Order/shipping update' },
      { pattern: /\b(password reset|verify your|security alert|login attempt)\b/i, weight: 0.7, reason: 'Security-related' },
      { pattern: /\b(verification code|2fa|two.factor|auth code)\b/i, weight: 0.75, reason: 'Authentication code' },
      { pattern: /\b(meeting|calendar|invited you|accepted|declined)\b/i, weight: 0.5, reason: 'Calendar event' },
      { pattern: /\b(your account|subscription|plan|billing)\b/i, weight: 0.45, reason: 'Account activity' },
      { pattern: /\b(action required|please confirm|verify)\b/i, weight: 0.4, reason: 'Requires user action' },
      { pattern: /\b(aws|amazon web services|vercel|netlify|github|stripe)\b.*\b(bill|invoice|usage|alert)\b/i, weight: 0.65, reason: 'Infrastructure/billing alert' },
      { pattern: /\b(deployment|build failed|error|routing)\b/i, weight: 0.55, reason: 'DevOps alert' },
    ],
    senderPatterns: [
      { pattern: /(support|help|security|billing|legal|admin)@/i, weight: 0.35, reason: 'Official department' },
      { pattern: /(aws\.amazon\.com|vercel\.com|github\.com|stripe\.com|paypal\.com)/i, weight: 0.4, reason: 'Critical service provider' },
      { pattern: /(calendly|zoom|calendar|google\.com.*calendar)/i, weight: 0.35, reason: 'Scheduling service' },
      { pattern: /(bank|credit union|investment|401k|retirement)/i, weight: 0.5, reason: 'Financial institution' },
      { pattern: /(irs|gov|tax|revenue)/i, weight: 0.6, reason: 'Government/tax' },
    ],
    bodyPatterns: [
      { pattern: /\$[\d,]+\.\d{2}/, weight: 0.4, reason: 'Contains dollar amount' },
      { pattern: /\b(total|amount|charged|paid|refund)\b.*\$/, weight: 0.45, reason: 'Payment information' },
    ],
  };

  const KEEP_INDICATORS = {
    subjectPatterns: [
      { pattern: /\b(welcome|getting started|new account)\b/i, weight: 0.3, reason: 'Onboarding email' },
      { pattern: /\b(update|changelog|new features|release)\b/i, weight: 0.25, reason: 'Product update' },
      { pattern: /\b(invitation|invited|joined)\b/i, weight: 0.35, reason: 'Invitation' },
    ],
    senderPatterns: [
      { pattern: /(founder|ceo|team)@/i, weight: 0.3, reason: 'Company leadership' },
      { pattern: /(product|engineering|design|updates)@/i, weight: 0.25, reason: 'Product/team updates' },
    ],
  };

  // ============================================================
  // GENERIC SERVICE HINTS (optional cold-start boosts)
  // ============================================================

  const SERVICE_HINTS = {
    infrastructureServices: [
      'aws.amazon.com', 'vercel.com', 'netlify.com', 'github.com',
      'railway.app', 'render.com', 'fly.io', 'digitalocean.com',
      'cloudflare.com', 'supabase.io', 'neon.tech',
    ],
    businessServices: [
      'stripe.com', 'paypal.com', 'wise.com', 'mercury.com',
      'brex.com', 'ramp.com', 'gusto.com', 'rippling.com',
    ],
    collabServices: [
      'slack.com', 'notion.so', 'linear.app', 'figma.com',
      'loom.com', 'zoom.us', 'calendly.com',
    ],
  };

  function checkUserProfile(email) {
    const sender = (email.sender || '') + ' ' + (email.from || '').toLowerCase();
    const subject = (email.subject || '').toLowerCase();
    let adjustments = { spam: 0, important: 0, keep: 0 };
    let reasons = [];

    SERVICE_HINTS.infrastructureServices.forEach((domain) => {
      if (sender.includes(domain)) {
        adjustments.important += 0.3;
        if (subject.includes('bill') || subject.includes('usage') || subject.includes('alert')) {
          adjustments.important += 0.2;
        }
        reasons.push('Infrastructure service');
      }
    });

    SERVICE_HINTS.businessServices.forEach((domain) => {
      if (sender.includes(domain)) {
        adjustments.important += 0.25;
        reasons.push('Business/financial service');
      }
    });

    SERVICE_HINTS.collabServices.forEach((domain) => {
      if (sender.includes(domain)) {
        if (subject.includes('invited') || subject.includes('meeting') || subject.includes('reminder')) {
          adjustments.important += 0.3;
          reasons.push('Calendar/scheduling invite');
        } else {
          adjustments.keep += 0.2;
          reasons.push('Collaboration tool notification');
        }
      }
    });

    if (/\b(recruiter|recruiting|talent|hiring)\b/i.test(subject)
        || /\b(opportunity|position|role|career)\b/i.test(subject)) {
      const isKnownService = SERVICE_HINTS.infrastructureServices.some((d) => sender.includes(d))
        || SERVICE_HINTS.businessServices.some((d) => sender.includes(d));
      if (!isKnownService) {
        adjustments.spam += 0.4;
        reasons.push('Recruiting outreach');
      }
    }

    if (/\b(seo|marketing agency|lead generation|growth hacking)\b/i.test(subject + ' ' + sender)) {
      adjustments.spam += 0.5;
      reasons.push('Marketing agency outreach');
    }

    return { adjustments, reasons };
  }

  // ============================================================
  // PREDICTION ENGINE
  // ============================================================

  function calculateScore(email, patterns) {
    let score = 0;
    let reasons = [];
    const maxWeight = 1.0;

    const text = [
      email.subject || '',
      email.snippet || '',
      email.sender || '',
      email.from || ''
    ].join(' ');

    // Check subject patterns
    patterns.subjectPatterns?.forEach(rule => {
      if (rule.pattern.test(email.subject || '')) {
        score += rule.weight;
        if (!reasons.find(r => r === rule.reason)) {
          reasons.push(rule.reason);
        }
      }
    });

    // Check sender patterns
    patterns.senderPatterns?.forEach(rule => {
      const senderText = (email.sender || '') + ' ' + (email.from || '');
      if (rule.pattern.test(senderText)) {
        score += rule.weight;
        if (!reasons.find(r => r === rule.reason)) {
          reasons.push(rule.reason);
        }
      }
    });

    // Check body patterns
    patterns.bodyPatterns?.forEach(rule => {
      if (rule.pattern.test(email.snippet || '')) {
        score += rule.weight;
        if (!reasons.find(r => r === rule.reason)) {
          reasons.push(rule.reason);
        }
      }
    });

    return { score: Math.min(score, maxWeight), reasons };
  }

  function normalizeConfidence(rawScore) {
    // Convert accumulated score to 0-1 range with dampening
    // Score of 0.5 = ~75% confidence, score of 1.0 = ~95% confidence
    const confidence = 0.5 + (Math.min(rawScore, 1.0) * 0.45);
    return Math.round(confidence * 100) / 100;
  }

  // ============================================================
  // PUBLIC API
  // ============================================================

  /**
   * Predict action for an email using baseline heuristics
   * @param {Object} email - Email object with subject, sender, from, snippet
   * @returns {Object} Prediction with action, confidence, and reasoning
   */
  function predict(email) {
    if (!email || typeof email !== 'object') {
      return {
        action: 'keep',
        confidence: 0.5,
        source: 'baseline-heuristic',
        reasoning: 'Insufficient data for prediction',
      };
    }

    // Calculate scores for each action
    const spamScore = calculateScore(email, SPAM_INDICATORS);
    const importantScore = calculateScore(email, IMPORTANT_INDICATORS);
    const keepScore = calculateScore(email, KEEP_INDICATORS);

    // Apply user profile adjustments
    const profile = checkUserProfile(email);

    // Final scores
    const scores = {
      spam: spamScore.score + profile.adjustments.spam,
      important: importantScore.score + profile.adjustments.important,
      keep: keepScore.score + profile.adjustments.keep + 0.1, // slight bias toward keep
    };

    // Determine winner
    let action = 'keep';
    let maxScore = scores.keep;
    const reasons = [...keepScore.reasons];

    if (scores.spam > maxScore) {
      action = 'spam';
      maxScore = scores.spam;
      reasons.length = 0;
      reasons.push(...spamScore.reasons);
    }

    if (scores.important > maxScore) {
      action = 'important';
      maxScore = scores.important;
      reasons.length = 0;
      reasons.push(...importantScore.reasons);
    }

    // Add profile-based reasons if they contributed
    reasons.push(...profile.reasons);

    // Remove duplicates and limit
    const uniqueReasons = [...new Set(reasons)].slice(0, 3);

    // Format reasoning
    let reasoning = uniqueReasons.length > 0
      ? uniqueReasons.join('; ')
      : 'No strong indicators (defaulting to keep)';

    // Add "Based on:" prefix for clarity
    reasoning = uniqueReasons.length > 0
      ? `Based on: ${reasoning}`
      : reasoning;

    return {
      action,
      confidence: normalizeConfidence(maxScore),
      source: 'baseline-heuristic',
      reasoning,
      details: {
        scores,
        rawScores: {
          spam: spamScore.score,
          important: importantScore.score,
          keep: keepScore.score,
        },
        profileAdjustments: profile.adjustments,
      },
    };
  }

  /**
   * Batch predict for multiple emails
   * @param {Array} emails - Array of email objects
   * @returns {Array} Predictions for each email
   */
  function predictBatch(emails) {
    return emails.map(email => ({
      emailId: email.id,
      ...predict(email),
    }));
  }

  /**
   * Get explanation of why an email was classified a certain way
   * @param {Object} prediction - Prediction result from predict()
   * @returns {string} Human-readable explanation
   */
  function explain(prediction) {
    const confidencePercent = Math.round(prediction.confidence * 100);
    return `${prediction.action.toUpperCase()} (${confidencePercent}% confidence)\n${prediction.reasoning}`;
  }

  /**
   * Check if an email is a newsletter/marketing email
   * @param {Object} email - Email object
   * @returns {boolean}
   */
  function isMarketing(email) {
    const pred = predict(email);
    return pred.action === 'spam' && pred.confidence > 0.6;
  }

  /**
   * Check if an email is likely a receipt/invoice
   * @param {Object} email - Email object
   * @returns {boolean}
   */
  function isReceipt(email) {
    const pred = predict(email);
    return pred.action === 'important' &&
           (email.subject || '').match(/\b(invoice|receipt|payment|order)\b/i) !== null;
  }

  // Return public API
  return {
    predict,
    predictBatch,
    explain,
    isMarketing,
    isReceipt,
    // Expose constants for debugging
    SPAM_INDICATORS,
    IMPORTANT_INDICATORS,
    USER_PROFILE,
  };
})();

// Export for different module systems
if (typeof module !== 'undefined' && module.exports) {
  module.exports = BaselinePredictor;
}

if (typeof window !== 'undefined') {
  window.BaselinePredictor = BaselinePredictor;
}
