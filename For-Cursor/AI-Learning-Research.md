# Email Preference Learning - Research for Cursor

## Executive Summary

We need "magic" under the hood that makes users feel like they're actually training an AI, not just creating a yes/no list. After researching, here are the 4 approaches ranked by impact vs effort.

---

## 1. SEMANTIC SIMILARITY ENGINE (Highest Impact)

### What It Does
Converts email text into mathematical vectors (embeddings) and finds similar emails to ones the user already sorted. Shows confidence scores like "This email is 94% similar to ones you marked as spam."

### Why It Creates "Magic"
- Users see the AI "understanding" email content, not just matching sender names
- Confidence scores ("92% spam") make the learning feel tangible
- Works with as few as 5-10 examples
- Surfaces emails most similar to training data first

### Best Implementation
**sentence-transformers** (Hugging Face)
- Repo: https://github.com/huggingface/sentence-transformers
- Model: `all-MiniLM-L6-v2` (fast, 22M parameters, good quality)
- Alternative: `all-mpnet-base-v2` (better quality, slower)

### How It Works
```python
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

model = SentenceTransformer('all-MiniLM-L6-v2')

# User's training data
spam_emails = ["Weekly newsletter...", "Promotional offer..."]
spam_embeddings = model.encode(spam_emails)

# New email arrives
new_email = "Monthly digest from TechCo"
new_embedding = model.encode([new_email])

# Calculate similarity
similarity = cosine_similarity(new_embedding, spam_embeddings)
# Result: [[0.94, 0.87]] - 94% and 87% similar to spam examples
```

### Pros
- Fast inference (milliseconds per email)
- No training required (pre-trained model)
- Works offline (model runs locally)
- Explains decisions ("similar to emails you marked as spam")

### Cons
- Requires ~50MB model download
- Similarity is semantic, not always action-based

---

## 2. ACTIVE LEARNING (High Impact, Medium Effort)

### What It Does
The system identifies emails it's most uncertain about and prioritizes them for user review. Each user decision provides maximum learning value.

### Why It Creates "Magic"
- System asks for help on specific emails: "I'm unsure about this one"
- Feels collaborative: "Help me learn"
- Dramatically reduces training data needed (10x fewer examples)
- Surfaces edge cases that would otherwise be misclassified

### Best Implementation
**modAL** (Active Learning framework)
- Repo: https://github.com/modAL-python/modAL
- Also see: https://github.com/orobix/active-learning (wraps modAL with extras)

### How It Works
```python
from modAL.models import ActiveLearner
from sklearn.ensemble import RandomForestClassifier

# Initialize with small amount of labeled data
learner = ActiveLearner(
    estimator=RandomForestClassifier(),
    X_training=X_initial, y_training=y_initial
)

# Pool of unlabeled emails
pool = X_unlabeled

# Query most uncertain email for user to label
query_idx, query_instance = learner.query(pool, n_instances=1)
uncertainty = 1 - max(learner.predict_proba(query_instance)[0])
# Show user: "I'm only 45% confident about this email"

# After user labels it, teach the learner
learner.teach(query_instance, user_label)
```

### Uncertainty Strategies
- **Uncertainty Sampling**: Highest entropy (closest to 50/50)
- **Margin Sampling**: Smallest gap between top 2 predictions
- **Entropy**: Most chaotic prediction distribution

### Pros
- Maximizes learning per user action
- Reduces labeling fatigue
- Adapts to user's specific patterns

### Cons
- Requires maintaining a "pool" of unlabeled emails
- More complex UI (need to explain uncertainty)

---

## 3. SMART BATCHING / CLUSTERING (Medium Impact, Low Effort)

### What It Does
Groups similar emails together so the user can sort one and apply the decision to the batch. Uses unsupervised clustering to find natural email groups.

### Why It Creates "Magic"
- "12 newsletters detected" - user sorts one, batch-apply
- Surprises users with patterns they didn't notice
- Speeds up triage significantly

### Best Implementation
**HDBSCAN** (Hierarchical Density-Based Clustering)
- Repo: https://github.com/scikit-learn-contrib/hdbscan
- Better than K-means for text (doesn't force spherical clusters)
- Alternative: Agglomerative Clustering from scikit-learn

### How It Works
```python
from sentence_transformers import SentenceTransformer
import hdbscan

# Embed all emails
model = SentenceTransformer('all-MiniLM-L6-v2')
emails = ["Email 1...", "Email 2...", "Email 3..."]
embeddings = model.encode(emails)

# Cluster them
clusterer = hdbscan.HDBSCAN(min_cluster_size=3)
labels = clusterer.fit_predict(embeddings)

# Result: labels like [0, 0, 1, 0, 2, 2] - emails 0,1,3 are similar
```

### Alternative: Simple Heuristics
Don't even need ML:
- Same sender domain → batch
- Subject contains same keywords → batch
- Similar timestamp patterns → batch

### Pros
- No training data needed (unsupervised)
- Immediate visual impact
- Users love batch operations

### Cons
- Clusters might not align with user preferences
- Needs UI for batch confirmation

---

## 4. PATTERN DISCOVERY (Medium Impact, High Effort)

### What It Does
Mines user's sorting history to discover explicit patterns: "You always archive marketing emails on weekends" or "You keep receipts from Amazon."

### Why It Creates "Magic"
- "I noticed you..." feels like the system is paying attention
- Surfaces user's own unconscious patterns
- Builds trust by explaining behavior

### Best Implementation
**Association Rule Learning** (Apriori or FP-Growth)
- Library: `mlxtend` (https://github.com/rasbt/mlxtend)
- Also: Manual pattern mining with pandas

### How It Works
```python
from mlxtend.frequent_patterns import apriori, association_rules
import pandas as pd

# Convert swipes to transaction format
# Each row: email features + action
data = pd.DataFrame([
    {'is_newsletter': True, 'domain': 'marketing.com', 'day': 'Saturday', 'action': 'archive'},
    {'is_newsletter': True, 'domain': 'marketing.com', 'day': 'Sunday', 'action': 'archive'},
    {'is_receipt': True, 'domain': 'amazon.com', 'action': 'keep'},
])

# Find frequent patterns
frequent_items = apriori(data, min_support=0.3)
rules = association_rules(frequent_items, metric="confidence", min_threshold=0.8)

# Results: "IF domain=marketing.com AND day=weekend THEN action=archive (90% confidence)"
```

### Manual Approach (Easier)
Just query the data:
```python
# Find sender domains always marked spam
sender_actions = df.groupby('sender_domain')['action'].value_counts()
patterns = sender_actions[sender_actions > 3]  # 3+ emails, same action
```

### Pros
- "Aha!" moments for users
- Creates explainable rules
- Good for building user trust

### Cons
- Requires significant data (20+ swipes minimum)
- Patterns might be spurious (correlation ≠ causation)
- Harder to implement well

---

## RECOMMENDATION

### Phase 1: Semantic Similarity (Week 1)
- Implement sentence-transformers
- Show confidence scores in UI
- Sort email queue by similarity to training examples

### Phase 2: Active Learning (Week 2-3)
- Add uncertainty-based email ordering
- Show "Help me learn" prompts for low-confidence emails
- Track learning curve (accuracy vs examples)

### Phase 3: Smart Batching (Week 4)
- Cluster remaining emails
- Offer batch operations
- Group by sender domain as MVP

### Skip for Now: Pattern Discovery
- High effort, medium impact
- Can surface simple patterns manually ("You always archive @marketing.com")

---

## KEY REPOSITORIES

| Approach | Primary Repo | License | Stars |
|----------|--------------|---------|-------|
| Semantic Similarity | huggingface/sentence-transformers | Apache 2.0 | 15k+ |
| Active Learning | modAL-python/modAL | MIT | 1.5k+ |
| Active Learning (wrapper) | orobix/active-learning | MIT | 300+ |
| Clustering | scikit-learn-contrib/hdbscan | BSD | 3k+ |
| Pattern Mining | rasbt/mlxtend | BSD | 5k+ |

---

## TECHNICAL NOTES

### Sentence-Transformers Models Comparison

| Model | Size | Speed | Quality | Use Case |
|-------|------|-------|---------|----------|
| all-MiniLM-L6-v2 | 22MB | Fast | Good | Production, mobile |
| all-mpnet-base-v2 | 110MB | Medium | Better | Desktop, accuracy-focused |
| paraphrase-MiniLM-L3-v2 | 13MB | Very Fast | OK | Embedded, resource-constrained |

### Running Locally vs API

**Local (Recommended)**
- No latency
- No API costs
- Privacy (emails stay local)
- ~50MB model download once

**API (OpenAI, etc)**
- Better quality (GPT-4 embeddings)
- Higher latency
- Privacy concerns
- Costs money

---

## USER EXPERIENCE FLOW

1. User swipes 5 emails
2. System embeds those 5 examples
3. Next email shown is the one most similar to training data
4. Confidence score displayed: "85% similar to your spam"
5. Uncertain emails (confidence 40-60%) get "Help me learn" badge
6. After 20 swipes, offer batch operation on detected clusters

---

*Research compiled for Cursor implementation*
*Date: 2026-07-01*
