# Nebulae Docker Setup Guide

## Quick Start

### 1. Prerequisites
- Docker and Docker Compose installed
- A domain name or static IP address for your node

### 2. Download Configuration Files

Download the production docker-compose file:
```bash
wget https://raw.githubusercontent.com/locqust/NODE/main/docker-compose.production.yml -O docker-compose.yml
wget https://raw.githubusercontent.com/locqust/NODE/main/.env.example -O .env
```

### 3. Configure Environment

# Generate a secure secret key
python3 -c "import secrets; print(secrets.token_hex(32))"
Or just make up a random long string!

Required settings:
- `SECRET_KEY`: Use the generated key above
- `NODE_HOSTNAME`: Your public address (e.g., `nebulae.example.com`)

```

### 4. (Optional) Configure User Media Volumes

If you want to connect existing photo libraries, edit `docker-compose.yml`:
```yaml
volumes:
  # Add your media paths:
  - /home/user/Photos:/app/user_media/username_media:ro
  - /home/user/Photos/uploads:/app/user_uploads/username_uploads
Or Windows filesystems
  - C:\Users\User\Photos:/app/user_media/username_media:ro
  - C:\Users\User\Uploads:/app/user_uploads/username_uploads

*** Note *** Users will not be able to add existing media or upload media to posts without one or both of these paths. 
```

**Important**: 
- Read-only volumes (`:ro`) are for browsing existing photos
- Writable volumes (no `:ro`) are for new uploads
- You'll configure the paths in the admin panel after first login

### 5. Start Nebulae
```bash
docker-compose up -d
```

### 6. First-Time Setup

1. Access your node: `http://<internal LAN IP address>:5000` (Configure public facing DNS name later)
2. The admin account is automatically created:
   - Username: `admin`
   - Password: `adminpassword`
3. **IMPORTANT**: You will be asked to change the admin password upon first logon.
```

### 7. Configure Users

1. Log in as admin
2. If first logon as admin, change password
3. Go to Admin Panel → Manage Users
4. Click 'Add New User'
5. Enter Username, this will generally be an email address
6. Enter a password
7. Set Display Name - this will be the persons name or nickname if they prefer. This is what other users see when discovering friends or on posts
8. Set the date of birth - you CANNOT change this once set.
9. Click Add User
10. (If configured in Step 4.) For each user, click  on 'Actions' and then "Set Media Path"
11. Enter the container path (e.g., `/app/user_media/username_media` for read-only, `/app/user_uploads/username_uploads` for uploads)
12. If user is under 16 set Parental Controls, add parents usernames as those that will approve actions child users will do
```
### 8. Email settings

1. Add SMTP server settings for your email provider (i.e Gmail)
2. Click 'Test Email settings and save'
3. You should get a test email from the configured email address
```

### 9. Push Notification settings

1. Generate a VAPID key
2. When users log in they'll be asked if they want the browser to send notifications, this is up to user and easily turned on/off in the browser. 

```

## 9. Backups ****RECOMMENDED ****

1. Click on 'Database backups'
2. Enable scheduled backups (if you want) and select the frequency
3. Run a test backup by clicking 'Create Backup', give it a name first.
4. You should see it in the list below and on your configured backups folder on your host machine.
5. You can restore from backup from that list.

```

## 10. Federation Setup

To federate with other Nebulae nodes:

1. Ensure `NODE_HOSTNAME` is publicly accessible
2. Set `FEDERATION_INSECURE_MODE=False` (use HTTPS in production)
3. Configure your reverse proxy (nginx/Apache) to handle HTTPS
4. Go to Manage Nodes in the Admin Dashboard
5a. Generate a new pairing token, pass to the admin of the node you wish to connect to
6a. Once they initiate connection - if it works you'll see their node appear at the bottom of the page in Full Node Connections
OR
5b. Add in the hostname and pairing code given to you by the admin of the other node.
6b. Initiate connection, if succesful you should see their node appear at the bottom of the page in Full Node Connections
7. Give the connected node a nickname so you know who it belongs to. (i.e Bob's Home Node) All your users will see any users, pages and groups from that node with that nickname

*** NOTE *** Targeted subscriptions are created automatically when joining/following groups, events and pages that have been discovered by the node via other nodes that are not directly connected to yours. ('word of mouth' sharing)
They are only for this function only and not for users. An upgrade to a Full Node Connection is the only way to find the users on that node, plus all othr groups and pages they may have on there. 

```

## 11. Make a local post as admin

1. Click on 'Post to All Local Users'
2. Create your post! All local users on that node will see this post. Admin is a hidden friend of everyone on the node. This feature is useful for letting users know about upcoming upgrades and outages.

```

## 12. Configure your reverse proxy
1. Out of scope for this document but recommend an NGINX docker container or for a an easier GUI based setup - NGINX PROXY MANAGER docker container
2. This will also require either a permanent IP address from your ISP and domain name from somewhere (expensive) or use a (usually free) DDNS service to keep a DDNS domain name up to date as your IP changes.
Dynu IP Update Client and Dynu.com for the domain name is one example.

```

## 13. Let your Users loose on there!
1. Let your users log in via https://<nebulae dns name>

```

## Updating Nebulae
```bash
docker-compose down
docker-compose pull
docker-compose up -d

```
## Optional extras

## 1. Create Groups

1. Click on 'Manage Groups' in the Admin Dashboard
2. Click on 'Create New Group'
3. Enter the groups name - this is what will be shown on Discover Groups
4. Write a short description
5. Assign a local user a the intial group admin. You can assign more than one and once up and running group members on federated nodes can be made additional group admins/mods.
6. This initial admin(s) cannot be demoted removed by other admins. And if that does somehow happen, the node admin can reassign them here.

```

## 2. Create a Public page
1. Click on 'Manage Public Pages' in the Admin Dashboard
2. Click on 'Add New Public Page'
3. As like with a normal user add a Username (email address)
4. Create a password
5. Create the Display Name - this is the name people see. (i.e Bob's window cleaning service)
6. Managing this page involves logging in like a normal user, to all intents and purposes it works more less like a normal user profile. But with slight differences like posting, followers etc.

```

## Troubleshooting

### Check logs
```bash
docker-compose logs -f
```

## Support

- GitHub: https://github.com/locqust/Nebulae
- Discord - Coming soon!
- Docs - coming soon!
- License: AGPL-3.0
```
