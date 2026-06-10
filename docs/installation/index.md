# Installation

Nebulae can be installed in several ways depending on your environment and preferences. All methods result in the same application — pick whichever fits your setup best.

!!! tip "Not sure which to choose?"
    - **Linux server or desktop** → [Linux (Native)](linux.md)
    - **Raspberry Pi** → [Raspberry Pi](raspberry-pi.md)
    - **Docker, Portainer, Podman, or Kubernetes** → [Docker / Podman](container.md)
    - **Windows or macOS** → Use [Docker / Podman](container.md) for now

---

## Choose Your Installation Method

<div class="grid cards" markdown>

-   :fontawesome-brands-linux: **Linux (Native)**

    ---

    Run Nebulae directly on any Linux server or desktop without Docker. Uses Gunicorn + systemd for production-quality reliability.

    Best for: Ubuntu/Debian servers, pizza-box home servers, anyone who'd rather not run Docker.

    [:octicons-arrow-right-24: Linux install guide](linux.md)

-   :material-raspberry-pi: **Raspberry Pi**

    ---

    Native install optimised for Pi 4 and Pi 5. Same approach as Linux but with Pi-specific notes on dependencies and performance tuning.

    Best for: Low-power always-on home servers.

    [:octicons-arrow-right-24: Raspberry Pi install guide](raspberry-pi.md)

-   :fontawesome-brands-docker: **Docker / Podman**

    ---

    The container-based install. Pre-built images for `amd64` and `arm64` are available from GHCR. Supports Docker Compose, Portainer, Podman, and Kubernetes.

    Best for: Anyone already running Docker, NAS devices, cloud VMs.

    [:octicons-arrow-right-24: Container install guide](container.md)

</div>

---

## Prerequisites Common to All Methods

Regardless of how you install Nebulae, you will need:

- A **domain name or static IP address** that other nodes (and your users) can reach. For home users, a free dynamic DNS service such as [DuckDNS](https://www.duckdns.org/) works well.
- **HTTPS** for federation. Nebulae nodes sign and verify requests; HTTP-only deployments cannot federate with other nodes. [Nginx Proxy Manager](https://nginxproxymanager.com/) is the easiest way to get a Let's Encrypt certificate if you don't have one already.
- Enough storage for your media. SQLite and the application code are tiny; your photos and videos are not.

---

## After Installation

Once Nebulae is running, head to the [Post-Install Setup](../admin-guide/post-install.md) guide to:

- Change the default admin password
- Create user accounts
- Configure media paths
- Set up email and push notifications
- Connect to other Nebulae nodes
