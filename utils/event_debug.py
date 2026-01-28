#!/usr/bin/env python3
"""
Event Attendance Diagnostic Script
Run this to check if event attendance is being recorded properly
and if posts are being created with the correct privacy settings.

Usage: python event_debug.py <user_puid> <event_puid>
"""

import sys
import sqlite3

def check_event_attendance(user_puid, event_puid):
    """Check if a user is properly recorded as attending an event"""
    
    conn = sqlite3.connect('/app/instance/openbook.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print(f"\n{'='*60}")
    print(f"CHECKING EVENT ATTENDANCE FOR USER: {user_puid}")
    print(f"{'='*60}\n")
    
    # Get event info
    cursor.execute("SELECT * FROM events WHERE puid = ?", (event_puid,))
    event = cursor.fetchone()
    
    if not event:
        print(f"❌ ERROR: Event {event_puid} not found!")
        return
    
    print(f"✓ Event found: {event['title']}")
    print(f"  Event ID: {event['id']}")
    print(f"  Created by: {event['created_by_user_puid']}")
    print(f"  Is public: {event['is_public']}")
    print(f"  Is cancelled: {event['is_cancelled']}")
    print()
    
    # Check if user exists
    cursor.execute("SELECT puid, username, display_name FROM users WHERE puid = ?", (user_puid,))
    user = cursor.fetchone()
    
    if not user:
        print(f"❌ ERROR: User {user_puid} not found!")
        return
    
    print(f"✓ User found: {user['display_name']} (@{user['username']})")
    print()
    
    # Check event_attendees table
    cursor.execute("""
        SELECT * FROM event_attendees 
        WHERE event_id = ? AND user_puid = ?
    """, (event['id'], user_puid))
    
    attendance = cursor.fetchone()
    
    if not attendance:
        print(f"❌ NO ATTENDANCE RECORD FOUND!")
        print(f"   User is NOT in event_attendees table for this event")
    else:
        print(f"✓ Attendance record found:")
        print(f"  Response: {attendance['response']}")
        print(f"  Updated at: {attendance['updated_at']}")
    
    print()
    
    # Check all attendees for this event
    cursor.execute("""
        SELECT ea.response, u.puid, u.display_name, u.username
        FROM event_attendees ea
        JOIN users u ON ea.user_puid = u.puid
        WHERE ea.event_id = ?
        ORDER BY ea.response
    """, (event['id'],))
    
    all_attendees = cursor.fetchall()
    print(f"📋 All attendees for this event ({len(all_attendees)} total):")
    for att in all_attendees:
        marker = "👉" if att['puid'] == user_puid else "  "
        print(f"{marker} {att['display_name']:20} | Response: {att['response']:12} | PUID: {att['puid']}")
    
    print()
    
    # Check posts by this user to this event
    cursor.execute("""
        SELECT p.cuid, p.content, p.privacy_setting, p.timestamp, p.event_id
        FROM posts p
        WHERE p.author_puid = ? AND p.event_id = ?
        ORDER BY p.timestamp DESC
    """, (user_puid, event['id']))
    
    user_event_posts = cursor.fetchall()
    
    print(f"📝 Posts by {user['display_name']} to this event ({len(user_event_posts)} total):")
    if user_event_posts:
        for post in user_event_posts:
            content_preview = post['content'][:50] if post['content'] else "[No content]"
            print(f"  CUID: {post['cuid']}")
            print(f"  Privacy: {post['privacy_setting']}")
            print(f"  Content: {content_preview}")
            print(f"  Time: {post['timestamp']}")
            print()
    else:
        print("  (None)")
    
    print()
    
    # Check if posts would appear in feed query
    print(f"🔍 FEED QUERY TEST:")
    print(f"   Checking if user would see event posts in their feed...")
    
    cursor.execute("""
        SELECT event_id FROM event_attendees 
        WHERE user_puid = ? AND response != 'declined'
    """, (user_puid,))
    
    attended_event_ids = [row['event_id'] for row in cursor.fetchall()]
    
    print(f"   Events user is attending (response != 'declined'): {attended_event_ids}")
    
    if event['id'] in attended_event_ids:
        print(f"   ✓ Event {event['id']} IS in the list - posts should appear!")
        
        # Now check what posts exist for this event
        cursor.execute("""
            SELECT cuid, author_puid, privacy_setting, timestamp
            FROM posts
            WHERE event_id = ? AND privacy_setting = 'event'
            ORDER BY timestamp DESC
        """, (event['id'],))
        
        all_event_posts = cursor.fetchall()
        print(f"\n   📋 All posts to this event with privacy='event' ({len(all_event_posts)} total):")
        for post in all_event_posts:
            cursor.execute("SELECT display_name FROM users WHERE puid = ?", (post['author_puid'],))
            author = cursor.fetchone()
            author_name = author['display_name'] if author else "Unknown"
            marker = "👉" if post['author_puid'] == user_puid else "  "
            print(f"{marker} {author_name:20} | CUID: {post['cuid']} | Time: {post['timestamp']}")
    else:
        print(f"   ❌ Event {event['id']} NOT in the list - posts will NOT appear!")
        print(f"   This is the problem!")
    
    print()
    print(f"{'='*60}")
    print(f"DIAGNOSIS COMPLETE")
    print(f"{'='*60}\n")
    
    conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python event_debug.py <user_puid> <event_puid>")
        print("\nExample:")
        print("  python event_debug.py user_abc123 event_xyz789")
        sys.exit(1)
    
    user_puid = sys.argv[1]
    event_puid = sys.argv[2]
    
    check_event_attendance(user_puid, event_puid)