#!/usr/bin/env python3
"""
Test Script: Camera + Dot Tracking Pipeline
============================================

Run this to test your Basler camera and dot tracking today!

Usage:
    python test_camera_tracking.py              # Auto-detect and run
    python test_camera_tracking.py --synthetic  # Test with fake dots (no camera)
    python test_camera_tracking.py --info       # Just list cameras

Controls (when running):
    q       - Quit
    s       - Set reference position (for displacement tracking)
    r       - Reset tracker (clear IDs)
    +/-     - Adjust threshold up/down
    m       - Toggle binary mask view
    SPACE   - Pause/resume
    
Requirements:
    pip install pypylon opencv-python numpy PyQt6
"""

import sys
import time
import argparse
import logging

import cv2
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import our modules
try:
    from src.core.basler_camera import BaslerCamera, PYPYLON_AVAILABLE
    from src.core.dot_tracker import DotTracker
except ImportError:
    # If running from project root, try relative import
    sys.path.insert(0, '.')
    from src.core.basler_camera import BaslerCamera, PYPYLON_AVAILABLE
    from src.core.dot_tracker import DotTracker


class CameraTestApp:
    """
    Simple test application for camera + dot tracking.
    Uses OpenCV window for display (no Qt GUI needed).
    """
    
    def __init__(self):
        self.camera = BaslerCamera()
        self.tracker = DotTracker(threshold=50, min_area=30, max_area=500)
        
        # State
        self.latest_frame = None
        self.latest_tracking = None
        self.show_mask = False
        self.paused = False
        self.running = True
        
        # Stats
        self.frame_count = 0
        self.start_time = None
        
        # Connect signals
        self.camera.frame_ready.connect(self._on_frame)
        self.camera.fps_updated.connect(self._on_fps)
        self.camera.error_occurred.connect(self._on_error)
        self.camera.connection_changed.connect(self._on_connection)
        
        self.current_fps = 0.0
    
    def _on_frame(self, frame_data: dict):
        """Handle incoming frame from camera."""
        if self.paused:
            return
            
        self.latest_frame = frame_data["frame"]
        self.frame_count = frame_data["frame_number"]
        
        # Run dot detection
        self.latest_tracking = self.tracker.detect(self.latest_frame)
    
    def _on_fps(self, fps: float):
        """Handle FPS update."""
        self.current_fps = fps
    
    def _on_error(self, msg: str):
        """Handle camera error."""
        logger.error(f"Camera error: {msg}")
    
    def _on_connection(self, connected: bool):
        """Handle connection change."""
        logger.info(f"Camera {'connected' if connected else 'disconnected'}")
    
    def run_with_camera(self, camera_index: int = 0):
        """Run test with actual Basler camera."""
        
        print("\n" + "="*60)
        print("CAMERA + DOT TRACKING TEST")
        print("="*60)
        
        # List cameras
        cameras = BaslerCamera.list_cameras()
        if not cameras:
            print("\n❌ No cameras found!")
            print("   Make sure your Basler camera is connected via USB 3.0")
            print("   Try running Pylon Viewer first to verify the camera works")
            return False
        
        print(f"\nFound {len(cameras)} camera(s):")
        for i, name in enumerate(cameras):
            marker = "→" if i == camera_index else " "
            print(f"  {marker} [{i}] {name}")
        
        # Connect
        print(f"\nConnecting to camera {camera_index}...")
        if not self.camera.connect(camera_index):
            print("❌ Failed to connect!")
            return False
        
        print("✓ Connected!")
        print("\nStarting frame capture...")
        self.camera.start()
        self.start_time = time.time()
        
        self._run_display_loop()
        
        # Cleanup
        print("\nStopping camera...")
        self.camera.stop()
        self.camera.disconnect()
        print("✓ Done!")
        
        return True
    
    def run_synthetic(self):
        """Run test with synthetic dot images (no camera needed)."""
        
        print("\n" + "="*60)
        print("SYNTHETIC DOT TRACKING TEST (No camera)")
        print("="*60)
        print("\nGenerating synthetic frames with moving dots...")
        
        self.start_time = time.time()
        
        # Generate frames in the display loop
        self._run_synthetic_loop()
        
        print("\n✓ Done!")
        return True
    
    def _run_display_loop(self):
        """Main display loop using OpenCV window."""
        
        print("\n" + "-"*60)
        print("CONTROLS:")
        print("  q       - Quit")
        print("  s       - Set reference position")
        print("  r       - Reset tracker")
        print("  +/-     - Adjust threshold")
        print("  m       - Toggle mask view")
        print("  SPACE   - Pause/resume")
        print("-"*60 + "\n")
        
        cv2.namedWindow("Camera Test", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Camera Test", 1280, 800)
        
        while self.running:
            # Process Qt events (needed for signals)
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.processEvents()
            
            # Display frame
            if self.latest_frame is not None and self.latest_tracking is not None:
                display = self._create_display_frame()
                cv2.imshow("Camera Test", display)
            
            # Handle keyboard
            key = cv2.waitKey(16) & 0xFF  # ~60fps display
            self._handle_key(key)
            
            if not self.running:
                break
        
        cv2.destroyAllWindows()
    
    def _run_synthetic_loop(self):
        """Generate and process synthetic frames."""
        
        print("\n" + "-"*60)
        print("CONTROLS:")
        print("  q       - Quit")
        print("  s       - Set reference position")
        print("  r       - Reset tracker")
        print("  +/-     - Adjust threshold")
        print("  m       - Toggle mask view")
        print("-"*60 + "\n")
        
        cv2.namedWindow("Synthetic Test", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Synthetic Test", 800, 600)
        
        frame_num = 0
        
        while self.running:
            if not self.paused:
                # Generate synthetic frame
                self.latest_frame = self._generate_synthetic_frame(frame_num)
                self.latest_tracking = self.tracker.detect(self.latest_frame)
                self.frame_count = frame_num
                frame_num += 1
            
            # Display
            if self.latest_frame is not None and self.latest_tracking is not None:
                display = self._create_display_frame()
                cv2.imshow("Synthetic Test", display)
            
            # Handle keyboard
            key = cv2.waitKey(33) & 0xFF  # ~30fps for synthetic
            self._handle_key(key)
            
            if not self.running:
                break
        
        cv2.destroyAllWindows()
    
    def _generate_synthetic_frame(self, frame_num: int) -> np.ndarray:
        """Generate a synthetic frame with moving dots."""
        
        # White background
        frame = np.ones((480, 640), dtype=np.uint8) * 240
        
        # Add some noise for realism
        noise = np.random.randint(-10, 10, frame.shape, dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        
        # Dot positions that move slightly over time
        t = frame_num * 0.05  # Time parameter
        
        dots = [
            (200 + int(20 * np.sin(t)), 150 + int(10 * np.cos(t))),
            (400 + int(15 * np.cos(t * 1.3)), 200 + int(25 * np.sin(t * 0.8))),
            (300 + int(10 * np.sin(t * 0.7)), 350 + int(15 * np.cos(t * 1.1))),
        ]
        
        # Draw black dots
        for (x, y) in dots:
            cv2.circle(frame, (x, y), 12, 20, -1)  # Dark gray filled circle
        
        return frame
    
    def _create_display_frame(self) -> np.ndarray:
        """Create annotated display frame with info overlay."""
        
        if self.show_mask and self.latest_tracking.get("binary_mask") is not None:
            # Show binary mask
            mask = self.latest_tracking["binary_mask"]
            display = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
        else:
            # Show annotated frame
            display = self.tracker.annotate_frame(
                self.latest_frame,
                self.latest_tracking["dots"],
                show_ids=True,
                show_displacement=True,
            )
        
        # Add info overlay
        h, w = display.shape[:2]
        
        # Semi-transparent background for text
        overlay = display.copy()
        cv2.rectangle(overlay, (10, 10), (350, 140), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.5, display, 0.5, 0, display)
        
        # Info text
        info_lines = [
            f"Frame: {self.frame_count}",
            f"FPS: {self.current_fps:.1f}",
            f"Dots: {self.latest_tracking['dot_count']}",
            f"Threshold: {self.tracker.threshold}",
            f"View: {'MASK' if self.show_mask else 'CAMERA'}",
        ]
        
        y = 35
        for line in info_lines:
            cv2.putText(display, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, (0, 255, 0), 2)
            y += 25
        
        # Dot positions
        if self.latest_tracking["dots"]:
            y = 170
            cv2.putText(display, "Dot Positions:", (20, y), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            y += 20
            
            for dot in self.latest_tracking["dots"][:5]:  # Show max 5
                text = f"  #{dot['id']}: ({dot['x']}, {dot['y']})"
                if dot['dx'] != 0 or dot['dy'] != 0:
                    text += f" Δ({dot['dx']}, {dot['dy']})"
                cv2.putText(display, text, (20, y),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
                y += 18
        
        # Paused indicator
        if self.paused:
            cv2.putText(display, "PAUSED", (w//2 - 60, h//2),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)
        
        # Reference set indicator
        if self.tracker._reference_positions:
            cv2.putText(display, "REF SET", (w - 100, 30),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        
        return display
    
    def _handle_key(self, key: int):
        """Handle keyboard input."""
        
        if key == ord('q'):
            self.running = False
            
        elif key == ord('s'):
            self.tracker.set_reference()
            print(f"✓ Reference set for {len(self.tracker._reference_positions)} dots")
            
        elif key == ord('r'):
            self.tracker.reset()
            print("✓ Tracker reset")
            
        elif key == ord('+') or key == ord('='):
            self.tracker.threshold = min(255, self.tracker.threshold + 5)
            print(f"  Threshold: {self.tracker.threshold}")
            
        elif key == ord('-'):
            self.tracker.threshold = max(0, self.tracker.threshold - 5)
            print(f"  Threshold: {self.tracker.threshold}")
            
        elif key == ord('m'):
            self.show_mask = not self.show_mask
            print(f"  View: {'MASK' if self.show_mask else 'CAMERA'}")
            
        elif key == ord(' '):
            self.paused = not self.paused
            print(f"  {'PAUSED' if self.paused else 'RESUMED'}")


def list_cameras():
    """Just list available cameras and exit."""
    
    print("\n" + "="*60)
    print("BASLER CAMERA DETECTION")
    print("="*60)
    
    if not PYPYLON_AVAILABLE:
        print("\n❌ pypylon not installed!")
        print("   Install with: pip install pypylon")
        print("   Also install Pylon SDK from baslerweb.com")
        return
    
    cameras = BaslerCamera.list_cameras()
    
    if not cameras:
        print("\n❌ No cameras found!")
        print("\nTroubleshooting:")
        print("  1. Check USB 3.0 connection (blue port)")
        print("  2. Try a different USB cable")
        print("  3. Open Pylon Viewer to verify camera works")
        print("  4. On Linux, check udev rules for camera permissions")
        return
    
    print(f"\n✓ Found {len(cameras)} camera(s):\n")
    
    for i, info in enumerate(BaslerCamera.get_camera_info()):
        print(f"  [{i}] {info['friendly_name']}")
        print(f"      Model:  {info['model']}")
        print(f"      Serial: {info['serial']}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Test Basler camera + dot tracking pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_camera_tracking.py              # Run with camera
  python test_camera_tracking.py --synthetic  # Run without camera
  python test_camera_tracking.py --info       # List cameras only
  python test_camera_tracking.py --camera 1   # Use camera index 1
        """
    )
    
    parser.add_argument(
        '--synthetic', '-s',
        action='store_true',
        help='Run with synthetic frames (no camera needed)'
    )
    
    parser.add_argument(
        '--info', '-i',
        action='store_true',
        help='Just list available cameras and exit'
    )
    
    parser.add_argument(
        '--camera', '-c',
        type=int,
        default=0,
        help='Camera index to use (default: 0)'
    )
    
    parser.add_argument(
        '--threshold', '-t',
        type=int,
        default=50,
        help='Initial threshold value 0-255 (default: 50)'
    )
    
    args = parser.parse_args()
    
    # Info only
    if args.info:
        list_cameras()
        return 0
    
    # Need Qt app for signals even without GUI
    from PyQt6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    
    # Create test app
    test_app = CameraTestApp()
    test_app.tracker.threshold = args.threshold
    
    # Run appropriate mode
    if args.synthetic:
        success = test_app.run_synthetic()
    else:
        if not PYPYLON_AVAILABLE:
            print("\n❌ pypylon not installed!")
            print("   Install with: pip install pypylon")
            print("   Or run with --synthetic flag to test without camera")
            return 1
        
        success = test_app.run_with_camera(args.camera)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())