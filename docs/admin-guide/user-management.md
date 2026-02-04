# User Management

This guide covers managing users on your Nebulae instance as an administrator.

---

## Accessing User Management

1. Log in as admin
2. Navigate to **Admin Panel**
3. Click **Manage Users**

---

## Adding Users

### Step 1: Click "Add New User"

From the Manage Users page, click the **Add New User** button.

### Step 2: Fill in User Details

| Field | Description | Notes |
|-------|-------------|-------|
| **Username** | User's email address | Used for login, never shared with remote nodes |
| **Password** | Initial password | User can change this later |
| **Display Name** | Public-facing name | What other users see |
| **Date of Birth** | User's birthdate | ⚠️ Cannot be changed after creation |

### Step 3: Create the User

Click **Add User** to create the account.

The user can now log in with:
- Username: (the email you entered)
- Password: (the password you set)

---

## Password Management

### Resetting User Passwords

1. Go to **Manage Users**
2. Find the user in the list
3. Click **Actions → Reset Password**
4. Enter new password
5. Confirm new password
6. Click **Reset Password**

The user will be able to log in with the new password immediately.

### Password Requirements

Passwords must meet these criteria:
- Minimum 8 characters
- At least one uppercase letter
- At least one lowercase letter
- At least one number
- At least one special character

---

## Changing Usernames

If a user needs to change their email address/username:

1. Go to **Manage Users**
2. Find the user
3. Click **Actions → Change Username**
4. Enter the new username (email address)
5. Click **Change Username**

⚠️ **Important:** The user will need to use the new username to log in.

---

## Media Path Configuration

Users cannot upload or browse media without configured media paths.

### Types of Media Paths

1. **Read-Only Media** (`user_media`) - Browse existing photos
2. **Upload Directory** (`user_uploads`) - Save new uploads

### Configuring Media Paths

#### Step 1: Set Up Docker Volumes

First, ensure volumes are mounted in `docker-compose.yml`:

```yaml
volumes:
  - /home/bob/Photos:/app/user_media/bob_media:ro
  - /home/bob/Uploads:/app/user_uploads/bob_uploads
```

#### Step 2: Configure in Admin Panel

1. Go to **Manage Users**
2. Find the user
3. Click **Actions → Set Media Path**
4. Enter paths:
   - **Read-only media path**: `/app/user_media/bob_media`
   - **Upload path**: `/app/user_uploads/bob_uploads`
5. Click **Save**

### Path Requirements

- Paths must be **inside the container** (not host paths)
- Read-only paths should match the `:ro` volume mounts
- Upload paths must be writable (no `:ro` flag)

---

## Parental Controls

For users under 16 years old (or your region's age requirement):

### Enabling Parental Controls

1. Go to **Manage Users**
2. Find the child user
3. Click **Actions → Manage Parental Controls**
4. Toggle **Enable Parental Controls**
5. Click **Add Parent**
6. Select parent username from dropdown
7. Click **Save Changes**

### What Parents Control

When parental controls are enabled, parents must approve:
- ✅ Friend requests (sent and received)
- ✅ Group join requests
- ✅ Event RSVPs
- ✅ Post creation
- ✅ Media uploads
- ✅ Comments on others' posts

### Multiple Parents

You can assign multiple parents. Any parent can approve or deny requests.

### Parent Dashboard

Parents can access their dashboard from:
**Profile → Settings → Parental Dashboard**

From here they can:
- View pending approval requests
- Approve or deny with explanations
- See their children's activity

---

## Deleting Users

⚠️ **Warning:** User deletion is permanent and cannot be undone!

### What Gets Deleted

- User account and profile
- All posts and comments by the user
- Media uploaded by the user
- Group memberships
- Event RSVPs
- Friend connections
- Notifications

### Deletion Process

1. Go to **Manage Users**
2. Find the user
3. Click **Actions → Delete User**
4. Confirm the deletion

### Deletion Behavior

- **Local users**: Completely removed from your node
- **Federated content**: Other nodes are notified to remove the user's content
- **Media files**: Removed from storage

---

## Viewing User Information

Click on a username in the Manage Users list to view:

- User ID (PUID)
- Account creation date
- Last login
- User type (user, admin, public_page, remote)
- Hostname (for remote users)
- Age and birthdate
- Media path configuration
- Parental control status

---

## User Types

### Regular Users
- Standard user accounts
- Can post, friend, join groups
- Subject to parental controls if under 16

### Admin Users
- Has access to admin panel
- Can manage all users
- Can create groups and public pages
- Not subject to parental controls

### Public Pages
- Special account type for organizations
- Followers instead of friends
- Can create public events
- See [Public Pages Management](public-pages.md)

### Remote Users
- Users from federated nodes
- Created automatically through federation
- Cannot be edited on your node
- Will show originating hostname

---

## Session Management

### Viewing Active Sessions

For security, you can view a user's active sessions:

1. Go to user profile (as admin)
2. View **Active Sessions** section
3. See:
   - Device/browser information
   - Last activity time
   - IP address (if available)

### Revoking Sessions

As admin, you cannot directly revoke user sessions. Users must manage their own sessions through:

**Profile → Settings → Security → Active Sessions**

However, changing a user's password will invalidate all their sessions, forcing them to log in again.

---

## Two-Factor Authentication

### Enabling 2FA for Users

Users must enable their own 2FA from:
**Profile → Settings → Security → Two-Factor Authentication**

As admin, you cannot enable/disable 2FA for users, but you can:

### Reset 2FA (if user loses access)

If a user loses access to their 2FA device:

1. Temporarily disable 2FA via database (requires SSH access)
2. Have user log in
3. Have user re-enable 2FA with new device

**Emergency 2FA Reset:**
```bash
docker exec -it nebulae sqlite3 /app/instance/nebulae.db
sqlite> UPDATE users SET totp_secret = NULL WHERE username = 'user@example.com';
sqlite> .quit
```

---

## Best Practices

### Account Creation

✅ **Do:**
- Use real email addresses for usernames
- Set strong initial passwords
- Configure media paths before users log in
- Enable parental controls for minors immediately

❌ **Don't:**
- Use simple/guessable passwords
- Forget to set date of birth (can't change later)
- Create accounts without media paths (users can't upload)

### Security

✅ **Do:**
- Encourage users to enable 2FA
- Regularly review active sessions
- Monitor for suspicious activity
- Use strong password requirements

❌ **Don't:**
- Share admin credentials
- Leave default admin password unchanged
- Ignore security notifications

### Privacy

✅ **Do:**
- Respect user privacy
- Only access user data when necessary
- Inform users of any data access
- Follow local privacy regulations

❌ **Don't:**
- Browse user's private posts without reason
- Share user information with third parties
- Monitor user activity without disclosure

---

## Troubleshooting

### User Can't Log In

1. Verify username (email) is correct
2. Reset password if needed
3. Check if 2FA is enabled
4. Verify account isn't suspended

### Media Not Showing

1. Check media path configuration
2. Verify Docker volume mounts
3. Check file permissions
4. Restart container if needed

### Parental Controls Not Working

1. Verify user's age (under 16)
2. Check parent assignments
3. Ensure parents have accounts
4. Verify parental controls are enabled

---

## Related Documentation

- [Public Pages Management](public-pages.md)
- [Group Management](group-management.md)
- [Configuration Guide](configuration.md)

---

[← Installation](installation.md) | [Group Management →](group-management.md)
