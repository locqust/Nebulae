# Linux (Native Install)

This guide walks through running Nebulae directly on a Linux server or desktop — no Docker required. The result is a production-quality deployment using Gunicorn behind Nginx, managed by systemd.

!!! note "Supported distributions"
    These instructions are written for **Ubuntu / Debian** and derivatives (including Linux Mint and Raspberry Pi OS). For RHEL, Fedora, or Arch, the process is identical but package names differ — see the [distro notes](#other-distributions) at the bottom.

---

## Quick Install (Debian / Ubuntu)

The fastest path is the install script. It handles everything below automatically.

```bash
curl -fsSL https://raw.githubusercontent.com/locqust/Nebulae/main/scripts/install-nebulae.sh -o install-nebulae.sh
# Review it before running (recommended)
less install-nebulae.sh
# Then run it
sudo bash install-nebulae.sh
```

The script will prompt you for your `NODE_HOSTNAME` and generate a `SECRET_KEY` for you. Everything else is automated.

If you prefer to know exactly what's happening, or want to customise the install, follow the manual steps below.

---

## Manual Install

### 1. System Dependencies

```bash
sudo apt update
sudo apt install -y \
    python3 python3-pip python3-venv python3-dev \
    sqlite3 \
    libffi-dev libssl-dev libjpeg-dev \
    git \
    nginx
```

!!! info "Why these packages?"
    - `python3-dev`, `libffi-dev`, `libssl-dev` — needed to compile the `cryptography` package (used by Web Push / VAPID)
    - `libjpeg-dev` — needed by Pillow for image processing
    - `nginx` — reverse proxy that sits in front of Gunicorn

### 2. Create a Dedicated User

Running Nebulae as its own unprivileged user is a security best practice. It keeps the application isolated from the rest of your system.

```bash
sudo useradd -r -s /bin/false -d /opt/nebulae nebulae
```

### 3. Clone the Repository

```bash
sudo git clone https://github.com/locqust/Nebulae.git /opt/nebulae
sudo chown -R nebulae:nebulae /opt/nebulae
```

### 4. Create a Virtual Environment and Install Dependencies

```bash
sudo -u nebulae python3 -m venv /opt/nebulae/venv
sudo -u nebulae /opt/nebulae/venv/bin/pip install --upgrade pip
sudo -u nebulae /opt/nebulae/venv/bin/pip install -r /opt/nebulae/requirements.txt
```

### 5. Create Required Directories

```bash
sudo -u nebulae mkdir -p \
    /opt/nebulae/instance \
    /opt/nebulae/instance/backups
```

!!! tip "Media directories"
    If you want to point Nebulae at existing photo libraries on your system, create those directories now too and note their paths — you'll configure them in the environment file next.

### 6. Configure the Environment

Create the configuration directory and file:

```bash
sudo mkdir -p /etc/nebulae
sudo nano /etc/nebulae/nebulae.env
```

Paste in the following, replacing the values for your setup:

```bash
# Required
SECRET_KEY=your_long_random_secret_key_here
NODE_HOSTNAME=nebulae.yourdomain.com
FLASK_ENV=production
FEDERATION_INSECURE_MODE=False

# Optional — override default media paths if needed
# USER_MEDIA_BASE_DIR=/home/yourname/Pictures
# USER_UPLOADS_BASE_DIR=/home/yourname/Pictures/uploads
# PROFILE_PICTURE_STORAGE_DIR=/opt/nebulae/instance/profile_pictures
# THUMBNAIL_CACHE_DIR=/opt/nebulae/instance/thumbnails
```

Generate a secure `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Lock down the file so only root can read it:

```bash
sudo chmod 600 /etc/nebulae/nebulae.env
```

!!! warning "Keep your SECRET_KEY safe"
    This key signs user sessions. If you change it, all users will be logged out. If you lose it, you'll need to regenerate it and accept that outcome.

### 7. Create the systemd Service

```bash
sudo nano /etc/systemd/system/nebulae.service
```

```ini
[Unit]
Description=Nebulae Social Platform
After=network.target

[Service]
User=nebulae
WorkingDirectory=/opt/nebulae
EnvironmentFile=/etc/nebulae/nebulae.env
ExecStart=/opt/nebulae/venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --worker-class gthread \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    "app:app"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable nebulae
sudo systemctl start nebulae
```

Verify it's running:

```bash
sudo systemctl status nebulae
```

You should see `Active: active (running)`. If not, check the logs:

```bash
sudo journalctl -u nebulae -f
```

### 8. Configure Nginx

Create an Nginx site configuration:

```bash
sudo nano /etc/nginx/sites-available/nebulae
```

```nginx
server {
    listen 80;
    server_name nebulae.yourdomain.com;

    # Increase max upload size for media files
    client_max_body_size 500M;

    # Extend timeouts for large uploads and long-running requests
    proxy_read_timeout 300s;
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/nebulae /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 9. Set Up HTTPS with Certbot

Federation requires HTTPS. Install Certbot and get a certificate:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d nebulae.yourdomain.com
```

Certbot will automatically update your Nginx config to handle HTTPS and redirect HTTP traffic. Certificates renew automatically.

---

## Verify the Installation

Open a browser and navigate to `https://nebulae.yourdomain.com`. You should see the Nebulae login page.

Default admin credentials:

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `adminpassword` |

!!! danger "Change this immediately"
    You will be prompted to change the admin password on first login. Do not skip this step.

Once you're in, head to the [Post-Install Setup](../admin-guide/post-install.md) guide.

---

## Updating Nebulae

```bash
cd /opt/nebulae
sudo -u nebulae git pull
sudo -u nebulae /opt/nebulae/venv/bin/pip install -r requirements.txt
sudo systemctl restart nebulae
```

---

## Useful Commands

| Task | Command |
|------|---------|
| Start | `sudo systemctl start nebulae` |
| Stop | `sudo systemctl stop nebulae` |
| Restart | `sudo systemctl restart nebulae` |
| View logs | `sudo journalctl -u nebulae -f` |
| Check status | `sudo systemctl status nebulae` |

---

## Other Distributions

The steps above work on any Linux distribution — only the package manager and package names differ.

=== "RHEL / Fedora / CentOS"

    ```bash
    sudo dnf install -y \
        python3 python3-pip python3-devel \
        sqlite \
        libffi-devel openssl-devel libjpeg-turbo-devel \
        git nginx
    ```

    Use `sudo systemctl enable --now nginx` and `sudo firewall-cmd --permanent --add-service=https && sudo firewall-cmd --reload` to open the firewall.

=== "Arch Linux"

    ```bash
    sudo pacman -S python python-pip sqlite libffi libjpeg-turbo git nginx certbot certbot-nginx
    ```

=== "openSUSE"

    ```bash
    sudo zypper install python3 python3-pip python3-devel sqlite3 libffi-devel libopenssl-devel libjpeg-devel git nginx
    ```

---

## Troubleshooting

**Nebulae won't start — `journalctl` shows a permission error**

Check that `/opt/nebulae` and its subdirectories are owned by the `nebulae` user:

```bash
sudo chown -R nebulae:nebulae /opt/nebulae
```

**Nebulae starts but shows a 502 Bad Gateway in the browser**

Gunicorn isn't running or isn't listening on port 5000. Check:

```bash
sudo systemctl status nebulae
sudo ss -tlnp | grep 5000
```

**`pip install` fails on `cryptography`**

Make sure the build dependencies are installed:

```bash
sudo apt install -y libffi-dev libssl-dev python3-dev
```

**Media files aren't showing up in the gallery**

Check that `USER_MEDIA_BASE_DIR` in `/etc/nebulae/nebulae.env` points to the correct path, and that the `nebulae` user can read it:

```bash
sudo -u nebulae ls /path/to/your/media
```

If you get `Permission denied`, either add the `nebulae` user to the appropriate group or adjust directory permissions.
