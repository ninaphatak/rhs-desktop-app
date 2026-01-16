"""
Purpose: Detect black dots on white valve using grayscale thresholding
Input: 
- Frame (numpy array, grayscale)
- threshold value (0-255, dots darker than this)
- min/max dot area (filter noise and large blobs)

Output: 
{
    "timestamp": float,
    "dots": [
        {"id": 0, "x": 523, "y": 412, "area": 156},
        {"id": 1, "x": 891, "y": 398, "area": 142},
    ],
    "dot_count": int,
    "frame_annotated": numpy.ndarray,  # Frame with dots circled
}
```

**Class Structure:**
```
DotTracker
│
├── Attributes:
│   ├── threshold: int           # Binary threshold value (default 50)
│   ├── min_area: int            # Minimum dot area in pixels (default 30)
│   ├── max_area: int            # Maximum dot area in pixels (default 500)
│   └── _previous_dots: list     # For tracking continuity
│
├── Methods:
│   ├── detect(frame) → dict             # Find dots in frame
│   ├── annotate_frame(frame, dots) → ndarray  # Draw circles on dots
│   ├── set_threshold(value: int)        # Adjust threshold
│   ├── set_area_range(min: int, max: int)  # Adjust size filter
│   └── calculate_displacement(dots, reference) → list  # Displacement from reference
│
└── Internal:
    ├── _threshold_frame(frame) → binary mask
    ├── _find_contours(mask) → contours
    ├── _filter_contours(contours) → valid dots
    └── _assign_ids(dots) → dots with consistent IDs


Key Logic: 

import cv2
import numpy as np

def detect(self, frame):
    # Threshold (black dots on white background)
    _, binary = cv2.threshold(frame, self.threshold, 255, cv2.THRESH_BINARY_INV)
    
    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    dots = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if self.min_area < area < self.max_area:
            M = cv2.moments(contour)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                dots.append({"x": cx, "y": cy, "area": area})
    
    # Assign consistent IDs based on position proximity to previous frame
    dots = self._assign_ids(dots)
    
    return {"dots": dots, "dot_count": len(dots), ...}
```

"""