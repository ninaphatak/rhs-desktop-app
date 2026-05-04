"""Shared Farneback dense optical flow parameters for valve videos.

Both `tools/flow_explore.py` (motion-mask visualizer) and
`tools/analyze_annotations.py` (Mode B accuracy comparison) compute
Farneback flow on the same recordings, so they share one parameter set
to avoid silent drift when the parameters are tuned.

The eventual dataset-exporter target (per CLAUDE.md and the flow-export
design doc) is winsize=21, poly_n=7, poly_sigma=1.5,
OPTFLOW_FARNEBACK_GAUSSIAN. The current values reflect the explorer's
working defaults and will be revisited during the validation study.
"""

FARNEBACK_PARAMS: dict = dict(
    pyr_scale=0.5,
    levels=3,
    winsize=15,
    iterations=3,
    poly_n=5,
    poly_sigma=1.2,
    flags=0,
)
