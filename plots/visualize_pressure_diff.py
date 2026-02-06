import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import argparse
import glob
import os
import sys

def discover_csv_files(directory='rhs_runs'):
    """Auto-discover all CSV files in the specified directory."""
    pattern = os.path.join(directory, '*.csv')
    files = glob.glob(pattern)
    if not files:
        print(f"Warning: No CSV files found in {directory}/")
    return files

def load_csv_files(file_paths):
    """Load one or more CSV files with validation.

    Args:
        file_paths: List of file paths (absolute or relative)

    Returns:
        Dictionary {filename: DataFrame}
    """
    required_columns = ['Time (s)', 'Pressure 1 (mmHg)', 'Pressure 2 (mmHg)']
    loaded_data = {}

    for filepath in file_paths:
        # Handle relative paths - prepend rhs_runs/ if needed
        if not os.path.isabs(filepath) and not os.path.exists(filepath):
            test_path = os.path.join('rhs_runs', filepath)
            if os.path.exists(test_path):
                filepath = test_path

        try:
            df = pd.read_csv(filepath)

            # Validate required columns
            missing_cols = [col for col in required_columns if col not in df.columns]
            if missing_cols:
                print(f"Warning: Skipping {filepath} - missing columns: {missing_cols}")
                continue

            # Check if file has enough data
            if len(df) < 2:
                print(f"Warning: Skipping {filepath} - insufficient data (only {len(df)} rows)")
                continue

            filename = os.path.basename(filepath)
            loaded_data[filename] = df
            print(f"Loaded {filename}: {len(df)} rows")

        except Exception as e:
            print(f"Warning: Failed to load {filepath}: {e}")
            continue

    return loaded_data

def calculate_pressure_difference(df):
    """Calculate P2-P1 difference for each row.

    Args:
        df: DataFrame with Pressure 1 and Pressure 2 columns

    Returns:
        DataFrame with added 'P2-P1 (mmHg)' column
    """
    df['P2-P1 (mmHg)'] = df['Pressure 2 (mmHg)'] - df['Pressure 1 (mmHg)']
    return df

def aggregate_by_time_interval(df, interval_seconds, agg_method='mean'):
    """Bin data by time intervals and aggregate pressure differences.

    Args:
        df: DataFrame with Time and P2-P1 columns
        interval_seconds: Bin size in seconds
        agg_method: 'mean', 'median', 'min', or 'max'

    Returns:
        Tuple of (aggregated Series, list of string labels)
    """
    time_max = df['Time (s)'].max()
    bins = np.arange(0, time_max + interval_seconds, interval_seconds)

    # Create time bins
    df['time_bin'] = pd.cut(df['Time (s)'], bins=bins)

    # Aggregate by bin
    aggregated = df.groupby('time_bin', observed=True)['P2-P1 (mmHg)'].agg(agg_method)

    # Create string labels for x-axis
    labels = []
    for interval in aggregated.index:
        if pd.notna(interval):
            left = int(interval.left)
            labels.append(str(left))
        else:
            labels.append("N/A")

    # Check if too many bins
    if len(aggregated) > 100:
        suggested_interval = int(time_max / 20)  # Aim for ~20 bins
        print(f"Warning: {len(aggregated)} time bins created. Consider using --interval {suggested_interval} for better visualization.")

    return aggregated, labels

def _thin_labels(labels, max_labels=30):
    """Thin out labels to avoid x-axis crowding.

    Args:
        labels: List of all labels
        max_labels: Maximum number of labels to display

    Returns:
        Tuple of (tick_positions, tick_labels)
    """
    n_labels = len(labels)

    if n_labels <= max_labels:
        # Not crowded, show all labels
        return np.arange(n_labels), labels

    # Calculate step size to show approximately max_labels
    step = max(1, n_labels // max_labels)

    # Create thinned positions and labels
    tick_positions = []
    tick_labels = []

    for i in range(0, n_labels, step):
        tick_positions.append(i)
        tick_labels.append(labels[i])

    # Always include the last label if not already included
    if tick_positions[-1] != n_labels - 1:
        tick_positions.append(n_labels - 1)
        tick_labels.append(labels[-1])

    return tick_positions, tick_labels

def create_diverging_bar_chart(aggregated_data, file_labels, interval, agg_method='mean', title=None, output_file=None):
    """Generate diverging bar chart visualization.

    Args:
        aggregated_data: Dictionary {filename: (aggregated_series, labels)}
        file_labels: List of filenames for legend
        interval: Time interval for title
        title: Custom title (optional)
        output_file: Path to save figure (optional)
    """
    fig, ax = plt.subplots(figsize=(14, 8))

    n_files = len(aggregated_data)

    if n_files == 1:
        # Single file: simple diverging bar chart
        filename = file_labels[0]
        aggregated, labels = aggregated_data[filename]

        x_positions = np.arange(len(aggregated))
        values = aggregated.values

        # Color based on sign: positive (red), negative (blue)
        colors = ['#d73027' if v > 0 else '#4575b4' for v in values]

        # bars is only used if we want to customize individual bars later (e.g., for annotations), but we can skip it for now: 
        # bars = ax.bar(x_positions, values, color=colors, alpha=0.8,
        #              edgecolor='black', linewidth=0.5)

        # Zero reference line
        ax.axhline(y=0, color='black', linewidth=2, linestyle='-', zorder=3)

        # Styling
        ax.set_xlabel('Time Interval (s)', fontsize=12)
        ax.set_ylabel('P2 - P1 (mmHg)', fontsize=12)

        if title:
            ax.set_title(title, fontsize=14, fontweight='bold')
        else:
            ax.set_title(f'Pressure Difference (P2 - P1) - {filename}\n{interval}s intervals, aggregated by {agg_method}',
                        fontsize=14, fontweight='bold')

        # Thin labels if too many time intervals
        tick_positions, tick_labels = _thin_labels(labels)
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        ax.grid(True, alpha=0.3, axis='y', linestyle='--')

        # Legend
        legend_elements = [
            Patch(facecolor='#d73027', edgecolor='black', label='P2 > P1 (Positive)'),
            Patch(facecolor='#4575b4', edgecolor='black', label='P2 < P1 (Negative)')
        ]
        ax.legend(handles=legend_elements, loc='upper right', fontsize=10)

    else:
        # Multiple files: grouped bar chart
        # Use first file's labels (assume all have same time range)
        first_file = file_labels[0]
        _, labels = aggregated_data[first_file]
        n_intervals = len(labels)

        x_positions = np.arange(n_intervals)
        width = 0.8 / n_files  # Bar width per file

        # Color schemes for different files (alternating red/blue families)
        base_colors = ['#d73027', '#4575b4', '#f46d43', '#74add1', '#fdae61', '#abd9e9']

        for i, filename in enumerate(file_labels):
            aggregated, _ = aggregated_data[filename]
            values = aggregated.values

            offset = width * (i - n_files/2 + 0.5)

            # Use base color with varying alpha for positive/negative
            base_color = base_colors[i % len(base_colors)]
            colors = [base_color] * len(values)

            ax.bar(x_positions + offset, values, width, label=filename,
                  color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)

        # Zero reference line
        ax.axhline(y=0, color='black', linewidth=2, linestyle='-', zorder=3)

        # Styling
        ax.set_xlabel('Time Interval', fontsize=12)
        ax.set_ylabel('P2 - P1 (mmHg)', fontsize=12)

        if title:
            ax.set_title(title, fontsize=14, fontweight='bold')
        else:
            ax.set_title(f'Pressure Difference (P2 - P1) - Multiple Files\n{interval}s intervals, aggregated by {agg_method}',
                        fontsize=14, fontweight='bold')

        # Thin labels if too many time intervals
        tick_positions, tick_labels = _thin_labels(labels)
        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, rotation=45, ha='right')
        ax.grid(True, alpha=0.3, axis='y', linestyle='--')
        ax.legend(loc='upper right', fontsize=9)

    plt.tight_layout()

    # Save or display
    if output_file:
        if os.path.exists(output_file):
            print(f"Replacing existing file: {output_file}")
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Figure saved to {output_file}")
    else:
        plt.show()

def main():
    parser = argparse.ArgumentParser(
        description='Visualize pressure differences (P2-P1) from RHS simulator CSV files as diverging bar charts.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python visualize_pressure_diff.py test1_02042026.csv
  python visualize_pressure_diff.py test1_02042026.csv test2_02042026.csv
  python visualize_pressure_diff.py --all
  python visualize_pressure_diff.py --interval 10 test2_02042026.csv
  python visualize_pressure_diff.py --aggregation median test3_02042026.csv
  python visualize_pressure_diff.py --output pressure_diff.png test1_02042026.csv
        '''
    )

    parser.add_argument('files', nargs='*',
                       help='CSV file(s) from rhs_runs/ (can be just filenames or full paths)')
    parser.add_argument('--interval', type=float, default=1.0,
                       help='Time interval in seconds for aggregation (default: 1)')
    parser.add_argument('--aggregation', choices=['mean', 'median', 'min', 'max'],
                       help='Aggregation method within each interval (default: mean)')
    parser.add_argument('--all', action='store_true',
                       help='Process all CSV files in rhs_runs/ directory')
    parser.add_argument('--output', type=str,
                       help='Save figure to file instead of displaying (e.g., pressure_diff.png)')
    parser.add_argument('--title', type=str,
                       help='Custom title for the chart')

    args = parser.parse_args()

    # Determine which files to process
    if args.all:
        file_paths = discover_csv_files('rhs_runs')
        if not file_paths:
            print("Error: No CSV files found in rhs_runs/")
            sys.exit(1)
    elif args.files:
        file_paths = args.files
    else:
        # Interactive mode - prompt for file
        filepath = input("Enter CSV path (or filename from rhs_runs/): ").strip().strip('"')
        file_paths = [filepath]

    # Load CSV files
    print("\nLoading CSV files...")
    data_dict = load_csv_files(file_paths)

    if not data_dict:
        print("Error: No valid CSV files loaded.")
        sys.exit(1)

    # Process each file
    print(f"\nProcessing files with {args.interval}s intervals, aggregation method: {args.aggregation}")
    aggregated_data = {}

    for filename, df in data_dict.items():
        # Calculate pressure difference
        df = calculate_pressure_difference(df)

        # Aggregate by time interval
        aggregated, labels = aggregate_by_time_interval(df, args.interval, args.aggregation)

        aggregated_data[filename] = (aggregated, labels)

        # Print summary statistics
        print(f"\n{filename}:")
        print(f"  Time range: {df['Time (s)'].min():.2f}s to {df['Time (s)'].max():.2f}s")
        print(f"  P2-P1 range: {df['P2-P1 (mmHg)'].min():.2f} to {df['P2-P1 (mmHg)'].max():.2f} mmHg")
        print(f"  Mean P2-P1: {df['P2-P1 (mmHg)'].mean():.2f} mmHg")
        print(f"  Number of intervals: {len(aggregated)}")

    # Create visualization
    print("\nGenerating diverging bar chart...")
    file_labels = list(aggregated_data.keys())
    create_diverging_bar_chart(aggregated_data, file_labels, args.interval,
                               agg_method=args.aggregation, title=args.title, output_file=args.output)

    if not args.output:
        print("\nClose the plot window to exit.")

if __name__ == '__main__':
    main()
