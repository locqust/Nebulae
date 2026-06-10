# Raspberry Pi

Nebulae runs natively on Raspberry Pi 4 and Pi 5 — no Docker required. This guide covers Pi-specific considerations on top of the standard [Linux install](linux.md). If you haven't read that page yet, start there; this page only documents where the Pi differs.

!!! info "Supported hardware"
    - **Raspberry Pi 4** (2GB RAM minimum, 4GB recommended)
    - **Raspberry Pi 5** (all variants)
    - **Recommended OS:** Raspberry Pi OS Lite (64-bit) or Ubuntu Server 22.04/24.04 for Pi

    32-bit OS builds are not recommended. The `cryptography` package (used for Web Push) has historically had build issues on 32-bit ARM.

---

## Pi-Specific Prerequisites

Before following the [Linux install guide](linux.md), take care of these Pi-specific steps.

### Use a Good SD Card or SSD

SQLite performs many small writes. A low-quality SD card will be a bottleneck and may corrupt the database under heavy write load. Options in order of preference:

1. **USB SSD** (best — fast and durable)
2. **USB HDD** (fine for low traffic)
3. **A rated SD card** (A2 spec minimum — look for the A2 symbol on the card)

If using a USB drive, make sure to [set it as the boot device](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#usb-mass-storage-boot) rather than SD.

### Enable 64-bit OS

On Raspberry Pi OS, confirm you're running 64-bit:

```bash
uname -m
```

You want `aarch64`. If you see `armv7l` you're on 32-bit and should reinstall with the 64-bit image.

### Update First

```bash
sudo apt update && sudo apt full-upgrade -y
sudo reboot
```

A fresh Pi image is often months behind — don't skip this.

---

## Install Dependencies

The Pi needs one extra package compared to a standard Linux install:

```bash
sudo apt install -y \
    python3 python3-pip python3-venv python3-dev \
    sqlite3 \
    libffi-dev libssl-dev libjpeg-dev \
    git nginx \
    libopenjp2-7
```

`libopenjp2-7` is required by Pillow on ARM for JPEG 2000 support. Without it, certain image operations will raise a warning (or fail silently).

---

## Follow the Linux Guide

From here, follow the [Linux install guide](linux.md) exactly — creating the system user, cloning the repo, setting up the venv, configuring the environment file, and creating the systemd service are all identical.

The only recommended change is to the Gunicorn worker count (see below).

---

## Pi-Specific Gunicorn Tuning

The standard Linux guide uses `--workers 2 --threads 4`. On a Pi 4 with 4GB RAM this is fine. On a Pi 4 with 2GB, or if you're running other services on the same Pi, drop to:

```ini
ExecStart=/opt/nebulae/venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --worker-class gthread \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    "app:app"
```

One worker with four threads is plenty for a family-scale Nebulae instance and keeps RAM usage well under 200MB.

---

## SQLite WAL Mode on SD Card

Nebulae enables WAL mode automatically on first run, which is good — WAL is much gentler on flash storage than the default journal mode. No action needed, just be aware it's there and don't manually change the journal mode.

---

## Keeping the Pi Cool

Nebulae is not particularly CPU-intensive at rest, but during initial media scans or heavy federation activity it will work the Pi. A heatsink is recommended; active cooling (fan) is recommended for Pi 4 in an enclosure.

The Pi 5 has an active cooler available from Raspberry Pi Ltd — worth getting if you're running 24/7.

---

## Static IP / DDNS

For a home Pi server you'll want either:

- A **static local IP** assigned by your router (usually via MAC address reservation in your router's DHCP settings)
- A **DDNS service** such as [DuckDNS](https://www.duckdns.org/) for the public-facing hostname

If your ISP gives you a dynamic public IP (most do), set up a DDNS updater. DuckDNS provides a simple cron-based updater:

```bash
# Create update script
mkdir -p ~/duckdns
echo "url=\"https://www.duckdns.org/update?domains=YOURSUBDOMAIN&token=YOURTOKEN&ip=\" | curl -k -o ~/duckdns/duck.log -K -" > ~/duckdns/duck.sh
chmod +x ~/duckdns/duck.sh

# Add to crontab (updates every 5 minutes)
crontab -e
# Add this line:
*/5 * * * * ~/duckdns/duck.sh >/dev/null 2>&1
```

---

## Port Forwarding

For federation to work, your Pi needs to be reachable from the internet on port 443 (HTTPS). In your router:

1. Find **Port Forwarding** (sometimes under NAT or Virtual Servers)
2. Forward external port **443** → your Pi's local IP, port **443**
3. You only need 443 — Nginx handles HTTP→HTTPS redirects internally

!!! tip "Nginx Proxy Manager users"
    If you're already running Nginx Proxy Manager on the same network, point it at `http://PI_IP:5000` and let NPM handle TLS termination. In that case you don't need Certbot on the Pi itself.

---

## Monitoring

A couple of useful commands to keep an eye on your Pi:

```bash
# CPU temperature
vcgencmd measure_temp

# Memory usage
free -h

# Disk usage
df -h

# Nebulae logs
sudo journalctl -u nebulae -f
```

If the temperature regularly exceeds 80°C under load, add cooling.

---

## Troubleshooting

**`pip install` fails on `cryptography` with a compiler error**

Make sure you're on a 64-bit OS (`uname -m` → `aarch64`) and that build deps are installed:

```bash
sudo apt install -y libffi-dev libssl-dev python3-dev build-essential
```

**Slow first startup**

The first time Nebulae starts it initialises the database and runs migrations. On an SD card this can take 20–30 seconds. Subsequent starts are much faster.

**Out of memory**

If Nebulae is killed by the OOM killer (`sudo journalctl -u nebulae | grep -i kill`), reduce workers to 1 and threads to 2, or upgrade to a Pi with more RAM.

**Federation isn't working from outside the network**

Check that port 443 is forwarded correctly and that your DDNS hostname resolves to your public IP:

```bash
curl https://api.ipify.org   # Your public IP
nslookup yournode.duckdns.org  # Should match
```
