"""
Purpose: Serial Communication with Arduino

Input:
- Serial port name
- Baud rate: 31250

Output:
- timestamp
- p1
- p2
- flowrate
- heart rate

**Class Structure:**
```
ArduinoHandler(QThread)
│
├── Signals:
│   ├── data_received(dict)      # Emitted with parsed sensor data
│   ├── connection_changed(bool) # Emitted on connect/disconnect
│   └── error_occurred(str)      # Emitted on error
│
├── Methods:
│   ├── list_ports() → list      # Static: get available ports
│   ├── connect(port: str)       # Open serial connection
│   ├── disconnect()             # Close connection
│   ├── run()                    # Thread loop: read → parse → emit
│   └── stop()                   # Stop thread gracefully
│
└── Internal:
    └── _parse_data(raw: str) → dict

    Key Logic: 
    - read lines from serial continuously
    - parse space-separated values: "P1 P2 FLOW HR"
    - add timestamp
    - emit signal with dict
    - handle malformed data gracefully (log, skip)

"""