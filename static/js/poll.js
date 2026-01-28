/**
 * poll.js
 * Handles poll creation and voting functionality
 */

// Store poll data for the create post form
let pollData = null;

/**
 * Opens the poll creation modal
 */
function openPollModal() {
    openModal('poll-modal');
    
    // Reset to default 3 options
    const container = document.getElementById('poll-options-container');
    if (container) {
        container.innerHTML = `
            <div class="poll-option-item flex items-center gap-2 mb-2">
                <input type="text" 
                       class="poll-option-input flex-1 px-4 py-2 border rounded-md form-input"
                       placeholder="Option 1"
                       maxlength="200">
                <button type="button" 
                        onclick="removePollOption(this)"
                        class="text-gray-400 hover:text-red-500 p-2 cursor-not-allowed opacity-50"
                        disabled>
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            <div class="poll-option-item flex items-center gap-2 mb-2">
                <input type="text" 
                       class="poll-option-input flex-1 px-4 py-2 border rounded-md form-input"
                       placeholder="Option 2"
                       maxlength="200">
                <button type="button" 
                        onclick="removePollOption(this)"
                        class="text-gray-400 hover:text-red-500 p-2 cursor-not-allowed opacity-50"
                        disabled>
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            <div class="poll-option-item flex items-center gap-2 mb-2">
                <input type="text" 
                       class="poll-option-input flex-1 px-4 py-2 border rounded-md form-input"
                       placeholder="Option 3"
                       maxlength="200">
                <button type="button" 
                        onclick="removePollOption(this)"
                        class="text-gray-400 hover:text-red-500 p-2">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
        `;
    }
    
    // Reset checkboxes
    const allowMultiple = document.getElementById('poll-allow-multiple');
    const allowAddOptions = document.getElementById('poll-allow-add-options');
    if (allowMultiple) allowMultiple.checked = false;
    if (allowAddOptions) allowAddOptions.checked = false;
    
    // Hide error
    const errorDiv = document.getElementById('poll-error');
    if (errorDiv) {
        errorDiv.classList.add('hidden');
    }
}

/**
 * Closes the poll creation modal
 */
function closePollModal() {
    closeModal('poll-modal');
}

/**
 * Adds a new poll option input
 */
function addPollOption() {
    const container = document.getElementById('poll-options-container');
    const currentOptions = container.querySelectorAll('.poll-option-item');
    const nextNum = currentOptions.length + 1;
    
    if (currentOptions.length >= 10) {
        showPollError('Maximum 10 options allowed');
        return;
    }
    
    const newOption = document.createElement('div');
    newOption.className = 'poll-option-item flex items-center gap-2 mb-2';
    newOption.innerHTML = `
        <input type="text" 
               class="poll-option-input flex-1 px-4 py-2 border rounded-md form-input"
               placeholder="Option ${nextNum}"
               maxlength="200">
        <button type="button" 
                onclick="removePollOption(this)"
                class="text-gray-400 hover:text-red-500 p-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
            </svg>
        </button>
    `;
    
    container.appendChild(newOption);
    updateRemoveButtons();
}

/**
 * Removes a poll option
 */
function removePollOption(button) {
    const container = document.getElementById('poll-options-container');
    const options = container.querySelectorAll('.poll-option-item');
    
    if (options.length <= 2) {
        showPollError('Poll must have at least 2 options');
        return;
    }
    
    button.closest('.poll-option-item').remove();
    updateRemoveButtons();
}

/**
 * Updates the state of remove buttons (first 2 should be disabled)
 */
function updateRemoveButtons() {
    const container = document.getElementById('poll-options-container');
    const options = container.querySelectorAll('.poll-option-item');
    
    options.forEach((option, index) => {
        const button = option.querySelector('button');
        if (index < 2) {
            button.disabled = true;
            button.classList.add('cursor-not-allowed', 'opacity-50');
        } else {
            button.disabled = false;
            button.classList.remove('cursor-not-allowed', 'opacity-50');
        }
    });
}

/**
 * Shows an error message in the poll modal
 */
function showPollError(message) {
    const errorDiv = document.getElementById('poll-error');
    if (errorDiv) {
        errorDiv.textContent = message;
        errorDiv.classList.remove('hidden');
        setTimeout(() => {
            errorDiv.classList.add('hidden');
        }, 3000);
    }
}

/**
 * Validates poll data
 */
function validatePoll(options) {
    if (options.length < 2) {
        showPollError('Please add at least 2 options');
        return false;
    }
    
    // Check for empty options
    const emptyOptions = options.filter(opt => !opt.trim());
    if (emptyOptions.length > 0) {
        showPollError('Please fill in all options or remove empty ones');
        return false;
    }
    
    // Check for duplicate options
    const uniqueOptions = new Set(options.map(opt => opt.trim().toLowerCase()));
    if (uniqueOptions.size !== options.length) {
        showPollError('Duplicate options are not allowed');
        return false;
    }
    
    return true;
}

/**
 * Applies the poll to the post
 */
function applyPoll() {
    const container = document.getElementById('poll-options-container');
    const optionInputs = container.querySelectorAll('.poll-option-input');
    
    // Collect options
    const options = [];
    optionInputs.forEach(input => {
        const value = input.value.trim();
        if (value) {
            options.push(value);
        }
    });
    
    // Validate
    if (!validatePoll(options)) {
        return;
    }
    
    // Get settings
    const allowMultiple = document.getElementById('poll-allow-multiple').checked;
    const allowAddOptions = document.getElementById('poll-allow-add-options').checked;
    
    // Store poll data
    pollData = {
        options: options,
        allow_multiple_answers: allowMultiple,
        allow_add_options: allowAddOptions
    };
    
    // Update hidden input
    const hiddenInput = document.getElementById('poll-data-input');
    if (hiddenInput) {
        hiddenInput.value = JSON.stringify(pollData);
    }
    
    // Update display
    updatePollDisplay();
    
    // Close modal
    closePollModal();
}

/**
 * Updates the poll display in the create post form
 */
function updatePollDisplay() {
    const section = document.getElementById('poll-display-section');
    const optionsContainer = document.getElementById('poll-display-options');
    const settingsContainer = document.getElementById('poll-display-settings');
    
    if (!pollData || !pollData.options || pollData.options.length === 0) {
        if (section) section.classList.add('hidden');
        return;
    }
    
    // Show section
    if (section) section.classList.remove('hidden');
    
    // Display options
    if (optionsContainer) {
        optionsContainer.innerHTML = pollData.options.map((option, index) => `
            <div class="flex items-center gap-2 text-sm">
                <div class="w-2 h-2 rounded-full bg-blue-500"></div>
                <span class="secondary-text">${escapeHtml(option)}</span>
            </div>
        `).join('');
    }
    
    // Display settings
    if (settingsContainer) {
        const settings = [];
        if (pollData.allow_multiple_answers) {
            settings.push('✓ Multiple answers allowed');
        }
        if (pollData.allow_add_options) {
            settings.push('✓ Anyone can add options');
        }
        
        settingsContainer.innerHTML = settings.length > 0 
            ? settings.join('<br>') 
            : '<span class="text-gray-400">Single choice poll</span>';
    }
}

/**
 * Removes poll from the post
 */
function removePollFromPost() {
    pollData = null;
    
    const hiddenInput = document.getElementById('poll-data-input');
    if (hiddenInput) {
        hiddenInput.value = '';
    }
    
    const section = document.getElementById('poll-display-section');
    if (section) {
        section.classList.add('hidden');
    }
}

/**
 * Votes on a poll option
 */
async function voteOnPoll(postCuid, optionId, isMultiChoice) {
    try {
        const response = await fetch(`/polls/vote/${postCuid}/${optionId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error('Failed to vote');
        }
        
        const data = await response.json();
        
        // Reload poll data
        if (data.success) {
            reloadPollDisplay(postCuid);
        }
    } catch (error) {
        console.error('Error voting on poll:', error);
        if (App.Toast && typeof App.Toast.show === 'function') {
            App.Toast.show('Failed to submit vote', 'error');
        }
    }
}

/**
 * Reloads poll display after voting
 */
async function reloadPollDisplay(postCuid) {
    try {
        const response = await fetch(`/polls/data/${postCuid}`);
        if (!response.ok) {
            throw new Error('Failed to load poll data');
        }
        
        const data = await response.json();
        updatePollDisplayInPost(postCuid, data.poll);
    } catch (error) {
        console.error('Error reloading poll:', error);
    }
}

/**
 * Updates poll display in a post after voting or deleting options
 */
function updatePollDisplayInPost(postCuid, pollData) {
    const pollContainer = document.querySelector(`[data-poll-cuid="${postCuid}"]`);
    if (!pollContainer) return;
    
    // Find the options container
    const optionsContainer = pollContainer.querySelector('.poll-options-container');
    if (!optionsContainer) return;
    
    // Check if current user is the poll creator
    const isCreator = pollData.is_creator || false;
    const canDelete = isCreator && pollData.options.length > 2;
    
    // Rebuild the options display
    optionsContainer.innerHTML = pollData.options.map(option => {
        const isVoted = pollData.viewer_votes && pollData.viewer_votes.includes(option.id);
        const percentage = option.percentage || 0;
        
        return `
            <div class="poll-option ${isVoted ? 'poll-option-voted' : ''} relative cursor-pointer rounded-lg border border-gray-300 dark:border-gray-600 p-3 transition hover:border-blue-400 dark:hover:border-blue-500" 
                 onclick="voteOnPoll('${postCuid}', ${option.id}, ${pollData.allow_multiple_answers})">
                <div class="poll-option-bar absolute inset-0 bg-blue-100 dark:bg-blue-900 rounded-lg transition-all" 
                     style="width: ${percentage}%; opacity: 0.3;"></div>
                <div class="poll-option-content relative flex items-center justify-between">
                    <div class="flex items-center gap-3 flex-1">
                        ${pollData.allow_multiple_answers 
                            ? `<input type="checkbox" ${isVoted ? 'checked' : ''} onclick="event.stopPropagation()" class="w-4 h-4 text-blue-600 bg-gray-100 border-gray-300 rounded focus:ring-blue-500">` 
                            : `<div class="poll-radio w-4 h-4 rounded-full border-2 ${isVoted ? 'border-blue-600' : 'border-gray-400'} flex items-center justify-center">
                                ${isVoted ? '<div class="w-2 h-2 rounded-full bg-blue-600"></div>' : ''}
                               </div>`
                        }
                        <span class="flex-1 primary-text">${escapeHtml(option.option_text)}</span>
                    </div>
                    <div class="flex items-center gap-3">
                        <span class="poll-percentage font-semibold text-blue-600 dark:text-blue-400">${percentage}%</span>
                        ${option.vote_count > 0 
                            ? `<button onclick="showPollVoters(event, ${option.id})" class="text-xs text-gray-500 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400 underline">${option.vote_count} vote${option.vote_count !== 1 ? 's' : ''}</button>` 
                            : ''
                        }
                        ${canDelete 
                            ? `<button onclick="event.stopPropagation(); deletePollOption('${postCuid}', ${option.id})" class="text-gray-400 hover:text-red-500 ml-2" title="Delete this option" aria-label="Delete option">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                                </svg>
                               </button>` 
                            : ''
                        }
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    // Update total votes
    const totalVotesEl = pollContainer.querySelector('.poll-total-votes');
    if (totalVotesEl) {
        totalVotesEl.textContent = `${pollData.total_votes} vote${pollData.total_votes !== 1 ? 's' : ''}`;
    }
}

/**
 * Shows voters for a poll option
 */
async function showPollVoters(event, optionId) {
    event.stopPropagation();
    
    try {
        const response = await fetch(`/polls/voters/${optionId}`);
        if (!response.ok) {
            throw new Error('Failed to load voters');
        }
        
        const data = await response.json();
        displayVotersModal(data.voters);
    } catch (error) {
        console.error('Error loading voters:', error);
        if (App.Toast && typeof App.Toast.show === 'function') {
            App.Toast.show('Failed to load voters', 'error');
        }
    }
}

/**
 * Displays voters in a modal
 */
function displayVotersModal(voters) {
    // Create modal HTML
    const modalHtml = `
        <div id="poll-voters-modal" class="modal flex">
            <div class="modal-content max-w-md">
                <span class="close-button" onclick="closePollVotersModal()">&times;</span>
                <h3 class="text-lg font-semibold primary-text mb-4">Voters</h3>
                <div class="max-h-96 overflow-y-auto">
                    ${voters.length > 0 
                        ? voters.map(voter => `
                            <div class="flex items-center gap-3 p-2 hover:bg-gray-50 dark:hover:bg-gray-800 rounded">
                                <div class="w-10 h-10 rounded-full overflow-hidden border border-gray-300 dark:border-gray-600">
                                    ${voter.profile_picture_path 
                                        ? `<img src="${getProfilePictureUrl(voter)}" alt="${voter.display_name}" class="w-full h-full object-cover" onerror="this.src='/static/images/default_avatar.png';">`
                                        : `<svg class="w-full h-full text-gray-500" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 9a3 3 0 100-6 3 3 0 000 6zm-7 9a7 7 0 1114 0H3z" clip-rule="evenodd"></path></svg>`
                                    }
                                </div>
                                <a href="${getUserProfileUrl(voter)}" class="name-link">${escapeHtml(voter.display_name)}</a>
                            </div>
                        `).join('')
                        : '<p class="text-center text-gray-500 py-4">No votes yet</p>'
                    }
                </div>
                <div class="flex justify-end mt-4">
                    <button onclick="closePollVotersModal()" class="px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600">Close</button>
                </div>
            </div>
        </div>
    `;
    
    // Add to body
    const temp = document.createElement('div');
    temp.innerHTML = modalHtml;
    document.body.appendChild(temp.firstElementChild);
}

/**
 * Closes poll voters modal
 */
function closePollVotersModal() {
    const modal = document.getElementById('poll-voters-modal');
    if (modal) {
        modal.remove();
    }
}

/**
 * Adds a new option to a poll (user-added)
 */
async function addUserPollOption(postCuid, pollId) {
    const input = document.querySelector(`[data-poll-id="${pollId}"] .add-poll-option-input`);
    if (!input) return;
    
    const optionText = input.value.trim();
    if (!optionText) {
        if (App.Toast && typeof App.Toast.show === 'function') {
            App.Toast.show('Please enter an option', 'warning');
        }
        return;
    }
    
    try {
        const response = await fetch(`/polls/add_option/${postCuid}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ option_text: optionText })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to add option');
        }
        
        const data = await response.json();
        
        if (data.success) {
            input.value = '';
            reloadPollDisplay(postCuid);
            if (App.Toast && typeof App.Toast.show === 'function') {
                App.Toast.show('Option added', 'success');
            }
        }
    } catch (error) {
        console.error('Error adding poll option:', error);
        if (App.Toast && typeof App.Toast.show === 'function') {
            App.Toast.show(error.message || 'Failed to add option', 'error');
        }
    }
}

/**
 * Deletes a user-added poll option
 */
async function deleteUserPollOption(postCuid, optionId) {
    if (!confirm('Delete this option?')) {
        return;
    }
    
    try {
        const response = await fetch(`/polls/delete_option/${optionId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            throw new Error('Failed to delete option');
        }
        
        const data = await response.json();
        
        if (data.success) {
            reloadPollDisplay(postCuid);
            if (App.Toast && typeof App.Toast.show === 'function') {
                App.Toast.show('Option deleted', 'success');
            }
        }
    } catch (error) {
        console.error('Error deleting poll option:', error);
        if (App.Toast && typeof App.Toast.show === 'function') {
            App.Toast.show('Failed to delete option', 'error');
        }
    }
}

/**
 * Deletes any poll option (for poll creator)
 * Uses the app's confirmation modal
 */
async function deletePollOption(postCuid, optionId) {
    // Use the app's modal system
    if (typeof App !== 'undefined' && App.Modal && typeof App.Modal.showConfirm === 'function') {
        App.Modal.showConfirm(
            'Are you sure you want to delete this option? All votes for it will be lost.',
            () => {
                performDeletePollOption(postCuid, optionId);
            }
        );
    } else {
        // Fallback to browser confirm
        if (confirm('Are you sure you want to delete this option? All votes for it will be lost.')) {
            performDeletePollOption(postCuid, optionId);
        }
    }
}

/**
 * Actually performs the poll option deletion
 */
async function performDeletePollOption(postCuid, optionId) {
    try {
        const response = await fetch(`/polls/delete_option/${optionId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to delete option');
        }
        
        const data = await response.json();
        
        if (data.success) {
            reloadPollDisplay(postCuid);
            if (App.Toast && typeof App.Toast.show === 'function') {
                App.Toast.show('Option deleted', 'success');
            }
        }
    } catch (error) {
        console.error('Error deleting poll option:', error);
        if (App.Toast && typeof App.Toast.show === 'function') {
            App.Toast.show(error.message || 'Failed to delete option', 'error');
        }
    }
}

/**
 * Helper function to escape HTML
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Helper to get profile picture URL
 */
function getProfilePictureUrl(user) {
    if (user.hostname) {
        const protocol = window.location.protocol;
        return `${protocol}//${user.hostname}/profile_pictures/${user.profile_picture_path}`;
    }
    return `/profile_pictures/${user.profile_picture_path}`;
}

/**
 * Helper to get user profile URL
 */
function getUserProfileUrl(user) {
    if (user.hostname) {
        return `/federation/user/${user.puid}`;
    }
    return `/user/${user.puid}`;
}

// Reset poll data on form submit
document.addEventListener('DOMContentLoaded', () => {
    const forms = document.querySelectorAll('form[action*="create_post"], form[action*="create_group_post"], form[action*="create_event_post"]');
    forms.forEach(form => {
        form.addEventListener('submit', () => {
            setTimeout(() => {
                pollData = null;
                const section = document.getElementById('poll-display-section');
                if (section) {
                    section.classList.add('hidden');
                }
            }, 100);
        });
    });
});