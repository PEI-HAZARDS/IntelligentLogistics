from enum import Enum
import itertools
from shared.utils import levenshtein_distance
import logging

logger = logging.getLogger("PlateMatcher")

class PlateMatcherMode(Enum):
    HYBRID = "hybrid"
    LEVENSHTEIN = "levenshtein"
    CONFUSION_MATRIX = "confusion_matrix"


class PlateMatcher:
    """
    Class to match license plates with possible OCR errors.
    
    Modes:
        - CONFUSION_MATRIX: Only uses confusion matrix to generate candidates
        - LEVENSHTEIN: Only uses Levenshtein distance on original OCR text
        - HYBRID: Uses confusion matrix first, then Levenshtein as fallback
    """
    
    def __init__(self, mode: PlateMatcherMode = PlateMatcherMode.HYBRID, max_distance: int = 2):
        self.mode = mode
        self.max_distance = max_distance
        self.confusion_matrix = {
            # --- NUMBERS ---
            '0': ['O', 'D', 'Q', 'U'],
            '1': ['I', 'L', 'T', 'J'],
            '2': ['Z', '7'],
            '3': ['B', 'E', '8'],
            '4': ['A'],
            '5': ['S'],
            '6': ['G', 'b'],
            '7': ['T', 'Y', 'Z'],
            '8': ['B', 'S'],
            '9': ['g', 'q', 'P'],
            # --- LETTERS ---
            'A': ['4'],
            'B': ['8', '3'],
            'C': ['G', '0'],
            'D': ['0', 'O', 'Q'],
            'E': ['3', 'F'],
            'F': ['P', 'E'],
            'G': ['6', 'C'],
            'H': ['A', 'N', 'M'],
            'I': ['1', 'L', 'T', 'J'],
            'J': ['1', 'I'],
            'K': ['X', 'R'],
            'L': ['1', 'I'],
            'M': ['W', 'N'],
            'N': ['M', 'H'],
            'O': ['0', 'D', 'Q', 'U'],
            'P': ['R', 'F', '9'],
            'Q': ['0', 'O', 'D', '9'],
            'R': ['P', 'K'],
            'S': ['5', '8'],
            'T': ['7', '1', 'I', 'Y'],
            'U': ['0', 'O', 'V'],
            'V': ['U', 'Y'],
            'W': ['M'],
            'X': ['K', 'Y'],
            'Y': ['V', 'T', '7'],
            'Z': ['2', '7']
        }
        
        logger.info(f"PlateMatcher initialized in {self.mode.value} mode with max distance {self.max_distance}")

    def _generate_plate_candidates(self, ocr_text: str, max_substitutions: int = 0):
        """
        Generates all likely license plate variations based on visual similarities.
        
        Args:
            ocr_text: The OCR-read text
            max_substitutions: Maximum number of characters to substitute (None = unlimited)
        """
        
        
        if max_substitutions is None:
            max_substitutions = len(ocr_text)
            
        # Build a list of possibilities for each character position
        possibilities = []
        for char in ocr_text:
            options = [char]
            if char in self.confusion_matrix:
                options.extend(self.confusion_matrix[char])
            possibilities.append(set(options))
        
        # Generate Cartesian product of all possibilities
        candidates = [''.join(p) for p in itertools.product(*possibilities)]
        
        # Filter by max_substitutions if needed
        if max_substitutions < len(ocr_text):
            filtered = []
            for candidate in candidates:
                diff_count = sum(1 for i, c in enumerate(candidate) if c != ocr_text[i])
                if diff_count <= max_substitutions:
                    filtered.append(candidate)
            return filtered

        logger.info(f"Generated {len(candidates)} candidates for OCR text '{ocr_text}'")        

        return candidates

    def _match_with_confusion_matrix(self, normalized_ocr: str, db_plates: list, normalized_db_plates: list) -> str | None:
        """
        Match using confusion matrix only - looks for exact matches among generated candidates.
        """
        candidates = self._generate_plate_candidates(normalized_ocr, max_substitutions=2)
        
        logger.info(f"Trying confusion matrix match for OCR '{normalized_ocr}' with {len(candidates)} candidates")
        
        for candidate in candidates:
            for i, normalized_db in enumerate(normalized_db_plates):
                if candidate == normalized_db:
                    return db_plates[i]
        
        return None

    def _match_with_levenshtein(self, normalized_ocr: str, db_plates: list, normalized_db_plates: list) -> str | None:
        """
        Match using Levenshtein distance only on the original OCR text.
        """
        best_match = None
        best_distance = None
        
        logger.info(f"Trying Levenshtein match for OCR '{normalized_ocr}'")
        
        for i, normalized_db in enumerate(normalized_db_plates):
            distance = levenshtein_distance(normalized_ocr, normalized_db)
            
            if distance <= self.max_distance:
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_match = db_plates[i]
        
        return best_match

    def _match_with_hybrid(self, normalized_ocr: str, db_plates: list, normalized_db_plates: list) -> str | None:
        """
        Match using hybrid approach: confusion matrix first, then Levenshtein fallback.
        """
        
        # Step 1: Try confusion matrix
        match = self._match_with_confusion_matrix(normalized_ocr, db_plates, normalized_db_plates)
        if match is not None:
            return match
        
        # Step 2: Fallback to Levenshtein
        return self._match_with_levenshtein(normalized_ocr, db_plates, normalized_db_plates)

    def match_plate(self, ocr_text: str, db_plates: list) -> str | None:
        """
        Matches the OCR-read license plate against a list of plates.
        Returns the best matching plate and its distance, or (None, None) if no match found.
        """
        
        logger.info(f"Matching OCR plate '{ocr_text}' against database plates: {db_plates}")
        
        if not db_plates:
            return None
            
        normalized_ocr = ocr_text.upper().replace(" ", "").replace("-", "")
        normalized_db_plates = [p.upper().replace(" ", "").replace("-", "") for p in db_plates]
        
        logger.info("Trying exact match...")
        
        # Step 1: Try exact match first
        for i, normalized_db in enumerate(normalized_db_plates):
            if normalized_ocr == normalized_db:
                return db_plates[i]
        
        if self.mode == PlateMatcherMode.CONFUSION_MATRIX:
            return self._match_with_confusion_matrix(normalized_ocr, db_plates, normalized_db_plates)
        
        elif self.mode == PlateMatcherMode.LEVENSHTEIN:
            return self._match_with_levenshtein(normalized_ocr, db_plates, normalized_db_plates)
        
        elif self.mode == PlateMatcherMode.HYBRID:
            return self._match_with_hybrid(normalized_ocr, db_plates, normalized_db_plates)
        
        return None