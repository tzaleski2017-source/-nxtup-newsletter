# Mega-Streamer Prediction Model Documentation

## Overview

The mega-streamer prediction model is a machine learning system designed to identify "hidden gem" streamers who have the potential to become mega-streamers (17,000+ average concurrent viewers). The model analyzes a streamer's **first 30 days** of performance and predicts their likelihood of **ever** achieving mega-streamer status.

## Business Use Case

**Target User**: Talent scouts, streamer agents, content network managers

**Problem Statement**: Among thousands of small streamers, which ones have genuine mega-streamer potential worth investing time and resources into?

**Solution**: A predictive model that scores streamers based on early performance indicators, enabling data-driven talent scouting.

## Model Architecture

### Classification Type
- **Type**: Binary classification
- **Target Variable**: `is_mega_streamer` (0 = No, 1 = Yes)
- **Threshold**: 17,000 average concurrent viewers

### Algorithm

**Primary**: XGBoost Classifier (XGBClassifier)
- Gradient boosting decision trees
- Excellent performance on imbalanced datasets
- Handles non-linear feature interactions
- Robust to outliers and missing values

**Fallback**: Gradient Boosting Classifier (scikit-learn)
- Used when XGBoost is not available
- Similar performance with `class_weight='balanced'`

### Key Configuration

```python
XGBClassifier(
    scale_pos_weight=<imbalance_ratio>,  # Handles rare positive class
    n_estimators=200,                    # Number of boosting rounds
    max_depth=6,                         # Tree depth for interactions
    learning_rate=0.05,                  # Conservative learning
    subsample=0.8,                       # Row sampling (80%)
    colsample_bytree=0.8,               # Feature sampling (80%)
    random_state=42                      # Reproducibility
)
```

## Input Features

The model uses **9 features** from a streamer's first 30 days:

### Broadcast Activity Features

| Feature | Type | Description | Importance |
|---------|------|-------------|------------|
| `total_broadcasts` | Count | Number of streams in first 30 days | Frequency indicator |
| `total_broadcast_hours` | Hours | Total airtime commitment | Dedication metric |

### Audience Size Features

| Feature | Type | Description | Importance |
|---------|------|-------------|------------|
| `first_30d_avg_viewers` | Count | Average concurrent viewers | Base popularity |
| `first_30d_follower_count` | Count | Total followers at 30-day mark | Cumulative audience |

### Engagement Features

| Feature | Type | Description | Importance |
|---------|------|-------------|------------|
| `first_30d_chat_rate` | Ratio | Chat messages per viewer per hour | Community engagement |
| `tune_in_ratio` | **Engineered** | `avg_viewers / followers` | Viewer conversion density |

### Growth Features

| Feature | Type | Description | Importance |
|---------|------|-------------|------------|
| `first_30d_follower_gain` | Count | Net new followers in 30 days | Growth velocity |
| `first_30d_follower_velocity` | Ratio | Followers gained per broadcast hour | Growth efficiency |

### Diversity Features

| Feature | Type | Description | Importance |
|---------|------|-------------|------------|
| `first_30d_unique_categories` | Count | Number of different games streamed | Content versatility |

### Feature Engineering: tune_in_ratio

The `tune_in_ratio` is a critical engineered feature:

```python
tune_in_ratio = avg_concurrent_viewers / (follower_count + 1e-6)
```

**Interpretation**:
- **High ratio (>0.5)**: Followers actively watch streams (strong pull)
- **Medium ratio (0.1-0.5)**: Moderate engagement
- **Low ratio (<0.1)**: Many followers, few watchers (weak pull)

**Example**:
- Streamer A: 100 avg viewers, 500 followers → ratio = 0.20
- Streamer B: 100 avg viewers, 10,000 followers → ratio = 0.01
- **Insight**: Streamer A has stronger engagement despite same viewer count

## Data Pipeline

### 1. Data Extraction (SQL)

The training data is extracted using a carefully designed SQL query that prevents temporal data leakage:

```sql
WITH streamer_peak_performance AS (
    -- Find lifetime peak performance
    SELECT streamer_id, MAX(avg_concurrent_viewers) AS peak_avg_viewers
    FROM streamer_statistics
    GROUP BY streamer_id
),
streamer_first_stats AS (
    -- Extract first 30-day record
    SELECT DISTINCT ON (streamer_id) *
    FROM streamer_statistics
    ORDER BY streamer_id, calculation_date ASC
)
-- Features = first 30 days, Label = ever reached 17k+
SELECT sfs.*, (spp.peak_avg_viewers >= 17000)::int AS is_mega_streamer
FROM streamer_first_stats sfs
JOIN streamer_peak_performance spp USING (streamer_id)
WHERE sfs.total_broadcast_hours > 10;
```

**Key Principles**:
- ✅ Features: First 30-day performance only
- ✅ Label: Peak lifetime performance
- ✅ No future information leaks into features
- ✅ Minimum 10 hours streamed for data quality

### 2. Preprocessing Pipeline

```
Raw Features → Imputation → Scaling → Model
```

**Step 1: Imputation**
- Strategy: Median imputation
- Handles missing values robustly
- Preserves distribution

**Step 2: Scaling**
- StandardScaler: Zero mean, unit variance
- Critical for tree-based models to weight features properly
- Prevents large-scale features from dominating

### 3. Train/Test Split

```python
train_test_split(
    X, y,
    test_size=0.2,
    stratify=y,  # CRITICAL: Maintains class ratio
    random_state=42
)
```

**Stratification**: Ensures both train and test sets have proportional representation of rare positive class.

## Handling Class Imbalance

### The Challenge

Mega-streamers are **extremely rare** in the population:
- Expected: 0.1-1% of all streamers
- Imbalance ratio: 100:1 to 1000:1
- Standard accuracy is useless (99% accuracy by always predicting "not mega")

### Solution: Multi-Layered Strategy

**Layer 1: Stratified Sampling**
- Ensures test set has positive examples
- Prevents evaluation on all-negative test sets

**Layer 2: Class Weighting**
```python
scale_pos_weight = n_negative / n_positive
```
- Makes each positive sample count more in loss function
- Example: If ratio is 100:1, each positive counts as 100 negatives

**Layer 3: Metric Selection**
- Focus on **Precision** and **Recall** for positive class
- Ignore overall accuracy

## Model Evaluation

### Primary Metrics (Class 1 Focus)

**Precision (Positive Predictive Value)**
```
Precision = TP / (TP + FP)
```
- **Question**: When model predicts "mega-streamer", how often is it correct?
- **Business Impact**: Low false positives = efficient resource allocation
- **Target**: ≥ 0.60 (60% of predictions are correct)

**Recall (Sensitivity)**
```
Recall = TP / (TP + FN)
```
- **Question**: Of all true mega-streamers, what % does model find?
- **Business Impact**: High recall = don't miss rising stars
- **Target**: ≥ 0.50 (find at least half of mega-streamers)

**F1-Score**
```
F1 = 2 * (Precision * Recall) / (Precision + Recall)
```
- **Question**: What's the balanced performance?
- **Target**: ≥ 0.55

**ROC-AUC**
- **Question**: How well does model discriminate between classes?
- **Target**: ≥ 0.75
- **Interpretation**:
  - 0.5 = Random guessing
  - 0.75 = Good discrimination
  - 0.9+ = Excellent discrimination

### Confusion Matrix Interpretation

```
                 Predicted
                 Not Mega  Mega-Streamer
Actual Not Mega     TN         FP        ← False alarms
       Mega         FN         TP        ← Correctly identified
```

**Key Values**:
- **TP (True Positives)**: Correctly identified mega-streamers ✅
- **FN (False Negatives)**: Missed mega-streamers ❌ (costly misses)
- **FP (False Positives)**: Incorrectly flagged as mega-streamers ⚠️
- **TN (True Negatives)**: Correctly identified non-mega streamers

### Performance Tiers

| Tier | Precision | Recall | Assessment |
|------|-----------|--------|------------|
| Excellent | ≥0.60 | ≥0.50 | Production-ready |
| Good | ≥0.50 | ≥0.40 | Promising, needs tuning |
| Moderate | ≥0.30 | ≥0.30 | Better than random |
| Poor | <0.30 | <0.30 | Needs more data/features |

## Training the Model

### Prerequisites

**Data Requirements**:
- PostgreSQL database with `streamer_statistics` table
- Data from both "hidden gems" and established mega-streamers
- Minimum 5 mega-streamer examples (more is better)
- At least 100 total streamer records

**Python Dependencies**:
```bash
pip install pandas numpy scikit-learn xgboost asyncpg joblib
```

### Running Training Script

**Basic Usage**:
```bash
# Set database connection
export DATABASE_URL="postgresql://user:password@host:port/database"

# Train model
python train_model.py
```

**Advanced Options**:
```bash
# Custom test split
python train_model.py --test-size 0.3

# Different random seed
python train_model.py --random-state 123

# Specify database URL
python train_model.py --database-url "postgresql://..."
```

### Output Files

1. **mega_streamer_model.joblib**: Serialized model pipeline
2. **model_evaluation_report.txt**: Performance metrics
3. **feature_importance.csv**: Feature ranking by importance

### Training Time

Expected training duration:
- 100 streamers: ~5 seconds
- 1,000 streamers: ~30 seconds
- 10,000 streamers: ~5 minutes

## Using the Trained Model

### Loading the Model

```python
import joblib
import pandas as pd

# Load model
model = joblib.load('mega_streamer_model.joblib')
```

### Preparing Input Data

The model expects a pandas DataFrame with these exact columns:

```python
feature_cols = [
    'total_broadcasts',
    'total_broadcast_hours',
    'first_30d_avg_viewers',
    'first_30d_chat_rate',
    'first_30d_follower_gain',
    'first_30d_follower_velocity',
    'first_30d_unique_categories',
    'first_30d_follower_count',
    'tune_in_ratio'
]
```

### Making Predictions

**Single Streamer Example**:

```python
# Prepare input data (from streamer's first 30 days)
streamer_data = pd.DataFrame([{
    'total_broadcasts': 25,
    'total_broadcast_hours': 80.5,
    'first_30d_avg_viewers': 150,
    'first_30d_chat_rate': 8.5,
    'first_30d_follower_gain': 1200,
    'first_30d_follower_velocity': 14.9,
    'first_30d_unique_categories': 4,
    'first_30d_follower_count': 2500,
    'tune_in_ratio': 150 / 2500  # 0.06
}])

# Get prediction
prediction = model.predict(streamer_data)[0]
probability = model.predict_proba(streamer_data)[0, 1]

print(f"Prediction: {'Mega-Streamer Potential' if prediction == 1 else 'Not Mega-Streamer'}")
print(f"Confidence: {probability:.1%}")
```

**Batch Prediction**:

```python
# Load multiple streamers
streamers_df = pd.read_csv('streamers_to_score.csv')

# Ensure tune_in_ratio is calculated
streamers_df['tune_in_ratio'] = (
    streamers_df['first_30d_avg_viewers'] /
    (streamers_df['first_30d_follower_count'] + 1e-6)
)

# Get predictions
predictions = model.predict(streamers_df[feature_cols])
probabilities = model.predict_proba(streamers_df[feature_cols])[:, 1]

# Add to dataframe
streamers_df['prediction'] = predictions
streamers_df['mega_streamer_score'] = probabilities

# Sort by score (highest potential first)
streamers_df.sort_values('mega_streamer_score', ascending=False, inplace=True)
```

### Interpreting Scores

The `predict_proba()` method returns probability between 0 and 1:

| Score Range | Interpretation | Action |
|-------------|----------------|--------|
| 0.8 - 1.0 | Very High Potential | Priority target, immediate outreach |
| 0.6 - 0.8 | High Potential | Strong candidate, monitor closely |
| 0.4 - 0.6 | Moderate Potential | Worth watching, periodic check-ins |
| 0.2 - 0.4 | Low Potential | Keep on radar, revisit later |
| 0.0 - 0.2 | Very Low Potential | Unlikely to become mega-streamer |

## Model Limitations

### Known Constraints

1. **Data Dependency**
   - Requires historical data from successful mega-streamers
   - Performance degrades if training data is unrepresentative
   - Platform changes (Twitch algorithm updates) may affect relevance

2. **Temporal Constraints**
   - Only evaluates first 30 days of performance
   - Cannot account for post-30-day improvements or declines
   - Assumes historical patterns repeat in future

3. **Class Imbalance**
   - Very few positive examples limits learning
   - High variance in predictions
   - May miss rare mega-streamer archetypes

4. **Feature Limitations**
   - No content quality assessment (personality, production value)
   - No external factors (social media presence, networking)
   - No streamer demographics or background

5. **False Negatives Risk**
   - Model may miss "late bloomers" who grow after 30 days
   - Streamers who switch strategies may be undervalued

### Confidence Calibration

Model probabilities are **not perfectly calibrated**. A 0.7 score doesn't mean "70% chance of becoming mega-streamer" in absolute terms. Instead:

- Use scores for **relative ranking** (score 0.8 > score 0.5)
- Set business-specific thresholds based on resource constraints
- Combine model scores with human judgment

## Retraining Recommendations

### When to Retrain

**Mandatory**:
- Every 6 months (Twitch ecosystem evolves)
- After major platform changes (algorithm updates, new features)
- When new mega-streamers emerge (add to training data)

**Optional**:
- Model performance degrades (precision/recall drops)
- Access to significantly more training data
- Want to experiment with new features

### Retraining Process

1. **Update Training Data**:
   ```bash
   # Ensure streamer_statistics is current
   python analyze.py  # Update with latest data
   ```

2. **Retrain Model**:
   ```bash
   python train_model.py
   ```

3. **Validate Performance**:
   - Check `model_evaluation_report.txt`
   - Compare new metrics to previous version
   - Test on known edge cases

4. **Deploy New Model**:
   - Replace `mega_streamer_model.joblib`
   - Update version tracking
   - Monitor predictions for anomalies

## Feature Importance

After training, check `feature_importance.csv` to understand which features drive predictions:

**Typical Ranking**:
1. `tune_in_ratio` - Usually most important (engagement density)
2. `first_30d_chat_rate` - Strong engagement indicator
3. `first_30d_follower_velocity` - Growth momentum
4. `first_30d_avg_viewers` - Base popularity
5. Others vary by dataset

**Actionable Insights**:
- If `tune_in_ratio` is #1: Focus on streamers with loyal, engaged audiences
- If `follower_velocity` is #1: Prioritize fast-growing channels
- If `unique_categories` is low: Content diversity may not matter for mega-streamer potential

## Troubleshooting

### Common Errors

**Error**: `ValueError: No training data returned from database`
- **Cause**: `streamer_statistics` table is empty
- **Solution**: Run `analyze.py` to populate statistics table

**Error**: `Insufficient positive samples for training`
- **Cause**: No mega-streamers in database
- **Solution**: Add data from established mega-streamers (17k+ avg viewers)

**Error**: `Cannot stratify split`
- **Cause**: Too few positive samples for train/test split
- **Solution**: Script automatically falls back to non-stratified split

**Warning**: `XGBoost not available. Using fallback.`
- **Cause**: XGBoost library not installed
- **Solution**: `pip install xgboost` (optional, fallback works fine)

### Poor Performance

**Symptom**: Precision/Recall both < 0.3
- **Cause 1**: Insufficient training data
  - **Solution**: Add more mega-streamer examples
- **Cause 2**: Imbalance too severe (>1000:1)
  - **Solution**: Collect more positive samples or try SMOTE oversampling
- **Cause 3**: Features don't correlate with success
  - **Solution**: Engineer new features or collect different metrics

## Advanced Topics

### Threshold Tuning

Default threshold is 0.5, but you can adjust for your use case:

```python
from sklearn.metrics import precision_recall_curve

# Find optimal threshold
precision, recall, thresholds = precision_recall_curve(y_test, y_pred_proba)

# Maximize F1 score
f1_scores = 2 * (precision * recall) / (precision + recall + 1e-10)
optimal_idx = np.argmax(f1_scores)
optimal_threshold = thresholds[optimal_idx]

print(f"Optimal threshold: {optimal_threshold:.3f}")

# Use custom threshold
y_pred_custom = (y_pred_proba >= optimal_threshold).astype(int)
```

### Feature Engineering Ideas

Potential new features to experiment with:
- **Stream consistency**: Variance in broadcast hours per day
- **Peak viewership growth**: Max viewers trend across first 30 days
- **Follower retention**: Followers at day 30 / followers at day 7
- **Category loyalty**: % of time in most-streamed category
- **Weekend vs weekday**: Performance comparison

### Hyperparameter Tuning

Use GridSearchCV for systematic tuning:

```python
from sklearn.model_selection import GridSearchCV

param_grid = {
    'model__n_estimators': [100, 200, 300],
    'model__max_depth': [4, 6, 8],
    'model__learning_rate': [0.01, 0.05, 0.1]
}

grid_search = GridSearchCV(
    full_pipeline,
    param_grid,
    cv=3,
    scoring='f1',  # Optimize for F1 score
    n_jobs=-1
)

grid_search.fit(X_train, y_train)
best_model = grid_search.best_estimator_
```

## API Integration Example

Integrate model into a web API:

```python
from flask import Flask, request, jsonify
import joblib

app = Flask(__name__)
model = joblib.load('mega_streamer_model.joblib')

@app.route('/predict', methods=['POST'])
def predict():
    data = request.get_json()

    # Validate input
    required_features = [
        'total_broadcasts', 'total_broadcast_hours',
        'first_30d_avg_viewers', 'first_30d_chat_rate',
        'first_30d_follower_gain', 'first_30d_follower_velocity',
        'first_30d_unique_categories', 'first_30d_follower_count',
        'tune_in_ratio'
    ]

    df = pd.DataFrame([data])
    prediction = model.predict(df)[0]
    probability = model.predict_proba(df)[0, 1]

    return jsonify({
        'prediction': int(prediction),
        'mega_streamer_probability': float(probability),
        'tier': classify_tier(probability)
    })

def classify_tier(prob):
    if prob >= 0.8: return 'Very High Potential'
    if prob >= 0.6: return 'High Potential'
    if prob >= 0.4: return 'Moderate Potential'
    if prob >= 0.2: return 'Low Potential'
    return 'Very Low Potential'

if __name__ == '__main__':
    app.run(debug=False, port=5000)
```

## References

- **XGBoost Documentation**: https://xgboost.readthedocs.io/
- **Scikit-learn User Guide**: https://scikit-learn.org/stable/user_guide.html
- **Imbalanced Learning**: https://imbalanced-learn.org/
- **ROC-AUC Interpretation**: https://developers.google.com/machine-learning/crash-course/classification/roc-and-auc

## Support

For issues or questions:
1. Check this documentation
2. Review `model_evaluation_report.txt` for model performance
3. Verify training data quality in `streamer_statistics` table
4. Consult feature importance to understand predictions

---

**Model Version**: 1.0
**Last Updated**: 2025-10-30
**Maintained By**: Twitch Analytics Platform Team
