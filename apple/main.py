#!/usr/bin/env python3
"""
Heart Rate Analysis Tool

This script analyzes Apple Health heart rate data from an export.xml file
and calculates daily minutes spent at 140+ BPM between specified timestamps.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from collections import defaultdict
import argparse
import sys


def parse_datetime(date_str):
    """Parse datetime string from Apple Health format to datetime object."""
    # Format: "2025-01-12 19:20:47 +0000"
    return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z")


def get_date_key(dt):
    """Get date key (YYYY-MM-DD) from datetime object."""
    return dt.strftime("%Y-%m-%d")


def parse_heart_rate_data(xml_file_path, start_utc, end_utc, min_bpm=140):
    """
    Parse heart rate data from Apple Health XML export.

    Args:
        xml_file_path (str): Path to the export.xml file
        start_utc (datetime): Start timestamp (UTC)
        end_utc (datetime): End timestamp (UTC)
        min_bpm (int): Minimum BPM threshold (default: 140)

    Returns:
        dict: Dictionary with date keys and minutes spent above threshold
    """
    records = []
    processed_records = 0

    print(f"Parsing XML file: {xml_file_path}")
    print(f"Looking for heart rate >= {min_bpm} BPM")
    print(f"Time range: {start_utc} to {end_utc}")
    print("Processing...")

    try:
        # Use iterparse for memory-efficient parsing of large XML files
        context = ET.iterparse(xml_file_path, events=("start", "end"))
        context = iter(context)
        event, root = next(context)

        for event, elem in context:
            if event == "end" and elem.tag == "Record":
                # Check if this is a heart rate record
                if elem.get("type") == "HKQuantityTypeIdentifierHeartRate":
                    processed_records += 1

                    # Progress indicator
                    if processed_records % 10000 == 0:
                        print(f"Processed {processed_records} heart rate records...")

                    try:
                        # Parse the record data
                        start_date_str = elem.get("startDate")
                        end_date_str = elem.get("endDate")
                        value_str = elem.get("value")

                        if not all([start_date_str, end_date_str, value_str]):
                            continue

                        record_start = parse_datetime(start_date_str)
                        record_end = parse_datetime(end_date_str)
                        heart_rate = float(value_str) if value_str else 0.0

                        # Check if record falls within our time range
                        if record_start < start_utc or record_start > end_utc:
                            continue

                        # Store all records for processing later
                        records.append(
                            {
                                "timestamp": record_start,
                                "heart_rate": heart_rate,
                                "date_key": get_date_key(record_start),
                            }
                        )

                    except (ValueError, TypeError):
                        # Skip malformed records
                        continue

                # Clear the element to save memory
                elem.clear()
                root.clear()

    except ET.ParseError as e:
        print(f"Error parsing XML: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"Error: File {xml_file_path} not found")
        sys.exit(1)

    print(f"Total heart rate records processed: {processed_records}")
    print(f"Total records in time range: {len(records)}")

    # Now process the records to find continuous periods above threshold
    daily_minutes = calculate_all_high_bpm_time(records, min_bpm)

    return daily_minutes


def calculate_all_high_bpm_time(records, min_bpm=140):
    """
    Calculate ALL time spent at or above the BPM threshold.
    Each reading represents the time until the next reading (Apple Watch typically takes readings every few seconds).

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

    large_gaps = []

    for i, record in enumerate(records):
        timestamp = record["timestamp"]
        heart_rate = record["heart_rate"]

        if heart_rate >= min_bpm:
            high_bpm_count += 1

            # Calculate the duration this reading represents
            if i < len(records) - 1:
                # Time until next reading
                next_timestamp = records[i + 1]["timestamp"]
                next_heart_rate = records[i + 1]["heart_rate"]
                duration_seconds = (next_timestamp - timestamp).total_seconds()

                # Conservative approach: only count actual reading duration, not gaps
                # Each reading represents a short interval, not the full gap to next reading
                duration_seconds = min(
                    duration_seconds, 10
                )  # Max 10 seconds per reading

                # Track large gaps for debugging
                if duration_seconds > 60:  # More than 1 minute
                    large_gaps.append(
                        {
                            "from": timestamp,
                            "to": next_timestamp,
                            "gap_minutes": duration_seconds / 60,
                            "current_hr": heart_rate,
                            "next_hr": next_heart_rate,
                        }
                    )
            else:
                # Last reading - assume average duration (5 seconds for Apple Watch)
                duration_seconds = 5

            total_high_seconds += duration_seconds

            # Add to daily total
            date_key = get_date_key(timestamp)
            daily_minutes[date_key] += duration_seconds / 60

    # Show large gaps for debugging
    if large_gaps:
        print(f"Found {len(large_gaps)} gaps > 1 minute between high BPM readings:")
        for gap in large_gaps[:3]:  # Show first 3
            print(
                f"  {gap['from'].strftime('%H:%M:%S')} -> {gap['to'].strftime('%H:%M:%S')} ({gap['gap_minutes']:.1f} min, HR: {gap['current_hr']} -> {gap['next_hr']})"
            )
        if len(large_gaps) > 3:
            print(f"  ... and {len(large_gaps) - 3} more gaps")

    total_minutes = total_high_seconds / 60
    print(f"Found {high_bpm_count} readings >= {min_bpm} BPM")
    print(
        f"Total time at >= {min_bpm} BPM: {total_minutes:.1f} minutes ({total_high_seconds:.0f} seconds)"
    )

    return dict(daily_minutes)


def print_daily_summary(daily_minutes, start_utc, end_utc):
    """Print daily summary of minutes spent at high BPM."""
    if not daily_minutes:
        print(f"No time >= 140 BPM found between {start_utc} and {end_utc}")
        return

    print(f"\nDaily Minutes at 140+ BPM (ALL time above threshold):")
    print("=" * 55)

    total_minutes = 0
    total_days = 0

    # Sort by date
    for date_key in sorted(daily_minutes.keys()):
        minutes = daily_minutes[date_key]
        total_minutes += minutes
        total_days += 1
        print(f"{date_key}: {minutes:.1f} minutes")

    print("=" * 50)
    print(f"Total days with 140+ BPM: {total_days}")
    print(f"Total minutes at 140+ BPM: {total_minutes:.1f}")
    if total_days > 0:
        avg_minutes = total_minutes / total_days
        print(f"Average minutes per day: {avg_minutes:.1f}")


def main():
    """Main function to handle command line arguments and execute analysis."""
    parser = argparse.ArgumentParser(
        description="Analyze Apple Health heart rate data for daily minutes at 140+ BPM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Run command:
  uv run main.py --start "2025-11-10 10:00:00" --end "2025-12-01 23:59:00"
        """,
    )

    parser.add_argument(
        "--start",
        required=True,
        help='Start timestamp in UTC (format: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SSZ")',
    )

    parser.add_argument(
        "--end",
        required=True,
        help='End timestamp in UTC (format: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SSZ")',
    )

    parser.add_argument(
        "--min-bpm", type=int, default=140, help="Minimum BPM threshold (default: 140)"
    )

    parser.add_argument(
        "--xml-file",
        default="export.xml",
        help="Path to Apple Health export.xml file (default: export.xml)",
    )

    args = parser.parse_args()

    # Parse timestamps
    try:
        # Try ISO format first (with 'T' and 'Z')
        if "T" in args.start and args.start.endswith("Z"):
            start_utc = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
        else:
            # Try standard format
            start_utc = datetime.strptime(args.start + " +0000", "%Y-%m-%d %H:%M:%S %z")

        if "T" in args.end and args.end.endswith("Z"):
            end_utc = datetime.fromisoformat(args.end.replace("Z", "+00:00"))
        else:
            end_utc = datetime.strptime(args.end + " +0000", "%Y-%m-%d %H:%M:%S %z")

    except ValueError as e:
        print(f"Error parsing timestamps: {e}")
        print('Please use format "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SSZ"')
        sys.exit(1)

    if start_utc >= end_utc:
        print("Error: Start timestamp must be before end timestamp")
        sys.exit(1)

    # Analyze the data
    daily_minutes = parse_heart_rate_data(
        args.xml_file, start_utc, end_utc, args.min_bpm
    )

    # Print results
    print_daily_summary(daily_minutes, start_utc, end_utc)


if __name__ == "__main__":
    main()
