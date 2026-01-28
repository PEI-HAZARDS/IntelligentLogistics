#!/bin/bash
# ============================================================================
# ENV Manager - Backup and Restore .env files with Google Drive sync
# ============================================================================
# Usage:
#   ./env_manager.sh backup [destination]   - Backup all .env to local destination
#   ./env_manager.sh restore [source]       - Restore .env from local source
#   ./env_manager.sh push                   - Push .env files to Google Drive
#   ./env_manager.sh pull                   - Pull .env files from Google Drive
#   ./env_manager.sh list                   - List all .env files in project
#   ./env_manager.sh setup                  - Setup rclone for Google Drive
#
# Examples:
#   ./env_manager.sh push                   # Upload to Google Drive
#   ./env_manager.sh pull                   # Download from Google Drive
#   ./env_manager.sh backup ~/backup        # Local backup
# ============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
SRC_DIR="$PROJECT_ROOT/src"

# Google Drive settings via rclone
RCLONE_REMOTE="gdrive"  # Nome do remote no rclone
# ID da pasta partilhada (extraído de https://drive.google.com/drive/folders/1lrFgKTUySEWRYefE1J3J15rjhKjClhJw)
GDRIVE_FOLDER_ID="1lrFgKTUySEWRYefE1J3J15rjhKjClhJw"
GDRIVE_SUBFOLDER="variaveis"  # Subpasta para os .env

# Default local backup location
DEFAULT_BACKUP_DIR="$PROJECT_ROOT/.env_backup"

# .env locations relative to src/
ENV_LOCATIONS=(
    # Favor adicionar os .env aqui! Sempre que meterem algo novo
    "AI_APP/agentA/.env"
    "AI_APP/agentB/.env"
    "AI_APP/agentC/.env"
    "AI_APP/broker/.env"
    "V_APP/api_gateway/.env"
    "V_APP/Data_Module/.env"
    "V_APP/decision_engine/.env"
    "devops/observability/.env"
    "devops/promtail-remote/.env"
    "streaming_middleware/.env"
)

# ============================================================================
# Functions
# ============================================================================

print_header() {
    echo -e "${BLUE}============================================${NC}"
    echo -e "${BLUE}  ENV Manager - $1${NC}"
    echo -e "${BLUE}============================================${NC}"
    echo ""
}

list_envs() {
    print_header "List .env Files"
    
    echo -e "${YELLOW}Configured locations:${NC}"
    for env_path in "${ENV_LOCATIONS[@]}"; do
        full_path="$SRC_DIR/$env_path"
        if [[ -f "$full_path" ]]; then
            size=$(wc -c < "$full_path")
            lines=$(wc -l < "$full_path")
            echo -e "  ${GREEN}✓${NC} $env_path (${lines} lines, ${size} bytes)"
        else
            echo -e "  ${RED}✗${NC} $env_path (not found)"
        fi
    done
    
    echo ""
    echo -e "${YELLOW}Other .env files found:${NC}"
    find "$SRC_DIR" -name ".env" -o -name ".env.*" 2>/dev/null | while read -r file; do
        rel_path="${file#$SRC_DIR/}"
        # Check if it's in our list
        if ! printf '%s\n' "${ENV_LOCATIONS[@]}" | grep -q "^$rel_path$"; then
            echo -e "  ${BLUE}?${NC} $rel_path"
        fi
    done
}

backup_envs() {
    local backup_dir="${1:-$DEFAULT_BACKUP_DIR}"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local versioned_dir="$backup_dir/$timestamp"
    
    print_header "Backup .env Files"
    
    echo -e "${YELLOW}Backup destination:${NC} $versioned_dir"
    echo ""
    
    # Create backup directory
    mkdir -p "$versioned_dir"
    
    # Create manifest
    echo "# ENV Backup Manifest" > "$versioned_dir/manifest.txt"
    echo "# Created: $(date)" >> "$versioned_dir/manifest.txt"
    echo "# Project: $PROJECT_ROOT" >> "$versioned_dir/manifest.txt"
    echo "" >> "$versioned_dir/manifest.txt"
    
    local count=0
    for env_path in "${ENV_LOCATIONS[@]}"; do
        full_path="$SRC_DIR/$env_path"
        if [[ -f "$full_path" ]]; then
            # Create subdirectory structure
            backup_subdir="$versioned_dir/$(dirname "$env_path")"
            mkdir -p "$backup_subdir"
            
            # Copy file
            cp "$full_path" "$backup_subdir/"
            echo -e "  ${GREEN}✓${NC} Backed up: $env_path"
            echo "$env_path" >> "$versioned_dir/manifest.txt"
            count=$((count+1))
        else
            echo -e "  ${YELLOW}⚠${NC} Skipped (not found): $env_path"
        fi
    done
    
    echo ""
    echo -e "${GREEN}Backup complete!${NC}"
    echo -e "  Files backed up: $count"
    echo -e "  Location: $versioned_dir"
    
    # Create/update latest symlink
    ln -sfn "$versioned_dir" "$backup_dir/latest"
    echo -e "  Latest symlink: $backup_dir/latest"
}

restore_envs() {
    local source_dir="${1:-$DEFAULT_BACKUP_DIR/latest}"
    
    print_header "Restore .env Files"
    
    # Check if source exists
    if [[ ! -d "$source_dir" ]]; then
        echo -e "${RED}Error: Source directory not found: $source_dir${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}Restore source:${NC} $source_dir"
    echo ""
    
    # Check manifest
    if [[ -f "$source_dir/manifest.txt" ]]; then
        echo -e "${BLUE}Manifest found:${NC}"
        head -5 "$source_dir/manifest.txt"
        echo ""
    fi
    
    local count=0
    for env_path in "${ENV_LOCATIONS[@]}"; do
        backup_file="$source_dir/$env_path"
        dest_file="$SRC_DIR/$env_path"
        
        if [[ -f "$backup_file" ]]; then
            # Create destination directory if needed
            mkdir -p "$(dirname "$dest_file")"
            
            # Check if destination exists
            if [[ -f "$dest_file" ]]; then
                # Compare files
                if cmp -s "$backup_file" "$dest_file"; then
                    echo -e "  ${BLUE}=${NC} Unchanged: $env_path"
                else
                    cp "$backup_file" "$dest_file"
                    echo -e "  ${GREEN}✓${NC} Updated: $env_path"
                    count=$((count+1))
                fi
            else
                cp "$backup_file" "$dest_file"
                echo -e "  ${GREEN}+${NC} Created: $env_path"
                count=$((count+1))
            fi
        else
            echo -e "  ${YELLOW}⚠${NC} Not in backup: $env_path"
        fi
    done
    
    echo ""
    echo -e "${GREEN}Restore complete!${NC}"
    echo -e "  Files restored/updated: $count"
}

check_rclone() {
    if ! command -v rclone &> /dev/null; then
        echo -e "${RED}Error: rclone not installed${NC}"
        echo ""
        echo "Install rclone:"
        echo "  curl https://rclone.org/install.sh | sudo bash"
        echo ""
        echo "Then run: $0 setup"
        exit 1
    fi
}

setup_rclone() {
    print_header "Setup rclone for Google Drive"
    
    check_rclone
    
    echo -e "${YELLOW}This will configure rclone to access Google Drive.${NC}"
    echo ""
    echo "Steps:"
    echo "  1. Run: rclone config"
    echo "  2. Choose 'n' for new remote"
    echo "  3. Name it: $RCLONE_REMOTE"
    echo "  4. Choose 'drive' (Google Drive)"
    echo "  5. Follow the OAuth flow"
    echo ""
    echo -e "${BLUE}Running rclone config...${NC}"
    echo ""
    
    rclone config
    
    echo ""
    echo -e "${GREEN}Setup complete!${NC}"
    echo "Test with: rclone lsd ${RCLONE_REMOTE}:"
}

push_to_drive() {
    print_header "Push .env to Google Drive"
    
    check_rclone
    
    local temp_dir=$(mktemp -d)
    # Usar root_folder_id para aceder à pasta partilhada
    local remote_path="${RCLONE_REMOTE},root_folder_id=${GDRIVE_FOLDER_ID}:${GDRIVE_SUBFOLDER}"
    
    echo -e "${YELLOW}Remote destination:${NC} $remote_path"
    echo ""
    
    # Collect .env files to temp dir with structure
    local count=0
    for env_path in "${ENV_LOCATIONS[@]}"; do
        full_path="$SRC_DIR/$env_path"
        if [[ -f "$full_path" ]]; then
            # Create subdirectory structure
            temp_subdir="$temp_dir/$(dirname "$env_path")"
            mkdir -p "$temp_subdir"
            
            # Copy file
            cp "$full_path" "$temp_subdir/"
            echo -e "  ${GREEN}✓${NC} Collected: $env_path"
            count=$((count+1))
        else
            echo -e "  ${YELLOW}⚠${NC} Skipped: $env_path (not found)"
        fi
    done
    
    # Create manifest
    echo "# ENV Backup" > "$temp_dir/manifest.txt"
    echo "# Updated: $(date)" >> "$temp_dir/manifest.txt"
    echo "# Files: $count" >> "$temp_dir/manifest.txt"
    
    echo ""
    echo -e "${BLUE}Uploading to Google Drive...${NC}"
    
    # Sync to remote (updates only changed files)
    rclone sync "$temp_dir" "$remote_path" --progress
    
    # Cleanup
    rm -rf "$temp_dir"
    
    echo ""
    echo -e "${GREEN}Push complete!${NC}"
    echo -e "  Files uploaded: $count"
    echo -e "  Location: $remote_path"
}

pull_from_drive() {
    print_header "Pull .env from Google Drive"
    
    check_rclone
    
    local remote_path="${RCLONE_REMOTE},root_folder_id=${GDRIVE_FOLDER_ID}:${GDRIVE_SUBFOLDER}"
    local temp_dir=$(mktemp -d)
    
    echo -e "${YELLOW}Remote source:${NC} $remote_path"
    echo ""
    
    echo -e "${BLUE}Downloading from Google Drive...${NC}"
    rclone copy "$remote_path" "$temp_dir" --progress
    
    echo ""
    
    # Restore from temp dir
    local count=0
    for env_path in "${ENV_LOCATIONS[@]}"; do
        source_file="$temp_dir/$env_path"
        dest_file="$SRC_DIR/$env_path"
        
        if [[ -f "$source_file" ]]; then
            mkdir -p "$(dirname "$dest_file")"
            
            if [[ -f "$dest_file" ]]; then
                if cmp -s "$source_file" "$dest_file"; then
                    echo -e "  ${BLUE}=${NC} Unchanged: $env_path"
                else
                    cp "$source_file" "$dest_file"
                    echo -e "  ${GREEN}✓${NC} Updated: $env_path"
                    count=$((count+1))
                fi
            else
                cp "$source_file" "$dest_file"
                echo -e "  ${GREEN}+${NC} Created: $env_path"
                count=$((count+1))
            fi
        fi
    done
    
    # Cleanup
    rm -rf "$temp_dir"
    
    echo ""
    echo -e "${GREEN}Pull complete!${NC}"
    echo -e "  Files restored/updated: $count"
}

list_drive_versions() {
    print_header "List Google Drive Versions"
    
    check_rclone
    
    local remote_path="${RCLONE_REMOTE},root_folder_id=${GDRIVE_FOLDER_ID}:${GDRIVE_SUBFOLDER}"
    
    echo -e "${YELLOW}Remote:${NC} Google Drive (pasta partilhada)"
    echo -e "${YELLOW}Subfolder:${NC} ${GDRIVE_SUBFOLDER}"
    echo ""
    echo -e "${BLUE}Available versions:${NC}"
    rclone lsd "$remote_path" 2>/dev/null | awk '{print "  " $5 " (" $2 " " $3 ")"}'
}

show_help() {
    echo "ENV Manager - Backup and Restore .env files with Google Drive"
    echo ""
    echo "Usage:"
    echo "  $0 push                   Upload .env files to Google Drive"
    echo "  $0 pull [version]         Download .env files from Google Drive"
    echo "  $0 versions               List available versions on Drive"
    echo "  $0 backup [destination]   Local backup to destination folder"
    echo "  $0 restore [source]       Restore from local backup"
    echo "  $0 list                   List all .env files in project"
    echo "  $0 setup                  Setup rclone for Google Drive"
    echo "  $0 help                   Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 push                   # Upload to Google Drive"
    echo "  $0 pull                   # Download latest from Drive"
    echo "  $0 pull 20260128_130000   # Download specific version"
    echo "  $0 backup ~/my_backup     # Local backup"
}

# ============================================================================
# Main
# ============================================================================

case "${1:-help}" in
    push)
        push_to_drive
        ;;
    pull)
        pull_from_drive "$2"
        ;;
    versions)
        list_drive_versions
        ;;
    backup)
        backup_envs "$2"
        ;;
    restore)
        restore_envs "$2"
        ;;
    list)
        list_envs
        ;;
    setup)
        setup_rclone
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac
