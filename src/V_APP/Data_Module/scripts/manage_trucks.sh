#!/usr/bin/env bash
# =============================================================================
# manage_trucks.sh — Add/Delete expected trucks from the database
#
# Usage:
#   ./manage_trucks.sh add    <LICENSE_PLATE>
#   ./manage_trucks.sh delete <LICENSE_PLATE>
#   ./manage_trucks.sh list
#
# Execs into the dm_postgres container and runs SQL directly.
# Hardcoded defaults (matching data_init_realistic.py seed data):
#   Company:  PT509123456 (Transportes Aveiro Lda)
#   Driver:   PT12345678  (Rui Almeida)
#   Terminal: 1
#   Gate In:  1
# =============================================================================

# ── Configuration ────────────────────────────────────────────────────────────
CONTAINER="dm_postgres"
DB_USER="${POSTGRES_USER:-pei_user}"
DB_NAME="${POSTGRES_DB:-IntelligentLogistics}"

# Hardcoded defaults (from seed data)
COMPANY_NIF="PT509123456"
DRIVER_LICENSE="PT12345678"
TERMINAL_ID=1
GATE_IN_ID=1
TRUCK_BRAND="Volvo FH16"
EXPECTED_DURATION=45
CARGO_QTY=10000
CARGO_STATE="solid"
CARGO_DESC="General cargo"

# ── Helpers ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; return 0; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; return 0; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; return 0; }
die()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# Run SQL and return the trimmed result. Errors are printed to stderr.
run_sql() {
    local query="$1"
    local result
    result=$(docker exec -i "$CONTAINER" \
        psql -U "$DB_USER" -d "$DB_NAME" -t -A -c "$query" 2>&1)
    local rc=$?
    if [[ $rc -ne 0 ]]; then
        echo -e "${RED}[SQL ERROR]${NC} $result" >&2
        return $rc
    fi
    # Strip trailing whitespace/newlines
    echo "$result" | sed '/^$/d'
    return 0
}

run_sql_verbose() {
    local query="$1"
    docker exec -i "$CONTAINER" \
        psql -U "$DB_USER" -d "$DB_NAME" -c "$query" 2>&1
    return 0
}

usage() {
    echo -e "${BOLD}Usage:${NC}"
    echo "  $0 add    <LICENSE_PLATE>   Add a truck + appointment"
    echo "  $0 delete <LICENSE_PLATE>   Remove a truck and its appointments"
    echo "  $0 list                     List all expected trucks"
    echo ""
    echo -e "${BOLD}Examples:${NC}"
    echo "  $0 add    XX-99-ZZ"
    echo "  $0 delete XX-99-ZZ"
    echo "  $0 list"
    exit 1
}

# ── Check container is running ───────────────────────────────────────────────
check_container() {
    if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
        die "Container '${CONTAINER}' is not running.\nStart the stack first: docker compose up -d"
    fi
    info "Connected to container ${BOLD}${CONTAINER}${NC}"
    return 0
}

# ── LIST ─────────────────────────────────────────────────────────────────────
do_list() {
    info "Listing all trucks with appointments...\n"
    run_sql_verbose "
        SELECT
            t.license_plate   AS plate,
            t.brand,
            a.arrival_id      AS pin,
            a.status,
            to_char(a.scheduled_start_time, 'HH24:MI') AS scheduled
        FROM truck t
        LEFT JOIN appointment a ON a.truck_license_plate = t.license_plate
        ORDER BY a.scheduled_start_time ASC NULLS LAST;
    "
    return 0
}

# ── ADD ──────────────────────────────────────────────────────────────────────
do_add() {
    local plate="$1"
    info "Adding truck ${BOLD}${plate}${NC} ..."

    # Auto-detect existing company, driver, terminal, gate from the DB
    local company_nif driver_license terminal_id gate_in_id

    company_nif=$(run_sql "SELECT nif FROM company LIMIT 1;") || die "Failed to query company table"
    [[ -z "$company_nif" ]] && die "No companies found in the database. Seed the DB first."

    driver_license=$(run_sql "SELECT drivers_license FROM driver LIMIT 1;") || die "Failed to query driver table"
    [[ -z "$driver_license" ]] && die "No drivers found in the database. Seed the DB first."

    terminal_id=$(run_sql "SELECT id FROM terminal LIMIT 1;") || die "Failed to query terminal table"
    [[ -z "$terminal_id" ]] && die "No terminals found in the database. Seed the DB first."

    gate_in_id=$(run_sql "SELECT id FROM gate LIMIT 1;") || die "Failed to query gate table"
    [[ -z "$gate_in_id" ]] && die "No gates found in the database. Seed the DB first."

    info "Using: company=${company_nif}, driver=${driver_license}, terminal=${terminal_id}, gate=${gate_in_id}"

    # Check if truck already exists
    local existing
    existing=$(run_sql "SELECT license_plate FROM truck WHERE license_plate = '${plate}';") || die "Failed to query truck table"

    if [[ -n "$existing" ]]; then
        warn "Truck '${plate}' already exists in the database."

        # Check if it already has an in_transit appointment
        local has_appt
        has_appt=$(run_sql "SELECT id FROM appointment WHERE truck_license_plate = '${plate}' AND status = 'in_transit' LIMIT 1;") || true
        if [[ -n "$has_appt" ]]; then
            warn "Truck already has an active appointment (id=${has_appt}). Skipping."
            return 0
        fi
        info "Creating a new appointment for existing truck..."
    else
        # Insert the truck
        run_sql "INSERT INTO truck (license_plate, company_nif, brand) VALUES ('${plate}', '${company_nif}', '${TRUCK_BRAND}');" || die "Failed to insert truck"
        ok "Truck created: ${plate} (${TRUCK_BRAND})"
    fi

    # Create a booking
    local today
    today=$(date +%Y%m%d)
    local next_seq
    next_seq=$(run_sql "SELECT COALESCE(MAX(CAST(SPLIT_PART(reference, '-', 3) AS INTEGER)), 0) + 1 FROM booking WHERE reference LIKE 'AVR-${today}-%';") || die "Failed to get next booking sequence"

    # Default to 1 if empty
    next_seq="${next_seq:-1}"
    local book_ref="AVR-${today}-$(printf '%04d' "$next_seq")"

    run_sql "INSERT INTO booking (reference, direction) VALUES ('${book_ref}', 'inbound');" || die "Failed to create booking"
    ok "Booking created: ${book_ref}"

    # Create cargo
    run_sql "INSERT INTO cargo (booking_reference, quantity, state, description) VALUES ('${book_ref}', ${CARGO_QTY}, '${CARGO_STATE}', '${CARGO_DESC}');" || die "Failed to create cargo"
    ok "Cargo created for booking ${book_ref}"

    # Create appointment (scheduled 5 min from now)
    local sched
    sched=$(date -d "+5 minutes" +"%Y-%m-%d %H:%M:%S" 2>/dev/null || date -v+5M +"%Y-%m-%d %H:%M:%S" 2>/dev/null)
    if [[ -z "$sched" ]]; then
        die "Failed to compute scheduled time"
    fi

    run_sql "
        INSERT INTO appointment (
            booking_reference, driver_license, truck_license_plate,
            terminal_id, gate_in_id, scheduled_start_time,
            expected_duration, status, notes
        ) VALUES (
            '${book_ref}', '${driver_license}', '${plate}',
            ${terminal_id}, ${gate_in_id}, '${sched}',
            ${EXPECTED_DURATION}, 'in_transit', 'Added via manage_trucks.sh'
        );
    " || die "Failed to create appointment"

    # Get the generated arrival_id
    local pin
    pin=$(run_sql "SELECT arrival_id FROM appointment WHERE truck_license_plate = '${plate}' ORDER BY id DESC LIMIT 1;") || true

    ok "Appointment created: PIN=${pin:-N/A}, scheduled at $(echo "$sched" | cut -d' ' -f2 | cut -d: -f1-2)"
    echo ""
    echo -e "${GREEN}${BOLD}✓ Truck ${plate} is now expected at the gate.${NC}"
    return 0
}

# ── DELETE ───────────────────────────────────────────────────────────────────
do_delete() {
    local plate="$1"
    info "Deleting truck ${BOLD}${plate}${NC} and related data..."

    # Check if truck exists
    local existing
    existing=$(run_sql "SELECT license_plate FROM truck WHERE license_plate = '${plate}';") || die "Failed to query truck table"
    if [[ -z "$existing" ]]; then
        die "Truck '${plate}' not found in the database."
    fi

    # Get all booking references tied to this truck's appointments
    local booking_refs
    booking_refs=$(run_sql "SELECT DISTINCT booking_reference FROM appointment WHERE truck_license_plate = '${plate}';") || true

    # Delete in order: alerts → visit → appointment → cargo → booking → truck
    # (respecting foreign key constraints)

    run_sql "
        DELETE FROM shift_alert_history
        WHERE id IN (
            SELECT sah.id FROM shift_alert_history sah
            JOIN alert al ON al.id = sah.alert_id
            JOIN visit v ON v.appointment_id = al.visit_id
            JOIN appointment a ON a.id = v.appointment_id
            WHERE a.truck_license_plate = '${plate}'
        );
    " || true

    run_sql "
        DELETE FROM alert
        WHERE visit_id IN (
            SELECT v.appointment_id FROM visit v
            JOIN appointment a ON a.id = v.appointment_id
            WHERE a.truck_license_plate = '${plate}'
        );
    " || true

    run_sql "
        DELETE FROM visit
        WHERE appointment_id IN (
            SELECT id FROM appointment WHERE truck_license_plate = '${plate}'
        );
    " || true

    # Delete appointments
    local deleted_appts
    deleted_appts=$(run_sql "DELETE FROM appointment WHERE truck_license_plate = '${plate}' RETURNING id;" | wc -l) || true
    ok "Deleted ${deleted_appts:-0} appointment(s)"

    # Delete cargo and bookings that are no longer referenced
    if [[ -n "$booking_refs" ]]; then
        while IFS= read -r ref; do
            [[ -z "$ref" ]] && continue
            # Only delete if no other appointments reference this booking
            local other
            other=$(run_sql "SELECT id FROM appointment WHERE booking_reference = '${ref}' LIMIT 1;") || true
            if [[ -z "$other" ]]; then
                run_sql "DELETE FROM cargo WHERE booking_reference = '${ref}';" || true
                run_sql "DELETE FROM booking WHERE reference = '${ref}';" || true
                ok "Deleted booking ${ref} and its cargo"
            fi
        done <<< "$booking_refs"
    fi

    # Delete the truck itself
    run_sql "DELETE FROM truck WHERE license_plate = '${plate}';" || die "Failed to delete truck"
    ok "Deleted truck ${plate}"

    echo ""
    echo -e "${GREEN}${BOLD}✓ Truck ${plate} fully removed.${NC}"
    return 0
}

# ── Main ─────────────────────────────────────────────────────────────────────
[[ $# -lt 1 ]] && usage

ACTION="${1,,}"  # lowercase

check_container

case "$ACTION" in
    add)
        [[ $# -lt 2 ]] && { die "Missing LICENSE_PLATE argument."; }
        do_add "$2"
        ;;
    delete|del|remove|rm)
        [[ $# -lt 2 ]] && { die "Missing LICENSE_PLATE argument."; }
        do_delete "$2"
        ;;
    list|ls)
        do_list
        ;;
    *)
        die "Unknown action: ${ACTION}"
        ;;
esac
