# Quick Start

Get Nebulae up and running in 5 minutes with this streamlined guide.

---

## Prerequisites Check

Before starting, verify you have:

```bash
# Check Docker
docker --version
# Should show: Docker version 20.x.x or higher

# Check Docker Compose
docker-compose --version
# Should show: docker-compose version 1.29.x or higher
```

If you don't have Docker, install it from [docker.com](https://docs.docker.com/get-docker/).

---

## 5-Minute Deployment

### Step 1: Download Configuration (30 seconds)

```bash
# Download docker-compose.yml
wget https://raw.githubusercontent.com/locqust/Nebulae/main/docker-compose.yml
```

### Step 2: Generate Secret Key (15 seconds)

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Or just generate a random string by mashing the keyboard. Or visit somewhere like https://codebeautify.org/generate-random-hexadecimal-numbers

Copy the output - you'll need it in the next step.

### Step 3: Configure Environment (1 minute)

Edit the `docker-compose.yml` file:

```bash
nano docker-compose.yml
```
(Windows - just use a text editor like notepad++)

Update these two **required** values:

```    environment:
      - SECRET_KEY=CHANGE_ME_GENERATE_A_SECRET_KEY
      - NODE_HOSTNAME=CHANGE_ME_TO_YOUR_HOSTNAME
```

**Important:** 
- `SECRET_KEY`: Paste the key from Step 2
- `NODE_HOSTNAME`: Use your actual domain name or IP address

Save and exit (Ctrl+X, Y, Enter in nano).

### Step 4: Start Nebulae (2 minutes)

```bash
docker-compose pull
docker-compose up -d
```

This will:
- Download the Nebulae Docker image (~200MB)
- Create necessary volumes
- Initialize the database
- Start the application

Wait for the download to complete...

### Step 5: Access Nebulae (30 seconds)

Open your browser and navigate to:

```
http://YOUR_SERVER_IP:5000
```

You should see the Nebulae login page!

**Default credentials:**
- Username: `admin`
- Password: `adminpassword`

⚠️ **You will be forced to change this password on first login!**

---

## First Login Checklist

After logging in for the first time:

### ✅ Step 1: Change Admin Password

You'll be prompted immediately. Choose a strong password.

### ✅ Step 2: Add Your First User

1. Go to **Admin Panel → Manage Users**
2. Click **Add New User**
3. Fill in:
   - Username (email address)
   - Password
   - Display name
   - Date of birth
4. Click **Add User**

### ✅ Step 3: Configure Email (Optional but Recommended)

1. Go to **Admin Panel → Settings**
2. Find **Email Configuration**
3. Enter your SMTP details:
   - SMTP Server (e.g., smtp.gmail.com)
   - Port (usually 587)
   - Username & Password
4. Click **Test Email Settings and Save**

### ✅ Step 4: Create Your First Group (Optional)

1. Go to **Admin Panel → Manage Groups**
2. Click **Create New Group**
3. Name it and add a description
4. Assign yourself as admin
5. Click **Create Group**

---

## What's Next?

### For Administrators

- **[Full Installation Guide](../admin-guide/installation.md)** - Detailed setup
- **[User Management](../admin-guide/user-management.md)** - Add and manage users
- **[Federation Setup](../admin-guide/federation-setup.md)** - Connect with other nodes
- **[Backups](../admin-guide/backups-updates.md)** - Set up automated backups

### For Users

- **[User Guide](../user-guide/getting-started.md)** - Learn to use Nebulae
- **[Creating Posts](../user-guide/creating-posts.md)** - Post content
- **[Groups](../user-guide/groups.md)** - Join communities

---

## Production Deployment

This quick start gets you running, but for production you should also:

### 1. Set Up HTTPS

Use a reverse proxy (nginx or Caddy) with SSL certificates:

```bash
# Example with Caddy
Caddyfile:
nebulae.example.com {
    reverse_proxy localhost:5000
}
```

### 2. Configure Firewall

```bash
# Allow HTTPS
sudo ufw allow 443/tcp

# Allow HTTP (for SSL certificate challenges)
sudo ufw allow 80/tcp

# Block direct access to port 5000
sudo ufw deny 5000/tcp
```

### 3. Set Up Backups

In the admin panel:
1. Go to **Database Backups**
2. Enable scheduled backups
3. Set frequency (daily recommended)
4. Run a test backup

### 4. Add Media Paths (Recommended)

To let users browse existing photos or upload new ones, add volume mounts in `docker-compose.yml, one set per user:

```yaml
volumes:
  - /path/to/photos:/app/user_media/username_media:ro
  - /path/to/uploads:/app/user_uploads/username_uploads
```

Then restart:
```bash
docker-compose down
docker-compose up -d
```

Apply the newly mapped volumes to the user(s) in the **Admin Dashboard > Manage Users**

---

## Verification Checklist

Ensure everything is working:

- ✅ Can access Nebulae at your domain/IP
- ✅ Can log in with admin credentials
- ✅ Changed default admin password
- ✅ Created at least one regular user
- ✅ That user can log in and see feed
- ✅ Can create posts
- ✅ Notifications appear
- ✅ (Optional) Email notifications working

---

## Troubleshooting Quick Fixes

### Can't Access on Port 5000

Check if the container is running:
```bash
docker-compose ps
```

Should show:
```
NAME       STATUS    PORTS
nebulae    Up        0.0.0.0:5000->5000/tcp
```

### Container Won't Start

Check logs:
```bash
docker-compose logs
```

Common issues:
- Port 5000 already in use
- Missing `environment` settings in `docker-compose.yml` file
- Invalid SECRET_KEY

### Forgot Admin Password

Reset it via database:
```bash
docker exec -it nebulae python3 << EOF
from db_utils import get_db
from werkzeug.security import generate_password_hash
db = get_db()
db.execute("UPDATE users SET password = ? WHERE username = 'admin'",
           (generate_password_hash('newpassword'),))
db.commit()
EOF
```

---

## Common Next Steps

After quick start, most admins:

1. **Add domain name** to `NODE_HOSTNAME` in `docker-compose.yml`
2. **Set up HTTPS** with reverse proxy
3. **Configure email** for notifications
4. **Add users** for friends/family
5. **Create groups** for communities
6. **Set up federation** to connect with other nodes

---

## Resources

- **Full Documentation**: [index.md](../index.md)
- **GitHub Repository**: https://github.com/locqust/Nebulae
- **Discord**: Coming soon!
- **Issues**: https://github.com/locqust/Nebulae/issues

---

## Docker Compose Quick Reference

```bash
# Start Nebulae
docker-compose up -d

# Stop Nebulae
docker-compose down

# View logs
docker-compose logs -f

# Restart Nebulae
docker-compose restart

# Update to latest version
docker-compose pull
docker-compose up -d

# Access database
docker exec -it nebulae sqlite3 /app/instance/nebulae.db
```

---

**Congratulations! You've deployed Nebulae! 🎉**

Now explore the [full documentation](../index.md) to learn about all the features.

---

[← Architecture](architecture.md) | [Admin Guide →](../admin-guide/installation.md)
