/**
 * edit_post_tagging.js
 * Handles friend tagging and location editing in the edit post modal
 * All functions are globally available
 */

// Store edit state separately from create post state
var editSelectedFriends = [];
var editCurrentLocation = '';

/**
 * Opens tag friends modal for editing
 */
function openEditTagFriendsModal() {
    console.log('openEditTagFriendsModal called');
    var modal = document.getElementById('tag-friends-modal');
    if (!modal) {
        console.error('Tag friends modal not found');
        return;
    }
    
    openModal('tag-friends-modal');
    
    // Load friends list
    fetch('/friends/api/friends_list')
        .then(function(response) {
            if (!response.ok) {
                throw new Error('Failed to load friends');
            }
            return response.json();
        })
        .then(function(data) {
            displayEditFriendsList(data.friends);
        })
        .catch(function(error) {
            console.error('Error loading friends:', error);
            document.getElementById('tag-friends-list').innerHTML = '<div class="text-center secondary-text py-8"><p class="text-red-500">Error loading friends. Please try again.</p></div>';
        });
}

/**
 * Displays friends list for editing with current selections
 */
function displayEditFriendsList(friends) {
    var listContainer = document.getElementById('tag-friends-list');
    
    if (!friends || friends.length === 0) {
        listContainer.innerHTML = '<div class="text-center secondary-text py-8"><svg class="w-12 h-12 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"></path></svg><p>No friends to tag</p></div>';
        return;
    }
    
    var html = '';
    for (var i = 0; i < friends.length; i++) {
        var friend = friends[i];
        var isChecked = editSelectedFriends.indexOf(friend.puid) > -1;
        html += '<div class="friend-item flex items-center gap-3 p-3 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-md" data-puid="' + friend.puid + '" data-name="' + friend.display_name.toLowerCase() + '">';
        html += '<input type="checkbox" id="friend-' + friend.puid + '" value="' + friend.puid + '" ' + (isChecked ? 'checked' : '') + ' onchange="toggleEditFriendTag(\'' + friend.puid + '\')" class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500">';
        if (friend.profile_picture_url) {
            html += '<img src="' + friend.profile_picture_url + '" alt="' + friend.display_name + '" class="w-10 h-10 rounded-full object-cover" onerror="this.src=\'/static/images/default_avatar.png\'">';
        } else {
            html += '<svg class="w-10 h-10 text-gray-500 rounded-full" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"></path></svg>';
        }
        html += '<label for="friend-' + friend.puid + '" class="flex-1 cursor-pointer primary-text">' + friend.display_name + '</label>';
        html += '</div>';
    }
    listContainer.innerHTML = html;
}

/**
 * Toggles friend selection for editing
 */
function toggleEditFriendTag(puid) {
    var index = editSelectedFriends.indexOf(puid);
    if (index > -1) {
        editSelectedFriends.splice(index, 1);
    } else {
        editSelectedFriends.push(puid);
    }
}

/**
 * Applies tagged friends to edit form
 */
function applyEditTaggedFriends() {
    var input = document.getElementById('edit-tagged-users');
    if (input) {
        input.value = JSON.stringify(editSelectedFriends);
    }
    updateEditTaggedUsersDisplay();
    if (typeof closeModal === 'function') {
        closeModal('tag-friends-modal');
    }
}

/**
 * Updates the display of tagged users in edit form
 */
function updateEditTaggedUsersDisplay() {
    var displayContainer = document.getElementById('edit-tagged-users-display');
    if (!displayContainer) return;
    
    if (editSelectedFriends.length === 0) {
        displayContainer.classList.add('hidden');
        displayContainer.innerHTML = '';
        return;
    }
    
    var html = '';
    for (var i = 0; i < editSelectedFriends.length; i++) {
        var puid = editSelectedFriends[i];
        var checkbox = document.querySelector('#friend-' + puid);
        var label = checkbox ? checkbox.parentElement.querySelector('label') : null;
        var name = label ? label.textContent.trim() : (window.editFriendNamesMap && window.editFriendNamesMap[puid] ? window.editFriendNamesMap[puid] : puid);
        
        html += '<span class="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-sm">';
        html += name;
        html += '<button type="button" onclick="removeEditTaggedUser(\'' + puid + '\')" class="hover:text-blue-600 dark:hover:text-blue-400">';
        html += '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>';
        html += '</button></span>';
    }
    
    displayContainer.classList.remove('hidden');
    displayContainer.innerHTML = html;
}

/**
 * Updates tagged users display with actual names (called after fetching friend list)
 */
function updateEditTaggedUsersDisplayWithNames() {
    var displayContainer = document.getElementById('edit-tagged-users-display');
    if (!displayContainer) return;
    
    if (editSelectedFriends.length === 0) {
        displayContainer.classList.add('hidden');
        displayContainer.innerHTML = '';
        return;
    }
    
    var html = '';
    for (var i = 0; i < editSelectedFriends.length; i++) {
        var puid = editSelectedFriends[i];
        var name = window.editFriendNamesMap && window.editFriendNamesMap[puid] ? window.editFriendNamesMap[puid] : puid;
        
        html += '<span class="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full text-sm">';
        html += name;
        html += '<button type="button" onclick="removeEditTaggedUser(\'' + puid + '\')" class="hover:text-blue-600 dark:hover:text-blue-400">';
        html += '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>';
        html += '</button></span>';
    }
    
    displayContainer.classList.remove('hidden');
    displayContainer.innerHTML = html;
}

/**
 * Removes a tagged user from edit form
 */
function removeEditTaggedUser(puid) {
    var index = editSelectedFriends.indexOf(puid);
    if (index > -1) {
        editSelectedFriends.splice(index, 1);
    }
    
    var checkbox = document.getElementById('friend-' + puid);
    if (checkbox) {
        checkbox.checked = false;
    }
    
    var input = document.getElementById('edit-tagged-users');
    if (input) {
        input.value = JSON.stringify(editSelectedFriends);
    }
    updateEditTaggedUsersDisplay();
}

/**
 * Opens location modal for editing
 */
function openEditLocationModal() {
    console.log('openEditLocationModal called');
    var modal = document.getElementById('location-modal');
    if (!modal) {
        console.error('Location modal not found');
        return;
    }
    
    openModal('location-modal');
    
    var input = document.getElementById('location-input-field');
    if (input) {
        input.value = editCurrentLocation;
        input.focus();
    }
}

/**
 * Applies location to edit form
 */
function applyEditLocation() {
    var input = document.getElementById('location-input-field');
    if (!input) return;
    
    var location = input.value.trim();
    
    if (location.length > 200) {
        alert('Location must be 200 characters or less');
        return;
    }
    
    editCurrentLocation = location;
    
    var hiddenInput = document.getElementById('edit-location');
    if (hiddenInput) {
        hiddenInput.value = location;
    }
    
    updateEditLocationDisplay();
    
    if (typeof closeModal === 'function') {
        closeModal('location-modal');
    }
}

/**
 * Updates the display of location in edit form
 */
function updateEditLocationDisplay() {
    var displayContainer = document.getElementById('edit-location-display');
    if (!displayContainer) return;
    
    if (!editCurrentLocation) {
        displayContainer.classList.add('hidden');
        displayContainer.innerHTML = '';
        return;
    }
    
    displayContainer.classList.remove('hidden');
    displayContainer.innerHTML = '<span class="inline-flex items-center gap-1 px-3 py-1 bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 rounded-full text-sm"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>' + editCurrentLocation + '<button type="button" onclick="removeEditLocation()" class="hover:text-green-600 dark:hover:text-green-400"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg></button></span>';
}

/**
 * Removes location from edit form
 */
function removeEditLocation() {
    editCurrentLocation = '';
    var hiddenInput = document.getElementById('edit-location');
    if (hiddenInput) {
        hiddenInput.value = '';
    }
    updateEditLocationDisplay();
}

/**
 * Initializes edit form with existing post data
 * Called when opening the edit modal
 */
function initializeEditPostTagging(taggedUserPuids, location) {
    if (typeof taggedUserPuids === 'string') {
        try {
            editSelectedFriends = taggedUserPuids ? JSON.parse(taggedUserPuids) : [];
        } catch (e) {
            editSelectedFriends = [];
        }
    } else if (Array.isArray(taggedUserPuids)) {
        editSelectedFriends = taggedUserPuids.slice();
    } else {
        editSelectedFriends = [];
    }
    
    editCurrentLocation = location || '';
    
    var taggedInput = document.getElementById('edit-tagged-users');
    var locationInput = document.getElementById('edit-location');
    
    if (taggedInput) taggedInput.value = JSON.stringify(editSelectedFriends);
    if (locationInput) locationInput.value = editCurrentLocation;
    
    // NEW: Update displays - but we need to fetch friend names first for proper display
    if (editSelectedFriends.length > 0) {
        // Fetch friends list to get names
        fetch('/friends/api/friends_list')
            .then(function(response) { return response.json(); })
            .then(function(data) {
                // Create a map of puid to friend data
                window.editFriendNamesMap = {};
                if (data.friends) {
                    for (var i = 0; i < data.friends.length; i++) {
                        var friend = data.friends[i];
                        window.editFriendNamesMap[friend.puid] = friend.display_name;
                    }
                }
                updateEditTaggedUsersDisplayWithNames();
            })
            .catch(function(error) {
                console.error('Error fetching friend names:', error);
                // Fall back to showing PUIDs
                updateEditTaggedUsersDisplay();
            });
    } else {
        updateEditTaggedUsersDisplay();
    }
    
    updateEditLocationDisplay();
}

/**
 * Resets edit post tagging state
 */
function resetEditPostTagging() {
    editSelectedFriends = [];
    editCurrentLocation = '';
    
    var taggedInput = document.getElementById('edit-tagged-users');
    var locationInput = document.getElementById('edit-location');
    
    if (taggedInput) taggedInput.value = '[]';
    if (locationInput) locationInput.value = '';
    
    updateEditTaggedUsersDisplay();
    updateEditLocationDisplay();
}

// Override the Done button in tag modal to use edit functions when in edit mode
document.addEventListener('DOMContentLoaded', function() {
    // We'll detect if we're in edit mode by checking if edit-tagged-users input exists
    var tagModalDoneBtn = document.querySelector('#tag-friends-modal button[onclick*="applyTaggedFriends"]');
    if (tagModalDoneBtn) {
        // Create a wrapper that detects context
        var originalOnClick = tagModalDoneBtn.getAttribute('onclick');
        tagModalDoneBtn.setAttribute('onclick', '');
        tagModalDoneBtn.addEventListener('click', function() {
            // Check if we're in edit mode
            var editInput = document.getElementById('edit-tagged-users');
            var editModal = document.getElementById('editPostModal');
            var isEditMode = editInput && editModal && (editModal.classList.contains('flex') || !editModal.classList.contains('hidden'));
            
            if (isEditMode) {
                applyEditTaggedFriends();
            } else if (typeof applyTaggedFriends === 'function') {
                applyTaggedFriends();
            }
        });
    }
    
    // Same for location modal
    var locationModalAddBtn = document.querySelector('#location-modal button[onclick*="applyLocation"]');
    if (locationModalAddBtn) {
        var originalOnClick = locationModalAddBtn.getAttribute('onclick');
        locationModalAddBtn.setAttribute('onclick', '');
        locationModalAddBtn.addEventListener('click', function() {
            var editInput = document.getElementById('edit-location');
            var editModal = document.getElementById('editPostModal');
            var isEditMode = editInput && editModal && (editModal.classList.contains('flex') || !editModal.classList.contains('hidden'));
            
            if (isEditMode) {
                applyEditLocation();
            } else if (typeof applyLocation === 'function') {
                applyLocation();
            }
        });
    }
});

console.log('Edit post tagging script loaded. Functions available:', typeof openEditTagFriendsModal, typeof openEditLocationModal);