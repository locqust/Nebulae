#!/bin/bash
# =============================================================================
# Nebulae Native Linux Installer
# https://github.com/locqust/Nebulae
# =============================================================================
# Supports: Debian / Ubuntu and derivatives (including Raspberry Pi OS)
#           RHEL / Fedora / CentOS / Rocky Linux / AlmaLinux
#           Arch Linux
#
# What this script does:
#   1. Detects your distro and installs system dependencies
#   2. Creates a dedicated 'nebulae' system user
#   3. Clones Nebulae from GitHub into /opt/nebulae
#   4. Creates a Python virtualenv and installs pip dependencies
#   5. Prompts you for NODE_HOSTNAME and generates a SECRET_KEY
#   6. Writes /etc/nebulae/nebulae.env
#   7. Creates and enables a systemd service
#   8. Optionally configures a basic Nginx reverse proxy block
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/locqust/Nebulae/main/scripts/install-nebulae.sh -o install-nebulae.sh
#   less install-nebulae.sh   # review before running (recommended)
#   sudo bash install-nebulae.sh
# =============================================================================

set -euo pipefail

# --- Colour helpers ----------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
die()     { error "$*"; exit 1; }
header()  { echo -e "\n${BOLD}${CYAN}=== $* ===${RESET}\n"; }

# --- Sanity checks -----------------------------------------------------------
[[ "$EUID" -ne 0 ]] && die "Please run as root or with sudo."
command -v git  >/dev/null 2>&1 || true  # will install below if missing
command -v curl >/dev/null 2>&1 || true

# --- Configuration defaults --------------------------------------------------
INSTALL_DIR="/opt/nebulae"
SERVICE_USER="nebulae"
ENV_DIR="/etc/nebulae"
ENV_FILE="${ENV_DIR}/nebulae.env"
SERVICE_FILE="/etc/systemd/system/nebulae.service"
NGINX_CONF="/etc/nginx/sites-available/nebulae"
GUNICORN_WORKERS=2
GUNICORN_THREADS=4
REPO_URL="https://github.com/locqust/Nebulae.git"

# On lower-RAM machines (Pi 4 2GB, etc.) reduce workers automatically
TOTAL_RAM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
if [[ "$TOTAL_RAM_MB" -lt 2048 ]]; then
    GUNICORN_WORKERS=1
    warn "Less than 2GB RAM detected (${TOTAL_RAM_MB}MB). Setting Gunicorn to 1 worker."
fi

# =============================================================================
# 1. Distro detection and dependency installation
# =============================================================================
header "Detecting distribution"

detect_distro() {
    if   [[ -f /etc/debian_version ]]; then echo "debian"
    elif [[ -f /etc/redhat-release ]]; then echo "rhel"
    elif [[ -f /etc/arch-release    ]]; then echo "arch"
    else echo "unknown"
    fi
}

DISTRO=$(detect_distro)
info "Detected: ${DISTRO}"

install_deps_debian() {
    info "Updating package lists..."
    apt-get update -q
    info "Installing system dependencies..."
    apt-get install -y -q \
        python3 python3-pip python3-venv python3-dev \
        sqlite3 \
        libffi-dev libssl-dev libjpeg-dev libopenjp2-7 \
        git nginx curl
}

install_deps_rhel() {
    info "Installing system dependencies..."
    # Use dnf if available (Fedora/RHEL 8+), else yum
    local pm="dnf"
    command -v dnf >/dev/null 2>&1 || pm="yum"
    "$pm" install -y \
        python3 python3-pip python3-devel \
        sqlite libffi-devel openssl-devel libjpeg-turbo-devel \
        git nginx curl
    # python3-venv is a separate package on some RHEL variants
    "$pm" install -y python3-virtualenv 2>/dev/null || true
}

install_deps_arch() {
    info "Installing system dependencies..."
    pacman -Sy --noconfirm \
        python python-pip \
        sqlite libffi openssl libjpeg-turbo \
        git nginx curl
}

case "$DISTRO" in
    debian) install_deps_debian ;;
    rhel)   install_deps_rhel   ;;
    arch)   install_deps_arch   ;;
    *)      die "Unsupported distribution. Please install dependencies manually and follow the manual install guide at https://locqust.github.io/Nebulae/installation/linux/" ;;
esac

success "System dependencies installed."

# =============================================================================
# 2. Create dedicated system user
# =============================================================================
header "Creating system user"

if id "$SERVICE_USER" &>/dev/null; then
    info "User '${SERVICE_USER}' already exists, skipping."
else
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
    success "Created user '${SERVICE_USER}'."
fi

# =============================================================================
# 3. Clone or update the repository
# =============================================================================
header "Installing Nebulae"

if [[ -d "${INSTALL_DIR}/.git" ]]; then
    warn "${INSTALL_DIR} already exists and contains a git repo."
    warn "Running 'git pull' to update instead of a fresh clone."
    sudo -u "$SERVICE_USER" git -C "$INSTALL_DIR" pull
else
    [[ -d "$INSTALL_DIR" ]] && die "${INSTALL_DIR} already exists but is not a git repo. Remove it first."
    info "Cloning Nebulae into ${INSTALL_DIR}..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "$INSTALL_DIR"
fi

success "Repository ready at ${INSTALL_DIR}."

# =============================================================================
# 4. Python virtual environment and dependencies
# =============================================================================
header "Setting up Python environment"

VENV_DIR="${INSTALL_DIR}/venv"
PYTHON_BIN=$(command -v python3)

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtualenv at ${VENV_DIR}..."
    sudo -u "$SERVICE_USER" "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

info "Upgrading pip..."
sudo -u "$SERVICE_USER" "${VENV_DIR}/bin/pip" install --quiet --upgrade pip

info "Installing Python dependencies (this may take a few minutes)..."
sudo -u "$SERVICE_USER" "${VENV_DIR}/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"

success "Python environment ready."

# =============================================================================
# 5. Create writable runtime directories
# =============================================================================
header "Creating runtime directories"

# These mirror the paths in app.py (the env vars below will override the Docker
# defaults, pointing to directories the nebulae user can actually write to).
INSTANCE_DIR="${INSTALL_DIR}/instance"
PROFILE_PIC_DIR="${INSTALL_DIR}/instance/profile_pictures_storage"
THUMBNAILS_DIR="${INSTALL_DIR}/instance/thumbnails"
BACKUPS_DIR="${INSTALL_DIR}/instance/backups"

for d in "$INSTANCE_DIR" "$PROFILE_PIC_DIR" "$THUMBNAILS_DIR" "$BACKUPS_DIR"; do
    mkdir -p "$d"
done
chown -R "${SERVICE_USER}:${SERVICE_USER}" "$INSTANCE_DIR"

success "Runtime directories created."

# =============================================================================
# 6. Configuration
# =============================================================================
header "Configuration"

mkdir -p "$ENV_DIR"
chmod 750 "$ENV_DIR"

# --- Prompt for NODE_HOSTNAME ------------------------------------------------
echo ""
echo -e "${BOLD}What is the public hostname for this Nebulae node?${RESET}"
echo "  e.g. nebulae.example.com or mynode.duckdns.org"
echo "  (Do NOT include http:// or https://)"
echo ""
read -rp "NODE_HOSTNAME: " NODE_HOSTNAME

[[ -z "$NODE_HOSTNAME" ]] && die "NODE_HOSTNAME cannot be empty."
# Basic sanity check — reject anything with a protocol prefix
[[ "$NODE_HOSTNAME" == http* ]] && die "NODE_HOSTNAME should be a bare hostname, not a URL."

# --- Generate SECRET_KEY -----------------------------------------------------
SECRET_KEY=$("${VENV_DIR}/bin/python" -c "import secrets; print(secrets.token_hex(32))")
info "Generated SECRET_KEY."

# --- Write env file ----------------------------------------------------------
if [[ -f "$ENV_FILE" ]]; then
    warn "${ENV_FILE} already exists. Backing up to ${ENV_FILE}.bak"
    cp "$ENV_FILE" "${ENV_FILE}.bak"
fi

cat > "$ENV_FILE" <<EOF
# Nebulae configuration - generated by install-nebulae.sh
# Keep this file private: chmod 600 ${ENV_FILE}

# ---- Required ---------------------------------------------------------------
SECRET_KEY=${SECRET_KEY}
NODE_HOSTNAME=${NODE_HOSTNAME}
FLASK_ENV=production
FEDERATION_INSECURE_MODE=False

# ---- Media paths (native install) -------------------------------------------
# These override the Docker-style /app/* defaults in app.py
PROFILE_PICTURE_STORAGE_DIR=${PROFILE_PIC_DIR}
THUMBNAIL_CACHE_DIR=${THUMBNAILS_DIR}

# ---- Optional: point at existing photo libraries ----------------------------
# Uncomment and set to let users browse existing photos from the host filesystem.
# These are READ-ONLY directories. Add per-user entries in the admin panel after
# first login (Admin → Manage Users → Actions → Set Media Path).
#
# USER_MEDIA_BASE_DIR=/home/yourname/Pictures
# USER_UPLOADS_BASE_DIR=/home/yourname/Pictures/uploads
EOF

chmod 600 "$ENV_FILE"
success "Configuration written to ${ENV_FILE}."

# =============================================================================
# 7. systemd service
# =============================================================================
header "Installing systemd service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Nebulae Social Platform
Documentation=https://locqust.github.io/Nebulae/
After=network.target

[Service]
User=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${VENV_DIR}/bin/gunicorn \\
    --bind 127.0.0.1:5000 \\
    --worker-class gthread \\
    --workers ${GUNICORN_WORKERS} \\
    --threads ${GUNICORN_THREADS} \\
    --timeout 120 \\
    --access-logfile - \\
    --error-logfile - \\
    "app:app"
Restart=always
RestartSec=5
# Give gunicorn time to finish in-flight requests on stop
TimeoutStopSec=30

# Basic hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nebulae
systemctl start nebulae

# Brief wait for startup
sleep 3

if systemctl is-active --quiet nebulae; then
    success "Nebulae service started successfully."
else
    error "Nebulae service failed to start. Check logs with: sudo journalctl -u nebulae -n 50"
    echo ""
    systemctl status nebulae --no-pager || true
    exit 1
fi

# =============================================================================
# 8. Optional Nginx configuration
# =============================================================================
header "Nginx configuration"

echo ""
echo -e "${BOLD}Would you like to set up a basic Nginx reverse proxy for Nebulae?${RESET}"
echo "  This creates a site config at ${NGINX_CONF}."
echo "  It serves HTTP on port 80 — you should add HTTPS via Certbot afterwards."
echo ""
read -rp "Configure Nginx? [Y/n]: " NGINX_CHOICE
NGINX_CHOICE="${NGINX_CHOICE:-Y}"

if [[ "${NGINX_CHOICE^^}" == "Y" ]]; then
    # Check nginx is available
    if ! command -v nginx >/dev/null 2>&1; then
        warn "nginx not found, skipping Nginx configuration."
    else
        cat > "$NGINX_CONF" <<EOF
# Nebulae reverse proxy - generated by install-nebulae.sh
server {
    listen 80;
    server_name ${NODE_HOSTNAME};

    # Increase upload size for media files
    client_max_body_size 500M;

    # Match the Gunicorn timeout
    proxy_read_timeout    300s;
    proxy_connect_timeout 300s;
    proxy_send_timeout    300s;

    location / {
        proxy_pass         http://127.0.0.1:5000;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;

        # WebSocket support (for future use)
        proxy_http_version 1.1;
        proxy_set_header   Upgrade    \$http_upgrade;
        proxy_set_header   Connection "upgrade";
    }
}
EOF
        # Enable the site (Debian/Ubuntu style)
        if [[ -d /etc/nginx/sites-enabled ]]; then
            ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/nebulae 2>/dev/null || true
            # Remove default site if it's there (conflicts on port 80)
            [[ -L /etc/nginx/sites-enabled/default ]] && rm -f /etc/nginx/sites-enabled/default && warn "Removed default Nginx site (was conflicting on port 80)."
        fi

        if nginx -t 2>/dev/null; then
            systemctl reload nginx
            success "Nginx configured and reloaded."
        else
            warn "Nginx config test failed. Check ${NGINX_CONF} manually."
            nginx -t
        fi

        echo ""
        info "To add HTTPS (required for federation), run:"
        echo -e "  ${BOLD}sudo apt install certbot python3-certbot-nginx${RESET}   # Debian/Ubuntu"
        echo -e "  ${BOLD}sudo certbot --nginx -d ${NODE_HOSTNAME}${RESET}"
    fi
else
    info "Skipping Nginx configuration."
fi

# =============================================================================
# 9. Summary
# =============================================================================
header "Installation complete"

echo -e "
${GREEN}${BOLD}Nebulae is running!${RESET}

  ${BOLD}Access:${RESET}        http://${NODE_HOSTNAME}  (add HTTPS with Certbot)
  ${BOLD}Local test:${RESET}    curl http://127.0.0.1:5000

  ${BOLD}Default login:${RESET}
    Username: admin
    Password: adminpassword
  ${YELLOW}${BOLD}Change this immediately after first login.${RESET}

  ${BOLD}Configuration:${RESET} ${ENV_FILE}
  ${BOLD}App directory:${RESET} ${INSTALL_DIR}
  ${BOLD}Logs:${RESET}          sudo journalctl -u nebulae -f

  ${BOLD}Useful commands:${RESET}
    sudo systemctl status nebulae
    sudo systemctl restart nebulae
    sudo journalctl -u nebulae -f

  ${BOLD}To update Nebulae later:${RESET}
    cd ${INSTALL_DIR}
    sudo -u ${SERVICE_USER} git pull
    sudo -u ${SERVICE_USER} ${VENV_DIR}/bin/pip install -r requirements.txt
    sudo systemctl restart nebulae

  ${BOLD}Post-install guide:${RESET}
    https://locqust.github.io/Nebulae/admin-guide/post-install/
"
