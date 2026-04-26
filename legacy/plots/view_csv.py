import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import sys

# Load CSV (drag file onto terminal or pass as argument)
if len(sys.argv) > 1:
    filepath = sys.argv[1]
else:
    filepath = input("Enter CSV path: ").strip().strip('"')

df = pd.read_csv(filepath)

# Detect laps early so we can offer lap-based filtering
has_laps = 'Lap' in df.columns and df['Lap'].nunique() > 1
lap_info: dict[int, tuple[float, float]] = {}  # lap_num -> (t_start, t_end)
if has_laps:
    for lap_num in sorted(df['Lap'].unique()):
        lap_data = df[df['Lap'] == lap_num]
        lap_info[lap_num] = (lap_data['Time (s)'].iloc[0], lap_data['Time (s)'].iloc[-1])

# Optional time range / lap filter
t_min = df['Time (s)'].min()
t_max = df['Time (s)'].max()
print(f"\nTime range in file: {t_min:.1f}s – {t_max:.1f}s")
if has_laps:
    print("\nAvailable laps:")
    for lap_num, (ls, le) in lap_info.items():
        print(f"  Lap {lap_num}: {ls:.1f}s – {le:.1f}s")
    print("\nFilter options:")
    print("  - Enter a time range as 'start end' (e.g. '3000 4000')")
    print("  - Enter a lap number (e.g. '3') or range (e.g. '2-5')")
    print("  - Press Enter to plot all")
    range_input = input("Choice: ").strip()
else:
    range_input = input("Enter time range as 'start end' (e.g. '3000 4000'), or press Enter to plot all: ").strip()

if range_input:
    # Check if input is a lap number or lap range
    if has_laps and '-' in range_input and not any(c == '.' for c in range_input):
        # Lap range like "2-5"
        lap_start, lap_end = map(int, range_input.split('-'))
        selected_laps = [n for n in lap_info if lap_start <= n <= lap_end]
        df = df[df['Lap'].isin(selected_laps)]
    elif has_laps and range_input.isdigit():
        # Single lap number
        lap_num = int(range_input)
        df = df[df['Lap'] == lap_num]
    else:
        # Time range
        t_start, t_end = map(float, range_input.split())
        df = df[(df['Time (s)'] >= t_start) & (df['Time (s)'] <= t_end)]

# Channel group selection
GROUPS = {
    "1": "all",
    "2": "pressure",
    "3": "flow",
    "4": "heart_rate",
    "5": "temperature",
}
print("\nWhich channels would you like to plot?")
print("  1) All (default)")
print("  2) Pressure only  (P1, P2)")
print("  3) Flow rate only")
print("  4) Heart rate only")
print("  5) Temperature only")
group_input = input("Enter number [1]: ").strip() or "1"
group = GROUPS.get(group_input, "all")

# Ask whether to run peak/trough analysis on the flow plot
show_peak_analysis = False
show_value_labels = False
if group in ("all", "flow"):
    analysis_input = input("Run peak/trough analysis on flow plot? (y/N): ").strip().lower()
    show_peak_analysis = analysis_input == 'y'
    if show_peak_analysis:
        label_input = input("  Label peak & trough values on plot? (y/N): ").strip().lower()
        show_value_labels = label_input == 'y'

# Same prompt for the pressure plot. Analog signal => uses scipy.find_peaks with
# an adaptive height threshold to ignore small baseline oscillations.
show_pressure_peak_analysis = False
show_pressure_value_labels = False
if group in ("all", "pressure"):
    analysis_input_p = input("Run peak/trough analysis on pressure plot? (y/N): ").strip().lower()
    show_pressure_peak_analysis = analysis_input_p == 'y'
    if show_pressure_peak_analysis:
        label_input_p = input("  Label peak & trough values on plot? (y/N): ").strip().lower()
        show_pressure_value_labels = label_input_p == 'y'

# Optional custom plot title
custom_title = input("Enter plot title (or press Enter for filename): ").strip()

def find_pressure_peaks_and_troughs(t: pd.Series, signal: pd.Series):
    """Detect large per-beat peaks (and intervening troughs) in an analog
    pressure trace.

    Uses scipy.signal.find_peaks with an adaptive height threshold so that
    small baseline oscillations between beats are discarded. Each trough is
    the minimum sample between two consecutive accepted peaks.
    """
    from scipy.signal import find_peaks  # lazy import; only needed here

    t_arr = t.values
    s_arr = signal.values
    if len(s_arr) < 3:
        return np.array([]), np.array([]), np.array([]), np.array([])

    dt = float(np.median(np.diff(t_arr))) if len(t_arr) > 1 else 1.0
    # Min 0.3 s between peaks (handles HR up to ~200 BPM without splitting beats)
    min_dist_samples = max(1, int(round(0.3 / dt))) if dt > 0 else 1
    # Adaptive: 40% of the per-trace max, with a 5 mmHg floor for low-amplitude runs
    height_thresh = max(0.4 * float(np.nanmax(s_arr)), 5.0)

    pk_idx, _ = find_peaks(s_arr, height=height_thresh, distance=min_dist_samples)
    peak_t = t_arr[pk_idx]
    peak_v = s_arr[pk_idx]

    trough_t, trough_v = [], []
    for i in range(len(pk_idx) - 1):
        a, b = pk_idx[i], pk_idx[i + 1]
        rel = int(np.argmin(s_arr[a:b + 1]))
        ti = a + rel
        trough_t.append(t_arr[ti])
        trough_v.append(s_arr[ti])

    return peak_t, peak_v, np.array(trough_t), np.array(trough_v)


def _channel_stats(peak_v: np.ndarray, trough_v: np.ndarray) -> dict:
    """Bundle the per-channel peak/trough stats used in the figure caption."""
    return {
        'n_peaks': len(peak_v),
        'n_troughs': len(trough_v),
        'peak_mean': float(np.mean(peak_v)) if len(peak_v) else 0.0,
        'peak_cv': compute_cv(peak_v),
        'trough_mean': float(np.mean(trough_v)) if len(trough_v) else 0.0,
        'trough_cv': compute_cv(trough_v),
    }


# Build list of panels to show: (axes_label, plot_fn)
def plot_pressure(ax: plt.Axes, t: pd.Series) -> None:
    p1 = df['Pressure 1 (mmHg)']
    p2 = df['Pressure 2 (mmHg)']
    ax.plot(t, p1, 'r-', label='P1 (Atrium)')
    ax.plot(t, p2, 'b-', label='P2 (Ventricle)')

    if show_pressure_peak_analysis:
        p1_pk_t, p1_pk_v, p1_tr_t, p1_tr_v = find_pressure_peaks_and_troughs(t, p1)
        p2_pk_t, p2_pk_v, p2_tr_t, p2_tr_v = find_pressure_peaks_and_troughs(t, p2)

        # Gold-filled peak markers / white-filled trough markers, with the
        # channel's line color as the edge so the user can tell which trace
        # each marker belongs to even when they overlap.
        ax.plot(p1_pk_t, p1_pk_v, 'o', mfc='gold',  mec='red',  mew=0.8, ms=7)
        ax.plot(p2_pk_t, p2_pk_v, 'o', mfc='gold',  mec='blue', mew=0.8, ms=7)
        if len(p1_tr_t):
            ax.plot(p1_tr_t, p1_tr_v, 'o', mfc='white', mec='red',  mew=0.8, ms=7)
        if len(p2_tr_t):
            ax.plot(p2_tr_t, p2_tr_v, 'o', mfc='white', mec='blue', mew=0.8, ms=7)

        if show_pressure_value_labels:
            for pt, pv in zip(p1_pk_t, p1_pk_v):
                ax.annotate(f'{pv:.1f}', xy=(pt, pv), xytext=(0, 8),
                            textcoords='offset points', ha='center', fontsize=7,
                            color='red', fontweight='bold')
            for tt, tv in zip(p1_tr_t, p1_tr_v):
                ax.annotate(f'{tv:.1f}', xy=(tt, tv), xytext=(0, -12),
                            textcoords='offset points', ha='center', fontsize=7,
                            color='red', fontweight='bold')
            for pt, pv in zip(p2_pk_t, p2_pk_v):
                ax.annotate(f'{pv:.1f}', xy=(pt, pv), xytext=(0, 8),
                            textcoords='offset points', ha='center', fontsize=7,
                            color='blue', fontweight='bold')
            for tt, tv in zip(p2_tr_t, p2_tr_v):
                ax.annotate(f'{tv:.1f}', xy=(tt, tv), xytext=(0, -12),
                            textcoords='offset points', ha='center', fontsize=7,
                            color='blue', fontweight='bold')

        ax._pressure_stats = {
            'p1': _channel_stats(p1_pk_v, p1_tr_v),
            'p2': _channel_stats(p2_pk_v, p2_tr_v),
        }

    ax.set_ylabel('Pressure (mmHg)')
    ax.legend()
    ax.grid(True, alpha=0.3)

def find_flow_peaks_and_troughs(t: pd.Series, flow: pd.Series):
    """Detect local max/min turning points in a step-function flow signal.

    Collapses consecutive duplicate values to find the underlying steps,
    then identifies where direction reverses (peak = higher than both
    neighbors, trough = lower than both neighbors among the step levels).
    """
    t_arr = t.values
    flow_arr = flow.values

    # Collapse consecutive duplicates to get step change points
    change_mask = np.concatenate(([True], flow_arr[1:] != flow_arr[:-1]))
    step_idx = np.where(change_mask)[0]
    step_t = t_arr[step_idx]
    step_v = flow_arr[step_idx]

    # Find all turning points among the step levels
    raw_peaks = []   # (time, value, index)
    raw_troughs = []
    for i in range(1, len(step_v) - 1):
        if step_v[i] > step_v[i - 1] and step_v[i] > step_v[i + 1]:
            raw_peaks.append((step_t[i], step_v[i], i))
        elif step_v[i] < step_v[i - 1] and step_v[i] < step_v[i + 1]:
            raw_troughs.append((step_t[i], step_v[i], i))

    # Filter: a peak must be >10 mL/s above its nearest trough(s)
    peak_times, peak_vals = [], []
    trough_times, trough_vals = [], []
    trough_arr = np.array([v for _, v, _ in raw_troughs]) if raw_troughs else np.array([])
    trough_t_arr = np.array([t for t, _, _ in raw_troughs]) if raw_troughs else np.array([])

    for pt, pv, pi in raw_peaks:
        if len(trough_t_arr) == 0:
            peak_times.append(pt)
            peak_vals.append(pv)
            continue
        # Find the previous trough (latest trough before this peak)
        before = np.where(trough_t_arr < pt)[0]
        # Find the next trough (earliest trough after this peak)
        after = np.where(trough_t_arr > pt)[0]
        prev_tv = trough_arr[before[-1]] if len(before) else None
        next_tv = trough_arr[after[0]] if len(after) else None
        # Peak must be >10 mL/s above both adjacent troughs
        ok = True
        if prev_tv is not None and pv - prev_tv <= 10.0:
            ok = False
        if next_tv is not None and pv - next_tv <= 10.0:
            ok = False
        if ok:
            peak_times.append(pt)
            peak_vals.append(pv)

    # Keep only troughs that sit between accepted peaks
    if len(peak_times) >= 2:
        for tt, tv, ti in raw_troughs:
            if peak_times[0] <= tt <= peak_times[-1]:
                trough_times.append(tt)
                trough_vals.append(tv)
    else:
        trough_times = [t for t, _, _ in raw_troughs]
        trough_vals = [v for _, v, _ in raw_troughs]

    return (np.array(peak_times), np.array(peak_vals),
            np.array(trough_times), np.array(trough_vals))


def compute_cv(values: np.ndarray) -> float:
    """Coefficient of variation (std / mean) as a percentage."""
    if len(values) == 0 or np.mean(values) == 0:
        return 0.0
    return (np.std(values) / np.mean(values)) * 100


def plot_flow(ax: plt.Axes, t: pd.Series) -> None:
    flow = df['Flow Rate (mL/s)']
    ax.plot(t, flow, 'g-', label='Flow Rate')

    # --- Peak / trough analysis (only if user opted in) ---
    if show_peak_analysis:
        peak_t, peak_v, trough_t, trough_v = find_flow_peaks_and_troughs(t, flow)

        # Mark peaks and troughs on the plot
        ax.plot(peak_t, peak_v, 'ro', markersize=7)
        if len(trough_t):
            ax.plot(trough_t, trough_v, 'bo', markersize=7)

        # Label each peak/trough with its value (if user opted in)
        if show_value_labels:
            for pt, pv in zip(peak_t, peak_v):
                ax.annotate(f'{pv:.1f}', xy=(pt, pv), xytext=(0, 8),
                            textcoords='offset points', ha='center', fontsize=7,
                            color='red', fontweight='bold')
            for tt, tv in zip(trough_t, trough_v):
                ax.annotate(f'{tv:.1f}', xy=(tt, tv), xytext=(0, -12),
                            textcoords='offset points', ha='center', fontsize=7,
                            color='blue', fontweight='bold')

        # Store stats for display below the figure
        ax._flow_stats = {
            'n_peaks': len(peak_v), 'n_troughs': len(trough_v),
            'peak_mean': np.mean(peak_v) if len(peak_v) else 0,
            'peak_cv': compute_cv(peak_v),
            'trough_mean': np.mean(trough_v) if len(trough_v) else 0,
            'trough_cv': compute_cv(trough_v),
        }

    ax.set_ylabel('Flow Rate (mL/s)')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)

def plot_heart_rate(ax: plt.Axes, t: pd.Series) -> None:
    ax.plot(t, df['Heart Rate (BPM)'], color='purple', label='Heart Rate')
    ax.set_ylabel('Heart Rate (BPM)')
    ax.legend()
    ax.grid(True, alpha=0.3)

def plot_temperature(ax: plt.Axes, t: pd.Series) -> None:
    temp_cols = [c for c in df.columns if 'Temperature' in c]
    colors = ['orange', 'red', 'cyan', 'magenta']
    for col, color in zip(temp_cols, colors):
        ax.plot(t, df[col], color=color, label=col.replace(' (°C)', ''))
    ax.set_ylabel('Temperature (°C)')
    ax.set_ylim(25, 39)
    ax.legend()
    ax.grid(True, alpha=0.3)

panel_map = {
    "pressure":   plot_pressure,
    "flow":       plot_flow,
    "heart_rate": plot_heart_rate,
    "temperature": plot_temperature,
}

if group == "all":
    panels = list(panel_map.keys())
else:
    panels = [group]

t = df['Time (s)']
n = len(panels)
fig, axes = plt.subplots(n, 1, figsize=(12, 3 * n), sharex=True)
if n == 1:
    axes = [axes]

for ax, key in zip(axes, panels):
    panel_map[key](ax, t)

# Highlight lap regions if Lap column exists and has multiple laps in the filtered data
if 'Lap' in df.columns and df['Lap'].nunique() > 1:
    lap_nums = sorted(df['Lap'].unique())

    # Ask user if they want to rename any lap labels
    print(f"\nLaps in plot: {', '.join(f'Lap {n}' for n in lap_nums)}")
    rename_input = input("Rename lap labels? (y/N): ").strip().lower()
    lap_labels: dict[int, str] = {}
    if rename_input == 'y':
        for lap_num in lap_nums:
            custom = input(f"  Replace 'Lap {lap_num}' as (press Enter to keep): ").strip()
            lap_labels[lap_num] = custom if custom else f'Lap {lap_num}'
    else:
        lap_labels = {ln: f'Lap {ln}' for ln in lap_nums}

    lap_colors = plt.cm.tab10.colors
    for lap_num in lap_nums:
        lap_data = df[df['Lap'] == lap_num]
        ls = lap_data['Time (s)'].iloc[0]
        le = lap_data['Time (s)'].iloc[-1]
        color = lap_colors[int((lap_num - 1) % len(lap_colors))]
        for ax in axes:
            ax.axvspan(ls, le, alpha=0.1, color=color)
        # Label with lap name + start time
        axes[0].text(
            (ls + le) / 2, axes[0].get_ylim()[1],
            f'{lap_labels[lap_num]} ({ls:.1f}s)',
            ha='center', va='bottom',
            fontsize=9, color=color, fontweight='bold',
        )

axes[-1].set_xlabel('Time (s)')
plt.suptitle(custom_title if custom_title else filepath.split('/')[-1])

# Collect any analysis stats stashed on axes by the panel functions.
flow_stats = None
pressure_stats = None
for ax in axes:
    if hasattr(ax, '_flow_stats'):
        flow_stats = ax._flow_stats
    if hasattr(ax, '_pressure_stats'):
        pressure_stats = ax._pressure_stats

stats_lines: list[str] = []

if flow_stats:
    s = flow_stats
    stats_lines.append(
        f"Flow   Peaks (n={s['n_peaks']:>2}): mean={s['peak_mean']:6.2f} mL/s, CV={s['peak_cv']:5.1f}%   "
        f"Troughs (n={s['n_troughs']:>2}): mean={s['trough_mean']:6.2f} mL/s, CV={s['trough_cv']:5.1f}%"
    )

if pressure_stats:
    for label, key in (("P1", 'p1'), ("P2", 'p2')):
        s = pressure_stats[key]
        if s['n_peaks'] == 0:
            continue
        stats_lines.append(
            f"{label}     Peaks (n={s['n_peaks']:>2}): mean={s['peak_mean']:6.2f} mmHg, CV={s['peak_cv']:5.1f}%   "
            f"Troughs (n={s['n_troughs']:>2}): mean={s['trough_mean']:6.2f} mmHg, CV={s['trough_cv']:5.1f}%"
        )

if stats_lines:
    stats_text = "\n".join(stats_lines)
    # Reserve more bottom margin when there are multiple lines so they all fit.
    bottom_margin = 0.06 + 0.03 * len(stats_lines)
    fig.subplots_adjust(bottom=bottom_margin)
    fig.text(0.5, 0.01, stats_text, ha='center', va='bottom',
             fontsize=9, fontfamily='monospace',
             bbox=dict(boxstyle='round,pad=0.4', facecolor='wheat', alpha=0.8))

plt.tight_layout(rect=[0, 0.05 if stats_lines else 0, 1, 0.96])
plt.show()