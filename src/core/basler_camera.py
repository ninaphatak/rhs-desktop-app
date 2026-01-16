"""
Docstring for rhs-desktop-app.src.core.basler_camera

Purpose: Capture frames from Basler Camera using pypylon
Input: 
- camera index (default 0)
- target FPS (default 60 FPS)
- exposure time in microseconds (default 1000 = 1ms)

{
    "timestamp": float,
    "frame": numpy.ndarray,    # Shape: (1200, 1920) grayscale
    "frame_number": int,
}
```

**Class Structure:**
```
BaslerCamera(QThread)
│
├── Signals:
│   ├── frame_ready(dict)        # Emitted with frame data
│   ├── connection_changed(bool) # Emitted on connect/disconnect
│   ├── fps_updated(float)       # Actual FPS measurement
│   └── error_occurred(str)      # Emitted on error
│
├── Methods:
│   ├── list_cameras() → list    # Static: enumerate cameras
│   ├── connect(index: int)      # Open camera
│   ├── disconnect()             # Release camera
│   ├── set_exposure(us: int)    # Set exposure time
│   ├── set_fps(fps: int)        # Set frame rate
│   ├── run()                    # Thread loop: grab → emit
│   └── stop()                   # Stop thread gracefully
│
└── Internal:
    └── _configure_camera()      # Set camera parameters

    
from pypylon import pylon

# Connect
tl_factory = pylon.TlFactory.GetInstance()
camera = pylon.InstantCamera(tl_factory.CreateFirstDevice())
camera.Open()

# Configure
camera.ExposureTime.SetValue(1000)  # 1ms
camera.AcquisitionFrameRateEnable.SetValue(True)
camera.AcquisitionFrameRate.SetValue(60)

# Grab loop
camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
while running:
    grab_result = camera.RetrieveResult(5000)
    if grab_result.GrabSucceeded():
        frame = grab_result.Array  # numpy array, grayscale
        emit signal
    grab_result.Release()

"""