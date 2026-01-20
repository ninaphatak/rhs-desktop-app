# Timeline Update Notice

**Date:** January 19, 2026

## Major Scope Change: Control System Added

The RHS Desktop Application project scope has expanded from a **passive monitoring tool** to an **active control system** with monitoring capabilities.

### What Changed

**Original Plan (8 weeks):**
- Real-time sensor data visualization
- Camera feed with dot tracking
- Data logging to CSV
- MapAnything export for 3D reconstruction

**New Plan (10 weeks, Week 2-12):**
- Everything above, PLUS:
- Bidirectional Arduino communication
- Hardware control interface (fan, solenoid, BPM)
- Three control modes (POT/AUTO/MANUAL)
- Emergency stop system
- Command validation and safety features

### Timeline Files

| File | Purpose |
|------|---------|
| `RHS_Development_Timeline.md` | **CURRENT** - 10-week plan with control system |
| `RHS_Development_Timeline_BACKUP.md` | Original 8-week monitoring-only plan (reference) |
| `RHS_Code_Structure.md` | Updated architecture with control components |

### Key Additions

**New Weeks:**
- **Week 4.5 (Jan 30 - Feb 2):** Arduino firmware modification for bidirectional communication
- **Week 6 (Feb 10-16):** Hardware control panel implementation
- **Week 11 (Mar 17-20):** Control system integration testing

**Enhanced Weeks:**
- **Week 4 (Jan 23-29):** Added command sending to ArduinoHandler
- **Week 5 (Feb 3-9):** Added hardware control state to StateManager and 3-column UI layout

### Impact

- **Timeline:** Extended from 8 weeks to 10 weeks (Week 2-12, ending March 22, 2026)
- **Work Hours:** Increased from ~80 hours to ~100 hours
- **Arduino Work:** ~15 hours of firmware development (YOU are responsible for this)
- **Risk:** Higher complexity, but more complete solution

### Critical Path

The control system features are now on the critical path:
1. Week 4 (Jan 23-29): Bidirectional ArduinoHandler
2. Week 4.5 (Jan 30 - Feb 2): Arduino firmware accepting commands
3. Week 5 (Feb 3-9): State manager with control state
4. Week 6 (Feb 10-16): Hardware control panel UI

Camera/dot tracking can proceed in parallel after Week 5.

---

**Bottom Line:** This is a bigger, more ambitious project, but it delivers a complete control system rather than just a monitoring tool. The extra 2 weeks are necessary for safe, reliable hardware control.
