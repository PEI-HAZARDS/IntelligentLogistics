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

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# Run SQL and return the trimmed result. Errors are printed to stderr.
run_sql() {
    local result
    result=$(docker exec -i "$CONTAINER" \
        psql -U "$DB_USER" -d "$DB_NAME" -t -A -c "$1" 2>&1)
    local rc=$?
    if [[ $rc -ne 0 ]]; then
        echo -e "${RED}[SQL ERROR]${NC} $result" >&2
        return $rc
    fi
    # Strip trailing whitespace/newlines
    echo "$result" | sed '/^$/d'
}

run_sql_verbose() {
    docker exec -i "$CONTAINER" \
        psql -U "$DB_USER" -d "$DB_NAME" -c "$1" 2>&1
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
}

# ── ADD ──────────────────────────────────────────────────────────────────────
do_add() {
    local PLATE="$1"
    info "Adding truck ${BOLD}${PLATE}${NC} ..."

    # Auto-detect existing company, driver, terminal, gate from the DB
    local COMPANY_NIF DRIVER_LICENSE TERMINAL_ID GATE_IN_ID

    COMPANY_NIF=$(run_sql "SELECT nif FROM company LIMIT 1;") || die "Failed to query company table"
    [[ -z "$COMPANY_NIF" ]] && die "No companies found in the database. Seed the DB first."

    DRIVER_LICENSE=$(run_sql "SELECT drivers_license FROM driver LIMIT 1;") || die "Failed to query driver table"
    [[ -z "$DRIVER_LICENSE" ]] && die "No drivers found in the database. Seed the DB first."

    TERMINAL_ID=$(run_sql "SELECT id FROM terminal LIMIT 1;") || die "Failed to query terminal table"
    [[ -z "$TERMINAL_ID" ]] && die "No terminals found in the database. Seed the DB first."

    GATE_IN_ID=$(run_sql "SELECT id FROM gate LIMIT 1;") || die "Failed to query gate table"
    [[ -z "$GATE_IN_ID" ]] && die "No gates found in the database. Seed the DB first."

    info "Using: company=${COMPANY_NIF}, driver=${DRIVER_LICENSE}, terminal=${TERMINAL_ID}, gate=${GATE_IN_ID}"

    # Check if truck already exists
    local existing
    existing=$(run_sql "SELECT license_plate FROM truck WHERE license_plate = '${PLATE}';") || die "Failed to query truck table"
    
    if [[ -n "$existing" ]]; then
        warn "Truck '${PLATE}' already exists in the database."
        
        # Check if it already has an in_transit appointment
        local has_appt
        has_appt=$(run_sql "SELECT id FROM appointment WHERE truck_license_plate = '${PLATE}' AND status = 'in_transit' LIMIT 1;") || true
        if [[ -n "$has_appt" ]]; then
            warn "Truck already has an active appointment (id=${has_appt}). Skipping."
            return 0
        fi
        info "Creating a new appointment for existing truck..."
    else
        # Insert the truck
        run_sql "INSERT INTO truck (license_plate, company_nif, brand) VALUES ('${PLATE}', '${COMPANY_NIF}', '${TRUCK_BRAND}');" || die "Failed to insert truck"
        ok "Truck created: ${PLATE} (${TRUCK_BRAND})"
    fi

    # Create a booking
    local TODAY
    TODAY=$(date +%Y%m%d)
    local NEXT_SEQ
    NEXT_SEQ=$(run_sql "SELECT COALESCE(MAX(CAST(SPLIT_PART(reference, '-', 3) AS INTEGER)), 0) + 1 FROM booking WHERE reference LIKE 'AVR-${TODAY}-%';") || die "Failed to get next booking sequence"
    
    # Default to 1 if empty
    NEXT_SEQ="${NEXT_SEQ:-1}"
    local BOOK_REF="AVR-${TODAY}-$(printf '%04d' "$NEXT_SEQ")"

    run_sql "INSERT INTO booking (reference, direction) VALUES ('${BOOK_REF}', 'inbound');" || die "Failed to create booking"
    ok "Booking created: ${BOOK_REF}"

    # Create cargo
    run_sql "INSERT INTO cargo (booking_reference, quantity, state, description) VALUES ('${BOOK_REF}', ${CARGO_QTY}, '${CARGO_STATE}', '${CARGO_DESC}');" || die "Failed to create cargo"
    ok "Cargo created for booking ${BOOK_REF}"

    # Create appointment (scheduled 5 min from now)
    local SCHED
    SCHED=$(date -d "+5 minutes" +"%Y-%m-%d %H:%M:%S" 2>/dev/null || date -v+5M +"%Y-%m-%d %H:%M:%S" 2>/dev/null)
    if [[ -z "$SCHED" ]]; then
        die "Failed to compute scheduled time"
    fi
    
    run_sql "
        INSERT INTO appointment (
            booking_reference, driver_license, truck_license_plate,
            terminal_id, gate_in_id, scheduled_start_time,
            expected_duration, status, notes
        ) VALUES (
            '${BOOK_REF}', '${DRIVER_LICENSE}', '${PLATE}',
            ${TERMINAL_ID}, ${GATE_IN_ID}, '${SCHED}',
            ${EXPECTED_DURATION}, 'in_transit', 'Added via manage_trucks.sh'
        );
    " || die "Failed to create appointment"

    # Get the generated arrival_id
    local PIN
    PIN=$(run_sql "SELECT arrival_id FROM appointment WHERE truck_license_plate = '${PLATE}' ORDER BY id DESC LIMIT 1;") || true

    ok "Appointment created: PIN=${PIN:-N/A}, scheduled at $(echo "$SCHED" | cut -d' ' -f2 | cut -d: -f1-2)"
    echo ""
    echo -e "${GREEN}${BOLD}✓ Truck ${PLATE} is now expected at the gate.${NC}"
}

# ── DELETE ───────────────────────────────────────────────────────────────────
do_delete() {
    local PLATE="$1"
    info "Deleting truck ${BOLD}${PLATE}${NC} and related data..."

    # Check if truck exists
    local existing
    existing=$(run_sql "SELECT license_plate FROM truck WHERE license_plate = '${PLATE}';") || die "Failed to query truck table"
    if [[ -z "$existing" ]]; then
        die "Truck '${PLATE}' not found in the database."
    fi

    # Get all booking references tied to this truck's appointments
    local BOOKING_REFS
    BOOKING_REFS=$(run_sql "SELECT DISTINCT booking_reference FROM appointment WHERE truck_license_plate = '${PLATE}';") || true

    # Delete in order: alerts → visit → appointment → cargo → booking → truck
    # (respecting foreign key constraints)

    run_sql "
        DELETE FROM shift_alert_history
        WHERE id IN (
            SELECT sah.id FROM shift_alert_history sah
            JOIN alert al ON al.id = sah.alert_id
            JOIN visit v ON v.appointment_id = al.visit_id
            JOIN appointment a ON a.id = v.appointment_id
            WHERE a.truck_license_plate = '${PLATE}'
        );
    " || true

    run_sql "
        DELETE FROM alert
        WHERE visit_id IN (
            SELECT v.appointment_id FROM visit v
            JOIN appointment a ON a.id = v.appointment_id
            WHERE a.truck_license_plate = '${PLATE}'
        );
    " || true

    run_sql "
        DELETE FROM visit
        WHERE appointment_id IN (
            SELECT id FROM appointment WHERE truck_license_plate = '${PLATE}'
        );
    " || true

    # Delete appointments
    local DELETED_APPTS
    DELETED_APPTS=$(run_sql "DELETE FROM appointment WHERE truck_license_plate = '${PLATE}' RETURNING id;" | wc -l) || true
    ok "Deleted ${DELETED_APPTS:-0} appointment(s)"

    # Delete cargo and bookings that are no longer referenced
    if [[ -n "$BOOKING_REFS" ]]; then
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
        done <<< "$BOOKING_REFS"
    fi

    # Delete the truck itself
    run_sql "DELETE FROM truck WHERE license_plate = '${PLATE}';" || die "Failed to delete truck"
    ok "Deleted truck ${PLATE}"

    echo ""
    echo -e "${GREEN}${BOLD}✓ Truck ${PLATE} fully removed.${NC}"
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
