# Docker / Podman

Nebulae ships pre-built container images for `linux/amd64` and `linux/arm64` (Pi 4/5 compatible) hosted on the GitHub Container Registry.

This is the recommended install method for:

- Anyone already running Docker or Portainer
- NAS devices (Synology, TrueNAS SCALE, Unraid)
- Cloud VMs
- Windows and macOS users

---

## Quick Start

### 1. Download the Compose File

```bash
wget https://raw.githubusercontent.com/locqust/Nebulae/main/docker-compose.yml
```

### 2. Generate a Secret Key

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Edit `docker-compose.yml`

Open the file and set the required environment variables:

```yaml
environment:
  - SECRET_KEY=paste_your_generated_key_here
  - NODE_HOSTNAME=nebulae.yourdomain.com
  - FEDERATION_INSECURE_MODE=False
  - FLASK_ENV=production
```

### 4. Start Nebulae

```bash
docker compose pull
docker compose up -d
```

### 5. First Login

Navigate to `http://YOUR_SERVER_IP:5000` (or your domain if you've set up a reverse proxy).

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | `adminpassword` |

!!! danger "Change this immediately"
    You will be prompted to change the admin password on first login. Do not skip this step.

---

## Connecting Photo Libraries

Nebulae can serve photos from existing directories on your host machine. Users browse their libraries inside the app without Nebulae ever copying or modifying the originals.

Add volume mounts to `docker-compose.yml` for each user:

```yaml
volumes:
  - nebulae_data:/app/instance
  - ./backups:/app/instance/backups
  - profile_pictures:/app/profile_pictures_storage
  - thumbnail_cache:/app/thumbnails

  # Read-only: existing photo library (Nebulae can browse but not modify)
  - /home/alice/Pictures:/app/user_media/alice_media:ro

  # Writable: where new uploads from the app are saved
  - /home/alice/Pictures/uploads:/app/user_uploads/alice_uploads
```

After adding volumes, configure the paths in the admin panel under **Manage Users → Actions → Set Media Path**.

!!! info "Path format in the admin panel"
    Enter the *container* path (e.g. `/app/user_media/alice_media`), not the host path. The host path is only relevant in `docker-compose.yml`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | ✅ | Signs user sessions. Use a long random string. Changing this logs everyone out. |
| `NODE_HOSTNAME` | ✅ | Your public hostname or IP (e.g. `nebulae.example.com`). Used in federation. |
| `FLASK_ENV` | ✅ | Set to `production`. Use `development` only for local dev work. |
| `FEDERATION_INSECURE_MODE` | ✅ | Set to `False` for HTTPS (production). `True` allows HTTP — local dev only. |
| `USER_MEDIA_BASE_DIR` | — | Override the container path where read-only media is mounted. Default: `/app/user_media` |
| `USER_UPLOADS_BASE_DIR` | — | Override the container path for writable uploads. Default: `/app/user_uploads` |

---

## Using a Reverse Proxy

For HTTPS (required for federation) the recommended approach is [Nginx Proxy Manager](https://nginxproxymanager.com/). It handles Let's Encrypt certificate issuance and renewal through a web UI.

When using a reverse proxy, change `ports` to `expose` in `docker-compose.yml` so Nebulae isn't directly accessible on the public network:

```yaml
services:
  web:
    expose:
      - "5000"
    networks:
      - nebulae_network

networks:
  nebulae_network:
    driver: bridge
```

Point Nginx Proxy Manager at `http://nebulae:5000` (using the container name as hostname if they're on the same Docker network).

!!! tip "Port 443 only"
    Home users only need to forward port **443** at their router. NPM handles HTTP→HTTPS redirects internally.

---

## Portainer

If you manage containers through Portainer:

1. Go to **Stacks → Add Stack**
2. Set the stack name to `nebulae`
3. Paste the contents of your edited `docker-compose.yml` into the web editor
4. Click **Deploy the stack**

---

## Podman

Podman is compatible with the Docker Compose file with minor adjustments:

```bash
pip3 install podman-compose
podman-compose up -d
```

If you encounter SELinux permission errors on volume mounts:

```bash
sudo chcon -Rt svirt_sandbox_file_t /path/to/media
```

---

## Kubernetes

A `kubernetes-manifest.yaml` is provided in the repository for Kubernetes deployments. Edit the `ConfigMap` section to set your environment variables, then:

```bash
kubectl apply -f kubernetes-manifest.yaml
```

---

## Updating

```bash
docker compose pull
docker compose up -d
```

Nebulae applies database migrations automatically on startup. No manual migration step is needed.

---

## Useful Commands

| Task | Command |
|------|---------|
| View logs | `docker compose logs -f` |
| Restart | `docker compose restart` |
| Stop | `docker compose down` |
| Shell access | `docker compose exec web bash` |
| Check status | `docker compose ps` |

!!! warning "Removing volumes"
    `docker compose down -v` removes named volumes including the database. Only use this if you want to start completely fresh.

---

## Troubleshooting

**Port 5000 already in use**

Either stop the conflicting service or change the port mapping in `docker-compose.yml`:

```yaml
ports:
  - "5001:5000"   # External:Internal
```

**Permission denied on volume mounts (Linux)**

```bash
sudo chown -R $USER:$USER /path/to/media
```

**Media not appearing in gallery**

- Verify the host path in `docker-compose.yml` exists and contains files
- Verify the container path entered in the admin panel matches the right-hand side of the volume mount
- Check for typos — paths are case-sensitive
- Restart the container and check logs for errors

**Federation not working**

- Verify `NODE_HOSTNAME` matches your public domain exactly (no trailing slash, no `http://`)
- Verify `FEDERATION_INSECURE_MODE=False` and that HTTPS is configured
- Check that port 443 is accessible from the internet: `curl https://nebulae.yourdomain.com`

**SSL certificate errors**

- Ensure your domain resolves to your public IP before requesting a certificate
- If using Nginx Proxy Manager, check NPM logs for Let's Encrypt errors
- Let's Encrypt has a rate limit of 5 certificates per domain per week — if you've hit it, wait before retrying
