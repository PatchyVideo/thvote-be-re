import json
import sys
from pathlib import Path


def convert(category: str, raw_list: list[dict]) -> list[dict]:
    """
    Convert snapshot JSON rows to import format for POST /admin/voteables/import.

    Args:
        category: "character" or "music"
        raw_list: list of snapshot records from whitelist_{category}.json

    Returns:
        list of dicts ready for import, with only non-empty/non-None keys
    """
    valid_work_types = {"old", "new", "CD", "book", "others"}
    rows = []

    for raw in raw_list:
        row = {}

        # Common fields
        row["old_id"] = raw.get("id")
        row["sort_order"] = raw.get("system_id")
        row["name"] = raw.get("name")
        row["name_jp"] = raw.get("name_jp")

        # type: kind[0], default "others"
        kind_list = raw.get("kind", [])
        row["type"] = kind_list[0] if kind_list else "others"

        # work_type: kind[0] if in valid set, else "others"
        row["work_type"] = (
            kind_list[0]
            if kind_list and kind_list[0] in valid_work_types
            else "others"
        )

        # first_appearance: str(date)
        date_val = raw.get("date")
        if date_val is not None:
            row["first_appearance"] = str(date_val)

        # work: category-specific
        if category == "character":
            work_list = raw.get("work", [])
            if work_list:
                row["work"] = work_list[0]
        elif category == "music":
            album = raw.get("album")
            if album is not None:
                row["work"] = album

        # Filter: keep only non-None/non-empty values
        filtered_row = {k: v for k, v in row.items() if v is not None and v != ""}
        rows.append(filtered_row)

    return rows


if __name__ == "__main__":
    if len(sys.argv) < 2:
        usage = "Usage: python3 scripts/whitelist_to_import.py <category>"
        print(usage, file=sys.stderr)
        sys.exit(1)

    category = sys.argv[1]
    data_dir = Path("src/apps/result/data")
    fixture_path = data_dir / f"whitelist_{category}.json"

    if not fixture_path.exists():
        msg = f"Error: fixture not found at {fixture_path}"
        print(msg, file=sys.stderr)
        sys.exit(1)

    raw = json.loads(fixture_path.read_text())
    converted = convert(category, raw)
    print(json.dumps(converted, ensure_ascii=False))
