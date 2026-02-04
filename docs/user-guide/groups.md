# Groups

Groups allow you to create communities within Nebulae, bringing together people with shared interests across nodes.

---

## Understanding Groups

### What Are Groups?

Groups are communities where members can:
- 📝 Post updates
- 💬 Have discussions
- 📅 Organize events
- 🤝 Connect with like-minded people
- 🌐 Include members from different nodes

### Group Types

#### Public Groups
- Anyone can join immediately
- Visible in discovery
- Posts visible to all members
- Open to federation

#### Private Groups
- Requires approval to join
- Visible in discovery (unless hidden)
- Posts only visible to members
- Can federate with approval

---

## Finding Groups

### Discover Groups

1. Click **👥 Discover** in the navigation
2. Select **Groups** tab
3. Browse available groups
4. Filter by:
   - Your node
   - Specific connected nodes
   - All nodes

### Group Information

Each group listing shows:
- Group name
- Description
- Member count
- Privacy type (Public/Private)
- Originating node
- Join/Request button

### Hide Groups

Not interested in a group?
1. Click **⋯** on the group card
2. Select **Hide from Discovery**
3. Group won't appear in your results anymore

---

## Joining Groups

### Public Groups

1. Find the group in Discovery
2. Click **Join Group**
3. You're immediately a member!
4. Group appears in your **Groups** section

### Private Groups

Private groups may require:
- Approval from admins
- Answers to questions
- Agreement to rules

#### Joining Process

1. Find the private group
2. Click **Request to Join**
3. Answer any required questions
4. Agree to group rules (if present)
5. Submit request
6. Wait for admin approval

You'll be notified when your request is:
- ✅ Approved - You're now a member!
- ❌ Denied - Try another group or contact admins

---

## Group Features

### Group Timeline

The group timeline shows:
- Posts from all members
- Group announcements
- Event announcements
- Pinned posts (from admins)

Access: Click on any group name to view its timeline.

### Posting in Groups

1. Navigate to the group timeline
2. Use the post creation box at the top
3. Post like normal
4. Privacy is automatically set to "Group"
5. All group members will see your post

#### @everyone Mentions

Group admins and moderators can use `@everyone` or `@all` to notify all members:

```
@everyone Don't forget about our meeting tomorrow!
```

All members receive a notification.

### Group Events

Groups can create events:
1. Click **Create Event** in the group
2. Fill in event details
3. Event appears on group timeline
4. Members can RSVP

See [Events Guide](events.md) for more details.

---

## Group Membership

### Member List

View all group members:
1. Go to group timeline
2. Click **Members** tab
3. See:
   - Admins (⭐)
   - Moderators (🛡️)
   - Regular members

### Member Roles

#### Admins (⭐)
- Full control over the group
- Can add/remove anyone
- Can promote/demote moderators
- Can edit group information
- Can delete any post
- Can create events

#### Moderators (🛡️)
- Can approve join requests
- Can remove posts
- Can remove problematic members
- Cannot change group settings
- Cannot promote/demote

#### Members
- Can post in the group
- Can comment
- Can create events (if allowed)
- Can invite friends

### Friends in Group

See which of your friends are members:
1. Go to group timeline
2. Click **Members** tab
3. Your friends appear with a **Friend** badge

---

## Inviting Friends

Share groups with your friends:

1. Go to the group timeline
2. Click **Invite Friends**
3. See list of friends not yet in group
4. Select friends to invite
5. Click **Send Invitations**

Your friends will receive:
- Notification of invitation
- Direct link to join
- Info about who invited them

---

## Creating Your Own Group

### Requirements

- Must be a regular user (not admin account)
- Must have permission from node admin

### Creation Process

1. Go to **Groups** section
2. Click **Create New Group**
3. Fill in details:

| Field | Description |
|-------|-------------|
| **Group Name** | What your group is called |
| **Description** | What the group is about |
| **Privacy** | Public or Private |
| **Profile Picture** | Group avatar (optional) |

4. Click **Create Group**

You are automatically:
- The group admin
- The first member
- The creator in the database

### Initial Setup

After creating your group:

1. **Customize Profile**
   - Add cover photo
   - Add detailed information
   - Set website/links

2. **Set Up Admins/Mods**
   - Promote trusted members
   - Distribute moderation duties

3. **Create Rules**
   - Add group rules
   - Make rules visible to all
   - Require agreement on join

4. **Invite Members**
   - Invite your friends
   - Share in other communities
   - Let discovery do its work

---

## Managing Your Group (Admins)

### Group Settings

Access via **Group Settings** button (only visible to admins).

#### Basic Information

- **Name**: Change group name
- **Description**: Update description
- **Privacy**: Change public/private
- **Cover Photo**: Change cover image

#### Profile Information

Add optional fields:
- Website URL
- Contact email
- About text
- Custom fields

Set visibility:
- Public (anyone can see)
- Members only

#### Join Questions

For private groups, add questions:
1. Click **Add Question**
2. Enter question text
3. Set as required or optional
4. Save

Examples:
- "Why do you want to join?"
- "How did you hear about us?"
- "Do you agree to follow our rules?"

#### Group Rules

Add rules that members must agree to:
1. Enter rule text
2. Toggle "Must agree to join"
3. Save rules

### Managing Members

#### Approving Join Requests

1. Click **Pending Requests** (shows count)
2. Review each request
3. See their answers to questions
4. **Approve** or **Deny**
5. Optionally add reason for denial

#### Promoting Members

To make someone a moderator:
1. Go to **Members** list
2. Find the member
3. Click **⋯** menu
4. Select **Promote to Moderator**

To make someone an admin:
1. Same process
2. Select **Promote to Admin**

⚠️ **Note**: Admins have full control. Only promote trusted members!

#### Removing Members

1. Go to **Members** list
2. Find the member
3. Click **⋯** menu
4. Select **Remove from Group**
5. Confirm removal

Removed members:
- Lose access to group content
- Can rejoin if public
- Must re-request if private

#### Banning Members

For serious violations:
1. Remove the member
2. Click **Ban User**
3. They cannot rejoin

---

## Group Content Moderation

### Removing Posts

Admins and moderators can remove posts:
1. Click **⋯** on any post
2. Select **Remove Post**
3. Confirm

The post is deleted from:
- Group timeline
- All member feeds
- Database

### Handling Reports

When members report content:
1. You receive a notification
2. Review the reported content
3. Take appropriate action:
   - Remove post
   - Warn member
   - Remove member
   - No action needed

---

## Leaving Groups

### As a Member

1. Go to the group timeline
2. Click **Leave Group**
3. Confirm

You'll:
- No longer see group posts
- Lose access to group timeline
- Not receive notifications
- Can rejoin later (if public)

### As the Creator

The group creator cannot leave while other members exist. You must:

1. Promote another member to admin
2. Then leave normally

Or:

1. Remove all other members
2. Delete the group (optional)

---

## Group Privacy

### What's Visible

#### Public Groups
- ✅ Name and description in discovery
- ✅ Member list (to members)
- ✅ Post count
- ✅ Posts (to members only)
- ❌ Posts do not appear publicly

#### Private Groups
- ✅ Name and description in discovery
- ❌ Member list (members only)
- ❌ Posts (members only)
- ❌ Join requests not visible

### Federation Behavior

Groups can federate:
- ✅ Remote users can join
- ✅ Content shared across nodes
- ✅ Targeted subscriptions created
- ❌ Group admin must be local user

---

## Best Practices

### For Members

✅ **Do:**
- Read group rules before posting
- Stay on topic
- Be respectful to other members
- Use @everyone sparingly
- Report problematic content

❌ **Don't:**
- Spam the group
- Share private info publicly
- Harass other members
- Ignore moderator warnings

### For Admins

✅ **Do:**
- Set clear rules
- Moderate consistently
- Promote trusted members
- Be responsive to reports
- Welcome new members

❌ **Don't:**
- Abuse admin powers
- Ignore serious violations
- Play favorites
- Be inactive
- Remove members without reason

---

## Troubleshooting

### Can't Join Group

**Possible reasons:**
- Private group needs approval
- You're banned
- Group is at capacity (unlikely)
- Federation issue

**Try:**
- Wait for approval (private groups)
- Contact group admin
- Check your connection to that node

### Posts Not Appearing

**Check:**
- Are you still a member?
- Is the group on a connected node?
- Check your feed filters
- Refresh the page

### Can't Create Group

**Reasons:**
- Only regular users can create groups
- Your node admin may have disabled this
- You may have reached a group limit

**Solution:**
- Contact your node administrator

---

## Related Documentation

- **[Events](events.md)** - Create events within groups
- **[Privacy Settings](privacy-settings.md)** - Control your group visibility
- **[Discovery](friends-discovery.md)** - Find more groups

---

[← Friends & Discovery](friends-discovery.md) | [Events →](events.md)
