# Installation Guide

This guide will walk you through installing Nebulae using Docker, the recommended deployment method.

---

## Prerequisites

Before you begin, ensure you have:

- **Docker** and **Docker Compose** installed
- A **domain name** or **static IP address** (for federation)
- Basic command-line knowledge
- At least **2GB RAM** and **10GB disk space**
- (Optional) Existing photo libraries you want to link

---

## Installation Methods

### Docker (Recommended)

Docker provides the easiest and most reliable way to deploy Nebulae. This guide focuses on Docker deployment.

### Manual Installation

While possible, manual installation is not recommended for production use. See [Advanced Installation](installation-advanced.md) for details.

---

## Quick Start (5 Minutes)

### Step 1: Download Configuration Files

```bash
wget https://raw.githubusercontent.com/locqust/Nebulae/main/docker-compose.yml
```
Or manually copy from the repo.

### Step 2: Generate Secret Key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Or just generate a random key by typing! Alternatively use a site like https://codebeautify.org/generate-random-hexadecimal-numbers
Copy the output — you'll need it in the next step.

### Step 3: Configure settings in docker-compose.yml

Edit the `docker-compose.yml` file:

```bash
nano docker-compose.yml
```
(Windows - just use text editor like notepad++)

Set the required values:

```
volumes:
      # Persistent database storage
      - nebulae_data:/app/instance
      # Optional: Backup location (users can customize)
      - ./backups:/app/instance/backups
      # Profile pictures storage
      - profile_pictures:/app/profile_pictures_storage
      # Thumbnail cache
      - thumbnail_cache:/app/thumbnails
      # User media volumes - USERS MUST CONFIGURE THESE - one each per user
      # Example format (commented out by default):
      # - /path/to/user/photos:/app/user_media/username_media:ro
      # - C:\Users\User\Photos:/app/user_media/username_media:ro
      # - /path/to/user/uploads:/app/user_uploads/username_uploads
      # - C:\Users\User\Documents\Uploads:/app/user_uploads/username_uploads

environment:
      # REQUIRED: Generate with: python -c "import secrets; print(secrets.token_hex(32))"
      - SECRET_KEY=CHANGE_ME_GENERATE_A_SECRET_KEY
      # REQUIRED: Your public hostname/IP (e.g., nebulae.example.com)
      - NODE_HOSTNAME=CHANGE_ME_TO_YOUR_HOSTNAME
      # Optional: Set to True only for testing without HTTPS
      - FEDERATION_INSECURE_MODE=False

```

**Important Settings:**
- `SECRET_KEY`: The key you generated in Step 2
- `NODE_HOSTNAME`: Your public domain name or IP address
- `FEDERATION_INSECURE_MODE`: Set to `False` for production (HTTPS required)

### Step 4: Linking Existing Media Libraries

If you want users to access existing photo libraries without uploading them:

Add volume mounts for each user:

```yaml
volumes:
  # Existing volumes...
  - /path/to/photos:/app/user_media/username_media:ro
  - /path/to/uploads:/app/user_uploads/username_uploads
```

**Linux Example:**
```yaml
- /home/bob/Photos:/app/user_media/bob_media:ro
- /home/bob/Uploads:/app/user_uploads/bob_uploads
```

And if you want to add folders where users can upload photos from their devices for posts:
 
**Windows Example:**
```yaml
- C:\Users\Bob\Pictures:/app/user_media/bob_media:ro
- C:\Users\Bob\Uploads:/app/user_uploads/bob_uploads
```


- **Read-only (`:ro`)** - For browsing existing photos
- **Writable (no `:ro`)** - For new uploads from Nebulae

### Step 5: Start Nebulae

```bash
docker-compose pull
docker-compose up -d
```

This will:
- Pull the Nebulae Docker image
- Create necessary volumes
- Start the application

### Step 6: Access Your Node

Open your browser and navigate to:
```
http://<your-server-ip>:5000
```

**Default admin credentials:**
- Username: `admin`
- Password: `adminpassword`

⚠️ **You will be required to change this password on first login!**

### Step 7: Configure users and user volumes in Admin Panel

After starting Nebulae:
1. Log in as admin
2. Go to **Admin Panel → Manage Users**
3. Click on **Add New User***
4. Enter a Username, this will usually be the user email address
5. Set a password, users can change this once they have logged in
6. Enter their Display name, this is their actual name - they can change this afterwards
7. Enter their Date of Birth, this is important for users under 16 so that parental permissions can be applied. **THIS CANNOT BE ALTERED ONCE SET**
8. Click **Add User**
9. Back on the user dashboard
10. Click **Actions → Set Media Path** for each user
11. Enter the container paths:
   - Read-only: `/app/user_media/username_media`
   - Uploads: `/app/user_uploads/username_uploads`


---

## Detailed Installation

### Environment Variables Explained

#### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `SECRET_KEY` | Cryptographic key for session security | `a1b2c3d4...` |
| `NODE_HOSTNAME` | Your public hostname/domain | `nebulae.example.com` |

#### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `FEDERATION_INSECURE_MODE` | Allow HTTP federation (testing only) | `False` |
| `FLASK_ENV` | Environment mode | `production` |
| `DATABASE_PATH` | SQLite database location | `/app/instance/nebulae.db` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |

### Docker Compose Configuration

The provided `docker-compose.yml` defines:

```yaml
version: '3.8'

services:
  web:
    image: ghcr.io/locqust/nebulae:latest 
    container_name: nebulae
    ports:
      - "5000:5000"
    volumes:
      # Persistent database storage
      - nebulae_data:/app/instance
      # Optional: Backup location (users can customize)
      - ./backups:/app/instance/backups
      # Profile pictures storage
      - profile_pictures:/app/profile_pictures_storage
      # Thumbnail cache
      - thumbnail_cache:/app/thumbnails
      # User media volumes - USERS MUST CONFIGURE THESE - one each per user
      # Example format (commented out by default):
      # - /path/to/user/photos:/app/user_media/username_media:ro
      # - C:\Users\User\Photos:/app/user_media/username_media:ro
      # - /path/to/user/uploads:/app/user_uploads/username_uploads
      # - C:\Users\User\Documents\Uploads:/app/user_uploads/username_uploads

    environment:
      # REQUIRED: Generate with: python -c "import secrets; print(secrets.token_hex(32))"
      - SECRET_KEY=CHANGE_ME_GENERATE_A_SECRET_KEY
      # REQUIRED: Your public hostname/IP (e.g., nebulae.example.com)
      - NODE_HOSTNAME=CHANGE_ME_TO_YOUR_HOSTNAME
      # Optional: Set to True only for testing without HTTPS
      - FEDERATION_INSECURE_MODE=False
      # Optional: Set to production
      - FLASK_ENV=production
    restart: unless-stopped
    command: gunicorn --bind 0.0.0.0:5000 --workers 4 --threads 2 --timeout 120 --access-logfile - --error-logfile - "app:app"

volumes:
  nebulae_data:
  profile_pictures:
  thumbnail_cache:
```

---

## Verifying Installation

### Check Logs

```bash
docker-compose logs -f
```

You should see:
```
[INFO] Starting gunicorn 20.1.0
[INFO] Listening at: http://0.0.0.0:5000
[INFO] Using worker: sync
[INFO] Booting worker with pid: ...
```

### Check Container Status

```bash
docker-compose ps
```

Should show:
```
NAME       STATUS    PORTS
nebulae    Up        0.0.0.0:5000->5000/tcp
```

### Access the Web Interface

Navigate to `http://<server-ip>:5000` and verify you see the login page.

---

## Post-Installation Steps

After installation, you should:

1. **[Change Admin Password](configuration.md#changing-admin-password)**
2. **[Configure Email Settings](configuration.md#email-configuration)**
3. **[Add Users](user-management.md#adding-users)**
4. **[Set Up Federation](federation-setup.md)** (optional)
5. **[Configure Backups](backups-updates.md#setting-up-backups)**

---

## Production Deployment

For production use, you should also:

### 1. Set Up Reverse Proxy

Use nginx or Caddy to:
- Handle HTTPS/SSL certificates
- Provide domain name routing
- Add security headers

See [Reverse Proxy Setup](reverse-proxy.md) for details.

### 2. Configure Firewall

```bash
# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Block direct access to port 5000
sudo ufw deny 5000/tcp
```

### 3. Set Up Automated Backups

Configure scheduled database backups in the admin panel.

### 4. Monitor Resources

Keep an eye on:
- Disk space (media files can grow)
- Database size
- Memory usage
- CPU load

---

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker-compose logs
```

Common issues:
- Port 5000 already in use, change the port mapping in the docker-compose.yml file to a different port, ie `5001:5000`
- Invalid environment variables
- Permission issues with volumes

### Can't Access Web Interface

1. Check firewall settings
2. Verify container is running: `docker-compose ps`
3. Check if port 5000 is accessible: `curl http://localhost:5000`

### Database Errors

The database initializes automatically on first run. If you see database errors:

1. Stop the container: `docker-compose down`
2. Remove the database volume: `docker volume rm nebulae_nebulae_data`
3. Restart: `docker-compose up -d`

⚠️ **This will erase all data!**

---

## Upgrading

To upgrade to the latest version:

```bash
docker-compose down
docker-compose pull
docker-compose up -d
```

Your data is preserved in Docker volumes.

---

## Next Steps

- **[Configuration Guide](configuration.md)** - Configure email, notifications, and more
- **[User Management](user-management.md)** - Add and manage users
- **[Federation Setup](federation-setup.md)** - Connect with other nodes

---

[← Back to Admin Guide](../index.md) | [Configuration →](configuration.md)
