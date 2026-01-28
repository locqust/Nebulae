/**
 * post_tagging.js
 * Handles friend tagging and location features for post creation
 */

// Store selected friends and location
let selectedFriends = [];
let currentLocation = '';

/**
 * Opens a Tailwind-based modal (for tag/location modals)
 */

/**
 * Closes a Tailwind-based modal (for tag/location modals)
 */

/**
 * Closes modal when clicking on backdrop
 */

/**
 * Opens the tag friends modal and loads friends list
 */
async function openTagFriendsModal() {
    const modal = document.getElementById('tag-friends-modal');
    if (!modal) return;
    
    openModal('tag-friends-modal');
    
    // Load friends list
    try {
        const response = await fetch('/friends/api/friends_list');
        if (!response.ok) {
            throw new Error('Failed to load friends');
        }
        
        const data = await response.json();
        displayFriendsList(data.friends);
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
 * Displays the list of friends with checkboxes
 */
function displayFriendsList(friends) {
    const listContainer = document.getElementById('tag-friends-list');
    
    if (!friends || friends.length === 0) {
        listContainer.innerHTML = `
            <div class="text-center secondary-text py-8">
                <svg class="w-12 h-12 mx-auto mb-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"></path>
                </svg>
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
                   id="friend-${friend.puid}" 
                   value="${friend.puid}"
                   ${selectedFriends.includes(friend.puid) ? 'checked' : ''}
                   onchange="toggleFriendTag('${friend.puid}')"
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
            <label for="friend-${friend.puid}" class="flex-1 cursor-pointer primary-text">
                ${friend.display_name}
            </label>
        </div>
    `).join('');
}

/**
 * Filters friends list based on search input
 */
function filterTagFriends() {
    const searchInput = document.getElementById('tag-friends-search');
    const searchTerm = searchInput.value.toLowerCase();
    const friendItems = document.querySelectorAll('.friend-item');
    
    friendItems.forEach(item => {
        const name = item.getAttribute('data-name');
        if (name.includes(searchTerm)) {
            item.style.display = 'flex';
        } else {
            item.style.display = 'none';
        }
    });
}

/**
 * Toggles a friend's tagged status
 */
function toggleFriendTag(puid) {
    const index = selectedFriends.indexOf(puid);
    if (index > -1) {
        selectedFriends.splice(index, 1);
    } else {
        selectedFriends.push(puid);
    }
}

/**
 * Applies the selected friends and updates the display
 */
function applyTaggedFriends() {
    updateTaggedUsersDisplay();
    closeModal('tag-friends-modal');
}

/**
 * Updates the tagged users display in the post form
 */
function updateTaggedUsersDisplay() {
    const section = document.getElementById('tagged-users-section');
    const listContainer = document.getElementById('tagged-users-list');
    const hiddenInput = document.getElementById('tagged-users-input');
    
    if (selectedFriends.length === 0) {
        section.style.display = 'none';
        hiddenInput.value = '[]';
        return;
    }
    
    // Get friend names from the modal
    const friendElements = selectedFriends.map(puid => {
        const friendItem = document.querySelector(`.friend-item[data-puid="${puid}"]`);
        if (!friendItem) return null;
        
        const label = friendItem.querySelector('label');
        const name = label ? label.textContent.trim() : 'Unknown';
        
        return `
            <div class="inline-flex items-center gap-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-3 py-1 rounded-full text-sm">
                <span>${name}</span>
                <button type="button" onclick="removeTaggedUser('${puid}')" class="ml-1 text-blue-600 dark:text-blue-300 hover:text-blue-800 dark:hover:text-blue-100">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
        `;
    }).filter(Boolean);
    
    listContainer.innerHTML = friendElements.join('');
    section.style.display = 'block';
    hiddenInput.value = JSON.stringify(selectedFriends);
}

/**
 * Removes a tagged user
 */
function removeTaggedUser(puid) {
    const index = selectedFriends.indexOf(puid);
    if (index > -1) {
        selectedFriends.splice(index, 1);
    }
    
    // Update checkbox if modal is open
    const checkbox = document.getElementById(`friend-${puid}`);
    if (checkbox) {
        checkbox.checked = false;
    }
    
    updateTaggedUsersDisplay();
}

/**
 * Opens the location modal
 */
function openLocationModal() {
    const modal = document.getElementById('location-modal');
    if (!modal) return;
    
    openModal('location-modal');
    
    // Pre-fill with current location if any
    const input = document.getElementById('location-input-field');
    if (input) {
        input.value = currentLocation;
        input.focus();
    }
}

/**
 * Applies the location and updates the display
 */
function applyLocation() {
    const input = document.getElementById('location-input-field');
    const location = input.value.trim();
    
    if (!location) {
        // If empty, just close
        closeModal('location-modal');
        return;
    }
    
    currentLocation = location;
    updateLocationDisplay();
    closeModal('location-modal');
}

/**
 * Updates the location display in the post form
 */
function updateLocationDisplay() {
    const section = document.getElementById('location-section');
    const display = document.getElementById('location-display');
    const hiddenInput = document.getElementById('location-input');
    
    if (!currentLocation) {
        section.style.display = 'none';
        hiddenInput.value = '';
        return;
    }
    
    display.textContent = currentLocation;
    section.style.display = 'block';
    hiddenInput.value = currentLocation;
}

/**
 * Removes the location
 */
function removeLocation() {
    currentLocation = '';
    updateLocationDisplay();
}

/**
 * Closes a tag/location modal by ID
 */

/**
 * Closes modal when clicking on backdrop
 */

/**
 * Resets all tagging data (call on form submit)
 */
function resetPostTagging() {
    selectedFriends = [];
    currentLocation = '';
    updateTaggedUsersDisplay();
    updateLocationDisplay();
}

// Add event listener to form submission to reset
document.addEventListener('DOMContentLoaded', () => {
    const forms = document.querySelectorAll('form[action*="create_post"], form[action*="create_group_post"], form[action*="create_event_post"]');
    forms.forEach(form => {
        form.addEventListener('submit', () => {
            // The form will submit with the current values
            // Reset after a delay to allow form submission
            setTimeout(resetPostTagging, 100);
        });
    });
    
    // Allow Enter key in location modal to submit
    const locationInput = document.getElementById('location-input-field');
    if (locationInput) {
        locationInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                applyLocation();
            }
        });
    }
});

// Make functions available globally
window.openTagFriendsModal = openTagFriendsModal;
window.filterTagFriends = filterTagFriends;
window.toggleFriendTag = toggleFriendTag;
window.applyTaggedFriends = applyTaggedFriends;
window.removeTaggedUser = removeTaggedUser;
window.openLocationModal = openLocationModal;
window.applyLocation = applyLocation;
window.removeLocation = removeLocation;
window.showTaggedPeopleModal = showTaggedPeopleModal;

/**
 * Shows modal with all tagged people for a post
 * @param {string} postCuid - The post CUID to fetch tagged users for
 * @param {Event} event - The click event
 */
async function showTaggedPeopleModal(postCuid, event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    const modal = document.getElementById('tagged-people-modal');
    if (!modal) return;
    
    openModal('tagged-people-modal');
    
    // Fetch post data to get tagged users
    try {
        const response = await fetch(`/api/post/${postCuid}/tagged_users`);
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
                     class="w-12 h-12 rounded-full object-cover"
                     onerror="this.src='/static/images/default_avatar.png'">
            ` : `
                <svg class="w-12 h-12 text-gray-500 rounded-full" fill="currentColor" viewBox="0 0 20 20">
                    <path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"></path>
                </svg>
            `}
            <div class="flex-1">
                <a href="${user.profile_url}" class="name-link font-medium">
                    ${user.display_name}
                </a>
            </div>
        </div>
    `).join('');
}