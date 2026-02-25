"""License plate fuzzy-matching utilities for the V_APP gate management system.

This module provides ``PlateMatcher``, which reconciles an OCR-read license
plate string against a list of candidate plates from the scheduling database.
Three matching strategies are available: a confusion-matrix expansion approach,
Levenshtein distance, and a hybrid of both.

Typical usage:
    matcher = PlateMatcher(mode=PlateMatcherMode.HYBRID, max_distance=2)
    result = matcher.match_plate("AB12CD", ["AB12C0", "XY99ZZ"])
"""

from enum import Enum
import itertools
import logging

from shared.src.utils import levenshtein_distance


logger = logging.getLogger("PlateMatcher")


class PlateMatcherMode(Enum):
    """Enumeration of the matching strategies supported by ``PlateMatcher``.

    Attributes:
        HYBRID: Attempts confusion-matrix expansion first; falls back to
            Levenshtein distance if no candidate matches.
        LEVENSHTEIN: Applies Levenshtein distance directly to the normalised
            OCR text without generating character-substitution candidates.
        CONFUSION_MATRIX: Expands the OCR text into all visually similar
            variants and looks for an exact match among database plates.
    """

    HYBRID = "hybrid"
    LEVENSHTEIN = "levenshtein"
    CONFUSION_MATRIX = "confusion_matrix"


class PlateMatcher:
    """Match license plates against a database list, tolerating OCR errors.

    OCR engines frequently confuse visually similar characters (e.g. ``'0'``
    and ``'O'``, ``'1'`` and ``'I'``). This class handles those errors via a
    configurable matching strategy:

    - ``CONFUSION_MATRIX``: Expands the OCR text into all character-substitution
      variants and checks each against the database.
    - ``LEVENSHTEIN``: Accepts the nearest database plate within
      ``max_distance`` edit operations.
    - ``HYBRID``: Runs confusion-matrix first (exact structural match), then
      falls back to Levenshtein if no candidate survives.

    All plate strings are normalised (uppercased, spaces and hyphens stripped)
    before any comparison.
    """

    def __init__(self, mode: PlateMatcherMode = PlateMatcherMode.HYBRID, max_distance: int = 2):
        """Initialise the matcher with a strategy and edit-distance threshold.

        Args:
            mode: Matching strategy to use. Defaults to ``HYBRID``.
            max_distance: Maximum Levenshtein distance accepted as a valid
                match. Only used in ``LEVENSHTEIN`` and ``HYBRID`` modes.
                Defaults to ``2``.
        """
        self.mode = mode
        self.max_distance = max_distance

        # Maps each character to a list of visually similar characters that
        # an OCR engine is likely to read in its place. Symmetric pairs are
        # intentional (e.g. '0'→'O' and 'O'→'0') so candidate generation
        # works correctly regardless of which side contains the OCR error.
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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def match_plate(self, ocr_text: str, db_plates: list) -> str | None:
        """Match an OCR-read plate string against a list of database candidates.

        Always attempts an exact match first (after normalisation). If no exact
        match is found, delegates to the configured fuzzy strategy.

        Args:
            ocr_text: The raw plate string returned by the OCR pipeline.
            db_plates: List of candidate plate strings retrieved from the
                scheduling database. Order is preserved for return values.

        Returns:
            The best-matching plate from ``db_plates`` (in its original,
            un-normalised form), or ``None`` if no match is found within the
            configured thresholds.
        """
        logger.info(f"Matching OCR plate '{ocr_text}' against {len(db_plates)} database plates...")

        if not db_plates:
            logger.warning("No database plates provided for matching")
            return None

        # Strip formatting characters and upper-case for a format-agnostic comparison.
        normalized_ocr = ocr_text.upper().replace(" ", "").replace("-", "")
        normalized_db_plates = [p.upper().replace(" ", "").replace("-", "") for p in db_plates]

        logger.info(f"Trying exact match for normalized OCR '{normalized_ocr}'...")

        # Always try exact match first — cheapest path, avoids fuzzy overhead.
        for i, normalized_db in enumerate(normalized_db_plates):
            if normalized_ocr == normalized_db:
                logger.info(f"Exact match found: '{ocr_text}' matched to '{db_plates[i]}'")
                return db_plates[i]

        logger.info("No exact match found, trying fuzzy matching...")

        match = None
        if self.mode == PlateMatcherMode.CONFUSION_MATRIX:
            match = self._match_with_confusion_matrix(normalized_ocr, db_plates, normalized_db_plates)

        elif self.mode == PlateMatcherMode.LEVENSHTEIN:
            match = self._match_with_levenshtein(normalized_ocr, db_plates, normalized_db_plates)

        elif self.mode == PlateMatcherMode.HYBRID:
            match = self._match_with_hybrid(normalized_ocr, db_plates, normalized_db_plates)

        if match:
            logger.info(f"Match found: '{ocr_text}' matched to '{match}' using {self.mode.value} mode")
        else:
            logger.warning(f"No match found for OCR plate '{ocr_text}' using {self.mode.value} mode")

        return match

    # ------------------------------------------------------------------
    # Private matching strategies
    # ------------------------------------------------------------------

    def _generate_plate_candidates(self, ocr_text: str, max_substitutions: int = 0) -> list[str]:
        """Generate all likely plate variants by substituting visually similar characters.

        For each position in ``ocr_text``, builds a set containing the original
        character plus all confusion-matrix alternatives. The Cartesian product
        of these sets yields every possible substitution variant.

        Args:
            ocr_text: Normalised OCR plate text to expand.
            max_substitutions: Maximum number of character positions that may
                be substituted simultaneously. ``0`` means no limit (all
                positions can be substituted).

        Returns:
            A list of candidate plate strings. When ``max_substitutions`` is
            less than the plate length, candidates that exceed the substitution
            budget are filtered out.
        """
        if max_substitutions == 0:
            max_substitutions = len(ocr_text)

        # Build a list of possibilities for each character position.
        possibilities = []
        for char in ocr_text:
            options = [char]
            if char in self.confusion_matrix:
                options.extend(self.confusion_matrix[char])
            possibilities.append(set(options))

        # Generate Cartesian product of all possibilities.
        candidates = [''.join(p) for p in itertools.product(*possibilities)]

        # Filter by max_substitutions if needed.
        if max_substitutions < len(ocr_text):
            filtered = []
            for candidate in candidates:
                # Count positions where the candidate differs from the original.
                diff_count = sum(1 for i, c in enumerate(candidate) if c != ocr_text[i])
                if diff_count <= max_substitutions:
                    filtered.append(candidate)
            logger.debug(f"Generated {len(filtered)} candidates for OCR text '{ocr_text}' (max {max_substitutions} substitutions)")
            return filtered

        logger.debug(f"Generated {len(candidates)} candidates for OCR text '{ocr_text}'")

        return candidates

    def _match_with_confusion_matrix(self, normalized_ocr: str, db_plates: list, normalized_db_plates: list) -> str | None:
        """Attempt a match by expanding the OCR text via the confusion matrix.

        Generates candidate variants of ``normalized_ocr`` and looks for an
        exact string match against each normalised database plate. Returns the
        first hit; does not rank candidates.

        Args:
            normalized_ocr: Normalised OCR plate string.
            db_plates: Original (un-normalised) database plates for return value.
            normalized_db_plates: Normalised counterparts of ``db_plates``,
                aligned by index.

        Returns:
            The matching plate from ``db_plates``, or ``None`` if no candidate
            matches any database entry.
        """
        candidates = self._generate_plate_candidates(normalized_ocr, max_substitutions=2)

        logger.info(f"Trying confusion matrix match with {len(candidates)} candidates...")

        for candidate in candidates:
            for i, normalized_db in enumerate(normalized_db_plates):
                if candidate == normalized_db:
                    logger.info(f"Confusion matrix match: candidate '{candidate}' matched to '{db_plates[i]}'")
                    return db_plates[i]

        logger.info("No confusion matrix match found")
        return None

    def _match_with_levenshtein(self, normalized_ocr: str, db_plates: list, normalized_db_plates: list) -> str | None:
        """Attempt a match using Levenshtein edit distance on the raw OCR text.

        Iterates over all database plates, computes the edit distance to
        ``normalized_ocr``, and returns the plate with the smallest distance
        that is still within ``self.max_distance``. When two plates share the
        same minimum distance, the one with the lower list index wins.

        Args:
            normalized_ocr: Normalised OCR plate string.
            db_plates: Original (un-normalised) database plates for return value.
            normalized_db_plates: Normalised counterparts of ``db_plates``,
                aligned by index.

        Returns:
            The closest-matching plate from ``db_plates``, or ``None`` if no
            plate is within ``self.max_distance`` edits.
        """
        best_match = None
        best_distance = None

        logger.info(f"Trying Levenshtein match (max distance: {self.max_distance})...")

        for i, normalized_db in enumerate(normalized_db_plates):
            distance = levenshtein_distance(normalized_ocr, normalized_db)

            # Keep only the closest match seen so far within the allowed budget.
            if distance <= self.max_distance:
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_match = db_plates[i]

        if best_match:
            logger.info(f"Levenshtein match: '{normalized_ocr}' matched to '{best_match}' (distance: {best_distance})")
        else:
            logger.info(f"No Levenshtein match found within distance {self.max_distance}")

        return best_match

    def _match_with_hybrid(self, normalized_ocr: str, db_plates: list, normalized_db_plates: list) -> str | None:
        """Attempt a match using the hybrid strategy (confusion matrix + Levenshtein fallback).

        Prefers the confusion-matrix result because it is a structurally exact
        match after character substitution, which is more accurate than edit
        distance alone. Levenshtein is used only when the confusion-matrix
        expansion produces no match.

        Args:
            normalized_ocr: Normalised OCR plate string.
            db_plates: Original (un-normalised) database plates for return value.
            normalized_db_plates: Normalised counterparts of ``db_plates``,
                aligned by index.

        Returns:
            The best-matching plate from ``db_plates`` found by either
            strategy, or ``None`` if both strategies fail.
        """
        logger.info("Trying hybrid matching (confusion matrix + Levenshtein fallback)...")

        # Try confusion matrix first — higher precision.
        match = self._match_with_confusion_matrix(normalized_ocr, db_plates, normalized_db_plates)
        if match is not None:
            logger.info("Hybrid match successful via confusion matrix")
            return match

        logger.info("Confusion matrix failed, falling back to Levenshtein...")

        # Fallback to Levenshtein for plates with errors outside the confusion matrix.
        match = self._match_with_levenshtein(normalized_ocr, db_plates, normalized_db_plates)
        if match is not None:
            logger.info("Hybrid match successful via Levenshtein fallback")
        else:
            logger.info("Hybrid match failed")

        return match