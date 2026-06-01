"""
PostgreSQL slow query analyser for Milestone 4 — Performance section.

Two modes:
  1. With pg_stat_statements (preferred): surfaces top-10 slowest queries.
     Requires Postgres to start with shared_preload_libraries=pg_stat_statements
     (already set in docker-compose.yml — needs one container restart to activate).

  2. Without pg_stat_statements (fallback): uses pg_stat_user_tables +
     pg_stat_user_indexes + EXPLAIN ANALYZE on critical queries.
     Works immediately with no config changes.

Usage:
    # Against local docker-compose:
    python scripts/pg_slow_queries.py

    # Against remote VM:
    PG_HOST=10.x.x.x python scripts/pg_slow_queries.py

    # Reset pg_stat_statements counters before a new load run:
    PG_HOST=10.x.x.x python scripts/pg_slow_queries.py --reset

Environment variables:
    PG_HOST      default: localhost
    PG_PORT      default: 5432
    PG_USER      default: pei_user
    PG_PASSWORD  required — no default. Use the value from src/V_APP/.env (POSTGRES_PASSWORD).
    PG_DB        default: IntelligentLogistics

Note: src/V_APP/.env is only loaded by docker-compose, not by this script.
Export the variables manually before running:

    export PG_PASSWORD=$(grep POSTGRES_PASSWORD src/V_APP/.env | cut -d= -f2)
    python scripts/pg_slow_queries.py

    # Against the stress-test VM:
    PG_HOST=<vm-ip> PG_PASSWORD=<password> python scripts/pg_slow_queries.py
"""

import os
import sys
import argparse
import psycopg2

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "pei_user")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
PG_DB = os.getenv("PG_DB", "IntelligentLogistics")

# Key queries to EXPLAIN ANALYZE in fallback mode
EXPLAIN_QUERIES = [
    ("arrivals paginated list",
     "SELECT * FROM appointment ORDER BY scheduled_start_time DESC LIMIT 20 OFFSET 0"),
    ("arrivals filtered by status",
     "SELECT * FROM appointment WHERE status = 'in_transit' ORDER BY scheduled_start_time DESC LIMIT 20"),
    ("arrival by id (PK)",
     "SELECT * FROM appointment WHERE id = 1"),
    ("appointments ordered by scheduled_start_time (sort + gate filter)",
     """SELECT id, status, scheduled_start_time, gate_in_id
        FROM appointment
        ORDER BY scheduled_start_time ASC
        LIMIT 5"""),
]


def connect():
    return psycopg2.connect(
        host=PG_HOST, port=PG_PORT,
        user=PG_USER, password=PG_PASSWORD,
        dbname=PG_DB, connect_timeout=10,
    )


def has_pg_stat_statements(cur) -> bool:
    """Check if pg_stat_statements is both installed AND loaded (shared_preload_libraries)."""
    try:
        cur.execute("SELECT count(*) FROM pg_stat_statements LIMIT 1")
        cur.fetchone()
        return True
    except psycopg2.Error:
        cur.connection.rollback()
        return False


def reset_stats(cur):
    cur.execute("SELECT pg_stat_statements_reset()")
    print("[INFO] pg_stat_statements counters reset.")


# ---------------------------------------------------------------------------
# Mode 1 — pg_stat_statements available
# ---------------------------------------------------------------------------

def top_by_mean_time(cur, limit: int):
    cur.execute("""
        SELECT
            round(mean_exec_time::numeric, 2)  AS mean_ms,
            round(max_exec_time::numeric,  2)  AS max_ms,
            calls,
            round((100 * total_exec_time /
                   NULLIF(sum(total_exec_time) OVER (), 0))::numeric, 1) AS pct_total,
            left(regexp_replace(query, E'[\\n\\r\\t ]+', ' ', 'g'), 100) AS query
        FROM pg_stat_statements
        WHERE query NOT ILIKE '%%pg_stat%%'
          AND query NOT ILIKE '%%SET %%'
          AND calls > 2
        ORDER BY mean_exec_time DESC
        LIMIT %s
    """, (limit,))
    return cur.fetchall()


def top_by_total_time(cur, limit: int):
    cur.execute("""
        SELECT
            round(mean_exec_time::numeric, 2)  AS mean_ms,
            round(total_exec_time::numeric, 2) AS total_ms,
            calls,
            round((100 * total_exec_time /
                   NULLIF(sum(total_exec_time) OVER (), 0))::numeric, 1) AS pct_total,
            left(regexp_replace(query, E'[\\n\\r\\t ]+', ' ', 'g'), 100) AS query
        FROM pg_stat_statements
        WHERE query NOT ILIKE '%%pg_stat%%'
          AND query NOT ILIKE '%%SET %%'
          AND calls > 2
        ORDER BY total_exec_time DESC
        LIMIT %s
    """, (limit,))
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Mode 2 — fallback (always available)
# ---------------------------------------------------------------------------

def seq_scan_tables(cur):
    """Tables with the most sequential scans — candidates for missing indexes."""
    cur.execute("""
        SELECT
            relname            AS table,
            seq_scan,
            idx_scan,
            seq_tup_read,
            n_live_tup         AS live_rows
        FROM pg_stat_user_tables
        ORDER BY seq_scan DESC
        LIMIT 10
    """)
    return cur.fetchall()


def index_usage(cur):
    """Index hit vs miss ratio per table."""
    cur.execute("""
        SELECT
            relname                                  AS table,
            idx_scan,
            seq_scan,
            round(100.0 * idx_scan /
                  NULLIF(idx_scan + seq_scan, 0), 1) AS idx_pct,
            n_live_tup                               AS live_rows
        FROM pg_stat_user_tables
        WHERE seq_scan + idx_scan > 0
        ORDER BY idx_pct ASC NULLS FIRST
        LIMIT 10
    """)
    return cur.fetchall()


def active_connections(cur):
    cur.execute("""
        SELECT state, count(*) AS cnt
        FROM pg_stat_activity
        WHERE datname = current_database()
        GROUP BY state
        ORDER BY cnt DESC
    """)
    return cur.fetchall()


def explain_key_queries(cur):
    results = []
    for label, q in EXPLAIN_QUERIES:
        try:
            cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {q}")
            plan = "\n".join(r[0] for r in cur.fetchall())
            results.append((label, plan))
        except psycopg2.Error as e:
            results.append((label, f"ERROR: {e}"))
    return results


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def print_table(headers, rows):
    if not rows:
        print("  (no data)\n")
        return
    col_widths = [max(len(str(h)), max(len(str(r[i])) for r in rows))
                  for i, h in enumerate(headers)]
    fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
    sep = "  " + "  ".join("-" * w for w in col_widths)
    print(fmt.format(*headers))
    print(sep)
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))
    print()


def section(title: str):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="Reset pg_stat_statements counters (run before load test)")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    print(f"\nConnecting to {PG_HOST}:{PG_PORT}/{PG_DB} as {PG_USER} ...")
    try:
        conn = connect()
    except psycopg2.OperationalError as e:
        print(f"[ERROR] Cannot connect: {e}")
        sys.exit(1)

    conn.autocommit = True
    cur = conn.cursor()

    stat_available = has_pg_stat_statements(cur)
    print(f"[INFO] pg_stat_statements: {'ACTIVE' if stat_available else 'NOT LOADED (using fallback)'}")
    if not stat_available:
        print("[INFO] To activate: restart the postgres container (docker-compose.yml already updated).")

    if args.reset:
        if stat_available:
            reset_stats(cur)
        else:
            print("[WARN] pg_stat_statements not active — nothing to reset.")
        cur.close()
        conn.close()
        return

    # -----------------------------------------------------------------------
    # Mode 1: pg_stat_statements
    # -----------------------------------------------------------------------
    if stat_available:
        section("TOP 10 SLOWEST QUERIES — by mean execution time")
        print_table(["mean_ms", "max_ms", "calls", "pct%", "query"],
                    top_by_mean_time(cur, args.limit))

        section("TOP 10 MOST EXPENSIVE QUERIES — by total time (overall impact)")
        print_table(["mean_ms", "total_ms", "calls", "pct%", "query"],
                    top_by_total_time(cur, args.limit))

    # -----------------------------------------------------------------------
    # Mode 2: always available
    # -----------------------------------------------------------------------
    section("SEQUENTIAL SCANS per table (high seq_scan = missing index candidate)")
    print_table(["table", "seq_scan", "idx_scan", "seq_tup_read", "live_rows"],
                seq_scan_tables(cur))

    section("INDEX USAGE RATIO per table (low idx_pct = full table scans)")
    print_table(["table", "idx_scan", "seq_scan", "idx_pct%", "live_rows"],
                index_usage(cur))

    section("ACTIVE CONNECTIONS — current state")
    print_table(["state", "count"], active_connections(cur))

    section("EXPLAIN ANALYZE — key query plans")
    for label, plan in explain_key_queries(cur):
        print(f"\n  >> {label}")
        for line in plan.splitlines()[:20]:   # cap at 20 lines per plan
            print(f"     {line}")
        print()

    cur.close()
    conn.close()
    print("Done.\n")


if __name__ == "__main__":
    main()
