# Key Features

Nebulae provides a comprehensive set of social networking features with privacy and user control at the core.

---

## 📝 Posts & Content

### Text Posts
- Rich text with automatic link detection
- @mention system for tagging friends
- @everyone mentions for group/event posts
- Link previews for shared URLs

### Media Sharing
- Photo and video uploads
- Multiple media attachments per post
- Automatic thumbnail generation
- Image tagging (tag people in photos)
- Media-specific comments

### Privacy Levels
Every post can be set to:
- **Local** - Only visible to users on your node
- **Friends** - Visible to your friends (including on other nodes)
- **Public** - Visible to everyone
- **Group** - Only group members can see
- **Event** - Only event attendees can see

### Special Post Types
- **Reposts** - Share someone else's *Public* content to your timeline
- **Wall Posts** - Post to a friend's profile timeline
- **Location Check-ins** - Tag locations in posts
- **Polls** - Create interactive polls with multiple options

---

## 👥 Social Features

### Friends System
- Send and accept friend requests
- View mutual friends
- Friends list visible to friends
- Cross-node friendship (federated friends)

### Discovery
- **Discover Users** - Find users on your node and connected nodes as well as public pages on your node, connected nodes and discovered by 'word of mouth'
- **Discover Groups** - Browse available groups on your node, connected nodes and discovered by 'word of mouth'
- Hide items you're not interested in

### User Profiles
- Customizable profile pictures
- Display name separate from username
- Profile information fields (optional)
- Media gallery for photos/videos
- Timeline of posts

---

## 👪 Groups

- **All Groups are visible** - Anyone can request to join, but you can set rules and questions as a pre-joining requisite

### Group Features
- Group posts and timelines
- Member management (admins/moderators/members)
- Group profile with customizable info
- Group events
- Join request system with custom questions
- Group rules and approval workflow
- Friends in group visibility

### Group Administration
- Multiple admins and moderators
- Different permission levels
- Promote/demote members
- Remove members
- Edit group information
- Manage join requests

---

## 📅 Events

### Event Creation
- Create events from user profiles, groups, or public pages
- Set event title, date/time, location, and details
- Public or private events
- Event cover photos

### RSVP System
- Going / Maybe / Not Going responses
- View attendee lists
- Invite specific users
- Event announcements for public pages

### Event Features
- Event timeline for posts
- @everyone mentions for announcements
- Update notifications when event details change
- Event discovery for public events

---

## 📄 Public Pages

### Page Types
Separate from personal profiles, public pages allow:
- Business/organization presence
- Community pages
- Public figures
- Content creators

### Page Features
- Followers instead of friends
- Post updates to followers
- Page-specific profile
- Event creation (public announcements)
- Cross-node visibility

---

## 🔔 Notifications

### Notification Types
- Comments on your posts
- Replies to your comments
- @mentions
- Friend requests (sent and accepted)
- Group invitations
- Group post notifications
- Event invitations
- Post reposts
- Photo tags
- Birthdays
- @everyone mentions

### Notification Channels
- **In-app notifications** - Bell icon with counter
- **Email notifications** - Customizable per type
- **Push notifications** - Browser notifications (opt-in)

---

## 🔒 Privacy & Security

### Privacy Controls
- Per-post privacy settings
- Profile information visibility control
- Media path isolation (your files stay yours)
- Email addresses never exposed to remote nodes
- Block problematic users
- Hide specific posts/comments

### Content Control
- Snooze friends temporarily (30d)
- Disable comments on posts
- Untag or unmention yourself from a post, comment or photo

---

## 📸 Media Management

### Media Albums
- Create albums from profile media
- Add descriptions
- Media-specific mixed privacy settings - an album can have media with different privacy settings and therefore tailored to your audience.

### Media Gallery
- Browse all your uploaded photos
- Search and filter media
- Comment on individual photos
- Tag people in photos
- Lazy loading for performance

---

## 👨‍👩‍👧 Parental Controls

For users under 16 - this needs to be configured on the **Admin Dashboard > Manage Users**

### Approval System
- Parents must approve:
  - Friend requests (sent or received)
  - Group memberships
  - Event attendance
  - Media and Post Tags
  - Post creation (Possible future enhancement)
  

### Parent Dashboard
- View pending approvals
- Approve or deny
- Monitor child's activity
- Multiple parents can be assigned

---

## 🔗 Federation Features

### Multi-Node Communication
- HTTPS-based federation
- HMAC-SHA256 request signing
- Shared secrets for node pairing

### Federation Types
- **Full Node Connection** - See all users, groups, pages from a node
- **Targeted Subscription** - Subscribe to specific groups/events/pages without full connection

### Privacy in Federation
- Control what content crosses node boundaries
- Per-post federation settings
- PUID system protects private information
- You choose which nodes to trust

---

## ⚙️ User Settings

### Account Settings
- Change display name
- Update password
- Enable two-factor authentication (TOTP)
- Session management (view and revoke sessions)
- Account export (coming soon)

### Notification Preferences
- Granular email notification controls
- Push notification settings
- Notification frequency settings

### Interface Settings
- Dark mode / Light mode
- Language preferences (coming soon)

---

## 📊 Polls

### Poll Features
- 2-10 poll options
- Allow multiple answers
- Allow users to add new options
- See who voted for what
- Poll results visualization

---

## 🎨 User Experience

### Modern Interface
- Responsive design (mobile, tablet, desktop)
- Dark mode support
- Smooth animations
- Lazy loading
- Progressive Web App (PWA) support

### Performance
- Thumbnail generation for fast loading
- Pagination for long feeds
- Efficient database queries with indexing
- Compressed media delivery

---

## 🛠️ Developer Features

### Open Source
- Full source code available
- AGPL-3.0 license
- Self-hostable
- Extensible architecture

### Tech Stack
- Python/Flask backend
- SQLite database with WAL mode
- Vanilla JavaScript frontend
- Docker deployment
- Tailwind CSS styling

---

## Coming Soon 🚀

Features in development/consideration:
- Stories/temporary posts
- Advanced search
- Multi-language support
- Parental approval of posts

---

[← Back to Overview](introduction.md) | [Architecture →](architecture.md)
