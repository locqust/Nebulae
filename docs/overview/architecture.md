# Architecture Overview

Understanding Nebulae's technical architecture helps administrators and developers work with the platform effectively.

---

## System Overview

Nebulae is a **monolithic web application** built with:
- Python/Flask backend
- SQLite database
- Vanilla JavaScript frontend
- Docker containerization

### Design Principles

1. **Privacy by Design** - Email addresses never leave the node
2. **Simplicity** - Single-binary deployment, minimal dependencies
3. **Performance** - Efficient database queries, lazy loading, caching
4. **Portability** - Runs anywhere Docker runs

---

## Technology Stack

### Backend

#### Flask Web Framework
- **Version**: Python 3.9+
- **WSGI Server**: Gunicorn (production)
- **Purpose**: Handle HTTP requests, routing, business logic

#### Database
- **Engine**: SQLite with WAL mode
- **Why SQLite?**
  - Zero configuration
  - Single-file database
  - ACID compliant
  - Perfect for small-to-medium deployments
  - Easy backups
- **WAL Mode**: Enables concurrent reads during writes

#### Key Libraries
- **Werkzeug**: Security utilities (password hashing, secure sessions)
- **Jinja2**: Template engine
- **Pillow**: Image processing and thumbnails
- **pywebpush**: Push notifications
- **cryptography**: HMAC signatures for federation

### Frontend

#### No Framework Approach
- **Vanilla JavaScript** - No React, Vue, or Angular
- **Modular Architecture** - Organized into `App` namespace

#### Styling
- **Tailwind CSS**: Utility-first CSS framework
- **Custom CSS**: Dark mode, animations, responsive design
- **SVG Icons**: Heroicons for UI elements

#### Progressive Web App (PWA)
- **Service Worker**: Offline support
- **Manifest**: Install as mobile app
- **Push API**: Browser notifications

### Infrastructure

#### Docker
- **Image**: Python 3.9-slim-bookworm base
- **Multi-stage**: Optimized build process
- **Volumes**: Persistent data storage
- **Networks**: Isolated container networking

#### Gunicorn
- **Workers**: 4 (adjustable)
- **Threads**: 2 per worker
- **Timeout**: 120 seconds
- **Binding**: 0.0.0.0:5000

---

## Application Structure

### Directory Layout

```
nebulae/
├── app.py                      # Application entry point
├── schema.sql                  # Database schema
├── requirements.txt            # Python dependencies
│
├── routes/                     # Flask blueprints (controllers)
│   ├── main.py                # Home feed, profiles
│   ├── auth.py                # Login, logout, registration
│   ├── friends.py             # Friend management
│   ├── groups.py              # Group features
│   ├── events.py              # Event management
│   ├── admin.py               # Admin panel
│   ├── federation.py          # Federation endpoints
│   ├── notifications.py       # Notification system
│   └── settings.py            # User settings
│
├── db_queries/                # Database operations (models)
│   ├── posts.py              # Post CRUD
│   ├── users.py              # User management
│   ├── groups.py             # Group queries
│   ├── friends.py            # Friend relationships
│   ├── events.py             # Event queries
│   ├── notifications.py      # Notification queries
│   └── federation.py         # Federation data
│
├── utils/                     # Utility functions
│   ├── federation_utils.py   # Federation helpers
│   ├── notifications.py      # Notification logic
│   ├── email.py              # Email sending
│   ├── image.py              # Image processing
│   └── text_processing.py    # Mention parsing
│
├── templates/                 # Jinja2 HTML templates (views)
│   ├── index.html           # Home feed
│   ├── user_profile.html    # User profile
│   ├── group_profile.html   # Group page
│   ├── event_profile.html   # Event page
│   └── _*.html              # Template partials
│
└── static/                    # Frontend assets
    ├── css/
    │   └── styles.css        # Custom styles
    ├── js/
    │   ├── app.js           # Main JavaScript
    │   ├── pwa.js           # Service worker
    │   └── media_carousel.js # Media viewer
    └── icons/               # PWA icons
```

---

## Data Architecture

### Database Schema

#### Core Tables

**users**
- Stores all users (local and remote)
- `puid`: Public User ID (for federation)
- `hostname`: NULL for local, domain for remote
- `user_type`: user, admin, public_page, remote

**posts**
- All posts across the platform
- `cuid`: Content Unique ID (globally unique)
- `privacy_setting`: local, friends, public, group, event
- `is_remote`: Boolean flag
- `is_repost`: For shared posts

**friends**
- Friendship relationships
- Symmetric: row exists for both directions
- Supports cross-node friendships

**groups**
- Group information
- `puid`: Group identifier
- Can be on any federated node

**events**
- Event information
- Linked to groups, users, or pages
- RSVP tracking in separate table

#### Federation Tables

**remote_nodes**
- Connected Nebulae instances
- Shared secrets for HMAC
- Connection status

**targeted_subscriptions**
- Specific group/event subscriptions
- Created automatically
- Lighter than full node connection

#### Support Tables

- **notifications**: User notification queue
- **sessions**: User login sessions
- **group_members**: Group membership
- **event_responses**: RSVP tracking
- **media_albums**: Photo albums
- **polls**: Interactive polls
- **parental_controls**: Parent-child relationships

### Key Relationships

```
users ─┬─> posts (author)
       ├─> groups (creator)
       ├─> events (creator)
       ├─> friends (both sides)
       └─> notifications (recipient)

posts ─┬─> comments
       ├─> post_media (attachments)
       ├─> polls
       └─> reactions

groups ─┬─> group_members
        ├─> posts (group timeline)
        └─> events (group events)
```

---

## Request Flow

### Typical User Request

1. **Browser** sends HTTP request
2. **Gunicorn** receives and passes to Flask
3. **Flask** routes to appropriate blueprint
4. **Blueprint** handles business logic
5. **db_queries** module queries database
6. **Template** renders HTML with data
7. **Response** sent back to browser

### Federation Request

1. **Remote node** signs request with HMAC
2. **Federation endpoint** receives request
3. **Signature verified** using shared secret
4. **Action processed** (e.g., create post)
5. **Database updated** with remote content
6. **Notifications created** for local users
7. **Response sent** to remote node

---

## Security Architecture

### Authentication

- **Session-based**: Flask sessions with secure cookies
- **Password hashing**: Werkzeug with pbkdf2:sha256
- **2FA**: TOTP (Time-based One-Time Password)

### Authorization

- **Role-based**: user, admin, moderator
- **Resource-level**: Post privacy settings
- **Parental controls**: Approval workflows

### Federation Security

1. **HTTPS Only**: TLS encryption in transit
2. **HMAC-SHA256**: Request signing
3. **Shared Secrets**: Node-to-node authentication
4. **PUID System**: Protect email addresses
5. **Per-request verification**: Every request authenticated

---

## Performance Considerations

### Database

- **Indexes**: On frequently queried columns
- **WAL Mode**: Concurrent reads
- **Connection pooling**: Reuse connections
- **Query optimization**: Efficient JOINs

### Media

- **Thumbnails**: Generated on upload
- **Lazy loading**: Load images as needed
- **Compression**: Reduce file sizes

### Frontend

- **Pagination**: Limit posts per page
- **Debouncing**: Rate-limit API calls
- **Caching**: Browser caching for static assets
- **Minification**: Compressed CSS/JS (production)

---

## Scalability

### Current Limitations

- Single-node deployment
- SQLite limitations (~10k users recommended)
- No horizontal scaling
- Single-threaded writes

### Scaling Options

For larger deployments:

1. **PostgreSQL**: Replace SQLite
2. **Redis**: Session storage, caching
3. **Object storage**: S3 for media
4. **CDN**: CloudFlare for static assets
5. **Load balancer**: Multiple app servers
6. **Queue system**: Celery for async tasks

---

## Extension Points

### Adding Features

1. **Routes**: Add new blueprints
2. **Database**: Modify schema.sql
3. **Queries**: Add to db_queries/
4. **Templates**: Create new views
5. **Frontend**: Extend App namespace

### API Development

Nebulae doesn't have a REST API, but could add:
- API authentication (OAuth2)
- JSON responses
- Rate limiting
- API versioning

---

## Development Environment

### Local Setup

```bash
# Clone repository
git clone https://github.com/locqust/Nebulae
cd Nebulae

# Install dependencies
pip install -r requirements.txt

# Initialize database
python -c "from db_utils import init_db; init_db()"

# Run development server
python app.py
```

### Development Tools

- **Flask Debug Mode**: Automatic reloading
- **SQLite Browser**: View database
- **Browser DevTools**: Frontend debugging
- **Docker Compose**: Local federation testing

---

## Deployment Architecture

### Production Stack

```
Internet
    ↓
Reverse Proxy (nginx/Caddy)
    ↓ HTTPS
Docker Container (Nebulae)
    ↓
Gunicorn (WSGI Server)
    ↓
Flask Application
    ↓
SQLite Database
```

### Recommended Setup

- **Reverse Proxy**: Handle SSL, rate limiting
- **Docker**: Isolated environment
- **Systemd**: Auto-restart on failure
- **Backups**: Automated daily backups
- **Monitoring**: Log aggregation

---


## Related Documentation

- [Installation Guide](../admin-guide/installation.md)
- [Federation Overview](../federation/overview.md)
- [Database Schema](database-schema.md)

---

[← Features](features.md) | [Quick Start →](quick-start.md)
