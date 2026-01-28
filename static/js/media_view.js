/**
 * media_view.js
 * Handles media viewing, tagging, and commenting functionality
 */

// State for media tagging
let mediaSelectedFriends = [];

/**
 * Navigates to a different media item in the carousel
 */
function navigateToMedia(muid) {
    navigateToMediaInModal(muid);
}

/**
 * Toggles the media options menu
 */
function toggleMediaOptions() {
    const menu = document.getElementById('media-options-menu');
    if (menu) {
        menu.classList.toggle('hidden');
    }
}

// Close menu when clicking outside
document.addEventListener('click', (e) => {
    const menu = document.getElementById('media-options-menu');
    if (menu && !menu.contains(e.target) && !e.target.closest('button[onclick*="toggleMediaOptions"]')) {
        menu.classList.add('hidden');
    }
});

/**
 * Opens the modal to tag people in this media
 */
async function openMediaTagModal() {
    const modal = document.getElementById('tag-friends-modal');
    if (!modal) return;
    
    // Hide options menu
    toggleMediaOptions();
    
    // Load current tags
    mediaSelectedFriends = window.mediaData.taggedUserPuids || [];
    
    openModal('tag-friends-modal');
    
    // Override the Done button to use media tagging
    setTimeout(() => {
        // Find the Done button by text content
        const allButtons = modal.querySelectorAll('button');
        let doneButton = null;
        
        allButtons.forEach(btn => {
            if (btn.textContent.trim() === 'Done') {
                doneButton = btn;
            }
        });
        
        if (doneButton) {
            // Remove ALL existing event listeners by cloning the button
            const newButton = doneButton.cloneNode(true);
            doneButton.parentNode.replaceChild(newButton, doneButton);
            
            // Remove onclick attribute
            newButton.removeAttribute('onclick');
            
            // Add our handler
            newButton.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                applyMediaTags();
            });
        }
    }, 100);
    
// Load friends list
    try {
        const response = await fetch('/friends/api/friends_list');
        if (!response.ok) {
            throw new Error('Failed to load friends');
        }
        
        const data = await response.json();
        let friendsList = data.friends || [];
        
        // NEW: Add current user to the list for self-tagging
        if (window.mediaData && window.mediaData.currentUserPuid) {
            const currentUserAlreadyInList = friendsList.some(f => f.puid === window.mediaData.currentUserPuid);
            
            if (!currentUserAlreadyInList) {
                // Try to get current user's profile picture from the page
                let profilePicUrl = '/static/images/default_avatar.png';
                const navProfilePic = document.querySelector('.profile-pic, [data-profile-pic], img[alt*="profile" i]');
                if (navProfilePic && navProfilePic.src) {
                    profilePicUrl = navProfilePic.src;
                }
                
                // Add current user at the beginning of the list
                friendsList.unshift({
                    puid: window.mediaData.currentUserPuid,
                    display_name: window.mediaData.currentUserDisplayName || 'Me',
                    profile_picture_url: profilePicUrl
                });
            }
        }
        
        displayMediaTagFriendsList(friendsList);
    } catch (error) {
        console.error('Error loading friends:', error);
        document.getElementById('tag-friends-list').innerHTML = `
            <div class="text-center secondary-text py-8">
                <p class="text-red-500">Error loading friends. Please try again.</p>
            </div>
        `;
    }
}

/**
 * Displays friends list for tagging
 */
function displayMediaTagFriendsList(friends) {
    const listContainer = document.getElementById('tag-friends-list');
    
    if (!friends || friends.length === 0) {
        listContainer.innerHTML = `
            <div class="text-center secondary-text py-8">
                <p>No friends to tag</p>
            </div>
        `;
        return;
    }
    
    listContainer.innerHTML = friends.map(friend => `
        <div class="friend-item flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-md" 
             data-puid="${friend.puid}" 
             data-name="${friend.display_name.toLowerCase()}">
            <input type="checkbox" 
                   id="media-friend-${friend.puid}" 
                   value="${friend.puid}"
                   ${mediaSelectedFriends.includes(friend.puid) ? 'checked' : ''}
                   onchange="toggleMediaFriendTag('${friend.puid}')"
                   class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500">
            ${friend.profile_picture_url ? `
                <img src="${friend.profile_picture_url}" 
                     alt="${friend.display_name}" 
                     class="w-10 h-10 rounded-full object-cover"
                     onerror="this.src='/static/images/default_avatar.png'">
            ` : `
                <svg class="w-10 h-10 text-gray-500 rounded-full" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"></path>
                </svg>
            `}
            <label for="media-friend-${friend.puid}" class="flex-1 cursor-pointer primary-text">
                ${friend.display_name}
            </label>
        </div>
    `).join('');
}

/**
 * Filters media tag friends list based on search input
 */
function filterMediaTagFriends() {
    const searchInput = document.getElementById('tag-friends-search');
    const searchTerm = searchInput.value.toLowerCase();
    const friendItems = document.querySelectorAll('#tag-friends-list .friend-item');
    
    friendItems.forEach(item => {
        const name = item.getAttribute('data-name');
        if (name && name.includes(searchTerm)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

/**
 * Toggles friend tag selection
 */
function toggleMediaFriendTag(puid) {
    const index = mediaSelectedFriends.indexOf(puid);
    if (index > -1) {
        mediaSelectedFriends.splice(index, 1);
    } else {
        mediaSelectedFriends.push(puid);
    }
}

// Add a flag to prevent multiple simultaneous calls
let isApplyingTags = false;

/**
 * Applies the selected tags to the media
 */
async function applyMediaTags() {
    // Prevent multiple simultaneous calls
    if (isApplyingTags) {
        return;
    }
    
    isApplyingTags = true;
    
    // Close the modal first
    closeModal('tag-friends-modal');
    
    if (!window.mediaData || !window.mediaData.muid) {
        isApplyingTags = false;
        if (App && App.Toast) {
            App.Toast.show('Error: Media data not available', 'error');
        }
        return;
    }
    
    try {
        const response = await fetch(`/media/${window.mediaData.muid}/tag`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                tagged_user_puids: mediaSelectedFriends
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to update tags');
        }
        
        // Reload the modal to show updated tags
        if (window.mediaData && window.mediaData.muid) {
            openMediaViewModal(window.mediaData.muid);
        }
        
        if (App && App.Toast) {
            App.Toast.show('Tags updated successfully!', 'success');
        }
    } catch (error) {
        console.error('Error updating tags:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to update tags. Please try again.', 'error');
        }
    } finally {
        isApplyingTags = false;
    }
}

// Override the modal Done button for media tagging
document.addEventListener('DOMContentLoaded', () => {
    const tagModalDoneBtn = document.querySelector('#tag-friends-modal button[onclick*="applyTaggedFriends"]');
    if (tagModalDoneBtn && window.mediaData) {
        // Replace with media-specific handler
        tagModalDoneBtn.setAttribute('onclick', 'applyMediaTags()');
    }
});

/**
 * Shows all tagged people in a modal
 */
async function showAllTaggedPeople() {
    // Check if modal exists
    const modal = document.getElementById('tagged-people-modal');
    if (!modal) {
        console.error('Tagged people modal not found');
        return;
    }
    
    // Open the modal
    openModal('tagged-people-modal');
    
    // Fetch media tags for this media item
    if (!window.mediaData || !window.mediaData.muid) {
        console.error('Media data not available');
        return;
    }
    
    try {
        const response = await fetch(`/api/media/${window.mediaData.muid}/tagged_users`);
        if (!response.ok) {
            throw new Error('Failed to load tagged users');
        }
        
        const data = await response.json();
        displayTaggedPeopleList(data.tagged_users);
    } catch (error) {
        console.error('Error loading tagged users:', error);
        document.getElementById('tagged-people-list').innerHTML = `
            <div class="text-center secondary-text py-8">
                <p class="text-red-500">Error loading tagged people. Please try again.</p>
            </div>
        `;
    }
}

/**
 * Displays the list of tagged people in the modal
 * @param {Array} taggedUsers - Array of user objects
 */
function displayTaggedPeopleList(taggedUsers) {
    const listContainer = document.getElementById('tagged-people-list');
    
    if (!taggedUsers || taggedUsers.length === 0) {
        listContainer.innerHTML = `
            <div class="text-center secondary-text py-8">
                <p>No tagged users found</p>
            </div>
        `;
        return;
    }
    
    listContainer.innerHTML = taggedUsers.map(user => `
        <div class="flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-md">
            ${user.profile_picture_url ? `
                <img src="${user.profile_picture_url}" 
                     alt="${user.display_name}" 
                     class="w-10 h-10 rounded-full object-cover"
                     onerror="this.src='/static/images/default_avatar.png'">
            ` : `
                <svg class="w-10 h-10 text-gray-500 rounded-full" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"></path>
                </svg>
            `}
            <div class="flex-1">
                <a href="${user.profile_url}" class="font-semibold text-gray-900 dark:text-white hover:underline">
                    ${user.display_name}
                </a>
                ${user.mutual_friends > 0 ? `
                    <div class="text-xs text-gray-500 dark:text-gray-400">
                        ${user.mutual_friends} mutual friend${user.mutual_friends !== 1 ? 's' : ''}
                    </div>
                ` : ''}
            </div>
            ${user.can_add_friend ? `
                <button onclick="addFriendFromModal('${user.puid}')" 
                        class="text-sm bg-blue-500 hover:bg-blue-600 text-white px-3 py-1 rounded">
                    Add Friend
                </button>
            ` : ''}
        </div>
    `).join('');
}

/**
 * Shows confirmation modal before untagging
 */
function confirmUntagMyself(muid) {
    // Close the options menu first
    toggleMediaOptions();
    
    // Use the app's confirmation modal
    if (typeof showConfirmationModal === 'function') {
        showConfirmationModal('Remove yourself from this photo?', () => {
            untagMyself(muid);
        });
    } else {
        // Fallback to browser confirm
        if (confirm('Remove yourself from this photo?')) {
            untagMyself(muid);
        }
    }
}

/**
 * Removes the current user's tag from the media
 */
async function untagMyself(muid) {
    try {
        const response = await fetch(`/media/${muid}/untag`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to remove tag');
        }
        
        // Reload the modal to show updated state
        if (window.mediaData && window.mediaData.muid) {
            openMediaViewModal(window.mediaData.muid);
        }
        
        if (App && App.Toast) {
            App.Toast.show('Tag removed successfully!', 'success');
        }
    } catch (error) {
        console.error('Error removing tag:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to remove tag. Please try again.', 'error');
        } else {
            alert('Failed to remove tag. Please try again.');
        }
    }
}



// ============================================================================
// MEDIA COMMENTING FUNCTIONS
// ============================================================================

/**
 * Submits a new comment on the media
 */
async function submitMediaComment(event, muid) {
    event.preventDefault();
    
    const form = event.target;
    const contentInput = form.querySelector('[name="content"]');
    const mediaFilesInput = form.querySelector('[name="selected_media_files"]');
    const parentCuidInput = form.querySelector('.parent-comment-cuid-input');
    
    if (!contentInput) {
        console.error('Content input not found');
        return;
    }
    
    const content = contentInput.value.trim();
    const mediaFiles = mediaFilesInput ? mediaFilesInput.value : '[]';
    const parentCommentCuid = parentCuidInput ? parentCuidInput.value : null;
    
    if (!content && mediaFiles === '[]') {
        if (App && App.Toast) {
            App.Toast.show('Please enter a comment or attach media', 'info');
        }
        return;
    }
    
    try {
        const response = await fetch(`/media/${muid}/comment`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                content: content,
                media_files: JSON.parse(mediaFiles),
                parent_comment_cuid: parentCommentCuid
            })
        });
        
        if (!response.ok) {
            throw new Error('Failed to post comment');
        }
        
        // Clear form
        contentInput.value = '';
        if (mediaFilesInput) mediaFilesInput.value = '[]';
        
        // Reset reply state
        cancelMediaCommentReply();
        
        // Reload the modal to show new comment
        if (window.mediaData && window.mediaData.muid) {
            openMediaViewModal(window.mediaData.muid);
        }
        
        if (App && App.Toast) {
            App.Toast.show('Comment posted!', 'success');
        }
    } catch (error) {
        console.error('Error posting comment:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to post comment. Please try again.', 'error');
        } else {
            alert('Failed to post comment. Please try again.');
        }
    }
}

/**
 * Shows reply form for a media comment - modifies main comment form
 */
function replyToMediaComment(commentCuid, authorName) {
    const form = document.getElementById('media-comment-form');
    if (!form) return;
    
    // Find or create the hidden input for parent comment
    let parentInput = form.querySelector('.parent-comment-cuid-input');
    if (!parentInput) {
        parentInput = document.createElement('input');
        parentInput.type = 'hidden';
        parentInput.name = 'parent_comment_cuid';
        parentInput.className = 'parent-comment-cuid-input';
        form.insertBefore(parentInput, form.firstChild);
    }
    parentInput.value = commentCuid;
    
    // Show "Replying to" display
    let replyingDisplay = form.querySelector('.replying-to-display');
    if (!replyingDisplay) {
        replyingDisplay = document.createElement('div');
        replyingDisplay.className = 'replying-to-display text-sm secondary-text mb-2 p-2 bg-gray-100 dark:bg-gray-800 rounded';
        replyingDisplay.innerHTML = `
            Replying to <span class="font-semibold reply-to-username"></span>
            <button type="button" onclick="cancelMediaCommentReply()" class="text-red-500 hover:text-red-700 ml-2 text-xs">Cancel</button>
        `;
        const textarea = form.querySelector('textarea');
        if (textarea && textarea.parentNode) {
            textarea.parentNode.insertBefore(replyingDisplay, textarea);
        }
    }
    
    replyingDisplay.querySelector('.reply-to-username').textContent = `@${authorName}`;
    replyingDisplay.classList.remove('hidden');
    
    // Set textarea value and focus
    const textarea = form.querySelector('textarea');
    if (textarea) {
        textarea.value = `@${authorName} `;
        textarea.focus();
        textarea.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

/**
 * Cancels reply to a media comment - resets main comment form
 */
function cancelMediaCommentReply() {
    const form = document.getElementById('media-comment-form');
    if (!form) return;
    
    const parentInput = form.querySelector('.parent-comment-cuid-input');
    if (parentInput) {
        parentInput.value = '';
    }
    
    const replyingDisplay = form.querySelector('.replying-to-display');
    if (replyingDisplay) {
        replyingDisplay.classList.add('hidden');
    }
    
    const textarea = form.querySelector('textarea');
    if (textarea) {
        textarea.value = '';
    }
}
/**
 * Submits a reply to a media comment
 */
async function submitMediaCommentReply(event, parentCommentCuid) {
    event.preventDefault();
    
    const form = event.target;
    const content = form.elements['content'].value.trim();
    
    if (!content) {
        return;
    }
    
    try {
        const response = await fetch(`/media/${window.mediaData.muid}/comment`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                content: content,
                parent_comment_cuid: parentCommentCuid,
                media_files: []
            })
        });
        
        if (!response.ok) {
            throw new Error('Failed to post reply');
        }
        
        // Reload page to show new reply
        window.location.reload();
    } catch (error) {
        console.error('Error posting reply:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to post reply. Please try again.', 'error');
        } else {
            alert('Failed to post reply. Please try again.');
        }
    }
}

/**
 * Opens edit modal for a media comment
 */
function editMediaComment(commentCuid, content, mediaJson) {
    // Close the dropdown
    document.querySelectorAll('[id^="media-comment-options-"]').forEach(menu => {
        menu.classList.add('hidden');
    });
    
    // Use the app's comment edit modal with media comment flag
    if (typeof App !== 'undefined' && App.Comment && typeof App.Comment.openEditModal === 'function') {
        App.Comment.openEditModal(commentCuid, content, mediaJson, window.location.origin, false, true); // Last parameter is isMediaComment
    } else {
        // Fallback: simple prompt
        const newContent = prompt('Edit comment:', content);
        if (newContent && newContent.trim() !== content) {
            updateMediaComment(commentCuid, newContent.trim());
        }
    }
}

/**
 * Updates a media comment
 */
async function updateMediaComment(commentCuid, newContent) {
    try {
        const response = await fetch(`/media/comment/${commentCuid}/edit`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                content: newContent,
                media_files: []
            })
        });
        
        if (!response.ok) {
            throw new Error('Failed to update comment');
        }
        
        // Reload the modal to show updated comment
        if (window.mediaData && window.mediaData.muid) {
            openMediaViewModal(window.mediaData.muid);
        }
        
        if (App && App.Toast) {
            App.Toast.show('Comment updated!', 'success');
        }
    } catch (error) {
        console.error('Error updating comment:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to update comment. Please try again.', 'error');
        }
    }
}

/**
 * Deletes a media comment with confirmation
 */
function deleteMediaComment(commentCuid) {
    // Close the dropdown first
    document.querySelectorAll('[id^="media-comment-options-"]').forEach(menu => {
        menu.classList.add('hidden');
    });
    
    // Use app confirmation modal if available
    if (typeof showConfirmationModal === 'function') {
        showConfirmationModal('Delete this comment?', () => {
            performDeleteMediaComment(commentCuid);
        });
    } else {
        // Fallback to browser confirm
        if (confirm('Delete this comment?')) {
            performDeleteMediaComment(commentCuid);
        }
    }
}

/**
 * Actually performs the delete operation
 */
async function performDeleteMediaComment(commentCuid) {
    try {
        const response = await fetch(`/media/comment/${commentCuid}/delete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to delete comment');
        }
        
        // Reload the modal to show updated comments
        if (window.mediaData && window.mediaData.muid) {
            openMediaViewModal(window.mediaData.muid);
        }
        
        if (App && App.Toast) {
            App.Toast.show('Comment deleted!', 'success');
        }
    } catch (error) {
        console.error('Error deleting comment:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to delete comment. Please try again.', 'error');
        } else {
            alert('Failed to delete comment. Please try again.');
        }
    }
}

/**
 * Shows confirmation before hiding media comment
 */
function hideMediaComment(commentId) {
    // Close the dropdown first
    document.querySelectorAll('[id^="media-comment-options-"]').forEach(menu => {
        menu.classList.add('hidden');
    });
    
    // Try multiple methods to show confirmation modal
    if (typeof App !== 'undefined' && App.Modal && typeof App.Modal.showConfirm === 'function') {
        // Use App.Modal directly
        App.Modal.showConfirm(
            'Hide this comment from your view?',
            () => {
                performHideMediaComment(commentId);
            }
        );
    } else if (typeof showConfirmationModal === 'function') {
        // Use global wrapper function
        showConfirmationModal(
            'Hide this comment from your view?',
            () => {
                performHideMediaComment(commentId);
            }
        );
    } else {
        // Fallback to browser confirm
        if (confirm('Hide this comment from your view?')) {
            performHideMediaComment(commentId);
        }
    }
}

/**
 * Actually performs the hide operation
 */
async function performHideMediaComment(commentId) {
    try {
        const response = await fetch(`/media/comment/${commentId}/hide`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to hide comment');
        }
        
        // Reload the modal to show updated comments
        if (window.mediaData && window.mediaData.muid) {
            openMediaViewModal(window.mediaData.muid);
        }
        
        if (App && App.Toast) {
            App.Toast.show('Comment hidden', 'success');
        }
    } catch (error) {
        console.error('Error hiding comment:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to hide comment. Please try again.', 'error');
        } else {
            alert('Failed to hide comment. Please try again.');
        }
    }
}

/**
 * Shows confirmation before removing mention from media comment
 */
function removeMentionFromMediaComment(commentCuid) {
    // Close the dropdown first
    document.querySelectorAll('[id^="media-comment-options-"]').forEach(menu => {
        menu.classList.add('hidden');
    });
    
    // Use the app's confirmation modal
    if (typeof showConfirmationModal === 'function') {
        showConfirmationModal(
            'Remove your @mention from this comment? This action cannot be undone.',
            () => {
                performRemoveMentionFromMediaComment(commentCuid);
            }
        );
    } else {
        // Fallback to browser confirm
        if (confirm('Remove your @mention from this comment?')) {
            performRemoveMentionFromMediaComment(commentCuid);
        }
    }
}

/**
 * Actually performs the mention removal
 */
async function performRemoveMentionFromMediaComment(commentCuid) {
    try {
        const response = await fetch(`/media/comment/${commentCuid}/remove_mention`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to remove mention');
        }
        
        // Reload the modal to show updated comment
        if (window.mediaData && window.mediaData.muid) {
            openMediaViewModal(window.mediaData.muid);
        }
        
        if (App && App.Toast) {
            App.Toast.show('Your mention has been removed', 'success');
        }
    } catch (error) {
        console.error('Error removing mention:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to remove mention. Please try again.', 'error');
        } else {
            alert('Failed to remove mention. Please try again.');
        }
    }
}

/**
 * Opens media browser for attaching media to comments in media modal
 */
async function openMediaCommentMediaBrowser() {
    // Load the media module if not already loaded
    if (typeof App !== 'undefined' && App.loadModule) {
        await App.loadModule('media.js');
    }
    
    // Get currently selected media
    const hiddenInput = document.getElementById('media-comment-media-files');
    const currentSelected = hiddenInput ? JSON.parse(hiddenInput.value || '[]') : [];
    
    // Open browser with proper context
    if (typeof App !== 'undefined' && App.Media && App.Media.openBrowser) {
        App.Media.openBrowser('mediaComment', { 
            currentSelected: currentSelected
        });
    } else {
        // Fallback
        window.open('/browse_media?mode=multi_select', '_blank', 'width=800,height=600');
    }
}

/**
 * Handles file upload for media comments in media modal
 */
async function handleMediaCommentUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    
    // Show loading indicator
    const previewContainer = document.getElementById('media-comment-media-preview');
    if (previewContainer) {
        previewContainer.classList.remove('hidden');
        previewContainer.innerHTML = '<div class="text-sm text-gray-500">Uploading...</div>';
    }
    
    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }
    
    try {
        const response = await fetch('/upload_media', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Upload failed');
        }
        
        const data = await response.json();
        
        if (data.uploaded_media && data.uploaded_media.length > 0) {
            // Add to selected media
            const hiddenInput = document.getElementById('media-comment-media-files');
            const currentMedia = JSON.parse(hiddenInput.value || '[]');
            const newMedia = currentMedia.concat(data.uploaded_media);
            hiddenInput.value = JSON.stringify(newMedia);
            
            // Update preview
            updateMediaCommentPreview(newMedia);
            
            if (App && App.Toast) {
                App.Toast.show('Media uploaded successfully', 'success');
            }
        } else {
            throw new Error('No media files returned');
        }
    } catch (error) {
        console.error('Error uploading media:', error);
        if (previewContainer) {
            previewContainer.innerHTML = '';
            previewContainer.classList.add('hidden');
        }
        if (App && App.Toast) {
            App.Toast.show(error.message || 'Failed to upload media. Please try again.', 'error');
        } else {
            alert('Failed to upload media. Please try again.');
        }
    }
    
    // Clear file input
    event.target.value = '';
}

/**
 * Updates the media preview for comment form in media modal
 */
function updateMediaCommentPreview(mediaFiles) {
    const previewContainer = document.getElementById('media-comment-media-preview');
    
    if (!previewContainer) return;
    
    if (!mediaFiles || mediaFiles.length === 0) {
        previewContainer.innerHTML = '';
        previewContainer.classList.add('hidden');
        return;
    }
    
    previewContainer.classList.remove('hidden');
    previewContainer.innerHTML = mediaFiles.map((media, index) => {
        const isImage = media.media_file_path.toLowerCase().match(/\.(jpg|jpeg|png|gif|bmp|tiff|webp)$/);
        const isVideo = media.media_file_path.toLowerCase().match(/\.(mp4|mov|webm|avi|mkv)$/);
        const mediaUrl = `/media/${window.mediaData.currentUserPuid || 'current'}/${media.media_file_path}`;
        
        return `
        <div class="relative inline-block">
            ${isImage ? `
                <img src="${mediaUrl}" 
                     class="w-20 h-20 object-cover rounded border">
            ` : isVideo ? `
                <video class="w-20 h-20 object-cover rounded border" muted>
                    <source src="${mediaUrl}#t=0.1">
                </video>
            ` : `
                <div class="w-20 h-20 flex items-center justify-center bg-gray-200 dark:bg-gray-700 rounded border text-xs">
                    File
                </div>
            `}
            <button type="button" 
                    onclick="removeMediaCommentMedia(${index})"
                    class="absolute -top-2 -right-2 bg-red-500 text-white rounded-full w-5 h-5 flex items-center justify-center hover:bg-red-600">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        </div>
        `;
    }).join('');
}

/**
 * Removes a media item from comment media selection
 */
function removeMediaCommentMedia(index) {
    const hiddenInput = document.getElementById('media-comment-media-files');
    const currentMedia = JSON.parse(hiddenInput.value || '[]');
    currentMedia.splice(index, 1);
    hiddenInput.value = JSON.stringify(currentMedia);
    updateMediaCommentPreview(currentMedia);
}

/**
 * Opens modal to edit alt text
 */
function openEditAltTextModal() {
    // Hide options menu
    toggleMediaOptions();
    
    // Set current alt text in textarea
    const altTextInput = document.getElementById('alt-text-input');
    if (altTextInput && window.mediaData) {
        altTextInput.value = window.mediaData.alt_text || '';
    }
    
    openModal('edit-alt-text-modal');
}

/**
 * Saves the updated alt text
 */
async function saveAltText() {
    const altTextInput = document.getElementById('alt-text-input');
    const newAltText = altTextInput.value.trim();
    
    if (!window.mediaData || !window.mediaData.id) {
        console.error('Media data not available');
        if (App && App.Toast) {
            App.Toast.show('Error: Media data not available', 'error');
        }
        return;
    }
    
    try {
        const response = await fetch(`/update_media_alt_text/${window.mediaData.id}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ alt_text: newAltText })
        });
        
        if (!response.ok) {
            throw new Error('Failed to update alt text');
        }
        
        // Update the displayed alt text
        window.mediaData.alt_text = newAltText;
        const captionElement = document.querySelector('.media-caption');
        if (captionElement) {
            captionElement.textContent = newAltText || 'No caption';
        }
        
        closeModal('edit-alt-text-modal');
        
        if (App && App.Toast) {
            App.Toast.show('Alt text updated successfully!', 'success');
        }
    } catch (error) {
        console.error('Error updating alt text:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to update alt text. Please try again.', 'error');
        } else {
            alert('Failed to update alt text. Please try again.');
        }
    }
}

// Listen for messages from browse media window - handled by App.Media module
// But we need to add a handler for the mediaComment mode
if (typeof App !== 'undefined' && App.Media && !App.Media._mediaCommentListenerAdded) {
    const originalHandleSelection = App.Media._handleSelection ? App.Media._handleSelection.bind(App.Media) : null;
    App.Media._handleSelection = function(event) {
        const data = event.data || event;
        const openerMode = data.mode;
        
        if (openerMode === 'mediaComment') {
            // Handle media comment mode
            const hiddenInput = document.getElementById('media-comment-media-files');
            if (hiddenInput) {
                hiddenInput.value = JSON.stringify(data.selectedMedia);
                updateMediaCommentPreview(data.selectedMedia);
            }
        } else if (originalHandleSelection) {
            // Call original handler for other modes (only if it exists)
            originalHandleSelection(event);
        }
    };
    App.Media._mediaCommentListenerAdded = true;
}

/**
 * Toggles media comment dropdown with fixed positioning
 */
function toggleMediaCommentDropdown(event, dropdownId) {
    event.stopPropagation();
    
    const button = event.currentTarget;
    const dropdown = document.getElementById(dropdownId);
    
    if (!dropdown) return;
    
    // Close all other dropdowns first
    document.querySelectorAll('[id^="media-comment-options-"]').forEach(menu => {
        if (menu.id !== dropdownId) {
            menu.classList.add('hidden');
        }
    });
    
    // Toggle this dropdown
    const isHidden = dropdown.classList.contains('hidden');
    
    if (isHidden) {
        // Position the dropdown relative to the button
        const buttonRect = button.getBoundingClientRect();
        dropdown.style.top = `${buttonRect.bottom + 4}px`;
        dropdown.style.left = `${buttonRect.right - 192}px`; // 192px = w-48 width
        dropdown.classList.remove('hidden');
    } else {
        dropdown.classList.add('hidden');
    }
}

/**
 * Disables comments on the media's parent post
 */
async function toggleMediaComments(muid) {
    // Close the dropdown first
    toggleMediaOptions();
    
    // Get the parent post CUID from window.mediaData
    if (!window.mediaData || !window.mediaData.post_cuid) {
        console.error('Post CUID not available');
        if (App && App.Toast) {
            App.Toast.show('Unable to disable comments', 'error');
        }
        return;
    }
    
    const postCuid = window.mediaData.post_cuid;
    
    // Show confirmation modal
    const confirmed = await new Promise((resolve) => {
        if (typeof App !== 'undefined' && App.Modal && typeof App.Modal.showConfirm === 'function') {
            App.Modal.showConfirm(
                'Are you sure you want to permanently disable comments on this post? This cannot be undone.',
                () => resolve(true),
                () => resolve(false)
            );
        } else if (typeof showConfirmationModal === 'function') {
            showConfirmationModal(
                'Are you sure you want to permanently disable comments on this post? This cannot be undone.',
                () => resolve(true)
            );
            // If modal doesn't have cancel callback, assume they'll dismiss
        } else {
            // Fallback to browser confirm
            resolve(confirm('Are you sure you want to permanently disable comments on this post? This cannot be undone.'));
        }
    });
    
    if (!confirmed) return;
    
    try {
        const response = await fetch(`/post/${postCuid}/disable_comments`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to disable comments');
        }
        
        // Reload the modal to show updated state
        if (window.mediaData && window.mediaData.muid) {
            openMediaViewModal(window.mediaData.muid);
        }
        
        if (App && App.Toast) {
            App.Toast.show('Comments have been disabled for this post', 'success');
        }
    } catch (error) {
        console.error('Error disabling comments:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to disable comments. Please try again.', 'error');
        } else {
            alert('Failed to disable comments. Please try again.');
        }
    }
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('[id^="media-comment-options-"]') && !e.target.closest('button[onclick*="toggleMediaCommentDropdown"]')) {
        document.querySelectorAll('[id^="media-comment-options-"]').forEach(menu => {
            menu.classList.add('hidden');
        });
    }
});

// Export to global scope
window.toggleMediaCommentDropdown = toggleMediaCommentDropdown;

// Make functions globally available
window.navigateToMedia = navigateToMedia;
window.toggleMediaOptions = toggleMediaOptions;
window.openMediaTagModal = openMediaTagModal;
window.toggleMediaFriendTag = toggleMediaFriendTag;
window.applyMediaTags = applyMediaTags;
window.showAllTaggedPeople = showAllTaggedPeople;
window.submitMediaComment = submitMediaComment;
window.replyToMediaComment = replyToMediaComment;
window.cancelMediaCommentReply = cancelMediaCommentReply;
window.submitMediaCommentReply = submitMediaCommentReply;
window.editMediaComment = editMediaComment;
window.deleteMediaComment = deleteMediaComment;
window.hideMediaComment = hideMediaComment;
window.openMediaCommentMediaBrowser = openMediaCommentMediaBrowser;
window.handleMediaCommentUpload = handleMediaCommentUpload;
window.removeMediaCommentMedia = removeMediaCommentMedia;
window.removeMentionFromMediaComment = removeMentionFromMediaComment;
window.openEditAltTextModal = openEditAltTextModal;
window.saveAltText = saveAltText;
window.filterMediaTagFriends = filterMediaTagFriends;
window.confirmUntagMyself = confirmUntagMyself;
window.untagMyself = untagMyself;
window.updateMediaComment = updateMediaComment;
window.performDeleteMediaComment = performDeleteMediaComment;
window.performRemoveMentionFromMediaComment = performRemoveMentionFromMediaComment;
window.performHideMediaComment = performHideMediaComment;
window.toggleMediaComments = toggleMediaComments;
window.displayTaggedPeopleList = displayTaggedPeopleList;