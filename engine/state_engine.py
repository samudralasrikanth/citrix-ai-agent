import cv2
import hashlib
import numpy as np
from typing import Optional, Tuple

class StateEngine:
    """
    Handles screen state identification and transition tracking.
    Uses perceptual-ish hashing (MD5 of downscaled image) to identify screens.
    """

    @staticmethod
    def compute_screen_hash(frame: np.ndarray) -> str:
        """
        Generate a stable hash for a given frame.
        """
        if frame is None:
            return "empty"
            
        # 1. Downscale significantly to make hash robust to minor noise/OCR text jitter
        small = cv2.resize(frame, (64, 64), interpolation=cv2.INTER_AREA)
        
        # 2. Convert to grayscale
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        
        # 3. MD5 hash of the pixel data
        return hashlib.md5(gray.tobytes()).hexdigest()

    @staticmethod
    def get_pixel_diff(frame1: np.ndarray, frame2: np.ndarray) -> float:
        """
        Calculate pixel-level difference ratio between two frames.
        """
        if frame1 is None or frame2 is None:
            return 1.0
        if frame1.shape != frame2.shape:
            return 1.0
            
        diff = cv2.absdiff(frame1, frame2)
        non_zero = np.count_nonzero(diff)
        return non_zero / frame1.size
