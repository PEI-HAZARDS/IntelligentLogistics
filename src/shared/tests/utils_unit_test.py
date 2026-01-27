"""
Unit tests for shared/src/utils.py

Tests cover:
- levenshtein_distance function
- load_from_file function
- extract_truck_id_from_headers function

Uses unittest.mock for file I/O mocking.
"""

import pytest
from unittest.mock import patch, MagicMock, mock_open
from utils import (
    levenshtein_distance,
    load_from_file,
    extract_truck_id_from_headers,
)


# =============================================================================
# Tests for levenshtein_distance
# =============================================================================

class TestLevenshteinDistance:
    """Tests for the levenshtein_distance function."""

    def test_identical_strings_returns_zero(self):
        """Identical strings should have distance 0."""
        # Arrange
        s1 = "HELLO"
        s2 = "HELLO"

        # Act
        result = levenshtein_distance(s1, s2)

        # Assert
        assert result == 0

    def test_empty_strings_returns_zero(self):
        """Two empty strings should have distance 0."""
        # Arrange & Act
        result = levenshtein_distance("", "")

        # Assert
        assert result == 0

    def test_one_empty_string_returns_length_of_other(self):
        """Empty vs non-empty returns length of non-empty string."""
        # Arrange
        s1 = ""
        s2 = "ABC"

        # Act
        result = levenshtein_distance(s1, s2)

        # Assert
        assert result == 3

    def test_one_empty_string_reversed_returns_length_of_other(self):
        """Non-empty vs empty returns length of non-empty string."""
        # Arrange
        s1 = "ABC"
        s2 = ""

        # Act
        result = levenshtein_distance(s1, s2)

        # Assert
        assert result == 3

    def test_single_character_difference(self):
        """Single substitution should return distance 1."""
        # Arrange
        s1 = "CAT"
        s2 = "BAT"

        # Act
        result = levenshtein_distance(s1, s2)

        # Assert
        assert result == 1

    def test_single_insertion(self):
        """Single insertion should return distance 1."""
        # Arrange
        s1 = "CAT"
        s2 = "CATS"

        # Act
        result = levenshtein_distance(s1, s2)

        # Assert
        assert result == 1

    def test_single_deletion(self):
        """Single deletion should return distance 1."""
        # Arrange
        s1 = "CATS"
        s2 = "CAT"

        # Act
        result = levenshtein_distance(s1, s2)

        # Assert
        assert result == 1

    def test_completely_different_strings(self):
        """Completely different strings of same length = full length substitutions."""
        # Arrange
        s1 = "ABC"
        s2 = "XYZ"

        # Act
        result = levenshtein_distance(s1, s2)

        # Assert
        assert result == 3

    def test_complex_edit_distance(self):
        """Complex case with multiple edits."""
        # Arrange
        s1 = "KITTEN"
        s2 = "SITTING"

        # Act
        result = levenshtein_distance(s1, s2)

        # Assert
        # KITTEN -> SITTEN (substitute K->S) -> SITTIN (substitute E->I) -> SITTING (insert G)
        assert result == 3

    def test_license_plate_example(self):
        """Test with license plate-like strings."""
        # Arrange
        s1 = "ABC1234"
        s2 = "ABC1235"

        # Act
        result = levenshtein_distance(s1, s2)

        # Assert
        assert result == 1

    def test_symmetric_distance(self):
        """Distance should be symmetric: d(s1, s2) == d(s2, s1)."""
        # Arrange
        s1 = "HELLO"
        s2 = "WORLD"

        # Act
        result1 = levenshtein_distance(s1, s2)
        result2 = levenshtein_distance(s2, s1)

        # Assert
        assert result1 == result2

    def test_short_string_first_triggers_swap(self):
        """Verify the optimization where shorter string is processed second."""
        # Arrange
        short = "AB"
        long = "ABCDEF"

        # Act
        result = levenshtein_distance(short, long)

        # Assert
        assert result == 4  # 4 insertions needed


# =============================================================================
# Tests for load_from_file
# =============================================================================

class TestLoadFromFile:
    """Tests for the load_from_file function."""

    def test_valid_file_with_separator(self):
        """Successfully load key-value pairs from file."""
        # Arrange
        file_content = "key1:value1\nkey2:value2\nkey3:value3"

        # Act
        with patch("builtins.open", mock_open(read_data=file_content)):
            result = load_from_file("test.txt", ":")

        # Assert
        assert result == {"key1": "value1", "key2": "value2", "key3": "value3"}

    def test_file_with_spaces_around_separator(self):
        """Spaces around separator should be stripped."""
        # Arrange
        file_content = "key1 : value1\nkey2:  value2"

        # Act
        with patch("builtins.open", mock_open(read_data=file_content)):
            result = load_from_file("test.txt", ":")

        # Assert
        assert result == {"key1": "value1", "key2": "value2"}

    def test_empty_file_returns_empty_dict(self):
        """Empty file should return empty dictionary."""
        # Arrange
        file_content = ""

        # Act
        with patch("builtins.open", mock_open(read_data=file_content)):
            result = load_from_file("empty.txt", ":")

        # Assert
        assert result == {}

    def test_file_with_empty_lines(self):
        """Empty lines should be skipped."""
        # Arrange
        file_content = "key1:value1\n\nkey2:value2\n\n"

        # Act
        with patch("builtins.open", mock_open(read_data=file_content)):
            result = load_from_file("test.txt", ":")

        # Assert
        assert result == {"key1": "value1", "key2": "value2"}

    def test_malformed_line_without_separator(self):
        """Lines without separator should be skipped."""
        # Arrange
        file_content = "key1:value1\nmalformed_line\nkey2:value2"

        # Act
        with patch("builtins.open", mock_open(read_data=file_content)):
            result = load_from_file("test.txt", ":")

        # Assert
        assert result == {"key1": "value1", "key2": "value2"}

    def test_line_with_multiple_separators(self):
        """Lines with multiple separators should be skipped (not exactly 2 parts)."""
        # Arrange
        file_content = "key1:value1:extra\nkey2:value2"

        # Act
        with patch("builtins.open", mock_open(read_data=file_content)):
            result = load_from_file("test.txt", ":")

        # Assert
        assert result == {"key2": "value2"}

    def test_different_separator(self):
        """Test with different separator character."""
        # Arrange
        file_content = "key1=value1\nkey2=value2"

        # Act
        with patch("builtins.open", mock_open(read_data=file_content)):
            result = load_from_file("test.txt", "=")

        # Assert
        assert result == {"key1": "value1", "key2": "value2"}


# =============================================================================
# Tests for extract_truck_id_from_headers
# =============================================================================

class TestExtractTruckIdFromHeaders:
    """Tests for the extract_truck_id_from_headers function."""

    def test_bytes_header_value(self):
        """Extract truck_id when value is bytes."""
        # Arrange
        headers = [("truckId", b"TRUCK-123")]

        # Act
        result = extract_truck_id_from_headers(headers)

        # Assert
        assert result == "TRUCK-123"

    def test_string_header_value(self):
        """Extract truck_id when value is already string."""
        # Arrange
        headers = [("truckId", "TRUCK-456")]

        # Act
        result = extract_truck_id_from_headers(headers)

        # Assert
        assert result == "TRUCK-456"

    def test_missing_truck_id_header(self):
        """Return None when truckId header is not present."""
        # Arrange
        headers = [("someOtherHeader", "value")]

        # Act
        result = extract_truck_id_from_headers(headers)

        # Assert
        assert result is None

    def test_empty_headers_list(self):
        """Return None for empty headers list."""
        # Arrange
        headers = []

        # Act
        result = extract_truck_id_from_headers(headers)

        # Assert
        assert result is None

    def test_none_headers(self):
        """Return None when headers is None."""
        # Arrange
        headers = None

        # Act
        result = extract_truck_id_from_headers(headers)

        # Assert
        assert result is None

    def test_multiple_headers_finds_truck_id(self):
        """Find truckId among multiple headers."""
        # Arrange
        headers = [
            ("header1", "val1"),
            ("truckId", b"FOUND-TRUCK"),
            ("header2", "val2"),
        ]

        # Act
        result = extract_truck_id_from_headers(headers)

        # Assert
        assert result == "FOUND-TRUCK"

    def test_first_truck_id_is_returned(self):
        """If multiple truckId headers exist, first one is returned."""
        # Arrange
        headers = [
            ("truckId", b"FIRST"),
            ("truckId", b"SECOND"),
        ]

        # Act
        result = extract_truck_id_from_headers(headers)

        # Assert
        assert result == "FIRST"
