<img width="192" height="192" alt="logo_900x900" src="https://github.com/user-attachments/assets/f034237e-351a-4e66-aacb-6eb44cc2f157" />


# **A privacy-focused, federated social media platform that puts you back in control.**

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://hub.docker.com)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org)

Remember when social media was about connecting with friends, not algorithms and ads? Nebulae brings back that authentic experience with modern privacy standards and decentralized federation.


## **🌟 What is Nebulae?**

Nebulae is a federated social networking platform designed as an alternative to algorithmic, corporate-controlled social media. It recreates the experience of early Facebook—focused on genuine connections with friends and family—while respecting your privacy and giving you complete control over your data.

### **Core Philosophy**

- Privacy First: Your data stays on your node. No corporate data mining, no tracking, no selling your information.
- Chronological, Always: See posts in the order they were made. No algorithm deciding what you should see.
- Federation: Connect your node with friends' nodes to share content while maintaining autonomy.
- User Control: You choose what to see, when to see it, and who can see your content.
- No Ads, Ever: Social media without the surveillance capitalism business model.
- Free: No one should make money from your social media data, nor charge you for using Nebulae. 


## **✨ Features**
### **Core Social Features**

- Chronological Feed: Posts appear in time order—no mysterious algorithms
- User Profiles: Customizable profiles with media galleries and albums
- Friends System: Connect with people across federated nodes
- Groups: Create groups with member management
- Events: Organize gatherings with RSVP tracking and attendee lists
- Rich Media: Share photos, videos with automatic thumbnail generation
- Comments & Replies: Threaded conversations on posts and media
- Polls: Create interactive polls with multiple options and settings
- User Tagging: Tag people in posts and photos

### **Privacy & Safety**

- Granular Privacy Controls: Choose who sees each post (local, friends, public, groups)
- PUID System: Public User IDs protect sensitive data like email addresses
- Parental Controls: Parent-managed accounts for users under 16
- Content Moderation: Hide posts, snooze users, block problematic accounts
- No Tracking: No analytics, no behavioral profiling, no data selling

### **Federation & Self-Hosting**

- True Federation: Multiple independent nodes communicate via HTTPS
- Self-Hosted: Run your own instance with full control
- Docker Deployment: Simple setup with Docker Compose
- Media Path Linking: Connect existing photo libraries without duplication
- HMAC Authentication: Secure node-to-node communication

### **Modern Features**

- Dark Mode: System-aware theme switching
- Mobile Responsive: Optimized for phones, tablets, and desktops
- PWA Support: Install as a mobile app
- Push Notifications: Stay updated with VAPID notifications
- Email Notifications: Rich HTML email digests
- Real-time Updates: See new content as it arrives
- Lazy Loading: Smooth, performant feed scrolling

## **🚀 Quick Start**
### **Prerequisites**

- Docker and Docker Compose
- A domain name or static IP address (for federation)
- Basic familiarity with command line

For detailed setup instructions, see [DOCKER_SETUP.md](DOCKER_SETUP.md).


## **🔧 Technology Stack**

- Backend: Python 3.9+ with Flask
- Database: SQLite with WAL mode
- Frontend: Vanilla JavaScript (modular architecture)
- Styling: CSS/Tailwind CSS
- Server: Gunicorn with multiple workers
- Deployment: Docker & Docker Compose
- Icons: SVG Heroicons


## **🌐 Federation**

Nebulae uses a federated architecture where multiple independent nodes can connect and share content:

- Node Autonomy: Each node is independently operated
- HTTPS Communication: Secure connections between nodes
- HMAC Authentication: Cryptographically signed requests
- Privacy Protection: PUIDs hide sensitive user data
- Selective Sharing: Users control what crosses node boundaries

### **How Federation Works**

- Users can friend people on other Nebulae nodes
- When you post with "public" or "friends" privacy, your node sends the content to relevant remote nodes
- Remote nodes verify the request signature and store the post
- Users on remote nodes see your content in their feeds
- Comments, reactions, and interactions flow back through federation
- Media stays on your Nebulae node

## **🛡️ Security & Privacy**

### **What We Do**

- ✅ End-to-end HTTPS for all federation
- ✅ HMAC-SHA256 request signing
- ✅ Password hashing with werkzeug.security
- ✅ CSRF protection on all forms
- ✅ Content Security Policy headers
- ✅ No third-party trackers or analytics
- ✅ No data selling or advertising
- ✅ Session management with secure tokens
- ✅ Media path isolation

### **What We Don't Do**

- ❌ No user tracking or profiling
- ❌ No behavioral data collection
- ❌ No algorithm manipulation
- ❌ No selling user data
- ❌ No advertising platform
- ❌ No facial recognition
- ❌ No shadow profiles


## **🤝 Contributing**

We welcome contributions! Nebulae is built on the principle that social media should serve users, not corporations.

### **Ways to Contribute**

- 🐛 Report bugs via GitHub Issues
- 💡 Suggest features or improvements
- 📝 Improve documentation
- 🔧 Submit pull requests
- 🌍 Help with federation testing
- 🎨 Design contributions welcome

### Development Setup

Clone the repository

`bash git clone https://github.com/locqust/Nebulae.git`

`cd Nebulae`

Install dependencies

`bash pip install -r requirements.txt`

Run locally

`bash python app.py`

Visit http://localhost:5000 to see your development instance.

## **📋 Roadmap**

### **Planned Features**

 - Multi-language support
 - Export/Import tools to move to a new node

### **Proposed Features**

 - Stories
 - Memories




## **🐛 Known Issues**

See our Issues page for current bugs and feature requests.

## **📜 License**

Nebulae is released under the GNU Affero General Public License v3.0 (AGPL-3.0).
This license ensures that:

- Users of federated instances have access to the source code
- Any modifications made to the software must be shared
- The software remains free and open for everyone

See LICENSE for full details.

## **🙏 Acknowledgments**

Nebulae is built with love and frustration—love for what social media could be, and frustration with what it has become. This project stands on the shoulders of:

- The free and open-source software community
- Everyone who believes privacy is a fundamental right
- People tired of algorithmic manipulation
- Those who remember when "social network" meant connecting with friends


## **📞 Support & Community**

- Documentation: Coming soon
- Discord: Coming soon
- GitHub Issues: Report bugs or request features

## **⚠️ Production Deployment Notes**

Before deploying to production:

- Use HTTPS: Configure a reverse proxy (nginx/Caddy) with SSL certificates
- Secure Your Keys: Generate strong SECRET_KEY and keep it secret
- Regular Backups: Backup your SQLite database regularly
- Monitor Resources: Check disk space for media uploads
- Update Regularly: Keep your Docker image updated
- Configure Email: Set up SMTP for notifications
- Media Paths: Plan your user media volume strategy

See DOCKER_SETUP.md for detailed production deployment instructions.

## **💭 Philosophy**

"The internet was supposed to connect us. Instead, it's been weaponised to extract our attention, manipulate our behaviour, and sell our data. Nebulae is a small step back toward what social media should have been: a tool for genuine human connection, not corporate profit."

Built by someone who got tired of watching social media become increasingly hostile to users.

Made with ❤️ and a healthy distrust of algorithms

*Nebulae: Your data, your rules, your connections.*
