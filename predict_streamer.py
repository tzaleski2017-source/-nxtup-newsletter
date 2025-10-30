#!/usr/bin/env python3
"""
Mega-Streamer Prediction - Usage Example

This script demonstrates how to use the trained mega-streamer prediction model
to score new streamers based on their first 30 days of performance.

Usage:
    python predict_streamer.py                  # Interactive mode
    python predict_streamer.py --batch input.csv # Batch mode from CSV
"""

import argparse
import sys
import pandas as pd
import joblib
from pathlib import Path


def load_model(model_path: str = 'mega_streamer_model.joblib'):
    """Load the trained model."""
    if not Path(model_path).exists():
        print(f"❌ Error: Model file not found at {model_path}")
        print("Run 'python train_model.py' to train the model first.")
        sys.exit(1)

    print(f"Loading model from {model_path}...")
    model = joblib.load(model_path)
    print("✅ Model loaded successfully\n")
    return model


def get_tier(probability: float) -> str:
    """Classify probability into tier."""
    if probability >= 0.8:
        return "🌟 Very High Potential"
    elif probability >= 0.6:
        return "⭐ High Potential"
    elif probability >= 0.4:
        return "✓ Moderate Potential"
    elif probability >= 0.2:
        return "→ Low Potential"
    else:
        return "· Very Low Potential"


def predict_single_streamer(model, streamer_data: dict) -> dict:
    """
    Predict mega-streamer potential for a single streamer.

    Args:
        model: Trained model
        streamer_data: Dictionary with streamer features

    Returns:
        Dictionary with prediction results
    """
    # Calculate tune_in_ratio if not provided
    if 'tune_in_ratio' not in streamer_data:
        streamer_data['tune_in_ratio'] = (
            streamer_data['first_30d_avg_viewers'] /
            (streamer_data['first_30d_follower_count'] + 1e-6)
        )

    # Create DataFrame
    df = pd.DataFrame([streamer_data])

    # Make prediction
    prediction = model.predict(df)[0]
    probability = model.predict_proba(df)[0, 1]

    return {
        'prediction': int(prediction),
        'probability': float(probability),
        'tier': get_tier(probability)
    }


def interactive_mode(model):
    """Interactive mode for single streamer prediction."""
    print("=" * 80)
    print("MEGA-STREAMER PREDICTION - INTERACTIVE MODE")
    print("=" * 80)
    print("\nEnter the streamer's first 30-day performance metrics:")
    print("(Leave blank to use example values)\n")

    # Get user input
    try:
        total_broadcasts = input("Total broadcasts [25]: ").strip()
        total_broadcasts = int(total_broadcasts) if total_broadcasts else 25

        total_hours = input("Total broadcast hours [80.5]: ").strip()
        total_hours = float(total_hours) if total_hours else 80.5

        avg_viewers = input("Average concurrent viewers [150]: ").strip()
        avg_viewers = float(avg_viewers) if avg_viewers else 150

        chat_rate = input("Chat rate (msgs/viewer/hour) [8.5]: ").strip()
        chat_rate = float(chat_rate) if chat_rate else 8.5

        follower_gain = input("Follower gain [1200]: ").strip()
        follower_gain = int(follower_gain) if follower_gain else 1200

        follower_velocity = input("Follower velocity (per hour) [14.9]: ").strip()
        follower_velocity = float(follower_velocity) if follower_velocity else 14.9

        unique_categories = input("Unique categories streamed [4]: ").strip()
        unique_categories = int(unique_categories) if unique_categories else 4

        follower_count = input("Total follower count [2500]: ").strip()
        follower_count = int(follower_count) if follower_count else 2500

    except ValueError as e:
        print(f"❌ Error: Invalid input - {e}")
        sys.exit(1)

    # Build streamer data
    streamer_data = {
        'total_broadcasts': total_broadcasts,
        'total_broadcast_hours': total_hours,
        'first_30d_avg_viewers': avg_viewers,
        'first_30d_chat_rate': chat_rate,
        'first_30d_follower_gain': follower_gain,
        'first_30d_follower_velocity': follower_velocity,
        'first_30d_unique_categories': unique_categories,
        'first_30d_follower_count': follower_count
    }

    # Make prediction
    result = predict_single_streamer(model, streamer_data)

    # Display results
    print("\n" + "=" * 80)
    print("PREDICTION RESULTS")
    print("=" * 80)
    print(f"\nMega-Streamer Score: {result['probability']:.1%}")
    print(f"Tier: {result['tier']}")
    print(f"Prediction: {'✅ MEGA-STREAMER POTENTIAL' if result['prediction'] == 1 else '❌ Not Mega-Streamer'}")

    print("\n" + "-" * 80)
    print("INTERPRETATION")
    print("-" * 80)

    if result['probability'] >= 0.8:
        print("This streamer shows VERY HIGH potential for mega-streamer status.")
        print("Recommended Action: Priority target - immediate outreach and evaluation.")
    elif result['probability'] >= 0.6:
        print("This streamer shows HIGH potential for mega-streamer status.")
        print("Recommended Action: Strong candidate - monitor closely and engage.")
    elif result['probability'] >= 0.4:
        print("This streamer shows MODERATE potential for mega-streamer status.")
        print("Recommended Action: Worth watching - periodic check-ins.")
    elif result['probability'] >= 0.2:
        print("This streamer shows LOW potential for mega-streamer status.")
        print("Recommended Action: Keep on radar - revisit in 3-6 months.")
    else:
        print("This streamer shows VERY LOW potential for mega-streamer status.")
        print("Recommended Action: Unlikely candidate - deprioritize.")

    print("=" * 80)


def batch_mode(model, input_file: str, output_file: str = None):
    """Batch mode for multiple streamer predictions."""
    print("=" * 80)
    print("MEGA-STREAMER PREDICTION - BATCH MODE")
    print("=" * 80)

    # Load input CSV
    if not Path(input_file).exists():
        print(f"❌ Error: Input file not found: {input_file}")
        sys.exit(1)

    print(f"\nLoading streamers from {input_file}...")
    df = pd.read_csv(input_file)
    print(f"✅ Loaded {len(df)} streamers")

    # Validate required columns
    required_cols = [
        'total_broadcasts',
        'total_broadcast_hours',
        'first_30d_avg_viewers',
        'first_30d_chat_rate',
        'first_30d_follower_gain',
        'first_30d_follower_velocity',
        'first_30d_unique_categories',
        'first_30d_follower_count'
    ]

    missing_cols = set(required_cols) - set(df.columns)
    if missing_cols:
        print(f"❌ Error: Missing required columns: {missing_cols}")
        sys.exit(1)

    # Calculate tune_in_ratio
    df['tune_in_ratio'] = (
        df['first_30d_avg_viewers'] /
        (df['first_30d_follower_count'] + 1e-6)
    )

    # Make predictions
    print("\nMaking predictions...")
    predictions = model.predict(df[required_cols + ['tune_in_ratio']])
    probabilities = model.predict_proba(df[required_cols + ['tune_in_ratio']])[:, 1]

    # Add results to dataframe
    df['mega_streamer_prediction'] = predictions
    df['mega_streamer_score'] = probabilities
    df['tier'] = df['mega_streamer_score'].apply(get_tier)

    # Sort by score
    df = df.sort_values('mega_streamer_score', ascending=False)

    # Save results
    if output_file is None:
        output_file = input_file.replace('.csv', '_predictions.csv')

    df.to_csv(output_file, index=False)
    print(f"✅ Predictions saved to {output_file}")

    # Display summary
    print("\n" + "=" * 80)
    print("PREDICTION SUMMARY")
    print("=" * 80)
    print(f"Total Streamers: {len(df)}")
    print(f"Predicted Mega-Streamers: {(predictions == 1).sum()} ({(predictions == 1).sum() / len(df) * 100:.1f}%)")
    print(f"\nScore Distribution:")
    print(f"  Very High (≥0.8): {(probabilities >= 0.8).sum()}")
    print(f"  High (0.6-0.8):   {((probabilities >= 0.6) & (probabilities < 0.8)).sum()}")
    print(f"  Moderate (0.4-0.6): {((probabilities >= 0.4) & (probabilities < 0.6)).sum()}")
    print(f"  Low (0.2-0.4):    {((probabilities >= 0.2) & (probabilities < 0.4)).sum()}")
    print(f"  Very Low (<0.2):  {(probabilities < 0.2).sum()}")

    # Show top 10
    print("\n" + "=" * 80)
    print("TOP 10 POTENTIAL MEGA-STREAMERS")
    print("=" * 80)

    top_10 = df.head(10)
    if 'username' in df.columns:
        for i, row in top_10.iterrows():
            print(f"{row['username']:20s} - Score: {row['mega_streamer_score']:.1%} - {row['tier']}")
    else:
        for i, row in top_10.iterrows():
            print(f"Streamer {i:3d} - Score: {row['mega_streamer_score']:.1%} - {row['tier']}")

    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Predict mega-streamer potential using trained model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # Interactive mode
  %(prog)s --batch streamers.csv        # Batch predictions from CSV
  %(prog)s --batch input.csv --output results.csv

CSV Format:
  Required columns:
    - total_broadcasts
    - total_broadcast_hours
    - first_30d_avg_viewers
    - first_30d_chat_rate
    - first_30d_follower_gain
    - first_30d_follower_velocity
    - first_30d_unique_categories
    - first_30d_follower_count

  Optional columns:
    - username (for display)
    - streamer_id (for tracking)
        """
    )

    parser.add_argument(
        '--model',
        type=str,
        default='mega_streamer_model.joblib',
        help='Path to trained model file (default: mega_streamer_model.joblib)'
    )

    parser.add_argument(
        '--batch',
        type=str,
        help='CSV file with streamers to score (batch mode)'
    )

    parser.add_argument(
        '--output',
        type=str,
        help='Output CSV file for batch predictions (default: input_predictions.csv)'
    )

    args = parser.parse_args()

    # Load model
    model = load_model(args.model)

    # Run appropriate mode
    if args.batch:
        batch_mode(model, args.batch, args.output)
    else:
        interactive_mode(model)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
