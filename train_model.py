#!/usr/bin/env python3
"""
Mega-Streamer Prediction Model Training Script

This script builds a machine learning model to predict which "hidden gem" streamers
have the potential to become "mega-streamers" (17k+ average concurrent viewers).

The model analyzes a streamer's first 30 days of performance and predicts their
likelihood of ever achieving mega-streamer status.

Key Features:
- SQL-based data extraction to prevent temporal leakage
- Handles severe class imbalance (mega-streamers are ~0.1-1% of population)
- Uses XGBoost with scale_pos_weight for rare class detection
- Focuses on Precision and Recall for the positive class

Usage:
    python train_model.py                    # Train with default settings
    python train_model.py --database-url URL # Specify database
    python train_model.py --test-size 0.3    # Custom train/test split

Output:
    - mega_streamer_model.joblib: Trained model pipeline
    - model_evaluation_report.txt: Performance metrics
    - feature_importance.csv: Feature ranking
"""

import argparse
import asyncio
import asyncpg
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd
import joblib

# Scikit-learn imports
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    precision_recall_curve
)

# XGBoost import with fallback
try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False
    from sklearn.ensemble import GradientBoostingClassifier

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# SQL query to fetch training data
# This query prevents temporal leakage by separating:
# - Features (X): First 30-day performance
# - Label (y): Peak lifetime performance
TRAINING_DATA_QUERY = """
WITH streamer_peak_performance AS (
    -- Find the peak 30-day avg_viewers for EVERY streamer in history
    SELECT
        streamer_id,
        MAX(avg_concurrent_viewers) AS peak_avg_viewers
    FROM streamer_statistics
    GROUP BY streamer_id
),
streamer_first_stats AS (
    -- Find the VERY FIRST 30-day statistical record for each streamer
    -- This is their "baseline" performance (our features)
    SELECT
        DISTINCT ON (streamer_id)
        streamer_id,
        total_broadcasts,
        total_broadcast_hours,
        avg_concurrent_viewers,
        avg_chat_rate,
        follower_gain_30d,
        follower_velocity,
        unique_categories,
        latest_follower_count
    FROM streamer_statistics
    ORDER BY streamer_id, calculation_date ASC
)
-- Join them together to build the final dataset
SELECT
    sfs.streamer_id,

    -- FEATURES (X): The first 30 days of performance
    sfs.total_broadcasts,
    sfs.total_broadcast_hours,
    sfs.avg_concurrent_viewers AS first_30d_avg_viewers,
    sfs.avg_chat_rate AS first_30d_chat_rate,
    sfs.follower_gain_30d AS first_30d_follower_gain,
    sfs.follower_velocity AS first_30d_follower_velocity,
    sfs.unique_categories AS first_30d_unique_categories,
    sfs.latest_follower_count AS first_30d_follower_count,

    -- LABEL (y): Did they EVER reach mega-streamer status?
    (spp.peak_avg_viewers >= 17000)::int AS is_mega_streamer

FROM streamer_first_stats sfs
JOIN streamer_peak_performance spp ON sfs.streamer_id = spp.streamer_id
-- Ensure we have enough data to make a prediction
WHERE sfs.total_broadcast_hours > 10
ORDER BY sfs.streamer_id;
"""


async def fetch_training_data(database_url: str) -> pd.DataFrame:
    """
    Fetch training data from PostgreSQL database.

    Executes the CTE query that extracts:
    - Features: First 30-day performance metrics
    - Label: Whether streamer ever achieved mega-streamer status (17k+ viewers)

    Args:
        database_url: PostgreSQL connection string

    Returns:
        DataFrame with features and labels

    Raises:
        Exception: If database connection or query fails
    """
    logger.info("Connecting to database...")

    try:
        conn = await asyncpg.connect(database_url)
        logger.info("Successfully connected to database")

        logger.info("Executing training data query...")
        rows = await conn.fetch(TRAINING_DATA_QUERY)

        if not rows:
            raise ValueError("No training data returned from database. Check that streamer_statistics table is populated.")

        logger.info(f"Fetched {len(rows)} streamer records")

        # Convert to pandas DataFrame
        df = pd.DataFrame([dict(row) for row in rows])

        await conn.close()
        logger.info("Database connection closed")

        return df

    except Exception as e:
        logger.error(f"Failed to fetch training data: {e}")
        raise


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Engineer additional features from raw data.

    Creates:
    - tune_in_ratio: Measures viewer density (avg_viewers / followers)
      High ratio = strong pull, followers actually tune in live

    Args:
        df: DataFrame with raw features

    Returns:
        DataFrame with engineered features added
    """
    logger.info("Engineering features...")

    # Tune-in ratio: How many of a streamer's followers actually watch?
    # High ratio (>0.5) = strong engagement
    # Low ratio (<0.1) = followers don't translate to viewership
    df['tune_in_ratio'] = df['first_30d_avg_viewers'] / (df['first_30d_follower_count'] + 1e-6)

    # Replace any infinite values with NaN (will be handled by imputer)
    df['tune_in_ratio'] = df['tune_in_ratio'].replace([np.inf, -np.inf], np.nan)

    logger.info(f"Created tune_in_ratio feature (mean: {df['tune_in_ratio'].mean():.4f})")

    return df


def analyze_class_distribution(y: pd.Series) -> Dict[str, Any]:
    """
    Analyze and report on class imbalance.

    Args:
        y: Target variable series

    Returns:
        Dictionary with class distribution statistics
    """
    class_counts = y.value_counts()
    n_negative = class_counts.get(0, 0)
    n_positive = class_counts.get(1, 0)

    total = len(y)
    imbalance_ratio = n_negative / n_positive if n_positive > 0 else float('inf')
    positive_pct = (n_positive / total * 100) if total > 0 else 0

    stats = {
        'total': total,
        'n_negative': n_negative,
        'n_positive': n_positive,
        'imbalance_ratio': imbalance_ratio,
        'positive_percentage': positive_pct
    }

    logger.info("=" * 80)
    logger.info("CLASS DISTRIBUTION ANALYSIS")
    logger.info("=" * 80)
    logger.info(f"Total samples: {total}")
    logger.info(f"Class 0 (Not Mega-Streamer): {n_negative} ({(n_negative/total*100):.1f}%)")
    logger.info(f"Class 1 (Mega-Streamer):     {n_positive} ({positive_pct:.1f}%)")
    logger.info(f"Imbalance ratio: {imbalance_ratio:.1f}:1")
    logger.info("=" * 80)

    if n_positive < 10:
        logger.warning(f"⚠️  Very few positive samples ({n_positive}). Model may struggle to learn patterns.")

    return stats


def prepare_features_and_target(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Prepare feature matrix (X) and target variable (y).

    Args:
        df: DataFrame with all columns

    Returns:
        Tuple of (X, y) where X is features and y is target
    """
    logger.info("Preparing features and target...")

    # Define feature columns
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

    # Validate all features exist
    missing_cols = set(feature_cols) - set(df.columns)
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    X = df[feature_cols].copy()
    y = df['is_mega_streamer'].astype(int)

    logger.info(f"Feature matrix shape: {X.shape}")
    logger.info(f"Features: {', '.join(feature_cols)}")

    # Check for missing values
    missing_counts = X.isnull().sum()
    if missing_counts.any():
        logger.info("\nMissing values per feature:")
        for col, count in missing_counts[missing_counts > 0].items():
            logger.info(f"  {col}: {count} ({count/len(X)*100:.1f}%)")

    # Log feature statistics
    logger.info("\nFeature statistics:")
    logger.info(X.describe().to_string())

    return X, y


def build_preprocessing_pipeline() -> Pipeline:
    """
    Build sklearn preprocessing pipeline.

    Pipeline steps:
    1. SimpleImputer: Fill missing values with median
    2. StandardScaler: Normalize features to zero mean, unit variance

    Returns:
        Configured sklearn Pipeline
    """
    logger.info("Building preprocessing pipeline...")

    pipeline = Pipeline([
        ('imputer', SimpleImputer(strategy='median')),
        ('scaler', StandardScaler())
    ])

    logger.info("Preprocessing pipeline: Imputer (median) → StandardScaler")

    return pipeline


def build_model(scale_pos_weight: float) -> Any:
    """
    Build classification model configured for imbalanced data.

    Primary: XGBClassifier with scale_pos_weight
    Fallback: GradientBoostingClassifier with class_weight='balanced'

    Args:
        scale_pos_weight: Ratio of negative to positive samples

    Returns:
        Configured classifier instance
    """
    if XGBOOST_AVAILABLE:
        logger.info("Building XGBoost classifier...")
        model = XGBClassifier(
            scale_pos_weight=scale_pos_weight,
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric='logloss',
            use_label_encoder=False
        )
        logger.info(f"XGBClassifier configured with scale_pos_weight={scale_pos_weight:.2f}")
    else:
        logger.warning("XGBoost not available. Using GradientBoostingClassifier fallback.")
        model = GradientBoostingClassifier(
            n_estimators=200,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            random_state=42
        )
        logger.info("GradientBoostingClassifier configured")

    return model


def evaluate_model(
    model: Any,
    X_test: np.ndarray,
    y_test: np.ndarray,
    feature_names: list
) -> Dict[str, Any]:
    """
    Evaluate model performance with focus on Class 1 (mega-streamer) metrics.

    Args:
        model: Trained model
        X_test: Test features (preprocessed)
        y_test: Test labels
        feature_names: List of feature names for importance ranking

    Returns:
        Dictionary with all evaluation metrics
    """
    logger.info("=" * 80)
    logger.info("MODEL EVALUATION")
    logger.info("=" * 80)

    # Generate predictions
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]

    # Classification report
    report_dict = classification_report(
        y_test,
        y_pred,
        target_names=['Not Mega', 'Mega-Streamer'],
        output_dict=True,
        zero_division=0
    )

    report_str = classification_report(
        y_test,
        y_pred,
        target_names=['Not Mega', 'Mega-Streamer'],
        digits=3,
        zero_division=0
    )

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)

    # Class 1 specific metrics
    precision_1 = precision_score(y_test, y_pred, zero_division=0)
    recall_1 = recall_score(y_test, y_pred, zero_division=0)
    f1_1 = f1_score(y_test, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_pred_proba)

    # Print results
    print("\n" + "=" * 80)
    print("MEGA-STREAMER PREDICTION MODEL - EVALUATION REPORT")
    print("=" * 80)
    print(f"\nTest Set Size: {len(y_test)} samples")
    print(f"Class Distribution: {(y_test == 0).sum()} negative, {(y_test == 1).sum()} positive")
    print("\nClassification Report:")
    print(report_str)

    print("\nConfusion Matrix:")
    print(f"                 Predicted")
    print(f"                 Not Mega  Mega-Streamer")
    print(f"Actual Not Mega  {cm[0,0]:8d}  {cm[0,1]:8d}")
    print(f"       Mega      {cm[1,0]:8d}  {cm[1,1]:8d}")

    print("\n" + "=" * 80)
    print("🎯 MEGA-STREAMER CLASS (1) METRICS")
    print("=" * 80)
    print(f"Precision: {precision_1:.3f} - When model predicts mega-streamer, {precision_1*100:.1f}% chance it's correct")
    print(f"Recall:    {recall_1:.3f} - Model finds {recall_1*100:.1f}% of all true mega-streamers")
    print(f"F1-Score:  {f1_1:.3f} - Harmonic mean of precision and recall")
    print(f"ROC-AUC:   {roc_auc:.3f} - Area under ROC curve")
    print("=" * 80)

    # Feature importance
    if hasattr(model.named_steps['model'], 'feature_importances_'):
        importance = model.named_steps['model'].feature_importances_
        feature_importance_df = pd.DataFrame({
            'feature': feature_names,
            'importance': importance
        }).sort_values('importance', ascending=False)

        print("\nFeature Importance (Top 5):")
        print(feature_importance_df.head().to_string(index=False))
    else:
        feature_importance_df = None

    # Performance assessment
    print("\n" + "=" * 80)
    print("PERFORMANCE ASSESSMENT")
    print("=" * 80)

    if precision_1 >= 0.6 and recall_1 >= 0.5:
        print("✅ EXCELLENT: Model meets/exceeds targets (Precision ≥0.60, Recall ≥0.50)")
    elif precision_1 >= 0.5 and recall_1 >= 0.4:
        print("✓ GOOD: Model shows promising performance")
    elif precision_1 >= 0.3 or recall_1 >= 0.3:
        print("⚠️  MODERATE: Model performs better than random but needs improvement")
    else:
        print("❌ POOR: Model struggles to identify mega-streamers")

    print("=" * 80)

    # Return metrics dictionary
    metrics = {
        'classification_report': report_dict,
        'classification_report_str': report_str,
        'confusion_matrix': cm,
        'precision_class_1': precision_1,
        'recall_class_1': recall_1,
        'f1_class_1': f1_1,
        'roc_auc': roc_auc,
        'feature_importance': feature_importance_df
    }

    return metrics


def save_model_and_artifacts(
    model: Pipeline,
    metrics: Dict[str, Any],
    feature_names: list
) -> None:
    """
    Save trained model and evaluation artifacts to disk.

    Args:
        model: Trained model pipeline
        metrics: Dictionary of evaluation metrics
        feature_names: List of feature names
    """
    logger.info("Saving model and artifacts...")

    # Save model
    model_path = 'mega_streamer_model.joblib'
    joblib.dump(model, model_path)
    logger.info(f"✅ Model saved to: {model_path}")

    # Save evaluation report
    report_path = 'model_evaluation_report.txt'
    with open(report_path, 'w') as f:
        f.write("MEGA-STREAMER PREDICTION MODEL - EVALUATION REPORT\n")
        f.write("=" * 80 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        f.write("Classification Report:\n")
        f.write(metrics['classification_report_str'] + "\n\n")

        f.write("Confusion Matrix:\n")
        cm = metrics['confusion_matrix']
        f.write(f"                 Predicted\n")
        f.write(f"                 Not Mega  Mega-Streamer\n")
        f.write(f"Actual Not Mega  {cm[0,0]:8d}  {cm[0,1]:8d}\n")
        f.write(f"       Mega      {cm[1,0]:8d}  {cm[1,1]:8d}\n\n")

        f.write("=" * 80 + "\n")
        f.write("MEGA-STREAMER CLASS (1) METRICS\n")
        f.write("=" * 80 + "\n")
        f.write(f"Precision: {metrics['precision_class_1']:.3f}\n")
        f.write(f"Recall:    {metrics['recall_class_1']:.3f}\n")
        f.write(f"F1-Score:  {metrics['f1_class_1']:.3f}\n")
        f.write(f"ROC-AUC:   {metrics['roc_auc']:.3f}\n\n")

        if metrics['feature_importance'] is not None:
            f.write("Feature Importance:\n")
            f.write(metrics['feature_importance'].to_string(index=False))

    logger.info(f"✅ Evaluation report saved to: {report_path}")

    # Save feature importance
    if metrics['feature_importance'] is not None:
        importance_path = 'feature_importance.csv'
        metrics['feature_importance'].to_csv(importance_path, index=False)
        logger.info(f"✅ Feature importance saved to: {importance_path}")


async def main(
    database_url: str,
    test_size: float = 0.2,
    random_state: int = 42
):
    """
    Main training pipeline.

    Args:
        database_url: PostgreSQL connection string
        test_size: Proportion of data to use for testing
        random_state: Random seed for reproducibility
    """
    logger.info("=" * 80)
    logger.info("MEGA-STREAMER PREDICTION MODEL TRAINING")
    logger.info("=" * 80)
    logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Test size: {test_size}")
    logger.info(f"Random state: {random_state}")
    logger.info(f"XGBoost available: {XGBOOST_AVAILABLE}")
    logger.info("=" * 80 + "\n")

    try:
        # Phase 1: Data Acquisition
        df = await fetch_training_data(database_url)
        logger.info(f"Loaded {len(df)} streamer records\n")

        # Phase 2: Feature Engineering
        df = engineer_features(df)

        # Phase 3: Prepare Features and Target
        X, y = prepare_features_and_target(df)
        feature_names = X.columns.tolist()

        # Phase 4: Analyze Class Distribution
        class_stats = analyze_class_distribution(y)

        # Check if we have enough data
        if class_stats['n_positive'] < 5:
            logger.error("❌ Insufficient positive samples for training. Need at least 5 mega-streamers.")
            logger.error("Please ensure streamer_statistics table contains data from established mega-streamers.")
            return

        # Phase 5: Train/Test Split
        logger.info("\nSplitting data into train/test sets...")
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y,
                test_size=test_size,
                random_state=random_state,
                stratify=y  # Critical for imbalanced data
            )
            logger.info(f"Training set: {len(X_train)} samples")
            logger.info(f"Test set: {len(X_test)} samples")
        except ValueError as e:
            logger.error(f"❌ Cannot stratify split: {e}")
            logger.error("This usually means too few samples in minority class.")
            # Fallback to non-stratified split
            logger.warning("Falling back to non-stratified split...")
            X_train, X_test, y_train, y_test = train_test_split(
                X, y,
                test_size=test_size,
                random_state=random_state,
                stratify=None
            )

        # Phase 6: Build Preprocessing Pipeline
        preprocessor = build_preprocessing_pipeline()

        # Phase 7: Calculate Class Weights
        n_negative = (y_train == 0).sum()
        n_positive = (y_train == 1).sum()
        scale_pos_weight = n_negative / n_positive if n_positive > 0 else 1.0

        logger.info(f"\nTraining set class distribution:")
        logger.info(f"  Negative: {n_negative}")
        logger.info(f"  Positive: {n_positive}")
        logger.info(f"  Scale positive weight: {scale_pos_weight:.2f}")

        # Phase 8: Build and Train Model
        logger.info("\nBuilding model...")
        model = build_model(scale_pos_weight)

        # Create full pipeline
        full_pipeline = Pipeline([
            ('preprocessor', preprocessor),
            ('model', model)
        ])

        logger.info("Training model...")
        logger.info("(This may take a few minutes...)\n")
        full_pipeline.fit(X_train, y_train)
        logger.info("✅ Model training complete\n")

        # Phase 9: Evaluate Model
        metrics = evaluate_model(full_pipeline, X_test, y_test, feature_names)

        # Phase 10: Save Model and Artifacts
        save_model_and_artifacts(full_pipeline, metrics, feature_names)

        logger.info("\n" + "=" * 80)
        logger.info("TRAINING COMPLETE")
        logger.info("=" * 80)
        logger.info(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("\nGenerated files:")
        logger.info("  - mega_streamer_model.joblib")
        logger.info("  - model_evaluation_report.txt")
        logger.info("  - feature_importance.csv")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"❌ Training failed: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train mega-streamer prediction model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Train with default settings
  %(prog)s --database-url URL           # Specify database connection
  %(prog)s --test-size 0.3              # Use 30% for testing
  %(prog)s --random-state 123           # Use different random seed

Database Connection:
  Set DATABASE_URL environment variable or use --database-url option.
  Format: postgresql://user:password@host:port/database
        """
    )

    parser.add_argument(
        "--database-url",
        type=str,
        help="PostgreSQL connection string (or set DATABASE_URL env var)"
    )

    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Proportion of data for testing (default: 0.2)"
    )

    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42)"
    )

    args = parser.parse_args()

    # Get database URL from args or environment
    database_url = args.database_url or os.getenv("DATABASE_URL")

    if not database_url:
        logger.error("Database URL not provided. Set DATABASE_URL environment variable or use --database-url")
        sys.exit(1)

    # Run async main
    try:
        asyncio.run(main(
            database_url=database_url,
            test_size=args.test_size,
            random_state=args.random_state
        ))
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
