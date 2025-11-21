#!/usr/bin/env python3
"""
Fitbit Heart Rate Analysis Tool

This script analyzes Fitbit heart rate data from daily JSON export files
and calculates daily minutes spent at 140+ BPM between specified timestamps.
"""

import json
import glob
import os
from datetime import datetime, timedelta
from collections import defaultdict
import argparse
import sys


def parse_fitbit_datetime(date_str):
    """Parse datetime string from Fitbit format to datetime object."""
    # Format: "11/18/25 23:00:00" (MM/DD/YY HH:MM:SS)
    # Treating as naive datetime for simplicity - user should specify times in the same timezone as Fitbit data
    return datetime.strptime(date_str, "%m/%d/%y %H:%M:%S")


def get_date_key(dt):
    """Get date key (YYYY-MM-DD) from datetime object."""
    return dt.strftime("%Y-%m-%d")


def load_fitbit_files(exports_dir, start_utc, end_utc):
    """
    Load all relevant Fitbit heart rate JSON files for the date range.

    Args:
        exports_dir (str): Path to the directory containing Fitbit export files
        start_utc (datetime): Start timestamp (UTC)
        end_utc (datetime): End timestamp (UTC)

    Returns:
        list: List of heart rate records within the time range
    """
    records = []

    # Find all heart rate JSON files
    pattern = os.path.join(exports_dir, "heart_rate-*.json")
    files = glob.glob(pattern)

    if not files:
        print(f"No heart rate files found in {exports_dir}")
        return records

    print(f"Found {len(files)} Fitbit heart rate files")

    for file_path in sorted(files):
        print(f"Processing {os.path.basename(file_path)}...")

        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            file_records = 0
            for entry in data:
                try:
                    # Parse the timestamp
                    timestamp = parse_fitbit_datetime(entry["dateTime"])

                    # Check if record falls within our time range
                    if timestamp < start_utc or timestamp > end_utc:
                        continue

                    # Extract heart rate data
                    bpm = entry["value"]["bpm"]
                    confidence = entry["value"].get("confidence", 0)

                    # Only include readings with reasonable confidence (Fitbit confidence levels: 0-3)
                    if confidence >= 1:  # Filter out very low confidence readings
                        records.append(
                            {
                                "timestamp": timestamp,
                                "heart_rate": float(bpm),
                                "confidence": confidence,
                                "date_key": get_date_key(timestamp),
                            }
                        )
                        file_records += 1

                except (KeyError, ValueError, TypeError):
                    # Skip malformed records
                    continue

            print(f"  Loaded {file_records} records from {os.path.basename(file_path)}")

        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error reading {file_path}: {e}")
            continue

    print(f"Total records loaded: {len(records)}")
    return records


def calculate_all_high_bpm_time(records, min_bpm=140):
    """
    Calculate ALL time spent at or above the BPM threshold.
    Each reading represents the time until the next reading (typically 2-3 seconds for Fitbit).

    Args:
        records (list): List of heart rate records with timestamp and heart_rate
        min_bpm (int): Minimum BPM threshold

    Returns:
        dict: Dictionary with date keys and minutes spent above threshold
    """
    if not records:
        return {}

    # Sort records by timestamp
    records.sort(key=lambda x: x["timestamp"])

    daily_minutes = defaultdict(float)
    total_high_seconds = 0
    high_bpm_count = 0

    print(f"Analyzing {len(records)} records for ALL time >= {min_bpm} BPM...")

    for i, record in enumerate(records):
        timestamp = record["timestamp"]
        heart_rate = record["heart_rate"]

        if heart_rate >= min_bpm:
            high_bpm_count += 1

            # Calculate the duration this reading represents
            if i < len(records) - 1:
                # Time until next reading
                next_timestamp = records[i + 1]["timestamp"]
                duration_seconds = (next_timestamp - timestamp).total_seconds()

                # Use actual duration without capping
            else:
                # Last reading - assume average duration (3 seconds)
                duration_seconds = 3

            total_high_seconds += duration_seconds

            # Add to daily total
            date_key = get_date_key(timestamp)
            daily_minutes[date_key] += duration_seconds / 60

    total_minutes = total_high_seconds / 60
    print(f"Found {high_bpm_count} readings >= {min_bpm} BPM")
    print(
        f"Total time at >= {min_bpm} BPM: {total_minutes:.1f} minutes ({total_high_seconds:.0f} seconds)"
    )

    return dict(daily_minutes)


def print_daily_summary(daily_minutes, start_utc, end_utc, min_bpm):
    """Print daily summary of minutes spent at high BPM."""
    if not daily_minutes:
        print(f"No time >= {min_bpm} BPM found between {start_utc} and {end_utc}")
        return

    print(f"\nDaily Minutes at {min_bpm}+ BPM (ALL time above threshold):")
    print("=" * 55)

    total_minutes = 0
    total_days = 0

    # Sort by date
    for date_key in sorted(daily_minutes.keys()):
        minutes = daily_minutes[date_key]
        total_minutes += minutes
        total_days += 1
        print(f"{date_key}: {minutes:.1f} minutes")

    print("=" * 55)
    print(f"Total days with {min_bpm}+ BPM: {total_days}")
    print(f"Total minutes at {min_bpm}+ BPM: {total_minutes:.1f}")
    if total_days > 0:
        avg_minutes = total_minutes / total_days
        print(f"Average minutes per day: {avg_minutes:.1f}")


def main():
    """Main function to handle command line arguments and execute analysis."""
    parser = argparse.ArgumentParser(
        description="Analyze Fitbit heart rate data for ALL time at 140+ BPM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run main.py --start "2025-11-12 00:00:00" --end "2025-11-15 23:59:59"
  uv run main.py --start "2025-11-10T10:30:00Z" --end "2025-11-12T18:45:00Z" --min-bpm 150

Note: This tool calculates ALL time spent above the BPM threshold.
Each reading represents ~2-3 seconds, and durations are calculated from actual timestamps.
Timestamps should be in the same timezone as your Fitbit data.
        """,
    )

    parser.add_argument(
        "--start",
        required=True,
        help='Start timestamp (format: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SSZ")',
    )

    parser.add_argument(
        "--end",
        required=True,
        help='End timestamp (format: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SSZ")',
    )

    parser.add_argument(
        "--min-bpm", type=int, default=140, help="Minimum BPM threshold (default: 140)"
    )

    parser.add_argument(
        "--exports-dir",
        default="exports",
        help="Path to Fitbit exports directory (default: exports)",
    )

    args = parser.parse_args()

    # Parse timestamps
    try:
        # Try ISO format first (with 'T' and 'Z')
        if "T" in args.start and args.start.endswith("Z"):
            start_utc = datetime.fromisoformat(args.start.replace("Z", ""))
        else:
            # Try standard format
            start_utc = datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S")

        if "T" in args.end and args.end.endswith("Z"):
            end_utc = datetime.fromisoformat(args.end.replace("Z", ""))
        else:
            end_utc = datetime.strptime(args.end, "%Y-%m-%d %H:%M:%S")

    except ValueError as e:
        print(f"Error parsing timestamps: {e}")
        print('Please use format "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SSZ"')
        sys.exit(1)

    if start_utc >= end_utc:
        print("Error: Start timestamp must be before end timestamp")
        sys.exit(1)

    print(f"Analyzing Fitbit heart rate data")
    print(f"Looking for heart rate >= {args.min_bpm} BPM")
    print(f"Time range: {start_utc} to {end_utc}")
    print(f"Exports directory: {args.exports_dir}")

    # Load and analyze the data
    records = load_fitbit_files(args.exports_dir, start_utc, end_utc)

    if not records:
        print("No heart rate data found in the specified time range.")
        sys.exit(0)

    daily_minutes = calculate_all_high_bpm_time(records, args.min_bpm)

    # Print results
    print_daily_summary(daily_minutes, start_utc, end_utc, args.min_bpm)


if __name__ == "__main__":
    main()
