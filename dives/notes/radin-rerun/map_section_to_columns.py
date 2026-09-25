def map_section_to_columns(section):
    """
    Convert a session Section string to observed/unobserved column names.

    Handles recycled arrays (>= 2000) by mapping back to original numbers.
    4000-series arrays are stored under their literal names in arrays_4000.csv
    and need no remapping.

    Examples:
        map_section_to_columns('a1385') -> ('a1385', 'b1385', 1385)
        map_section_to_columns('a2501') -> ('a501',  'b501',  501)   # recycled
        map_section_to_columns('b1385') -> ('b1385', 'a1385', 1385)  # b is observed
        map_section_to_columns('a4001') -> ('a4001', 'b4001', 4001)  # 4000-series
    """
    s = str(section)
    prefix = s[0].lower()
    array_num = int(s[1:])

    if array_num >= 4000:
        original_num = array_num
    elif array_num >= 2000:
        original_num = array_num - 2000
    else:
        original_num = array_num

    if prefix == 'a':
        obs_col   = f'a{original_num}'
        unobs_col = f'b{original_num}'
    elif prefix == 'b':
        obs_col   = f'b{original_num}'
        unobs_col = f'a{original_num}'
    else:
        obs_col = unobs_col = None
        original_num = None

    return obs_col, unobs_col, original_num


if __name__ == "__main__":
    cases = [
        ('a1385', ('a1385', 'b1385', 1385)),
        ('a2501', ('a501',  'b501',  501)),
        ('b1385', ('b1385', 'a1385', 1385)),
        ('a4001', ('a4001', 'b4001', 4001)),
        ('x999',  (None,    None,    None)),
    ]
    for section, expected in cases:
        result = map_section_to_columns(section)
        assert result == expected, f"{section}: expected {expected}, got {result}"
        print(f"  {section} -> obs={result[0]}, unobs={result[1]}, num={result[2]}")
    print("All checks passed.")
