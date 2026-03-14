<img width="192" height="192" alt="logo_900x900" src="https://github.com/user-attachments/assets/f034237e-351a-4e66-aacb-6eb44cc2f157" />


# **A privacy-focused, self-hosted, federated social media platform.**

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://hub.docker.com)
[![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)](https://www.python.org)

Remember when social media was about connecting with friends, not algorithms and ads? In the late 00's, early 10's? Yeah me too. It annoys me when I scroll through my Facebook feed and its all 'sponsored' posts, 'follow suggestions', outright adverts. I can scroll for a good minute or two before I see a post from someone (or a group) I actually know. And then I find the post was 6 days ago! Let's face it, mainstream social media now is all about keeping you locked to that screen cnstantly feeding you suggestions, or tweaking what it shows you because you briefly paused from scrolling near a random advert you don't care about and now it thinks thats what you want to see more of! 
Nebulae attempts brings back that social media experience of before with modern privacy standards and using a decentralized federation method. Why decentralised? So YOU control your data. 


## **What is Nebulae?**

Nebulae is a federated social networking platform designed as an alternative to algorithmic, corporate-controlled social media. It recreates the experience of early Facebook—focused on genuine connections with friends and family—while respecting your privacy and giving you complete control over your data.

### **Core Principles**

- Privacy First: Your data stays on your node. No corporate data mining, no tracking, no selling your information.
- Chronological, Always: See posts in the order they were made. No algorithm deciding what you should see.
- Federation: Connect your node with friends' nodes to share content while maintaining autonomy.
- User Control: You choose what to see, when to see it, and who can see your content.
- No Ads, Ever: Social media without the mining of your data for someone else's gain.
- Free: No one should make money from your social media data, nor charge you for using Nebulae. (If you do see that, don't download it, get it from here!)
- A node is your home. Each node in Nebulae should ideally represent a household - therefore you know who is on your node, you know who your admin is, you know who has an account, you know who can see your data.
- No 'like' button. Social media shouldn't be about farming for likes or 'content engagement'. Social media should be seeing what your friends and interests are up to. 


## **Features**
### **Core Social Features**

- Chronological Feed: Posts appear in time order. No mysterious algorithms ditacting what you should see.
- User Profiles: You, just you. Profiles with media galleries, albums, your posts and posts made your timeline by friends.
- Public page profiles: Own a business? A charity? Actually a fairly famous person? Then create a public facing page where people can follow you and get all the latest updates.
- Discover Friends: Connect with people across both your local and connected nodes.
- Groups: Create groups about your interests with member management, media, events. All the things you expect to see in a group.
- Events: Organize gatherings with RSVP tracking and attendee lists. Events can be by a user, in a group or a public page. 
- Media: Share photos and videos with automatic thumbnail generation in a post/media gallery to improve load times in feeds. Media stays on your node!
- Posts: Create Local, friends or public posts (event attendees or group only for events and groups respectively) Comment and reply to those posts, just like you have been used to doing.
- Polls: Create interactive polls with multiple options and settings.
- User Tagging: Tag people in posts and photos.
- Direct Messages: Message a user or create a multiple user chat.

### **Privacy & Safety**

- Granular Privacy Controls: Choose who sees each post. (local, friends, public, groups)
- UUIDs: Everything, where possible, is hidden behind a UUID. So emails, user names and file directories (to look at media) are hidden by a UUID.
- Parental Controls: Parent-managed accounts for users under 16. Approve tags in posts and media, approve DM incoming and outgoing requests, approve incoming and outgoing friend requests.  
- Content Moderation: Hide posts, snooze users, block problematic accounts. Admins can disconnect problematic nodes entirely from their local node.  
- No Tracking: No analytics, no behavioral profiling, no data selling.

### **Federation & Self-Hosting**

- True Federation: Multiple independent nodes communicate via HTTPS.
- Self-Hosted: Run your own instance on Docker/Kubernetes with full control.
- Docker Deployment: Simple setup with Docker Compose or Kubernetes Manifest file.
- Media Path Linking: Connect existing photo libraries without duplication, media folders are read-only. Except a dedicated uploaded media folder where you can upload direct from your device.
- HMAC Authentication: Secure node-to-node communication.
- Targeted subscriptions: Node connections can either be a full node connection where admins share keys. Allowing you see all users, groups and pages on that node. Or a Targeted Subcription, where upon joining a group or following a page/event. A node connection is established for just THAT purpose. These can be upgraded later to a full connection. 

### **Modern Features**

- Dark Mode!
- PWA: Install as a mobile app!
- Push Notifications: Stay updated with VAPID notifications.
- Email Notifications: Email notifications can be turned on or off by category. 
- Real-time Updates: See new content as it arrives with periodic message and post polling.  
- Lazy Loading: Smooth, performant feed scrolling, reduced size thumbnails, all to reduce bandwidth. 

## **Quick Start**
### **Prerequisites**

- Docker/Docker for Desktop and Docker Compose
- Or a Kubernetes instance
- A Mini-PC, NAS, workstation, Raspberry Pi 4 or 5
- A DDNS domain name for normal ISP setups or a DNS domain name with static IP address (for node federation)
- Basic familiarity with command line

For detailed setup instructions, see [DOCKER_SETUP.md](DOCKER_SETUP.md).

## **Federation**

Nebulae uses a federated architecture where multiple independent nodes can connect and share content:

- Node Autonomy: Each node is independently operated.
- HTTPS Communication: Secure connections between nodes.
- HMAC Authentication: Cryptographically signed requests.
- Privacy Protection: UUIDs hide sensitive user data.
- Selective Sharing: Users control what crosses node boundaries.

### **How Federation Works**

- Users can friend people on other Nebulae nodes.
- When you post with "public" or "friends" privacy, your node sends the content to relevant remote nodes.
- Remote nodes verify the request signature and store the post.
- Users on remote nodes see your content in their feeds.
- Comments, and interactions flow back through federation.
- Media stays on your Nebulae node.

## **Security & Privacy**

### **What We Do**

- ✅ End-to-end HTTPS for all federation
- ✅ HMAC-SHA256 request signing
- ✅ Password hashing with werkzeug.security
- ✅ CSRF protection on all forms
- ✅ Content Security Policy headers
- ✅ Session management with secure tokens
- ✅ Media path isolation

### **What We Don't Do**

- ❌ No user tracking or profiling
- ❌ No behavioral data collection
- ❌ No algorithm manipulation
- ❌ No selling user data
- ❌ No advertising platform
- ❌ No facial recognition
- ❌ No 'Like' button.

## **Contributing**

I welcome contributions! Nebulae is built on the principle that social media should be free, open source and not there to mine your data.

### **Ways to Contribute**

- Report bugs via GitHub Issues. It's early days there are bound to be a few.
- Suggest features or improvements.
- Improve documentation.
- Submit pull requests.
- Help with federation testing.
- Design contributions welcome.

### Development Setup

Clone the repository

`bash git clone https://github.com/locqust/Nebulae.git`

`cd Nebulae`

Install dependencies

`bash pip install -r requirements.txt`

Run locally

`bash python app.py`

Visit http://localhost:5000 to see your development instance.

## **Roadmap**

### **Planned Features**

 - [ ] Multi-language support
 - [ ] Export/Import tools to move your profile/public page/group to a new node (Aspirational, this might not be an easy thing to do)
 - [x] Direct Messages
 - [x] Memories
 - [x] Feelings


## **Known Issues**

See our Issues page for current bugs and feature requests.

## **License**

Nebulae is released under the GNU Affero General Public License v3.0 (AGPL-3.0).
This license ensures that:

- Users of federated instances have access to the source code
- Any modifications made to the software must be shared
- The software remains free and open for everyone

See LICENSE for full details.

## **Support & Community**

- Documentation: [Github Docs](https://locqust.github.io/Nebulae/)
- Discord: [Nebulae](https://discord.gg/WrmWSm94WK)
- GitHub Issues: Report bugs or request features

## **Production Deployment Notes**

Before deploying to production:

- Use HTTPS: Configure a reverse proxy (nginx/Caddy) with SSL certificates
- Secure Your Keys: Generate strong SECRET_KEY and keep it secret
- Regular Backups: Backup your SQLite database regularly
- Monitor Resources: Check disk space for media uploads
- Update Regularly: Keep your Docker image updated
- Configure Email: Set up SMTP for notifications
- Media Paths: Plan your user media volume strategy

See DOCKER_SETUP.md for detailed production deployment instructions.

