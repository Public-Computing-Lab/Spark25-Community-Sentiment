import re
from pathlib import Path

# Path to the big SQL dump
DUMP_PATH = Path("goebel_iad1-mysql-e2-17b_dreamhost_com.sql")

# Regex patterns to catch common table-defining statements
CREATE_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+`?(\w+)`?", re.IGNORECASE)
TABLE_RE = re.compile(r"Table\s+structure\s+for\s+table\s+`?(\w+)`?", re.IGNORECASE)
INTO_TABLE_RE = re.compile(r"INSERT\s+INTO\s+`?(\w+)`?", re.IGNORECASE)

def extract_table_names(path: Path):
    tables = set()

    # Read the file line by line to avoid loading 200MB+ into memory
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            for regex in (CREATE_TABLE_RE, TABLE_RE, INTO_TABLE_RE):
                m = regex.search(line)
                if m:
                    tables.add(m.group(1))

    return sorted(tables)

if __name__ == "__main__":
    if not DUMP_PATH.exists():
        print(f"File not found: {DUMP_PATH}")
    else:
        table_names = extract_table_names(DUMP_PATH)
        print(f"Found {len(table_names)} tables:\n")
        for name in table_names:
            print(name)