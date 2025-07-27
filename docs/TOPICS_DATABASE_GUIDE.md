# Topics and Interests in YSocial: Database Storage and Client Access Guide

This document explains how topics assigned to experiments are stored in the YSocial database and how client applications can access these values.

## Overview

YSocial uses a dual-database architecture to manage topics and interests:

1. **Dashboard Database** (`database_dashboard.db`): Used by the admin panel for experiment configuration
2. **Experiment Database** (`database_clean_server.db`): Used at runtime for actual social media simulation

## Database Schema

### Dashboard Database (Admin Configuration)

#### Topic Management Tables

```sql
-- Master list of all available topics
CREATE TABLE topic_list (
    id   SERIAL PRIMARY KEY,
    name TEXT
);

-- Links experiments to their assigned topics
CREATE TABLE exp_topic (
    id       SERIAL PRIMARY KEY,
    exp_id   INTEGER NOT NULL REFERENCES exps(idexp) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topic_list(id) ON DELETE CASCADE
);

-- Links pages to topics (for news aggregation)
CREATE TABLE page_topic (
    id       SERIAL PRIMARY KEY,
    page_id  INTEGER REFERENCES pages(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topic_list(id) ON DELETE CASCADE
);
```

### Experiment Database (Runtime)

#### Interest and Topic Tracking Tables

```sql
-- Runtime interests (can be different from admin topics)
CREATE TABLE interests (
    iid      SERIAL PRIMARY KEY,
    interest TEXT
);

-- User interests for each round
CREATE TABLE user_interest (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES user_mgmt(id) ON DELETE CASCADE,
    interest_id INTEGER REFERENCES interests(iid) ON DELETE CASCADE,
    round_id    INTEGER REFERENCES rounds(id) ON DELETE CASCADE
);

-- Post topic classification
CREATE TABLE post_topics (
    id       SERIAL PRIMARY KEY,
    post_id  INTEGER REFERENCES post(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES interests(iid) ON DELETE CASCADE
);

-- Article topic classification
CREATE TABLE article_topics (
    id         SERIAL PRIMARY KEY,
    article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    topic_id   INTEGER REFERENCES interests(iid) ON DELETE CASCADE,
    CONSTRAINT article_topic UNIQUE (article_id, topic_id)
);
```

## How Topics Are Stored

### 1. Experiment Topic Assignment

When an experiment is created in the admin panel, topics are assigned to it through the `exp_topic` table:

```python
# Example: Assigning topics to an experiment
experiment_id = 1
topic_ids = [1, 2, 3]  # Technology, Politics, Sports

for topic_id in topic_ids:
    exp_topic = Exp_Topic(exp_id=experiment_id, topic_id=topic_id)
    db.session.add(exp_topic)
db.session.commit()
```

### 2. Runtime Interest Management

During experiment execution, the assigned topics are used to:
- Generate user interests
- Classify content (posts, articles)
- Drive recommendation algorithms

## Client Access Patterns

### 1. Getting Experiment Topics (Admin API)

#### Endpoint: `/admin/topic_data`
Retrieves all available topics with search, sorting, and pagination support.

**Request Parameters:**
- `search` (optional): Filter topics by name
- `sort` (optional): Sort specification (e.g., "+name", "-name")
- `start` (optional): Pagination offset
- `length` (optional): Number of items per page

**Response Format:**
```json
{
    "data": [
        {"id": 1, "name": "Technology"},
        {"id": 2, "name": "Politics"},
        {"id": 3, "name": "Sports"}
    ],
    "total": 25
}
```

**Implementation:**
```python
@experiments.route("/admin/topic_data")
@login_required
def topic_data():
    query = Topic_List.query

    # Search filter
    search = request.args.get("search")
    if search:
        query = query.filter(Topic_List.name.like(f"%{search}%"))
    
    # Sorting
    sort = request.args.get("sort")
    if sort:
        order = []
        for s in sort.split(","):
            direction = s[0]  # + or -
            name = s[1:]      # column name
            col = getattr(Topic_List, name)
            if direction == "-":
                col = col.desc()
            order.append(col)
        if order:
            query = query.order_by(*order)

    # Pagination
    start = request.args.get("start", type=int, default=-1)
    length = request.args.get("length", type=int, default=-1)
    if start != -1 and length != -1:
        query = query.offset(start).limit(length)

    topics = query.all()
    return {
        "data": [{"id": t.id, "name": t.name} for t in topics],
        "total": Topic_List.query.count()
    }
```

#### Usage Examples:
```bash
# Get all topics
GET /admin/topic_data

# Search for topics containing "tech"
GET /admin/topic_data?search=tech

# Get topics with pagination
GET /admin/topic_data?start=0&length=10

# Get topics sorted by name descending
GET /admin/topic_data?sort=-name

# Combined: search, sort, and paginate
GET /admin/topic_data?search=pol&sort=+name&start=0&length=5
```

### 2. Getting Topics for Specific Experiment

```python
# Get all topics assigned to an experiment
def get_experiment_topics(exp_id):
    topics = Exp_Topic.query.filter_by(exp_id=exp_id).all()
    topic_ids = [t.topic_id for t in topics]
    
    topics_list = (
        db.session.query(Topic_List)
        .filter(Topic_List.id.in_(topic_ids))
        .all()
    )
    
    return [t.name for t in topics_list]

# Example usage
experiment_topics = get_experiment_topics(1)
# Returns: ["Technology", "Politics", "Sports"]
```

### 3. User Interest Access (Runtime Database)

```python
# Get user interests for recommendation system
def get_user_interests(user_id, last_rounds=36):
    last_round = Rounds.query.order_by(Rounds.id.desc()).first()
    last_round_id = last_round.id if last_round else 0

    interests = (
        db.session.query(
            Interests.interest,
            User_interest.interest_id,
            func.count(User_interest.interest_id).label("count")
        )
        .join(User_interest, Interests.iid == User_interest.interest_id)
        .filter(
            User_interest.user_id == user_id,
            User_interest.round_id >= last_round_id - last_rounds
        )
        .group_by(Interests.interest, User_interest.interest_id)
        .order_by(desc("count"))
        .all()
    )
    
    return [(interest, interest_id, count) for interest, interest_id, count in interests]
```

### 4. Trending Topics Access

```python
# Get trending topics across the platform
def get_trending_topics(limit=10, window=120):
    last_round_obj = Rounds.query.order_by(desc(Rounds.id)).first()
    last_round = last_round_obj.id if last_round_obj else 0

    trending = (
        db.session.query(
            Interests.iid,
            Interests.interest,
            func.count(Post_topics.topic_id).label("count")
        )
        .join(Post_topics, Post_topics.topic_id == Interests.iid)
        .join(Post, Post.id == Post_topics.post_id)
        .filter(Post.round >= last_round - window)
        .group_by(Interests.iid, Interests.interest)
        .order_by(desc("count"))
        .limit(limit)
        .all()
    )
    
    return trending
```

### 5. Post Topic Classification Access

```python
# Get topics for a specific post
def get_post_topics(post_id):
    post_topics = (
        db.session.query(Interests.interest, Post_topics.topic_id)
        .join(Post_topics, Interests.iid == Post_topics.topic_id)
        .filter(Post_topics.post_id == post_id)
        .all()
    )
    
    return [{"topic": topic, "topic_id": topic_id} for topic, topic_id in post_topics]
```

## API Endpoints for Client Applications

### Admin Panel Endpoints

| Endpoint | Method | Purpose | Authentication |
|----------|--------|---------|----------------|
| `/admin/topic_data` | GET | List all topics with search/pagination | Required |
| `/admin/create_topic` | POST | Create new topic | Required |
| `/admin/delete_topic/<id>` | DELETE | Delete topic | Required |

### Data Access Functions (Internal API)

These functions are available within the Flask application context:

| Function | Purpose | Database |
|----------|---------|----------|
| `get_experiment_topics(exp_id)` | Get topics for experiment | Dashboard |
| `get_user_interests(user_id)` | Get user's interests | Experiment |
| `get_trending_topics(limit, window)` | Get trending topics | Experiment |
| `get_post_topics(post_id)` | Get topics for post | Experiment |

## Client Integration Examples

### 1. Web Interface Integration

```javascript
// Fetch topics for experiment configuration
async function loadExperimentTopics(experimentId) {
    const response = await fetch(`/api/experiment/${experimentId}/topics`);
    const topics = await response.json();
    return topics;
}

// Load trending topics for dashboard
async function loadTrendingTopics() {
    const response = await fetch('/api/trending-topics?limit=10');
    const trending = await response.json();
    return trending;
}
```

### 2. External Client Applications

```python
import requests

class YSocialClient:
    def __init__(self, base_url, auth_token):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {auth_token}"}
    
    def get_experiment_topics(self, experiment_id):
        """Get topics assigned to a specific experiment"""
        url = f"{self.base_url}/api/experiment/{experiment_id}/topics"
        response = requests.get(url, headers=self.headers)
        return response.json()
    
    def get_user_interests(self, user_id):
        """Get interests for a specific user"""
        url = f"{self.base_url}/api/user/{user_id}/interests"
        response = requests.get(url, headers=self.headers)
        return response.json()
    
    def get_trending_topics(self, limit=10):
        """Get currently trending topics"""
        url = f"{self.base_url}/api/trending-topics?limit={limit}"
        response = requests.get(url, headers=self.headers)
        return response.json()

# Usage example
client = YSocialClient("http://localhost:8080", "your_auth_token")
topics = client.get_experiment_topics(1)
user_interests = client.get_user_interests(123)
trending = client.get_trending_topics(5)
```

### 3. Database Direct Access

For applications with direct database access:

```python
from sqlalchemy import create_engine, text

# Dashboard database connection
dashboard_engine = create_engine('sqlite:///data_schema/database_dashboard.db')

# Get experiment topics
def get_experiment_topics_direct(exp_id):
    with dashboard_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT tl.name 
            FROM exp_topic et 
            JOIN topic_list tl ON et.topic_id = tl.id 
            WHERE et.exp_id = :exp_id
        """), {"exp_id": exp_id})
        return [row[0] for row in result]

# Experiment database connection
experiment_engine = create_engine('sqlite:///data_schema/database_clean_server.db')

# Get user interests
def get_user_interests_direct(user_id):
    with experiment_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT i.interest, COUNT(*) as frequency
            FROM user_interest ui
            JOIN interests i ON ui.interest_id = i.iid
            WHERE ui.user_id = :user_id
            GROUP BY i.interest
            ORDER BY frequency DESC
        """), {"user_id": user_id})
        return [(row[0], row[1]) for row in result]
```

## Data Flow Summary

1. **Configuration Phase**: Admin assigns topics to experiments via dashboard (`topic_list` → `exp_topic`)
2. **Initialization Phase**: Client configurations include assigned topics
3. **Runtime Phase**: 
   - User interests are generated based on experiment topics
   - Content is classified using topic models
   - Recommendations use topic/interest matching
4. **Access Phase**: Client applications query topics/interests for analysis and personalization

## Practical Usage Examples

### Scenario 1: Setting Up a Political Discussion Experiment

```python
# Step 1: Create topics for political experiment
political_topics = ["Politics", "Democracy", "Elections", "Government Policy"]

for topic_name in political_topics:
    # Check if topic exists
    existing = Topic_List.query.filter_by(name=topic_name).first()
    if not existing:
        new_topic = Topic_List(name=topic_name)
        db.session.add(new_topic)

db.session.commit()

# Step 2: Assign topics to experiment
experiment_id = 5  # Political Discussion Experiment
for topic_name in political_topics:
    topic = Topic_List.query.filter_by(name=topic_name).first()
    exp_topic = Exp_Topic(exp_id=experiment_id, topic_id=topic.id)
    db.session.add(exp_topic)

db.session.commit()

# Step 3: Verify assignment
assigned_topics = get_experiment_topics(experiment_id)
print(f"Experiment {experiment_id} topics: {assigned_topics}")
# Output: ['Politics', 'Democracy', 'Elections', 'Government Policy']
```

### Scenario 2: Analyzing User Interest Evolution

```python
# Track how user interests change over time
def analyze_user_interest_evolution(user_id, rounds_back=100):
    """Analyze how user interests have evolved over the last N rounds"""
    
    # Get all rounds the user was active
    user_rounds = (
        db.session.query(User_interest.round_id, Rounds.day, Rounds.hour)
        .join(Rounds, User_interest.round_id == Rounds.id)
        .filter(User_interest.user_id == user_id)
        .order_by(Rounds.id.desc())
        .limit(rounds_back)
        .all()
    )
    
    interest_timeline = {}
    for round_id, day, hour in user_rounds:
        round_interests = (
            db.session.query(Interests.interest)
            .join(User_interest, Interests.iid == User_interest.interest_id)
            .filter(
                User_interest.user_id == user_id,
                User_interest.round_id == round_id
            )
            .all()
        )
        
        interest_timeline[f"Day {day}, Hour {hour}"] = [i[0] for i in round_interests]
    
    return interest_timeline

# Usage
user_evolution = analyze_user_interest_evolution(123, 50)
print("User interest evolution:")
for timepoint, interests in user_evolution.items():
    print(f"{timepoint}: {interests}")
```

### Scenario 3: Content Recommendation Based on Interests

```python
# Recommend posts based on user interests and trending topics
def recommend_posts_by_interests(user_id, limit=10):
    """Recommend posts based on user's interests and current trends"""
    
    # Get user's top interests
    user_interests = get_user_interests(user_id, last_rounds=20)
    top_interest_ids = [interest_id for _, interest_id, _ in user_interests[:5]]
    
    if not top_interest_ids:
        return []
    
    # Get recent posts in user's interest areas
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()
    recent_rounds = current_round.id - 10 if current_round else 0
    
    recommended_posts = (
        db.session.query(Post)
        .join(Post_topics, Post.id == Post_topics.post_id)
        .filter(
            Post_topics.topic_id.in_(top_interest_ids),
            Post.round >= recent_rounds,
            Post.user_id != user_id  # Don't recommend user's own posts
        )
        .order_by(Post.reaction_count.desc())  # Popular posts first
        .limit(limit)
        .all()
    )
    
    return recommended_posts

# Usage
recommendations = recommend_posts_by_interests(user_id=123, limit=5)
for post in recommendations:
    print(f"Post {post.id}: {post.tweet[:50]}...")
```

### Scenario 4: Real-time Topic Monitoring Dashboard

```python
# Create a real-time dashboard for monitoring topic activity
def get_topic_activity_dashboard():
    """Get comprehensive topic activity data for dashboard"""
    
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()
    last_24_rounds = current_round.id - 24 if current_round else 0
    
    # Get topic activity in last 24 rounds
    topic_stats = (
        db.session.query(
            Interests.interest,
            func.count(Post_topics.post_id).label('post_count'),
            func.count(func.distinct(Post.user_id)).label('active_users'),
            func.avg(Post.reaction_count).label('avg_engagement')
        )
        .join(Post_topics, Interests.iid == Post_topics.topic_id)
        .join(Post, Post_topics.post_id == Post.id)
        .filter(Post.round >= last_24_rounds)
        .group_by(Interests.interest)
        .order_by(desc('post_count'))
        .all()
    )
    
    dashboard_data = []
    for topic, posts, users, engagement in topic_stats:
        dashboard_data.append({
            'topic': topic,
            'posts_24h': posts,
            'active_users': users,
            'avg_engagement': round(float(engagement or 0), 2),
            'activity_score': posts * users * (engagement or 1)
        })
    
    return sorted(dashboard_data, key=lambda x: x['activity_score'], reverse=True)

# Usage
dashboard = get_topic_activity_dashboard()
print("Top 5 Most Active Topics:")
for i, topic_data in enumerate(dashboard[:5], 1):
    print(f"{i}. {topic_data['topic']}: {topic_data['posts_24h']} posts, "
          f"{topic_data['active_users']} users, "
          f"{topic_data['avg_engagement']} avg engagement")
```

### Scenario 5: Cross-Experiment Topic Analysis

```python
# Compare topics across different experiments
def compare_experiment_topics():
    """Compare topics assigned to different experiments"""
    
    # Get all experiments with their topics
    experiment_topics = (
        db.session.query(
            Exps.exp_name,
            Exps.idexp,
            Topic_List.name.label('topic_name')
        )
        .join(Exp_Topic, Exps.idexp == Exp_Topic.exp_id)
        .join(Topic_List, Exp_Topic.topic_id == Topic_List.id)
        .all()
    )
    
    # Group by experiment
    experiments = {}
    for exp_name, exp_id, topic in experiment_topics:
        if exp_name not in experiments:
            experiments[exp_name] = {
                'id': exp_id,
                'topics': []
            }
        experiments[exp_name]['topics'].append(topic)
    
    # Find common topics across experiments
    all_topics = set()
    for exp_data in experiments.values():
        all_topics.update(exp_data['topics'])
    
    topic_frequency = {}
    for topic in all_topics:
        frequency = sum(1 for exp_data in experiments.values() 
                       if topic in exp_data['topics'])
        topic_frequency[topic] = frequency
    
    return {
        'experiments': experiments,
        'topic_frequency': sorted(topic_frequency.items(), 
                                key=lambda x: x[1], reverse=True),
        'most_common_topics': [topic for topic, freq in topic_frequency.items() 
                              if freq >= len(experiments) * 0.5]
    }

# Usage
analysis = compare_experiment_topics()
print("Experiments and their topics:")
for exp_name, exp_data in analysis['experiments'].items():
    print(f"{exp_name}: {exp_data['topics']}")

print(f"\nMost common topics: {analysis['most_common_topics']}")
```

## Common Pitfalls and Troubleshooting

### Issue 1: Topics Not Appearing in Experiment

**Problem:** Topics assigned to an experiment don't appear when clients access them.

**Possible Causes:**
1. Topics assigned to wrong database (dashboard vs. experiment)
2. Experiment not properly initialized
3. Database connection issues

**Solution:**
```python
# Verify topic assignment
def debug_experiment_topics(exp_id):
    # Check dashboard database
    dashboard_topics = get_experiment_topics(exp_id)
    print(f"Dashboard topics for experiment {exp_id}: {dashboard_topics}")
    
    # Check if experiment database has corresponding interests
    experiment_interests = Interests.query.all()
    interest_names = [i.interest for i in experiment_interests]
    print(f"Available interests in experiment database: {interest_names}")
    
    # Check for missing mappings
    missing = set(dashboard_topics) - set(interest_names)
    if missing:
        print(f"Missing in experiment database: {missing}")
        # Auto-create missing interests
        for topic in missing:
            new_interest = Interests(interest=topic)
            db.session.add(new_interest)
        db.session.commit()
        print("Missing interests created.")

# Usage
debug_experiment_topics(1)
```

### Issue 2: User Interests Not Generating

**Problem:** Users in experiment don't have any interests assigned.

**Possible Causes:**
1. Interest generation algorithm not running
2. No topics assigned to experiment
3. Database constraints preventing insertion

**Solution:**
```python
# Manually assign interests to users based on experiment topics
def bootstrap_user_interests(exp_id, user_id):
    # Get experiment topics
    topics = get_experiment_topics(exp_id)
    if not topics:
        print(f"No topics assigned to experiment {exp_id}")
        return
    
    current_round = Rounds.query.order_by(Rounds.id.desc()).first()
    round_id = current_round.id if current_round else 1
    
    # Assign random selection of topics as interests
    import random
    selected_topics = random.sample(topics, min(3, len(topics)))
    
    for topic_name in selected_topics:
        interest = Interests.query.filter_by(interest=topic_name).first()
        if interest:
            # Check if already assigned
            existing = User_interest.query.filter_by(
                user_id=user_id, 
                interest_id=interest.iid, 
                round_id=round_id
            ).first()
            
            if not existing:
                user_interest = User_interest(
                    user_id=user_id,
                    interest_id=interest.iid,
                    round_id=round_id
                )
                db.session.add(user_interest)
    
    db.session.commit()
    print(f"Assigned interests {selected_topics} to user {user_id}")

# Usage
bootstrap_user_interests(exp_id=1, user_id=123)
```

### Issue 3: Inconsistent Topic Naming

**Problem:** Topics with similar meanings but different names (e.g., "Tech", "Technology").

**Solution:**
```python
# Topic normalization and deduplication
def normalize_topics():
    # Define normalization rules
    normalization_map = {
        'tech': 'Technology',
        'politics': 'Politics',
        'govt': 'Government',
        'gov': 'Government',
        'sci': 'Science',
        'env': 'Environment'
    }
    
    # Get all topics
    topics = Topic_List.query.all()
    
    for topic in topics:
        normalized_name = topic.name.lower()
        
        # Apply normalization rules
        for old_name, new_name in normalization_map.items():
            if old_name in normalized_name:
                print(f"Normalizing '{topic.name}' to '{new_name}'")
                
                # Check if normalized topic already exists
                existing = Topic_List.query.filter_by(name=new_name).first()
                if existing and existing.id != topic.id:
                    # Merge: update all references to use existing topic
                    Exp_Topic.query.filter_by(topic_id=topic.id).update(
                        {'topic_id': existing.id}
                    )
                    db.session.delete(topic)
                else:
                    # Just rename
                    topic.name = new_name
                break
    
    db.session.commit()
    print("Topic normalization complete")

# Usage
normalize_topics()
```

### Issue 4: Performance Issues with Large Datasets

**Problem:** Slow queries when dealing with many topics, users, or posts.

**Solutions:**

1. **Add Database Indexes:**
```sql
-- Add these indexes to improve query performance
CREATE INDEX idx_exp_topic_exp_id ON exp_topic(exp_id);
CREATE INDEX idx_user_interest_user_round ON user_interest(user_id, round_id);
CREATE INDEX idx_post_topics_topic_id ON post_topics(topic_id);
CREATE INDEX idx_post_round ON post(round);
```

2. **Optimize Queries:**
```python
# Instead of N+1 queries, use eager loading
def get_experiment_topics_optimized(exp_id):
    # Single query with join
    result = (
        db.session.query(Topic_List.name)
        .join(Exp_Topic, Topic_List.id == Exp_Topic.topic_id)
        .filter(Exp_Topic.exp_id == exp_id)
        .all()
    )
    return [name for name, in result]

# Use batch operations for multiple users
def get_multiple_user_interests(user_ids, last_rounds=20):
    # Single query for multiple users
    interests_data = (
        db.session.query(
            User_interest.user_id,
            Interests.interest,
            func.count().label('frequency')
        )
        .join(Interests, User_interest.interest_id == Interests.iid)
        .filter(User_interest.user_id.in_(user_ids))
        .group_by(User_interest.user_id, Interests.interest)
        .all()
    )
    
    # Group by user
    result = {}
    for user_id, interest, frequency in interests_data:
        if user_id not in result:
            result[user_id] = []
        result[user_id].append((interest, frequency))
    
    return result
```

3. **Use Caching for Frequent Queries:**
```python
from functools import lru_cache
import time

@lru_cache(maxsize=100)
def get_trending_topics_cached(window=120, cache_duration=300):
    """Cache trending topics for 5 minutes"""
    return get_trending_topics(window=window)

# Clear cache when data changes
def invalidate_topic_cache():
    get_trending_topics_cached.cache_clear()
```

### Issue 5: Database Migration Between Versions

**Problem:** Updating YSocial breaks existing topic assignments.

**Solution:**
```python
# Migration script for topic schema changes
def migrate_topic_schema():
    """Migrate topics from old schema to new schema"""
    
    # Backup existing data
    backup_topics = db.session.query(Topic_List).all()
    backup_assignments = db.session.query(Exp_Topic).all()
    
    print(f"Backing up {len(backup_topics)} topics and {len(backup_assignments)} assignments")
    
    # Perform migration steps here
    # ... migration logic ...
    
    # Verify migration
    topics_after = db.session.query(Topic_List).count()
    assignments_after = db.session.query(Exp_Topic).count()
    
    print(f"Migration complete: {topics_after} topics, {assignments_after} assignments")
    
    if topics_after != len(backup_topics):
        print("WARNING: Topic count mismatch after migration!")

# Usage
migrate_topic_schema()
```

## Performance Optimization Tips

1. **Batch Operations:** When creating multiple topics or assignments, use batch operations instead of individual commits.

2. **Query Optimization:** Use joins instead of multiple queries, and select only needed columns.

3. **Caching:** Cache frequently accessed topic data, especially for trending topics.

4. **Database Indexing:** Ensure proper indexes on foreign keys and frequently queried columns.

5. **Pagination:** Always use pagination for large result sets to avoid memory issues.

## Security Considerations

- All admin endpoints require authentication
- Direct database access should be restricted
- API rate limiting should be implemented for public endpoints
- Sensitive user interest data should be anonymized in public APIs

This architecture allows for flexible topic management while maintaining clear separation between configuration and runtime data.