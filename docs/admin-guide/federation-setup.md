# Federation Setup

This guide explains how to connect your Nebulae node with other nodes to enable federated social networking.

---

## Understanding Federation

### What is Federation?

Federation allows multiple independent Nebulae nodes to connect and share content while maintaining autonomy. Think of it like email — you can have @gmail.com and email @yahoo.com users, but they can still communicate.

### Benefits of Federation

- 🌐 **Expand Your Network** - Connect with friends on other nodes
- 🔒 **Maintain Privacy** - Only share what you choose to share
- 🏠 **Keep Control** - Your data stays on your server
- 🤝 **Build Communities** - Create cross-node groups and events

### Types of Federation

#### Full Node Connection
- See all users, groups, and pages from the remote node
- Users can friend people on the remote node
- Bidirectional content sharing
- Requires mutual trust and pairing tokens

#### Targeted Subscription
- Subscribe to specific groups, events, or pages
- No access to the node's users
- Automatically created when needed
- Useful for following specific communities

---

## Prerequisites

Before setting up federation:

✅ Your node must have:
- A **public domain name** or **static IP**
- **HTTPS configured** (reverse proxy with SSL)
- `FEDERATION_INSECURE_MODE=False` in production
- Accessible on port 443 (standard HTTPS)

✅ The remote node must have:
- Same requirements as above
- Nebulae running (same or compatible version)
- Administrator willing to pair with you

---

## Federation Security

### How It Works

Federation uses:
- **HTTPS** for encrypted transport
- **HMAC-SHA256** signatures for request authentication
- **Shared secrets** for node pairing
- **PUIDs** to protect user email addresses

### What Gets Shared

When you connect nodes:
- ✅ Public User IDs (PUIDs)
- ✅ Display names
- ✅ Public posts
- ✅ Group/event information
- ✅ Profile pictures

### What Stays Private

- ❌ Email addresses (usernames)
- ❌ Passwords
- ❌ Private messages (when implemented)
- ❌ Local-only posts
- ❌ Internal user IDs

---

## Setting Up Federation

### Accessing Node Management

1. Log in as admin
2. Go to **Admin Panel**
3. Click **Manage Nodes**

### Method 1: You Initiate Connection

Use this method when another admin gives you their pairing token.

#### Step 1: Receive Pairing Information

The other admin will provide:
- **Hostname**: `their-node.example.com`
- **Pairing Token**: `abc123def456...`

#### Step 2: Add Remote Node

1. In **Manage Nodes**, find **Add New Remote Node**
2. Enter the hostname: `their-node.example.com`
3. Enter the pairing token they provided
4. Click **Initiate Connection**

#### Step 3: Wait for Confirmation

If successful, you'll see:
- "Successfully connected to remote node!"
- The node appears in **Full Node Connections**

#### Step 4: Set Node Nickname

1. Find the node in **Full Node Connections**
2. Click **Set Nickname**
3. Enter a friendly name (e.g., "Bob's Family Node")
4. Click **Save**

This nickname helps users identify where remote content comes from.

### Method 2: They Initiate Connection

Use this method when you want another admin to connect to you.

#### Step 1: Generate Pairing Token

1. In **Manage Nodes**, find **Generate New Pairing Token**
2. Click **Generate Token**
3. Copy the generated token

#### Step 2: Share with Other Admin

Send them:
- **Your hostname**: `your-node.example.com`
- **The pairing token**: (what you just generated)

You can share this via:
- Email
- Signal/encrypted messaging
- In person

⏰ **Tokens expire after 24 hours** for security.

#### Step 3: Wait for Connection

When they initiate the connection, you'll see their node appear in **Full Node Connections**.

#### Step 4: Set Node Nickname

Give the connected node a friendly name so users know where content comes from.

---

## Managing Connected Nodes

### Viewing Connected Nodes

The **Manage Nodes** page shows:

#### Full Node Connections
- Nodes you're fully connected with
- Bidirectional content sharing
- Users can discover and friend people

#### Targeted Subscriptions
- Specific groups/events/pages you're subscribed to
- One-way content flow
- Created automatically when needed

### Testing Federation

After connecting, test the federation:

1. Have a user on your node send a friend request to someone on the remote node
2. Post a public post and verify it appears on the remote node
3. Check that notifications work across nodes

### Node Nicknames

Node nicknames appear throughout the interface:

- **Discovery pages**: "Users from Bob's Family Node"
- **Post attributions**: "Alice (via Bob's Family Node)"
- **Notifications**: "Someone from Bob's Family Node mentioned you"

### Disconnecting Nodes

To disconnect from a node:

1. Go to **Manage Nodes**
2. Find the node in **Full Node Connections**
3. Click **Disconnect**
4. Confirm the action

⚠️ **What happens when you disconnect:**
- No new content from that node
- Existing posts remain visible
- Users can't send new friend requests
- Existing friendships preserved locally

---

## Targeted Subscriptions

### What Are They?

Targeted subscriptions allow your node to subscribe to specific resources (groups, events, pages) on remote nodes without a full connection.

### How They're Created

Automatically created when:
- A user discovers a remote group and joins it
- Someone is invited to a remote event
- A user follows a remote public page

### Benefits

- 🎯 **Specific access** - Only to what's needed
- 🔒 **More privacy** - Don't share all your users
- ⚡ **Lightweight** - Less data transfer

### Managing Targeted Subscriptions

View them in **Manage Nodes → Targeted Subscriptions**.

You can:
- See what you're subscribed to
- Remove subscriptions if no longer needed
- Upgrade to a full connection

---

## Troubleshooting Federation

### Connection Fails

**Check:**
1. Is the remote hostname accessible?
   ```bash
   curl https://remote-node.example.com
   ```
2. Is HTTPS properly configured?
3. Are both nodes running compatible versions?
4. Is the pairing token valid (not expired)?

**Common Issues:**
- ❌ Self-signed certificates (use proper SSL)
- ❌ Port 443 blocked by firewall
- ❌ Hostname not resolving
- ❌ `FEDERATION_INSECURE_MODE` mismatch

### Content Not Appearing

**Check:**
1. Is the post privacy set to "public" or "friends"?
2. Are the users actually friends?
3. Check Docker logs for federation errors:
   ```bash
   docker-compose logs -f | grep federation
   ```

### HMAC Signature Errors

This usually means:
- Shared secrets don't match
- System clocks are out of sync
- Request was tampered with

**Fix:**
1. Disconnect and reconnect the nodes
2. Verify system times are synchronized:
   ```bash
   timedatectl status
   ```

### Posts Duplicating

This can happen if federation messages are processed multiple times.

**Fix:**
1. Check logs for duplicate message warnings
2. Ensure only one Nebulae instance is running
3. Restart both nodes if needed

---

## Security Best Practices

### Only Connect Trusted Nodes

Federation requires trust. Only connect with:
- ✅ People you know personally
- ✅ Communities you trust
- ✅ Nodes with responsible administrators

### Monitor Federation Activity

Regularly check:
- New targeted subscriptions
- Unusual content patterns
- User reports about remote content

### Respond to Abuse

If a connected node has problematic users:
1. Ask the remote admin to handle it
2. Local users can block individuals
3. As last resort, disconnect the node

### Keep Shared Secrets Secure

- Don't share pairing tokens publicly
- Generate new tokens regularly
- Tokens auto-expire after 24 hours

### Use HTTPS Always

Never use `FEDERATION_INSECURE_MODE=True` in production. HTTP is:
- Not encrypted
- Vulnerable to tampering
- Against Nebulae's privacy principles

---

## Federation Etiquette

### As a Node Administrator

**Do:**
- ✅ Inform users before connecting new nodes
- ✅ Moderate problematic local users
- ✅ Respond to reports from remote admins
- ✅ Keep your node updated
- ✅ Communicate with connected admins

**Don't:**
- ❌ Connect nodes without user awareness
- ❌ Ignore abuse reports
- ❌ Suddenly disconnect established nodes
- ❌ Share user data outside federation

### Content Moderation

Remember:
- Each node controls their own users
- You can't moderate remote users directly
- Communication between admins is key
- Disconnection is always an option

---

## Advanced Topics

### Federation API

Nebulae uses a custom federation protocol over HTTPS. Key endpoints:

- `POST /federation/inbox` - Receive federated content
- `POST /federation/discover` - Share discoverable resources
- Authenticated with HMAC-SHA256 signatures

### Shared Secrets

When nodes connect:
1. Initial handshake with pairing token
2. Shared secret generated and exchanged
3. Future requests signed with shared secret
4. Signatures verified on each request

### PUID System

Public User IDs protect privacy:
- Generated on user creation
- Used for all federation
- Email addresses never leave the node
- Format: `puid_` + random string

---

## Monitoring Federation Health

### Check Federation Status

```bash
docker-compose logs -f | grep "federation"
```

Look for:
- ✅ "Successfully sent to remote node"
- ✅ "Federation request verified"
- ❌ "HMAC verification failed"
- ❌ "Remote node unreachable"

### Database Queries

Check connected nodes:
```bash
docker exec -it nebulae sqlite3 /app/instance/nebulae.db
sqlite> SELECT hostname, nickname, created_at FROM remote_nodes;
```

---

## Related Documentation

- [Privacy & Security](../federation/privacy-security.md)
- [Troubleshooting Federation](../troubleshooting/federation-issues.md)
- [Configuration Guide](configuration.md)

---

[← Group Management](group-management.md) | [Backups & Updates →](backups-updates.md)
