# TODO / Deferred Fixes

Running list of known issues and improvements that are not currently
blocking the deliverable but should be addressed when convenient.

## GUI grab thread drops frames during recording

**Status:** Deferred. Workaround in place (split USB docks + clock-offset
correction in triangulation). Cameras are essentially hardware-trigger-
quality synced at the hw_timestamp level once the per-camera clock
origin offset is subtracted.

**Symptom:** When recording from the PySide6 GUI, both cameras drop
~7% of frames over a 30-40 second clip, scattered as single-frame gaps.
A headless `tools/record_valve.py --dual` recording on the same
hardware drops only ~0.17% (with split docks) or ~2% (both cams on
the same dock). So the cameras and Pylon are fine; the GUI grab thread
is missing wakeups.

**Evidence (2026-05-10):**

| Recording | Loss rate | Per-cam hw_ticks gaps >50ms |
|---|---|---|
| GUI `14-23-18` (both cams, one dock) | ~7% | 71-75 / ~1014 |
| Headless `--dual` `14-50-23` (one dock) | ~2% | 3-5 / 1199 |
| Headless `--dual` `15-30-43` (split docks) | 0.17% | 1 / 1199 |

In all GUI recordings, `system_time` between consecutive frames
exhibits 200+ ms spikes that line up exactly with the hw_timestamp
gaps — i.e. frames arrive at the camera on schedule but the Python
grab thread is too busy to retrieve them, and `GrabStrategy_LatestImageOnly`
discards anything not consumed in time.

**Likely cause:** The grab thread does too much per frame — pulls the
frame, copies it, writes it to the ffmpeg stdin pipe, emits a Qt signal
to update the preview, and updates the timestamp sidecar. Under GIL
contention with the UI thread, one of these blocks long enough to miss
the next frame.

**Possible fixes (in order of effort):**

1. **Offload ffmpeg pipe writes to a writer thread per camera** with a
   small bounded queue. The grab thread just enqueues the raw bytes
   and returns. This is the biggest contributor: ffmpeg's stdin can
   stall briefly when its internal buffer is full.
2. **Decimate the preview update.** Only emit every Nth frame to the
   preview widget; the live view doesn't need 30 fps.
3. **Move timestamp sidecar writes to the writer thread** along with
   the frame bytes (write both atomically).
4. **Investigate Basler grab strategy.** `GrabStrategy_OneByOne` would
   queue missed frames instead of discarding them, surfacing the
   problem rather than hiding it — useful for diagnosis but doesn't
   fix the throughput issue.

**Why we're deferring:** Split USB docks + correct timestamp pairing
already gives us ~0.17% loss and microsecond-level sync (after constant
offset correction). The triangulation pipeline can tolerate this.
Only revisit if a recording session shows the loss rate creeping back
up, or if we need the GUI for something more demanding than monitoring.

**Related files:** `src/core/basler_camera.py`, `src/ui/camera_panel.py`,
`tools/record_valve.py` (headless A/B reference).
