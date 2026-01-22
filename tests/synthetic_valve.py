"""
Test video generator that simulates what the camera will see
"""

import cv2
import numpy as np


class SyntheticValveGenerator:
    """
    Generates fake valve frames for testing tracker without hardware.
    Simulates markers moving in realistic patterns.
    """

    def __init__(
        self,
        resolution: tuple = (1920, 1200),
        num_markers: int = 4,
        marker_radius: int = 15,
    ):
        self.resolution = resolution
        self.num_markers = num_markers
        self.marker_radius = marker_radius

        # Define reference marker positions (normalized 0-1)
        # Asymmetric pattern for unambiguous identification
        self.reference_positions = [
            (0.5, 0.3),   # Top center
            (0.35, 0.6),  # Bottom left
            (0.65, 0.6),  # Bottom right
            (0.5, 0.75),  # Bottom center
        ][:num_markers]

    def generate_frame(
        self,
        cycle_phase: float,  # 0.0 to 1.0 (one heartbeat cycle)
        displacement_magnitude: float = 20.0,  # pixels
    ) -> np.ndarray:
        """Generate a single frame at given phase of cardiac cycle."""

        # White background (valve surface)
        frame = np.ones((self.resolution[1], self.resolution[0]), dtype=np.uint8) * 255

        # Calculate displaced positions based on cycle phase
        # Simulate valve bulging outward during systole
        for i, (nx, ny) in enumerate(self.reference_positions):
            # Base position in pixels
            x = int(nx * self.resolution[0])
            y = int(ny * self.resolution[1])

            # Add displacement (sinusoidal motion simulating heartbeat)
            # Each marker moves slightly differently to simulate deformation
            phase_offset = i * 0.1  # Markers don't all move in sync
            displacement = displacement_magnitude * np.sin(2 * np.pi * (cycle_phase + phase_offset))

            # Radial displacement from center
            center_x, center_y = self.resolution[0] / 2, self.resolution[1] / 2
            dx = (x - center_x) / self.resolution[0]
            dy = (y - center_y) / self.resolution[1]

            x += int(dx * displacement)
            y += int(dy * displacement)

            # Draw black marker
            cv2.circle(frame, (x, y), self.marker_radius, 0, -1)

        return frame

    def generate_video(
        self,
        output_path: str,
        duration_seconds: float = 5.0,
        fps: int = 60,
        bpm: int = 72,
    ):
        """Generate a test video file."""

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, self.resolution, isColor=False)

        total_frames = int(duration_seconds * fps)
        beats_per_second = bpm / 60.0

        for frame_idx in range(total_frames):
            t = frame_idx / fps
            cycle_phase = (t * beats_per_second) % 1.0

            frame = self.generate_frame(cycle_phase)
            out.write(frame)

        out.release()
        print(f"Generated {total_frames} frames at {output_path}")


if __name__ == "__main__":
    gen = SyntheticValveGenerator(num_markers=4)
    gen.generate_video("test_valve_72bpm.mp4", duration_seconds=5, bpm=72)
