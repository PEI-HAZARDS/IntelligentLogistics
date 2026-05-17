import cv2 # type: ignore
import numpy as np # type: ignore
import logging

logger = logging.getLogger("PlateClassifier")

class PlateClassifier:
    """
    Classifies plate crops into:
    - LICENSE_PLATE: License plate (white/yellow, horizontal rectangle)
    - HAZARD_PLATE: Hazard plate (orange/red, diamond/vertical rectangle)
    """

    LICENSE_PLATE = "license_plate"
    HAZARD_PLATE = "hazard_plate"
    UNKNOWN = "unknown"

    # Visualization defaults
    BORDER_WIDTH = 5

    def __init__(self) -> None:
        # Classification thresholds
        # License plates are wide (width/height > 1.8)
        self.min_aspect_ratio_license = 1.05
        self.min_aspect_ratio_license_color = 1.3
        self.max_aspect_ratio_hazard = 1.9   # Hazard plates are square/vertical
        self.min_color_coverage = 0.05
        self.min_license_color_wide = 0.03
        self.min_hazard_color = 0.45
        self.hazard_bias_ratio = 0.7
        self.max_hazard_for_license = 0.3

        # HSV color ranges
        # White/Yellow (license plates)
        self.license_plate_colors = [
            # White
            ([0, 0, 130], [180, 60, 255]),
            # Yellow (includes warm yellowish tones, Hue 15-35)
            ([15, 80, 80], [35, 255, 255])
        ]

        # Orange/Red (hazard plates)
        self.hazard_plate_colors = [
            # Orange (Hue 5-22, below yellow)
            ([5, 70, 80], [22, 255, 255]),
            # Red (part 1)
            ([0, 70, 80], [5, 255, 255]),
            # Red (part 2)
            ([170, 70, 80], [180, 255, 255])
        ]

        # Precompute numpy arrays for color ranges (avoids repeated allocation)
        self._license_np = [(np.array(lo), np.array(hi)) for lo, hi in self.license_plate_colors]
        self._hazard_np = [(np.array(lo), np.array(hi)) for lo, hi in self.hazard_plate_colors]

    def classify(self, crop: np.ndarray | None) -> str:
        """
        Classifies the crop as LICENSE_PLATE or HAZARD_PLATE.

        Args:
            crop: BGR image of the crop

        Returns:
            str: LICENSE_PLATE, HAZARD_PLATE or UNKNOWN
        """
        if crop is None or crop.size == 0:
            logger.debug("classify: empty or None crop, returning UNKNOWN")
            return self.UNKNOWN

        height, width = crop.shape[:2]

        if height == 0 or width == 0:
            logger.debug("classify: zero-dimension crop, returning UNKNOWN")
            return self.UNKNOWN

        # 1. Shape Analysis (Aspect Ratio)
        aspect_ratio = width / height
        is_wide = aspect_ratio >= self.min_aspect_ratio_license
        is_hazard_shape = aspect_ratio <= self.max_aspect_ratio_hazard

        # 2. Dominant Color Analysis
        color_score = self._analyze_colors(crop)
        max_color = max(color_score['license'], color_score['hazard'])

        logger.debug(
            f"classify: AR={aspect_ratio:.2f}, "
            f"license_score={color_score['license']:.3f}, "
            f"hazard_score={color_score['hazard']:.3f}"
        )

        if not is_wide and max_color < self.min_color_coverage:
            return self.UNKNOWN

        # 3. Rule-Based Classification

        # License plates: Wide AND white/yellow colors
        # Hazard plates are NEVER wide rectangles, therefore
        # a high aspect ratio is a strong indicator of a license plate
        if is_wide and color_score['license'] >= self.min_license_color_wide:
            if color_score['license'] > color_score['hazard']:
                return self.LICENSE_PLATE
            # Even with ambiguous color, wide shape = almost certainly a license plate
            if color_score['hazard'] <= self.max_hazard_for_license:
                return self.LICENSE_PLATE

        # Hazard plates: Square/Vertical AND orange/red colors
        if is_hazard_shape:
            if (
                color_score['hazard'] >= self.min_hazard_color
                and color_score['hazard'] >= color_score['license'] * self.hazard_bias_ratio
            ):
                return self.HAZARD_PLATE
            if color_score['hazard'] > color_score['license']:
                return self.HAZARD_PLATE

        # Tiebreak by color only if shape is inconclusive
        if (
            color_score['license'] > color_score['hazard'] * 1.5
            and aspect_ratio >= self.min_aspect_ratio_license_color
            and color_score['license'] >= self.min_license_color_wide
        ):
            return self.LICENSE_PLATE

        if (
            color_score['hazard'] > color_score['license'] * 1.2
            and aspect_ratio <= self.max_aspect_ratio_hazard
        ):
            return self.HAZARD_PLATE

        # When in doubt, prefer LICENSE_PLATE if shape is wide
        if aspect_ratio >= self.min_aspect_ratio_license:
            return self.LICENSE_PLATE

        return self.UNKNOWN

    def _analyze_colors(self, crop: np.ndarray) -> dict[str, float]:
        """
        Analyzes the predominance of characteristic colors.

        Args:
            crop: BGR image of the crop

        Returns:
            dict: {'license': score, 'hazard': score} normalized to 0-1
        """
        # Convert to HSV
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        # Calculate total area
        total_pixels = crop.shape[0] * crop.shape[1]
        if total_pixels == 0:
            return {'license': 0.0, 'hazard': 0.0}

        # Score for license plate colors (white/yellow)
        license_pixels = 0
        for lower, upper in self._license_np:
            mask = cv2.inRange(hsv, lower, upper)
            license_pixels += cv2.countNonZero(mask)

        # Score for hazard plate colors (orange/red)
        hazard_pixels = 0
        for lower, upper in self._hazard_np:
            mask = cv2.inRange(hsv, lower, upper)
            hazard_pixels += cv2.countNonZero(mask)

        # Normalize to 0-1
        license_score = license_pixels / total_pixels
        hazard_score = hazard_pixels / total_pixels

        return {
            'license': license_score,
            'hazard': hazard_score
        }

    def visualize_classification(
        self,
        crop: np.ndarray,
        classification: str,
        save_path: str | None = None,
    ) -> np.ndarray:
        """
        Creates a visualization of the crop with its classification.

        Args:
            crop: Original image
            classification: Classification result
            save_path: Path to save to (optional)

        Returns:
            np.ndarray: Image with overlay
        """
        # Make a copy
        vis = crop.copy()

        # Add colored border
        if classification == self.LICENSE_PLATE:
            color = (0, 255, 0)  # Green
            label = "LICENSE PLATE"
            
        elif classification == self.HAZARD_PLATE:
            color = (0, 0, 255)  # Red
            label = "HAZARD PLATE"
        else:
            color = (128, 128, 128)  # Gray
            label = "UNKNOWN"

        bw = self.BORDER_WIDTH

        # Border
        vis = cv2.copyMakeBorder(
            vis, bw, bw, bw, bw, cv2.BORDER_CONSTANT, value=color)

        # Text
        cv2.putText(vis, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, color, 2, cv2.LINE_AA)

        # Save if requested
        if save_path:
            success = cv2.imwrite(save_path, vis)
            if not success:
                logger.warning(f"Failed to save visualization to: {save_path}")

        return vis
