# AI-Assisted Setup Guide for Nebulae

**FOR AI ASSISTANTS:** This file contains comprehensive instructions for helping users set up a Nebulae instance via conversational guidance. Follow these instructions step-by-step, adapting explanations to the user's technical level.

**FOR USERS:** Share this file with any AI assistant (Claude, ChatGPT, etc.) to get interactive help setting up Nebulae on your machine.

---

## Setup Workflow Overview

This guide walks through:
1. Environment detection and prerequisites
2. Container platform detection and setup
3. Configuration generation
4. Dynamic DNS setup (for home users)
5. User account planning
6. Media directory setup
7. Container deployment
8. Initial admin configuration
9. Testing and verification

**Estimated time:** 15-30 minutes for first-time setup

---

## Phase 1: Environment Detection

### Detect Operating System

**AI Instructions:** First, determine the user's operating system.

**Ask the user:**
"What operating system are you using? (Windows, macOS, or Linux)"

**Set these variables based on the response:**
- `OS_TYPE`: windows / macos / linux
- `USES_WSL`: (Windows users) Ask "Are you using WSL (Windows Subsystem for Linux)?" (yes/no)

---

## Phase 2: Container Platform Check

### Step 2: Detect Container Platform

**AI Instructions:** Determine what container platform the user has or wants to use.

**Ask the user:**
"Do you already have a container platform installed, or would you like me to help you set one up?"

**Possible responses:**
- "I don't have anything" → Guide through Docker installation
- "I have Docker" → Verify and continue
- "I use Portainer" → Provide Portainer stack instructions
- "I use Kubernetes" → Provide Kubernetes manifest
- "I use Podman" → Provide Podman instructions
- "I use something else" → Ask what specifically

---

### Step 2A: Docker (Most Common)

**If user says they have Docker or don't have anything:**

**Ask the user to run:**

```bash
docker --version
docker compose version
```

**Expected output:** Version numbers (e.g., `Docker version 24.0.7`, `Docker Compose version v2.23.0`)

**If Docker is NOT installed:**

Proceed with **Docker Installation Guide** below.

**If Docker IS installed:**

✅ Docker verified - **Skip to Step 2F: Platform Summary**

---

#### Docker Installation Guide

**Windows Installation:**
1. Download Docker Desktop from: https://www.docker.com/products/docker-desktop/
2. Run the installer
3. Restart computer if prompted
4. Start Docker Desktop
5. Wait for "Docker Desktop is running" notification
6. Verify with `docker --version`

**Important Windows Notes:**
- WSL 2 is required (Docker Desktop will prompt to enable it)
- Virtualization must be enabled in BIOS
- User needs to join the "docker-users" group (installer usually handles this)

**macOS Installation:**
1. Download Docker Desktop from: https://www.docker.com/products/docker-desktop/
2. Drag Docker.app to Applications folder
3. Open Docker.app
4. Grant necessary permissions when prompted
5. Wait for Docker icon in menu bar to show "Docker Desktop is running"
6. Verify with `docker --version`

**Linux Installation:**
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install docker.io docker-compose-plugin
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
```

**After installation:** User must log out and back in for group changes to take effect.

**Verify Docker is running:**
```bash
docker ps
```

Should return an empty list or running containers, NOT an error.

**Continue to Step 2F**

---

### Step 2B: Portainer

**If user says they use Portainer:**

Great! Portainer makes this easier with its web UI. You'll deploy Nebulae as a stack.

**Verify Portainer is accessible:**
Ask: "What URL do you access Portainer at?" (e.g., `http://localhost:9000` or `https://portainer.yourdomain.com`)

**Guide them through stack deployment:**

1. **Log into Portainer**
2. **Navigate to:** Stacks → Add Stack
3. **Stack name:** `nebulae`
4. **Web editor:** Select this option
5. **Paste the docker-compose.yml content** (we'll generate this in Phase 5)

**Mark as:** "Will configure in Phase 5 - need to gather info first"

**Continue to Step 2F**

---

### Step 2C: Kubernetes

**If user says they use Kubernetes:**

Excellent! You'll need either a local cluster (minikube, k3s, microk8s) or a cloud cluster.

**Ask:**
"What Kubernetes setup are you using? (minikube, k3s, microk8s, EKS, GKE, AKS, or other)"

**Verify kubectl access:**
```bash
kubectl version --short
kubectl get nodes
```

**Expected output:** Version info and a list of nodes

**Check if they have Helm:**
```bash
helm version
```

**If they don't have Helm:**
```bash
# Install Helm
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

**Deployment approach:**
"We'll create a Kubernetes manifest for Nebulae. I'll provide you with a complete YAML file in Phase 5."

**Continue to Step 2F**

---

### Step 2D: Podman

**If user says they use Podman:**

Perfect! Podman is compatible with Docker Compose files with some minor adjustments.

**Verify Podman installation:**
```bash
podman --version
podman-compose --version
```

**If podman-compose is not installed:**

**Linux:**
```bash
pip3 install podman-compose
```

**macOS:**
```bash
brew install podman-compose
```

**Key differences from Docker:**
- Rootless by default (more secure)
- Uses `podman-compose` instead of `docker-compose`
- May need to adjust user permissions for volume mounts

**Continue to Step 2F**

---

### Step 2E: Other Platforms

**If user mentions another platform:**

**Ask:** "What container platform are you using specifically?"

**Common alternatives:**
- **Rancher:** Similar to Kubernetes deployment
- **Nomad:** Use Docker driver with job spec
- **LXC/LXD:** Can run Docker inside LXC, or deploy natively
- **Unraid:** Use Docker Compose or Community Applications
- **TrueNAS Scale:** Use Apps → Custom App with docker-compose
- **Synology NAS:** Use Container Manager with docker-compose

**General approach:**
Most platforms either:
1. Support docker-compose files directly (upload via UI)
2. Support Kubernetes manifests
3. Have their own template format (can be converted from docker-compose)

**Ask:** "Can your platform import a docker-compose.yml file?"
- **Yes:** Continue with docker-compose approach
- **No:** "What format does your platform use?" Then adapt accordingly

**Continue to Step 2F**

---

### Step 2F: Platform Summary

**AI Instructions:** Before moving to Phase 3, confirm the detected platform and deployment method.

**Summarize for the user:**

"Confirmed setup:
- **Platform:** [Docker/Portainer/Kubernetes/Podman/Other]
- **Deployment method:** [docker-compose/Portainer Stack/Kubernetes Manifest/Other]
- **Command tool:** [docker compose/podman-compose/kubectl]

We'll adapt the instructions accordingly. Let's continue!"

**Set these variables internally:**
```
CONTAINER_PLATFORM=[docker|portainer|kubernetes|podman|other]
DEPLOYMENT_METHOD=[compose|stack|k8s-manifest|custom]
COMMAND_PREFIX=[docker compose|podman-compose|kubectl]
```

**Continue to Phase 3**

---

## Phase 3: Configuration Setup

### Step 3A: Download Configuration Files

**AI Instructions:** Help the user obtain the necessary configuration files.

**For Docker/Portainer/Podman users:**

**Option 1 - Direct Download (Recommended):**
```bash
wget https://raw.githubusercontent.com/locqust/Nebulae/main/docker-compose.yml
```

**Option 2 - Manual Copy:**
Ask the user to:
1. Visit: https://github.com/locqust/Nebulae/blob/main/docker-compose.yml
2. Click "Raw" button
3. Copy all content
4. Create a new file called `docker-compose.yml` in their chosen directory
5. Paste the content and save

**Option 3 - Git Clone:**
```bash
git clone https://github.com/locqust/Nebulae.git
cd Nebulae
```

**For Kubernetes users:**

Download the Kubernetes manifest:
```bash
wget https://raw.githubusercontent.com/locqust/Nebulae/main/kubernetes-manifest.yaml
```

Or manually copy from: https://github.com/locqust/Nebulae/blob/main/kubernetes-manifest.yaml

### Step 3B: Generate Secret Key

**AI Instructions:** Generate a cryptographically secure SECRET_KEY.

**Method 1 - Python (Preferred):**
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

**Method 2 - Online Generator:**
Direct user to: https://codebeautify.org/generate-random-hexadecimal-numbers
- Set length to 64 characters
- Click Generate

**Method 3 - OpenSSL (Linux/macOS):**
```bash
openssl rand -hex 32
```

**IMPORTANT:** Store this key securely! User should save it in a password manager.

**Set the variable:**
`SECRET_KEY=[generated_key]`

### Step 3C: Reverse Proxy Configuration

**AI Instructions:** Determine if user needs reverse proxy assistance.

**Ask the user:**
"Do you already have a reverse proxy (like nginx, Caddy, Traefik, or Nginx Proxy Manager) configured, or would you like me to help you set one up?"

**If they answer "I already have one":**
- Inform them: "Great! You'll need to configure your existing reverse proxy to forward HTTPS traffic to the Nebulae container on port 5000. Make sure your DNS A record points to your server and your SSL certificate is valid."
- **Continue to Step 3D**

**If they answer "I need help setting one up":**
Continue with **Step 3C-1: Nginx Proxy Manager Setup** below.

---

#### Step 3C-1: Install Nginx Proxy Manager

**AI Instructions:** Guide user through installing Nginx Proxy Manager alongside Nebulae.

Nginx Proxy Manager (NPM) is a user-friendly web interface for managing reverse proxies and SSL certificates. It will handle HTTPS for your Nebulae instance automatically.

**Create a new file called `docker-compose-npm.yml`:**

```yaml
version: '3.8'

services:
  npm:
    image: 'jc21/nginx-proxy-manager:latest'
    container_name: nginx-proxy-manager
    restart: unless-stopped
    ports:
      - '80:80'    # HTTP
      - '443:443'  # HTTPS
      - '81:81'    # Admin UI (local access only)
    volumes:
      - npm_data:/data
      - npm_letsencrypt:/etc/letsencrypt
    networks:
      - nebulae_network

networks:
  nebulae_network:
    external: true

volumes:
  npm_data:
  npm_letsencrypt:
```

**Save this file in the same directory as your `docker-compose.yml`**

**Now modify your existing `docker-compose.yml`:**

Find the `services:` section and add this at the bottom (after the `volumes:` section):

```yaml
networks:
  nebulae_network:
    driver: bridge
```

And under the `services: web:` section, change the ports and add networks:

**Replace this:**
```yaml
ports:
  - "5000:5000"
```

**With this:**
```yaml
expose:
  - "5000"
networks:
  - nebulae_network
```

Your `services: web:` section should now include:

```yaml
services:
  web:
    image: ghcr.io/locqust/nebulae:latest 
    container_name: nebulae
    expose:
      - "5000"
    volumes:
      # ... rest of your config
    networks:
      - nebulae_network
    # ... rest of your config
```

**Create the network first:**
```bash
docker network create nebulae_network
```

**Start Nginx Proxy Manager:**
```bash
docker compose -f docker-compose-npm.yml up -d
```

**Wait 30 seconds for NPM to start, then access the admin UI:**
`http://[your-server-ip]:81`

**Default login credentials:**
- Email: `admin@example.com`
- Password: `changeme`

**You'll be prompted to change these immediately - do so now!**

---

#### Step 3C-2: Configure Proxy Host in NPM

**Once logged into Nginx Proxy Manager:**

1. Click **"Hosts"** → **"Proxy Hosts"** → **"Add Proxy Host"**

2. **Details Tab:**
   - **Domain Names:** Enter your domain (e.g., `nebulae.example.com`)
   - **Scheme:** `http`
   - **Forward Hostname / IP:** `nebulae` (this is your Nebulae container name)
   - **Forward Port:** `5000`
   - **Cache Assets:** ✓ (check)
   - **Block Common Exploits:** ✓ (check)
   - **Websockets Support:** ✓ (check)

3. **SSL Tab:**
   - ✓ **SSL Certificate:** Select "Request a new SSL Certificate"
   - ✓ **Force SSL:** (check)
   - ✓ **HTTP/2 Support:** (check)
   - **Email Address:** Enter your email for Let's Encrypt notifications
   - ✓ **I Agree to the Let's Encrypt Terms of Service:** (check)

4. Click **"Save"**

NPM will automatically obtain an SSL certificate from Let's Encrypt. This takes 30-60 seconds.

**Verify SSL is working:**
Visit `https://[your-domain]` - you should see a valid padlock icon and be redirected to HTTPS automatically.

---

#### Step 3C-3: Update Nebulae Configuration

**Now that your reverse proxy is working, you'll set your NODE_HOSTNAME in the next step.**

**Important Note:** You only need port 443 forwarded on your router (covered in Phase 3D-5). NPM handles Let's Encrypt validation through port 443 using TLS-ALPN-01 method.

**Continue to Step 3D**

---

#### Accessing NPM Admin Securely

**If you need to access NPM admin interface remotely:**

**Option 1 - SSH Tunnel (Recommended):**
```bash
ssh -L 8081:localhost:81 user@your-home-ip
```
Then access NPM at `http://localhost:8081`

**Option 2 - Tailscale/Wireguard VPN:**
Set up a VPN to your home network and access `http://192.168.x.x:81` directly

**Never expose port 81 to the internet** - this is a common security vulnerability.

---

### Step 3D: Dynamic DNS Configuration (Home/Residential Users)

**AI Instructions:** Determine if user needs DDNS based on their hosting scenario.

**Ask the user:**
"Are you hosting this on a home internet connection (residential ISP like Comcast, BT, Sky, etc.) or on a VPS/dedicated server with a static IP?"

**If they answer "VPS/dedicated server with static IP":**
- Ask: "What is your domain name or public IP address?"
- Domain example: `nebulae.example.com`
- IP example: `203.0.113.42`
- Set: `NODE_HOSTNAME=[their_domain_or_ip]`
- Set: `FEDERATION_INSECURE_MODE=False`
- Skip to **Phase 4**

**If they answer "Home internet connection":**

Most residential ISPs assign **dynamic IP addresses** that can change periodically (during modem reboot, lease renewal, or randomly). This breaks federation because your hostname won't resolve to the correct IP.

**Solution:** Set up Dynamic DNS (DDNS) to automatically update your DNS records when your IP changes.

---

#### Step 3D-1: Choose a DDNS Provider

**AI Instructions:** Help user select and sign up for a DDNS service.

**Recommended Free DDNS Providers:**

1. **Duck DNS** (Recommended - Simplest)
   - Website: https://www.duckdns.org/
   - Free subdomains: `yourname.duckdns.org`
   - No account required - just login with social/GitHub
   - Simple token-based API
   - Works worldwide

2. **No-IP**
   - Website: https://www.noip.com/
   - Free tier: 3 hostnames
   - Requires monthly confirmation to keep free hostnames active
   - Desktop client available for all platforms

3. **Dynu**
   - Website: https://www.dynu.com/
   - Free tier: 4 hostnames
   - No confirmation required
   - Multiple top-level domains available

4. **Cloudflare** (Advanced - for custom domains)
   - Website: https://www.cloudflare.com/
   - Free tier with full DNS management
   - Requires you to own a domain and point nameservers to Cloudflare
   - More complex setup but most professional option

**For this guide, we'll use Duck DNS as it's the simplest.**

---

#### Step 3D-2: Sign Up for Duck DNS

**Guide the user through Duck DNS setup:**

1. Visit https://www.duckdns.org/
2. Click **"sign in with"** and choose your preferred method (Google, GitHub, Reddit, etc.)
3. After signing in, you'll see your **token** at the top - this is like a password
   - **CRITICAL:** Copy and save this token securely (password manager)
   - Example token: `a7f3c8e9-d2b4-f1a6-c8e3-d9f2b7a4c1e9`

4. **Create your subdomain:**
   - In the "sub domain" box, enter your desired name
   - Example: `myname-nebulae` (full domain will be `myname-nebulae.duckdns.org`)
   - Must be unique across all Duck DNS users
   - Can contain: letters, numbers, hyphens (no spaces or special characters)
   - Click **"add domain"**

5. Your new domain appears in the list with your current IP detected
6. Click **"install"** at the top to see installation guides

**Set these variables:**
```
DDNS_DOMAIN=myname-nebulae.duckdns.org
DDNS_TOKEN=a7f3c8e9-d2b4-f1a6-c8e3-d9f2b7a4c1e9
NODE_HOSTNAME=myname-nebulae.duckdns.org
FEDERATION_INSECURE_MODE=False
```

---

#### Step 3D-3: Install DDNS Update Client

**AI Instructions:** Install the appropriate DDNS updater based on user's container platform.

DDNS works by periodically checking your public IP and updating the DNS record if it changes. We'll set this up as a Docker container that runs alongside Nebulae.

**Create a new file called `docker-compose-ddns.yml`:**

```yaml
version: '3.8'

services:
  duckdns:
    image: lscr.io/linuxserver/duckdns:latest
    container_name: duckdns
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=Europe/London  # Change to your timezone
      - SUBDOMAINS=myname-nebulae  # Your subdomain WITHOUT .duckdns.org
      - TOKEN=your_duckdns_token_here  # Your Duck DNS token
      - LOG_FILE=true
    volumes:
      - duckdns_config:/config
    restart: unless-stopped
    networks:
      - nebulae_network

networks:
  nebulae_network:
    external: true

volumes:
  duckdns_config:
```

**Customize the file:**

1. **TZ (Timezone):** Change to your timezone
   - Find yours at: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
   - Examples: `America/New_York`, `Europe/London`, `Australia/Sydney`

2. **SUBDOMAINS:** Replace `myname-nebulae` with YOUR subdomain (the part before .duckdns.org)

3. **TOKEN:** Replace `your_duckdns_token_here` with your actual Duck DNS token

**Example with real values:**
```yaml
    environment:
      - PUID=1000
      - PGID=1000
      - TZ=America/Chicago
      - SUBDOMAINS=johns-nebulae
      - TOKEN=a7f3c8e9-d2b4-f1a6-c8e3-d9f2b7a4c1e9
      - LOG_FILE=true
```

**Save the file**

---

#### Step 3D-4: Start DDNS Updater

**Start the Duck DNS container:**

**Docker:**
```bash
docker compose -f docker-compose-ddns.yml up -d
```

**Podman:**
```bash
podman-compose -f docker-compose-ddns.yml up -d
```

**Expected output:**
```
Creating volume "duckdns_config" with default driver
Pulling duckdns (lscr.io/linuxserver/duckdns:latest)...
Creating duckdns ... done
```

**Check if it's working:**

```bash
docker logs duckdns
```
(or `podman logs duckdns`)

**Expected output (look for this):**
```
Your IP address is XXX.XXX.XXX.XXX
```

This container now checks your IP every 5 minutes and updates Duck DNS if it changes.

**Verify DNS is working:**

**Option 1 - Online tool:**
Visit https://www.whatsmydns.net/
Enter your full domain: `myname-nebulae.duckdns.org`
Should show your current public IP address

**Option 2 - Command line:**

**Windows (PowerShell):**
```powershell
nslookup myname-nebulae.duckdns.org
```

**macOS/Linux:**
```bash
nslookup myname-nebulae.duckdns.org
# or
dig myname-nebulae.duckdns.org
```

**Expected:** Should return your public IP address

**To find your public IP for comparison:**
Visit https://ifconfig.me/ or run:
```bash
curl ifconfig.me
```

**If DNS is working correctly, the domain should resolve to the same IP that ifconfig.me shows.**

---

#### Step 3D-5: Router Configuration (Port Forwarding)

**AI Instructions:** Guide user through port forwarding setup.

For your Nebulae instance to be accessible from the internet, you must configure port forwarding on your home router.

**Ask the user:**
"Can you access your router's admin panel? You'll typically need to go to `192.168.1.1` or `192.168.0.1` in your browser."

**Common router admin addresses:**
- `192.168.1.1` (most common)
- `192.168.0.1` (also common)
- `192.168.1.254`
- `10.0.0.1` (some ISP routers)

**Common default credentials** (CHANGE THESE AFTER LOGIN):
- Username: `admin`, Password: `admin`
- Username: `admin`, Password: `password`
- Check the sticker on your router for defaults

**If they can't access their router:**
They may need to contact their ISP or search for their specific router model's admin instructions.

**Once in the router admin panel:**

1. Find the **Port Forwarding** section (might be called):
   - "Port Forwarding"
   - "Virtual Servers"
   - "NAT/Gaming"
   - "Applications & Gaming"
   - "Advanced → Port Forwarding"

2. Create **ONE** port forwarding rule:

**HTTPS Port Forwarding:**
- **Service Name:** `Nebulae-HTTPS` (or anything descriptive)
- **External Port:** `443`
- **Internal IP:** `[Your server's local IP]` (find this with `ipconfig` on Windows or `ip addr` on Linux)
- **Internal Port:** `443`
- **Protocol:** `TCP`

**That's it! You only need port 443.**

**Why only 443?**
- Nginx Proxy Manager handles SSL certificate validation through port 443 (using TLS-ALPN-01 method)
- NPM automatically redirects HTTP → HTTPS internally
- Port 80 is not needed for Let's Encrypt when using NPM
- Port 81 (NPM admin) should **never** be exposed to the internet for security reasons

**How to find your server's local IP address:**

**Windows:**
```powershell
ipconfig
```
Look for "IPv4 Address" under your active connection (usually starts with `192.168.`)

**macOS/Linux:**
```bash
ip addr show
# or
ifconfig
```
Look for `inet` address on your active interface (usually starts with `192.168.`)

**Example:**
If your server's local IP is `192.168.1.100`:
- External Port: `443`
- Internal IP: `192.168.1.100`
- Internal Port: `443`
- Protocol: `TCP`

**Save/Apply the port forwarding rules**

**Important note:** Some routers require a reboot after changing port forwarding rules.

---

#### Step 3D-6: Test External Access

**Verify your domain resolves and ports are open:**

**Method 1 - Mobile data test (easiest):**
1. Turn off WiFi on your phone
2. Use mobile data
3. Try to visit `https://myname-nebulae.duckdns.org` in your phone's browser
4. You should see either the Nebulae login page OR an error from Nginx Proxy Manager (which means the port forwarding works)

**Method 2 - Online port checker:**
Visit https://www.yougetsignal.com/tools/open-ports/
- Remote Address: Your Duck DNS domain
- Port Number: 443
- Click "Check"
- Should show "open"

**Method 3 - Ask a friend:**
Have someone on a different network visit your domain

**If it works:** ✅ Port forwarding is configured correctly!

**If it doesn't work, check:**
- Port forwarding rule is correct and saved
- Router has been rebooted if needed
- Your ISP isn't blocking port 443 (rare, but some do)
- Firewall on server isn't blocking port 443

---

#### Step 3D-7: Alternative - Custom Domain with Cloudflare DDNS

**If user owns a domain and wants to use it instead of duckdns.org:**

**Ask:** "Do you own a custom domain (like `example.com`) that you'd like to use instead of a `.duckdns.org` subdomain?"

**If yes, continue with Cloudflare setup:**

1. **Sign up for Cloudflare:** https://dash.cloudflare.com/sign-up
2. **Add your domain** to Cloudflare (follow their wizard)
3. **Update nameservers** at your domain registrar to Cloudflare's nameservers
4. **Wait for DNS propagation** (up to 24 hours, usually <1 hour)

5. **Create API token:**
   - Go to: My Profile → API Tokens → Create Token
   - Use template: "Edit zone DNS"
   - Zone Resources: Include → Specific zone → [your domain]
   - Copy the token

6. **Use Cloudflare DDNS container** instead of Duck DNS:

Create `docker-compose-cloudflare-ddns.yml`:

```yaml
version: '3.8'

services:
  cloudflare-ddns:
    image: oznu/cloudflare-ddns:latest
    container_name: cloudflare-ddns
    environment:
      - API_KEY=your_cloudflare_api_token
      - ZONE=example.com
      - SUBDOMAIN=nebulae  # Creates nebulae.example.com
      - PROXIED=false  # IMPORTANT: Keep false for federation
    restart: unless-stopped
    networks:
      - nebulae_network

networks:
  nebulae_network:
    external: true
```

Start it: 
```bash
docker compose -f docker-compose-cloudflare-ddns.yml up -d
```

**Set:** `NODE_HOSTNAME=nebulae.example.com`

**Note:** If using Cloudflare proxy (`PROXIED=true`), federation will break because Cloudflare doesn't support non-HTTP protocols well. Keep `PROXIED=false`.

---

**Continue to Phase 4**

---

## Phase 4: User Planning

### Step 4: Gather User Information

**AI Instructions:** Help the user plan their accounts and media paths.

**Ask:**
"How many user accounts do you want to create initially? (You can add more later)"

For EACH user, collect:

1. **Username** (usually their email address)
   - Will be used for login
   - Example: `john.doe@email.com`

2. **Display Name** (their actual name)
   - How they appear to others
   - Example: `John Doe`

3. **Media Directories** (optional but recommended)
   - **Read-only path**: Existing photo library (family photos, etc.)
   - **Uploads path**: Where new uploads should be saved
   
**Path Examples:**

**Windows:**
```yaml
- C:\Users\John\Pictures\FamilyPhotos:/app/user_media/john_media:ro
- C:\Users\John\Documents\NebulaeUploads:/app/user_uploads/john_uploads
```

**macOS:**
```yaml
- /Users/john/Pictures/Family:/app/user_media/john_media:ro
- /Users/john/Documents/NebulaeUploads:/app/user_uploads/john_uploads
```

**Linux:**
```yaml
- /home/john/Photos:/app/user_media/john_media:ro
- /home/john/nebulae_uploads:/app/user_uploads/john_uploads
```

**Important Notes:**
- The `:ro` flag makes the read-only path actually read-only
- Container path MUST follow pattern: `/app/user_media/[username]_media`
- Container upload path MUST follow: `/app/user_uploads/[username]_uploads`
- Create upload directories before starting the container!

**Create Upload Directories:**

**Windows:**
```powershell
mkdir "C:\Users\John\Documents\NebulaeUploads"
```

**macOS/Linux:**
```bash
mkdir -p ~/nebulae_uploads
```

**Store this information in a table:**

| Username | Display Name | Read-Only Path | Upload Path |
|----------|-------------|----------------|-------------|
| john@email.com | John Doe | C:\Users\John\Pictures | C:\Users\John\Documents\NebulaeUploads |
| jane@email.com | Jane Doe | C:\Users\Jane\Photos | C:\Users\Jane\Documents\NebulaeUploads |

---

## Phase 5: Configure Deployment Files

### Step 5A: Docker Compose Configuration (Docker/Portainer/Podman)

**AI Instructions:** Guide the user through editing the docker-compose.yml file.

**Open the file for editing:**
- Windows: Use Notepad, VS Code, or any text editor
- macOS/Linux: Use nano, vim, VS Code, or any text editor

**Find and replace these values:**

```yaml
environment:
  - SECRET_KEY=CHANGE_ME_GENERATE_A_SECRET_KEY  # Replace with generated key
  - NODE_HOSTNAME=CHANGE_ME_TO_YOUR_HOSTNAME   # Replace with domain/IP
  - FEDERATION_INSECURE_MODE=False              # Keep False for production
  - FLASK_ENV=production                         # Keep as is
```

**Example after editing:**
```yaml
environment:
  - SECRET_KEY=a7f3c8e9d2b4f1a6c8e3d9f2b7a4c1e9d3f8b2a5c7e1d4f9b3a6c2e8d1f5b9a3
  - NODE_HOSTNAME=myname-nebulae.duckdns.org
  - FEDERATION_INSECURE_MODE=False
  - FLASK_ENV=production
```

---

### Step 5B: Add Volume Mounts for Users

**Find this section in docker-compose.yml:**
```yaml
volumes:
  # User media volumes - USERS MUST CONFIGURE THESE
  # Example format (commented out by default):
  # - /path/to/user/photos:/app/user_media/username_media:ro
```

**Uncomment and add entries for each user:**

**Example for 2 users:**
```yaml
volumes:
  - nebulae_data:/app/instance
  - ./backups:/app/instance/backups
  - profile_pictures:/app/profile_pictures_storage
  - thumbnail_cache:/app/thumbnails
  # User 1: John
  - C:\Users\John\Pictures\FamilyPhotos:/app/user_media/john_media:ro
  - C:\Users\John\Documents\NebulaeUploads:/app/user_uploads/john_uploads
  # User 2: Jane
  - C:\Users\Jane\Photos:/app/user_media/jane_media:ro
  - C:\Users\Jane\Documents\NebulaeUploads:/app/user_uploads/jane_uploads
```

**If using Nginx Proxy Manager, also add the network configuration:**

At the bottom of the file, add:
```yaml
networks:
  nebulae_network:
    driver: bridge
```

And under `services: web:`, change ports to expose and add networks:
```yaml
services:
  web:
    # ... existing config ...
    expose:
      - "5000"
    networks:
      - nebulae_network
    # ... rest of config ...
```

**CRITICAL FORMATTING NOTES:**
- Indentation must be EXACTLY 2 spaces (no tabs!)
- The hyphen `-` must have a space after it
- Windows paths use backslashes `\` but should work as-is in docker-compose
- If paths have spaces, wrap in quotes: `"C:\Users\John Doe\Pictures"`

**Save the file** (Ctrl+S or `:wq` in vim)

**Validate the file:**

**Docker:**
```bash
docker compose config
```

**Podman:**
```bash
podman-compose config
```

If valid, it will show the parsed configuration. If errors, it will indicate what's wrong.

**For Portainer users:** You'll paste this edited content into Portainer's stack editor in Phase 6.

---

### Step 5C: Kubernetes Configuration (Kubernetes users only)

**AI Instructions:** For Kubernetes users, edit the kubernetes-manifest.yaml file.

**Download the manifest if you haven't already:**
```bash
wget https://raw.githubusercontent.com/locqust/Nebulae/main/kubernetes-manifest.yaml
```

**Edit the ConfigMap section:**

Find this section:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: nebulae-config
  namespace: nebulae
data:
  SECRET_KEY: "CHANGE_ME_GENERATE_A_SECRET_KEY"
  NODE_HOSTNAME: "CHANGE_ME_TO_YOUR_HOSTNAME"
  FEDERATION_INSECURE_MODE: "False"
  FLASK_ENV: "production"
```

Replace with your values:
```yaml
data:
  SECRET_KEY: "a7f3c8e9d2b4f1a6c8e3d9f2b7a4c1e9d3f8b2a5c7e1d4f9b3a6c2e8d1f5b9a3"
  NODE_HOSTNAME: "myname-nebulae.duckdns.org"
  FEDERATION_INSECURE_MODE: "False"
  FLASK_ENV: "production"
```

**Add user media volumes:**

Find the `volumeMounts` section in the Deployment:
```yaml
        volumeMounts:
        - name: nebulae-data
          mountPath: /app/instance
        - name: profile-pictures
          mountPath: /app/profile_pictures_storage
        - name: thumbnail-cache
          mountPath: /app/thumbnails
        # Add user media mounts here
```

Add your user mounts:
```yaml
        volumeMounts:
        - name: nebulae-data
          mountPath: /app/instance
        - name: profile-pictures
          mountPath: /app/profile_pictures_storage
        - name: thumbnail-cache
          mountPath: /app/thumbnails
        - name: user-john-media
          mountPath: /app/user_media/john_media
          readOnly: true
        - name: user-john-uploads
          mountPath: /app/user_uploads/john_uploads
```

And add corresponding volumes at the bottom:
```yaml
      volumes:
      - name: nebulae-data
        persistentVolumeClaim:
          claimName: nebulae-data
      - name: profile-pictures
        persistentVolumeClaim:
          claimName: profile-pictures
      - name: thumbnail-cache
        persistentVolumeClaim:
          claimName: thumbnail-cache
      - name: user-john-media
        hostPath:
          path: /path/to/john/photos
          type: Directory
      - name: user-john-uploads
        hostPath:
          path: /path/to/john/uploads
          type: DirectoryOrCreate
```

**Update the Ingress section:**

Find this:
```yaml
  tls:
  - hosts:
    - nebulae.example.com  # CHANGE THIS
    secretName: nebulae-tls
  rules:
  - host: nebulae.example.com  # CHANGE THIS
```

Replace with your domain:
```yaml
  tls:
  - hosts:
    - myname-nebulae.duckdns.org
    secretName: nebulae-tls
  rules:
  - host: myname-nebulae.duckdns.org
```

**Save the file**

---

## Phase 6: Deploy Container

### Step 6: Start Nebulae (Platform-Specific)

**AI Instructions:** Guide user through deployment based on their platform.

---

### Docker / Docker Compose

**In the directory containing docker-compose.yml, run:**

```bash
docker compose up -d
```

**Expected output:**
```
Creating network "nebulae_default" with the default driver
Creating volume "nebulae_nebulae_data" with default driver
Creating volume "nebulae_profile_pictures" with default driver
Creating volume "nebulae_thumbnail_cache" with default driver
Pulling web (ghcr.io/locqust/nebulae:latest)...
latest: Pulling from locqust/nebulae
...
Creating nebulae ... done
```

**Check if container is running:**
```bash
docker compose ps
```

**Expected output:**
```
NAME      STATE   PORTS
nebulae   Up      0.0.0.0:5000->5000/tcp (or nebulae_network if using NPM)
```

**Check logs for startup:**
```bash
docker compose logs -f
```

**Look for:**
```
[INFO] Starting gunicorn 20.1.0
[INFO] Listening at: http://0.0.0.0:5000
[INFO] Using worker: sync
[INFO] Booting worker with pid: ...
```

**Press Ctrl+C to stop following logs** (container keeps running)

---

### Portainer

**Deploy via Portainer UI:**

1. **Log into Portainer**
2. **Go to:** Stacks → Add Stack (or find your existing `nebulae` stack)
3. **Stack name:** `nebulae`
4. **Web editor:** Paste your edited docker-compose.yml content
5. Click **"Deploy the stack"**
6. Wait for deployment (green checkmark)

**Verify deployment:**
1. Go to **Containers**
2. Find `nebulae` container
3. Status should be "running"
4. Click on container name → **Logs** tab to verify startup

---

### Kubernetes

**Apply the manifest:**

```bash
kubectl apply -f kubernetes-manifest.yaml
```

**Expected output:**
```
namespace/nebulae created
configmap/nebulae-config created
persistentvolumeclaim/nebulae-data created
persistentvolumeclaim/profile-pictures created
persistentvolumeclaim/thumbnail-cache created
deployment.apps/nebulae created
service/nebulae created
ingress.networking.k8s.io/nebulae created
```

**Check pod status:**
```bash
kubectl get pods -n nebulae
```

**Wait for pod to be "Running":**
```
NAME                       READY   STATUS    RESTARTS   AGE
nebulae-xxxxxxxxxx-xxxxx   1/1     Running   0          30s
```

**Check logs:**
```bash
kubectl logs -n nebulae -l app=nebulae -f
```

**Look for gunicorn startup messages**

**Press Ctrl+C to stop following logs**

---

### Podman

**Start with podman-compose:**

```bash
podman-compose up -d
```

**Check if container is running:**
```bash
podman ps | grep nebulae
```

**Check logs:**
```bash
podman logs nebulae -f
```

**Note:** If you encounter permission issues with volumes:
```bash
sudo chcon -Rt svirt_sandbox_file_t /path/to/media/directories
```

**Press Ctrl+C to stop following logs**

---

### Common Startup Issues

**"Port 5000 already in use"**
Solution: Change port in docker-compose.yml (or use `expose` if using NPM)

**"Cannot connect to Docker daemon"**
Solution: Start Docker Desktop and wait for it to fully initialize

**"Permission denied" on volume mounts**
Solution (Linux):
```bash
sudo chown -R $USER:$USER /path/to/media
```

Solution (Windows): Ensure Docker Desktop has permission to access the drive (Settings → Resources → File Sharing)

**"Module not found" or Python errors**
Solution: Pull latest image:
```bash
docker compose pull
docker compose up -d --force-recreate
```

---

## Phase 7: Initial Admin Setup

### Step 7A: Access Web Interface

**AI Instructions:** Guide user to access Nebulae for the first time.

**Open web browser and navigate to:**

**If using reverse proxy with domain:**
- `https://[your-domain]` (e.g., `https://myname-nebulae.duckdns.org`)

**If testing locally without reverse proxy:**
- `http://localhost:5000`

**If accessing from another device on network:**
- `http://[server-ip]:5000`

**For Kubernetes with Ingress:**
- `https://[your-ingress-domain]`

**Expected:** Nebulae login page appears

**First-time setup:** The database will auto-initialize on first access.

---

### Step 7B: Initial Admin Login

**AI Instructions:** Guide user through first-time admin access.

**You'll see the Nebulae login page.**

**Default admin credentials:**
- **Username:** `admin`
- **Password:** `adminpassword`

**Enter these credentials and click "Log In"**

**🔒 CRITICAL SECURITY STEP:**

You will **immediately** be prompted to change the default password.

**Create a strong new password that includes:**
- At least 8 characters
- Uppercase letter (A-Z)
- Lowercase letter (a-z)
- Number (0-9)
- Special character (!@#$%^&*)

**Example strong password:** `N3bu!ae_Adm1n_2025`

**Store this password securely** (password manager recommended)

**After setting new password, you'll be logged in as Administrator.**

**Proceed to Step 7C to create user accounts.**

---

### Step 7C: Create User Accounts

**Navigate to:** Admin Panel → Manage Users → Add New User

**For each user in your planning table:**

1. Click **"Add New User"**
2. **Username:** Enter their username (e.g., `john@email.com`)
3. **Password:** Create temporary password (users can change later)
   - Must meet same requirements: 8+ chars, upper, lower, number, special
4. **Display Name:** Enter their full name
5. **Date of Birth:** Enter DOB 
   - **IMPORTANT:** This CANNOT be changed later
   - Required for users under 16 (parental controls apply automatically)
6. Click **"Add User"**

**Repeat for all planned users**

---

### Step 7D: Configure Media Paths

**For each user:**

1. Go to **Admin Panel → Manage Users**
2. Find the user in the list
3. Click **Actions → Set Media Path**
4. Enter **Container Paths** (NOT the Windows/Mac/Linux host paths!):
   - **Read-only media path:** `/app/user_media/[username]_media`
   - **Upload media path:** `/app/user_uploads/[username]_uploads`

**Example for user "john":**
```
Read-only: /app/user_media/john_media
Uploads: /app/user_uploads/john_uploads
```

**These paths must match what you configured in docker-compose.yml or kubernetes-manifest.yaml!**

5. Click **"Save"** or **"Update"**

**Verify:** Log in as the user and check if their existing photos from the read-only directory appear in their gallery.

---

## Phase 8: Testing & Verification

### Step 8: Verify Installation

**AI Instructions:** Walk the user through testing core functionality.

**Test Checklist:**

#### 1. **User Login Test**
   - Log out from admin account
   - Log in as one of the created users
   - Verify dashboard loads correctly

#### 2. **Create a Post**
   - Click "Create Post" or write in the post box
   - Write a test message: "Testing my new Nebulae instance! 🚀"
   - Upload a test image (any photo)
   - Click "Post"
   - Verify post appears on your feed

#### 3. **Check Media Gallery**
   - Click on your username/profile picture
   - Navigate to "Gallery" or "Photos" tab
   - **Verify existing photos** from your read-only media path appear
   - **Verify newly uploaded photo** from the test post appears
   - Click on a photo to open it in full-screen view

#### 4. **Upload New Media Verification**
   - After uploading a photo in step 2, check your upload directory on your host system
   - **Windows:** `C:\Users\[YourName]\Documents\NebulaeUploads`
   - **macOS/Linux:** `~/nebulae_uploads`
   - Verify the uploaded file exists there

#### 5. **Test Social Features**
   - **Create a comment** on your test post
   - **Reply to a comment** (test nested comments)
   - **Edit your post** (click the "..." menu → Edit)
   - **Delete a post** (create another test post, then delete it)
   - **Tag a friend** in a post (if you've added multiple users)

#### 6. **Test Groups (Admin Only)**
   - Log in as **admin**
   - Go to **Admin Panel → Manage Groups**
   - Click **"Create New Group"**
   - Enter group name and description
   - Select a user as the initial group admin
   - Click **"Create Group"**
   - Visit the group page
   - Post something in the group
   - Log in as the group admin user and verify they can manage the group

#### 7. **Test Events (Optional)**
   - Create a test event
   - Set a date/time and location
   - Verify event appears on your profile

#### 8. **Mobile Responsiveness**
   - Open Nebulae on your phone's web browser
   - Test creating a post from mobile
   - Verify the interface adapts to mobile screen size

#### 9. **Admin Panel Check**
   - Log back in as admin
   - Go to **Admin Panel**
   - Verify you can see:
     - User list
     - System statistics
     - Admin controls

#### 10. **Reverse Proxy & HTTPS (if configured)**
   - Visit your domain in a browser
   - Click the padlock icon next to the URL
   - Verify SSL certificate is valid
   - Verify automatic HTTP → HTTPS redirect works

---

### All Tests Passing?

**✅ Congratulations!** Your Nebulae instance is fully operational!

**Proceed to Phase 9 for next steps and ongoing maintenance.**

---

## Phase 9: Next Steps

### Additional Configuration

**Security Hardening:**
- Set up automated backups (see below)
- Configure firewall rules
- Enable fail2ban or similar for brute-force protection
- Change router admin password if still default
- Disable UPnP on router if enabled

**Optional Features:**
- Email notifications (configure SMTP settings in Admin Panel)
- Push notifications (configure VAPID keys)
- Custom themes
- Parental controls for users under 16

**Backup Strategy:**

Database backup location is already configured: `./backups:/app/instance/backups`

**Manual backup:**

**Docker/Podman:**
```bash
docker compose exec web sqlite3 /app/instance/nebulae.db ".backup /app/instance/backups/backup-$(date +%Y%m%d).db"
```

**Kubernetes:**
```bash
kubectl exec -n nebulae -it $(kubectl get pod -n nebulae -l app=nebulae -o jsonpath='{.items[0].metadata.name}') -- sqlite3 /app/instance/nebulae.db ".backup /app/instance/backups/backup-$(date +%Y%m%d).db"
```

**Automated backups (Linux cron):**
```bash
# Edit crontab
crontab -e

# Add this line for daily backups at 2 AM
0 2 * * * cd /path/to/nebulae && docker compose exec web sqlite3 /app/instance/nebulae.db ".backup /app/instance/backups/backup-$(date +\%Y\%m\%d).db"
```

**Regular Maintenance:**
- Weekly database backups
- Monthly Docker image updates: `docker compose pull && docker compose up -d`
- Monitor disk space (media files can grow large)
- Review logs: `docker compose logs -f`

---

## Maintenance Commands Reference

### Docker / Docker Compose

```bash
# Start Nebulae
docker compose up -d

# Stop Nebulae
docker compose down

# Restart Nebulae
docker compose restart

# View logs
docker compose logs -f

# Update to latest version
docker compose pull
docker compose up -d

# Access container shell
docker compose exec web bash

# Check container status
docker compose ps

# Remove everything (DESTRUCTIVE - deletes database!)
docker compose down -v
```

### Portainer

- Start/Stop: Use Portainer UI → Stacks → nebulae → Stop/Start
- View logs: Containers → nebulae → Logs tab
- Update: Stacks → nebulae → Pull and redeploy
- Shell access: Containers → nebulae → Console

### Kubernetes

```bash
# View pods
kubectl get pods -n nebulae

# View logs
kubectl logs -n nebulae -l app=nebulae -f

# Restart deployment
kubectl rollout restart deployment/nebulae -n nebulae

# Update image
kubectl set image deployment/nebulae nebulae=ghcr.io/locqust/nebulae:latest -n nebulae

# Access pod shell
kubectl exec -n nebulae -it $(kubectl get pod -n nebulae -l app=nebulae -o jsonpath='{.items[0].metadata.name}') -- bash

# Delete everything (DESTRUCTIVE)
kubectl delete namespace nebulae
```

### Podman

```bash
# Start Nebulae
podman-compose up -d

# Stop Nebulae
podman-compose down

# Restart Nebulae
podman-compose restart

# View logs
podman logs nebulae -f

# Update to latest version
podman-compose pull
podman-compose up -d

# Access container shell
podman exec -it nebulae bash

# Check container status
podman ps
```

---

## Troubleshooting Guide

### Common Issues

**"Port already in use"**
Solution: Change port in configuration file or stop conflicting service

**"Cannot connect to container runtime"**
Solution: Ensure Docker/Podman is running and user has permissions

**"Permission denied" on volume mounts**
Solution (Linux):
```bash
sudo chown -R $USER:$USER /path/to/media
```

Solution (Windows): Ensure container platform has permission to access the drive

**"Module not found" or Python errors**
Solution: Pull latest image and recreate container

**Media not showing up in gallery**
Solution: 
- Verify paths in configuration match paths set in admin panel
- Check that media directories exist and contain files
- Restart container
- Check container logs for errors

**Can't access from internet (home users)**
Solution:
- Verify port forwarding is configured
- Check DNS resolution: `nslookup your-domain.com`
- Verify DDNS updater is running
- Check router firewall rules
- Verify ISP isn't blocking ports

**SSL certificate errors**
Solution:
- Ensure domain resolves to correct IP
- Check Nginx Proxy Manager logs
- Verify port 443 is accessible from internet
- Wait for Let's Encrypt rate limits to reset (1 hour)

**Federation not working**
Solution:
- Verify `NODE_HOSTNAME` is correct and publicly accessible
- Check `FEDERATION_INSECURE_MODE` is False for HTTPS
- Ensure SSL certificate is valid
- Test with another Nebulae instance

---

## Support & Resources

- **Documentation:** https://github.com/locqust/Nebulae/tree/main/docs
- **GitHub Issues:** https://github.com/locqust/Nebulae/issues
- **GitHub Discussions:** https://github.com/locqust/Nebulae/discussions
- **Docker Hub:** https://github.com/locqust/Nebulae/pkgs/container/nebulae

---

## AI Assistant Notes

**When helping users with this guide:**

1. **Pace appropriately:** Don't overwhelm beginners. Break complex steps into smaller chunks.

2. **Adapt to technical level:** 
   - Beginners: Provide exact commands, explain what each does
   - Advanced users: Can skip explanations, provide just the commands

3. **Platform-specific help:** Tailor path formats and commands to their OS and container platform

4. **Validate understanding:** After each phase, ask if they successfully completed it before moving on

5. **Troubleshooting mindset:** If something fails, help debug systematically:
   - Check logs
   - Verify configuration
   - Test incrementally

6. **Security emphasis:** Remind users about:
   - Strong passwords
   - Secure SECRET_KEY storage
   - HTTPS for internet-facing instances
   - Regular backups
   - Never exposing admin ports (81, 9000, etc.) to internet

7. **Encourage questions:** Make it clear users can ask for clarification at any point

8. **Celebrate milestones:** Acknowledge when phases are completed successfully

9. **Privacy principles:** Remind users that Nebulae is designed for privacy - no likes, no algorithms, just genuine connections

10. **Federation context:** Explain that federation allows different Nebulae instances to connect while each user maintains control of their own data

---

**End of AI Setup Guide**
