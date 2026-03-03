# Solenoid Control Protocol (Future)

This document describes the planned serial protocol for starting and stopping the RHS solenoid from the desktop app. **This requires firmware modification and is not yet implemented.**

## Current State

- The solenoid is controlled by a manual potentiometer on the hardware
- The Arduino firmware does not listen for serial commands
- The app is read-only (monitoring only)

## Proposed Serial Commands

| Direction | Command | Meaning |
|-----------|---------|---------|
| App -> Arduino | `S\n` | Start solenoid cycling |
| App -> Arduino | `X\n` | Stop solenoid cycling |

## Arduino Firmware Changes Required

Add to `loop()` in `rhs_firmware.ino`:

```cpp
// At top of file, add:
bool running = false;

// In loop(), add before solenoid logic:
if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == 'S') {
        running = true;
    } else if (cmd == 'X') {
        running = false;
        // Ensure solenoid is OFF when stopped
        digitalWrite(solenoidPin, LOW);
    }
}

// Gate existing solenoid cycling behind:
if (running) {
    // ... existing solenoid cycling code ...
}
```

Estimated change: ~15 lines of code.

## Safety Considerations

- **Default state on power-up:** solenoid OFF (`running = false`)
- **Default state on serial disconnect:** solenoid stays in last state; physical E-stop is the safety mechanism
- **No automatic start:** app never sends `S\n` without explicit user action (button click)
- The physical emergency stop button on the hardware always overrides software control

## GUI Design

- "Start RHS" / "Stop RHS" toggle button in the control bar
- Button is **disabled (grayed out)** until firmware is updated to support serial commands
- Tooltip: "Requires firmware update — see docs/solenoid_protocol.md"
- When enabled: green "Start RHS" → red "Stop RHS" toggle behavior
