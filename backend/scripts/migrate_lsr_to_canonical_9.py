"""Migrates lsr_tags table in sif_sentinel.db to the 9 Canonical IOGP Life-Saving Rules."""

import sqlite3
from pathlib import Path


def migrate():
    db_path = Path(__file__).resolve().parents[1] / "sif_sentinel.db"
    if not db_path.exists():
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # 1. Delete records for removed non-canonical extension rules
    removed_categories = (
        "Managing Change",
        "Fit for Duty",
        "Personal Protective Equipment",
    )
    cur.execute(
        "DELETE FROM lsr_tags WHERE lsr_category IN (?, ?, ?) OR (rule_id IN ('LSR08', 'LSR09', 'LSR12') AND lsr_category IN (?, ?, ?))",
        (*removed_categories, *removed_categories),
    )
    deleted = cur.rowcount
    print(f"Deleted {deleted} tags for removed non-canonical rules.")

    # 2. Fix legacy LSR-04
    cur.execute("UPDATE lsr_tags SET rule_id = 'LSR04' WHERE rule_id = 'LSR-04'")
    legacy_fixed = cur.rowcount
    print(f"Updated {legacy_fixed} legacy 'LSR-04' rule IDs to 'LSR04'.")

    # 3. Remap Work Authorization (LSR10 -> LSR08)
    cur.execute(
        "UPDATE lsr_tags SET rule_id = 'LSR08' WHERE rule_id = 'LSR10' OR (lsr_category = 'Work Authorization' AND rule_id != 'LSR08')"
    )
    remapped_wa = cur.rowcount
    print(f"Remapped {remapped_wa} Work Authorization tags to 'LSR08'.")

    # 4. Remap Working at Height (LSR11 -> LSR09)
    cur.execute(
        "UPDATE lsr_tags SET rule_id = 'LSR09' WHERE rule_id = 'LSR11' OR (lsr_category = 'Working at Height' AND rule_id != 'LSR09')"
    )
    remapped_wah = cur.rowcount
    print(f"Remapped {remapped_wah} Working at Height tags to 'LSR09'.")

    conn.commit()

    cur.execute("SELECT rule_id, lsr_category, count(*) FROM lsr_tags GROUP BY rule_id, lsr_category ORDER BY rule_id")
    print("\nUpdated lsr_tags distribution:")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]} -> {row[2]} tags")

    conn.close()


if __name__ == "__main__":
    migrate()
