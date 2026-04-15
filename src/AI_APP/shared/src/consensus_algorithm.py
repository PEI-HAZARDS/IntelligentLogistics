from typing import Any
from logging import getLogger
from shared.src.utils import levenshtein_distance

# Consensus configuration
DECISION_THRESHOLD = 8
MIN_TEXT_LENGTH = 4
MIN_CONFIDENCE_CONSENSUS = 0.80

class ConsensusAlgorithm:
    def __init__(self):
        self.consensus_reached = False
        self.counter = {}  # {position: {character: count}}
        self.decided_chars = {}  # {position: character}
        self.frames_processed = 0
        self.length_counter = {}  # {length: count}
        self.best_crop = None
        self.best_confidence = 0.0
        self.candidate_crops = []  # [{"crop": array, "text": str, "confidence": float}]
        self.accepted_confidences = []  # OCR confidences that passed validation
        self.logger = getLogger("ConsensusAlgorithm")

    def reset(self):
            """Reset consensus algorithm state."""
            self.counter = {}
            self.decided_chars = {}
            self.consensus_reached = False
            self.best_crop = None
            self.best_confidence = 0.0
            self.candidate_crops = []
            self.accepted_confidences = []
            self.frames_processed = 0
            self.length_counter = {}
            self.consecutive_none_frames = 0

    def add_candidate_crop(self, crop: Any, text: str, confidence: float, is_fallback: bool = False):
        """
        Add a candidate crop for consensus processing.
        
        Args:
            crop: The cropped image
            text: OCR text (empty string for fallback crops)
            confidence: OCR confidence (for text crops) or YOLO confidence (for fallback crops)
            is_fallback: True if this is a fallback crop based on YOLO detection only
        """

        self.logger.debug(
            f"Adding candidate crop: "
            f"text='{text}', conf={confidence:.2f}, is_fallback={is_fallback}")

        # Check if we already have a crop with the same text or position
        existing_idx = None
        for i, candidate in enumerate(self.candidate_crops):
            if candidate["text"] == text and text:  # Match on text if both have text
                existing_idx = i
                break
            elif not candidate["text"] and not text and is_fallback:  # Both are fallback crops
                # Keep the one with higher confidence
                if confidence > candidate["confidence"]:
                    existing_idx = i
                break
        
        candidate_entry = {
            "crop": crop,
            "text": text,
            "confidence": confidence,
            "is_fallback": is_fallback
        }
        
        if existing_idx is not None:
            # Replace existing candidate if this one is better
            if (not is_fallback) or (is_fallback and confidence > self.candidate_crops[existing_idx]["confidence"]):
                self.candidate_crops[existing_idx] = candidate_entry
        else:
            # Add new candidate
            self.candidate_crops.append(candidate_entry)
    
    def update_position_decision(self, pos: int, char: str):
        """Update decision for a character position if threshold reached."""
        if self.counter[pos][char] < DECISION_THRESHOLD:
            return

        if pos not in self.decided_chars:
            self.decided_chars[pos] = char
            self.logger.debug(f"Position {pos} decided: '{char}'")
        elif self.decided_chars[pos] != char:
            old_char = self.decided_chars[pos]
            self.decided_chars[pos] = char
            self.logger.debug(f"Position {pos} changed: '{old_char}' -> '{char}'")

    def add_to_consensus(self, text: str, confidence: float):
        """
        Add OCR result to consensus algorithm.
        Vote for each character at its position.
        """
        text_normalized = self._normalize_text(text)

        if not self._is_valid_for_consensus(text_normalized, confidence):
            return

        if not self._track_text_length(len(text_normalized)):
            return

        self.accepted_confidences.append(confidence)

        self.logger.debug(
            f"Adding to consensus: '{text_normalized}' "
            f"(conf={confidence:.2f}, len={len(text_normalized)})")

        # Initialize positions
        for pos in range(len(text_normalized)):
            if pos not in self.counter:
                self.counter[pos] = {}

        # Add votes for each character
        vote_weight = self._get_vote_weight(confidence)
        for pos, char in enumerate(text_normalized):
            if char not in self.counter[pos]:
                self.counter[pos][char] = 0

            self.counter[pos][char] += vote_weight
            self.update_position_decision(pos, char)

    def check_full_consensus(self) -> bool:
        """
        Check if full consensus reached.

        Full consensus requires all expected positions to be decided.
        Expected positions are inferred from the most common accepted text length.
        """
        if not self.counter:
            return False

        expected_positions = self._get_expected_positions()
        if expected_positions <= 0:
            return False

        # Count only positions within expected range to avoid out-of-range false positives.
        decided_count = sum(1 for pos in range(expected_positions) if pos in self.decided_chars)

        if decided_count >= expected_positions:
            self.logger.info(
                f"Consensus reached! {decided_count}/{expected_positions} "
                "positions decided ✓")
            self.consensus_reached = True
            return True

        self.logger.debug(
            f"Consensus check: {decided_count}/{expected_positions} "
            "positions decided")
        return False

    def build_final_text(self) -> str:
        """Build final text from decided characters."""
        if not self.decided_chars:
            return ""
        # This gives us the expected text length of the detection
        expected_positions = self._get_expected_positions()
        if expected_positions > 0:

            #The missing positions on the text
            missing_positions = [pos for pos in range(expected_positions) if pos not in self.decided_chars]
            if missing_positions:
                self.logger.debug(
                    f"Cannot build full text yet, missing positions: {missing_positions}")
                return ""

            text_chars = [self.decided_chars[pos] for pos in range(expected_positions)]
            final_text = "".join(text_chars)
            self.logger.debug(f"Built final text: '{final_text}'")
            return final_text

        text_chars = []
        for pos in sorted(self.decided_chars.keys()):
            text_chars.append(self.decided_chars[pos])

        final_text = "".join(text_chars)
        self.logger.debug(f"Built final text: '{final_text}'")
        return final_text

    def compute_consensus_confidence(self) -> float:
        """
        Compute composite confidence score based on:
        1. Position dominance: how strongly the winning character dominated at each position
        2. Average OCR confidence: mean confidence of all accepted readings
        
        Returns:
            float: Confidence score between 0.0 and 1.0
        """
        if not self.decided_chars or not self.counter:
            return 0.0

        # Compute dominance per decided position
        position_dominances = []
        for pos, char in self.decided_chars.items():
            total_votes = sum(self.counter[pos].values())
            winner_votes = self.counter[pos].get(char, 0)
            position_dominances.append(winner_votes / total_votes if total_votes > 0 else 0.0)

        agreement_score = sum(position_dominances) / len(position_dominances)

        # Combine with average OCR confidence
        if self.accepted_confidences:
            avg_ocr_confidence = sum(self.accepted_confidences) / len(self.accepted_confidences)
        else:
            avg_ocr_confidence = 0.0

        confidence = agreement_score * avg_ocr_confidence

        self.logger.info(
            f"Consensus confidence: {confidence:.3f} "
            f"(agreement={agreement_score:.3f}, avg_ocr={avg_ocr_confidence:.3f}, "
            f"readings={len(self.accepted_confidences)})")

        return confidence
    
    def select_best_crop(self, final_text: str):
        """
        Select best crop based on similarity to final consensus text.
        
        Returns:
            Crop image or None
        """
        if not self.candidate_crops:
            self.logger.warning("No candidate crops available")
            return None
        
        if not final_text:
            best = max(self.candidate_crops, key=lambda x: x["confidence"])
            self.logger.debug(
                f"No final text, using highest confidence crop: '{best['text']}'")
            return best["crop"]
        
        # Calculate scores for each candidate
        scored_crops = []
        for candidate in self.candidate_crops:
            distance = levenshtein_distance(candidate["text"], final_text)
            max_len = max(len(candidate["text"]), len(final_text), 1)
            similarity = 1 - (distance / max_len)
            scored_crops.append({
                "crop": candidate["crop"],
                "text": candidate["text"],
                "confidence": candidate["confidence"],
                "distance": distance,
                "similarity": similarity
            })
        
        # Sort by similarity (descending), then confidence (descending)
        scored_crops.sort(key=lambda x: (x["similarity"], x["confidence"]), reverse=True)
        
        best = scored_crops[0]
        self.logger.debug(
            f"Selected best crop: '{best['text']}' "
            f"(similarity={best['similarity']:.2f}, distance={best['distance']}, "
            f"conf={best['confidence']:.2f}) for final text '{final_text}'"
        )
        
        self.best_crop = best["crop"]
        self.best_confidence = best["confidence"]
        
        return best["crop"]

    def get_best_partial_result(self, object_type: str):
        """
        Return best partial result if full consensus not reached.
        Fill undecided positions with most voted character.
        Always returns a crop, falling back to YOLO confidence if no text consensus.
        """
        # If we have text consensus data, build partial result
        if self.counter:
            text_chars = []
            total_positions = self._get_expected_positions()
            if total_positions <= 0:
                total_positions = max(self.counter.keys()) + 1

            for pos in range(total_positions):
                if pos in self.decided_chars:
                    text_chars.append(self.decided_chars[pos])
                elif pos in self.counter and self.counter[pos]:
                    best_char = max(self.counter[pos].items(), key=lambda x: x[1])[0]
                    text_chars.append(best_char)
                else:
                    text_chars.append("_")

            partial_text = "".join(text_chars)
            decided_count = len(self.decided_chars)
            confidence = decided_count / total_positions
            confidence = min(confidence, 0.95)

            best_crop = self.select_best_crop(partial_text)

            self.logger.info(
                f"Partial result: '{partial_text}' "
                f"({decided_count}/{total_positions} decided, conf={confidence:.2f})")

            return partial_text, confidence, best_crop
        
        # No text consensus possible - check if we have any crops at all
        if not self.candidate_crops:
            self.logger.warning(
                f"No valid {object_type}s detected in any frame.")
            return None, None, None
        
        # Fallback: return best crop based on YOLO confidence with no text
        best_crop = self.select_best_crop("")
        self.logger.debug(
            f"No text consensus - using best YOLO detection (conf={self.best_confidence:.2f})")
        
        return "N/A", self.best_confidence, best_crop
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for consensus: uppercase and remove dashes."""
        return text.upper().replace("-", "")

    def _is_valid_for_consensus(self, text_normalized: str, confidence: float) -> bool:
        """Check if OCR result is valid for consensus algorithm."""
        if confidence < MIN_CONFIDENCE_CONSENSUS:
            self.logger.debug(
                f"Confidence too low ({confidence:.2f}), skipping")
            return False

        if len(text_normalized) < MIN_TEXT_LENGTH:
            self.logger.debug(
                f"Text too short ('{text_normalized}'), skipping")
            return False

        return True

    def _track_text_length(self, text_len: int) -> bool:
        """
        Track text length and validate against most common length.
        
        Returns:
            True if text length is acceptable, False otherwise
        """
        if text_len not in self.length_counter:
            self.length_counter[text_len] = 0
        self.length_counter[text_len] += 1

        if sum(self.length_counter.values()) < 3:
            return True

        most_common_length = self._get_most_common_length()
        if text_len != most_common_length:
            self.logger.debug(
                f"Text length mismatch: {text_len} chars, "
                f"expected {most_common_length} (most common). Skipping to avoid misalignment.")
            return False

        return True

    def _get_vote_weight(self, confidence: float) -> int:
        """Return vote weight based on confidence level."""
        return 2 if confidence >= 0.95 else 1

    def _get_expected_positions(self) -> int:
        """Return expected text length based on observed accepted OCR lengths."""
        if self.length_counter:
            return self._get_most_common_length()

        if self.counter:
            return max(self.counter.keys()) + 1

        return 0

    def _get_most_common_length(self) -> int:
        """Return most frequent accepted text length.

        Tie-breaker prefers shorter length to reduce outlier impact.
        """
        if not self.length_counter:
            return 0

        return max(self.length_counter.items(), key=lambda x: (x[1], -x[0]))[0]
