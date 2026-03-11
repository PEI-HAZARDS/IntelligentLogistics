def levenshtein_distance(s1, s2):
    """Calculate Levenshtein (edit) distance between two strings."""
    # Ensure s1 is the shorter string for memory efficiency
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    # Use a single row to save memory (we only need the previous row)
    previous_row = range(len(s2) + 1)
    
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Calculate costs
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            
            # Append the minimum cost to the current row
            current_row.append(min(insertions, deletions, substitutions))
            
        previous_row = current_row
    
    return previous_row[-1]

def load_from_file(filename: str, separator: str) -> dict:
    """Load key-value pairs from a file into a dictionary."""
    dic = {}

    with open(filename, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue  # skip empty lines

            parts = line.split(separator)
            if len(parts) != 2:
                continue

            part1, part2 = parts[0].strip(), parts[1].strip()
            dic[part1] = part2

    return dic