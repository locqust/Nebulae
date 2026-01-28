// This script assumes window.appConfig is defined in the HTML template
// before this script is loaded.

/**
 * @file app.js (consolidated build)
 * @description Main client-side script loader for the social media application.
 * This is a consolidated build containing all application modules in a single file
 * for optimal loading performance. Previously split across 20+ files.
 */

// 1. Define the main App namespace and its shells for modules.
const App = {
    // Tracks the loading state of modules to prevent redundant fetches.
    // 'loading' | 'loaded'
    _moduleStatus: new Map(),

    state: {
        selectedCreatePostMedia: [],
        selectedNewCommentMedia: {}, // { postId: [{...}] }
        selectedEditCommentMedia: [],
        selectedEditPostMedia: [],
        editingComment: { cuid: null, viewerHomeUrl: '', isFederated: false },
        editingPost: { cuid: null, authorPuid: null, viewerHomeUrl: '', isFederated: false },
    },
    // Core modules (loaded immediately)
    Utils: {},
    Modal: {},
    Media: { Previews: {} },
    Federation: {},
    Toast: {},
    LoadMore: {},
    
    // Feature modules (loaded on demand)
    Post: {},
    Comment: {},
    Profile: { Cropper: {}, Info: {} },
    Group: {},
    Discover: {},
    Admin: {},
    Actions: {},
    Notifications: {},
    Settings: { Sessions: {} },
    Events: {},
    Privacy: {},  // NEW: Privacy actions module
    Parental: {},
    Sidebar: {},
    Router: {},
    NewPostsPolling: {},
    

    // --- NEW: Loader Functions ---
    showLoader() {
        document.body.classList.add('loading-active');
        const loader = document.getElementById('pageLoader');
        if (loader) {
            loader.classList.remove('loader-fade-out'); // Ensure it's not mid-fade
            loader.style.display = 'flex'; // Ensure it's visible
            loader.style.opacity = '1'; // Ensure it's fully opaque
        }
    },

    /**
     * Hides the page loader and returns a Promise that resolves
     * after the fade-out animation has completed.
     * @returns {Promise<void>}
     */
    hideLoader() {
        // Return a promise that resolves when the animation is done
        return new Promise((resolve) => {
            const loader = document.getElementById('pageLoader');
            if (loader && loader.style.display !== 'none') {
                // Set a timeout fallback in case animationend never fires
                const fallback = setTimeout(() => {
                    console.warn('hideLoader: animationend event timeout.');
                    loader.style.display = 'none';
                    document.body.classList.remove('loading-active');
                    resolve();
                }, 500); // Animation is 300ms, so 500 is a safe fallback

                loader.classList.add('loader-fade-out');
                loader.addEventListener('animationend', () => {
                    clearTimeout(fallback); // Clear the fallback
                    loader.style.display = 'none';
                    document.body.classList.remove('loading-active');
                    resolve();
                }, { once: true });
            } else {
                document.body.classList.remove('loading-active');
                resolve(); // Resolve immediately if no loader
            }
        });
    },
    // --- END: Loader Functions ---
};

// =================================================================================
// CONSOLIDATED MODULES
// All modules below were previously in separate files under static/js/modules/
// Now consolidated for optimal loading performance
// =================================================================================

/**
 * @file modules/utils.js
 * @description General utility functions.
 * Populates the App.Utils namespace.
 */
App.Utils = {
    getMediaType(filename) {
        if (!filename) return 'other';
        const ext = filename.split('.').pop().toLowerCase();
        if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp'].includes(ext)) {
            return 'image';
        }
        if (['mp4', 'mov', 'webm', 'avi', 'mkv'].includes(ext)) {
            return 'video';
        }
        return 'other';
    },

    convertUTCTimestamp(element) {
        const utcString = element.dataset.timestamp;
        if (!utcString) return;

        const date = new Date(utcString.endsWith(' UTC') ? utcString : utcString + ' UTC');
        if (isNaN(date)) {
            console.warn(`Could not parse date: ${utcString}`);
            return;
        }

        const userTimezone = (window.appConfig && window.appConfig.userSettings.timezone !== 'auto') 
            ? window.appConfig.userSettings.timezone 
            : Intl.DateTimeFormat().resolvedOptions().timeZone;

        const options = {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit',
            timeZone: userTimezone,
            hour12: false
        };

        try {
            element.textContent = new Intl.DateTimeFormat('default', options).format(date);
        } catch (e) {
            console.error(`Error formatting date for timezone ${userTimezone}:`, e);
            element.textContent = date.toLocaleString();
        }
    },

    convertAllUTCTimestamps() {
        document.querySelectorAll('.utc-timestamp').forEach(App.Utils.convertUTCTimestamp);
    },

    formatDisplayDate(dateString) {
        if (!dateString || dateString === "Not set") return "Not set";
        try {
            const date = new Date(dateString + 'T00:00:00');
            if (isNaN(date)) return dateString;
            const day = String(date.getDate()).padStart(2, '0');
            const month = String(date.getMonth() + 1).padStart(2, '0');
            const year = date.getFullYear();
            return `${day}/${month}/${year}`;
        } catch (e) {
            return dateString;
        }
    },

    autoHideFlashMessages() {
        document.querySelectorAll('.flash-message').forEach(flash => {
            setTimeout(() => {
                flash.classList.add('flash-fade-out');
                flash.addEventListener('animationend', () => {
                    const parent = flash.parentElement;
                    flash.remove();
                    if (parent && parent.classList.contains('mb-4') && parent.children.length === 0) {
                        parent.remove();
                    }
                });
            }, 5000);
        });
    },

    flashMessage(message, category, onVanish) {
        const flashContainer = document.querySelector('.max-w-5xl.w-full > .mb-4, .max-w-4xl.w-full > .mb-4, .max-w-2xl.w-full > .mb-4');
        if (!flashContainer) {
             console.warn("Flash message container not found.");
             // Fallback to info modal
             App.Modal.showInfo(message);
             if (onVanish) onVanish();
             return;
        }

        let flashDiv = document.createElement('div');
        flashDiv.className = `flash-message flash-${category} mb-4`;
        flashDiv.textContent = message;

        flashContainer.innerHTML = '';
        flashContainer.appendChild(flashDiv);

        setTimeout(() => {
            flashDiv.classList.add('flash-fade-out');
            flashDiv.addEventListener('animationend', () => {
                flashDiv.remove();
                if (typeof onVanish === 'function') {
                    onVanish();
                }
            });
        }, 5000);
    }
};



/**
 * @file modules/modal.js
 * @description Handles all modal dialog interactions.
 * Populates the App.Modal namespace.
 */
App.Modal = {
    injectHTML() {
        const confirmModalHTML = `
            <div id="confirmModal" class="modal hidden">
                <div class="modal-content max-w-sm">
                    <h2 id="confirmModalTitle" class="text-xl font-bold mb-4 primary-text">Confirm Action</h2>
                    <p id="confirmModalMessage" class="primary-text mb-6"></p>
                    <div class="flex justify-end gap-4">
                        <button id="confirmModalCancel" class="bg-gray-500 hover:bg-gray-600 text-white font-semibold py-2 px-4 rounded-lg">Cancel</button>
                        <button id="confirmModalConfirm" class="bg-red-600 hover:bg-red-700 text-white font-semibold py-2 px-4 rounded-lg">Confirm</button>
                    </div>
                </div>
            </div>`;
        const infoModalHTML = `
            <div id="infoModal" class="modal hidden">
                <div class="modal-content max-w-sm">
                    <p id="infoModalMessage" class="primary-text mb-6 text-center text-lg"></p>
                    <div class="flex justify-center">
                        <button id="infoModalOk" class="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded-lg">OK</button>
                    </div>
                </div>
            </div>`;
        document.body.insertAdjacentHTML('beforeend', confirmModalHTML);
        document.body.insertAdjacentHTML('beforeend', infoModalHTML);

        document.getElementById('confirmModalCancel').addEventListener('click', () => this.close('confirmModal'));
    },
    open(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'flex';
            modal.classList.remove('hidden');
        } else {
            console.error(`Modal with ID ${modalId} not found.`);
        }
    },
    close(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
            modal.classList.add('hidden');
            
            const cleanup = {
                'discoverUsersModal': [
                    // Don't hide the lists themselves, only hide loading/error/noResults
                    'discoverUsersError', 'discoverPagesError',
                    'hiddenUsersError', 'hiddenPagesError',
                    'discoverUsersLoading', 'discoverPagesLoading',
                    'hiddenUsersLoading', 'hiddenPagesLoading',
                    'noDiscoverableUsers', 'noDiscoverablePages',
                    'noHiddenUsers', 'noHiddenPages'
                ],
                'discoverGroupsModal': [
                    // Don't hide the list itself, only hide loading/error/noResults
                    'discoverGroupsError', 'hiddenGroupsError',
                    'discoverGroupsLoading', 'hiddenGroupsLoading',
                    'noDiscoverableGroups', 'noHiddenGroups'
                ]
            };

            if (cleanup[modalId]) {
                cleanup[modalId].forEach(elId => {
                    const el = document.getElementById(elId);
                    if(el) {
                        el.style.display = 'none';
                    }
                });
                
                // Clear the lists but DON'T hide them (display: none)
                const listsToClear = {
                    'discoverUsersModal': ['discoverUsersList', 'discoverPagesList', 'hiddenUsersList', 'hiddenPagesList'],
                    'discoverGroupsModal': ['discoverGroupsList', 'hiddenGroupsList']
                };
                
                if (listsToClear[modalId]) {
                    listsToClear[modalId].forEach(listId => {
                        const list = document.getElementById(listId);
                        if (list) {
                            list.innerHTML = '';
                            // Don't set display: none on the lists - that's what was breaking it!
                        }
                    });
                }
            }
            if (modalId === 'settingsModal' && window.appConfig && window.appConfig.userSettings) {
                // Use text_size (snake_case) to match what's saved
                const textSize = window.appConfig.userSettings.text_size || window.appConfig.userSettings.textSize || 100;
                document.documentElement.style.fontSize = `${textSize}%`;
            }
        } else {
            console.error(`Modal with ID ${modalId} not found.`);
        }
    },
    showInfo(message, onOk) {
        const messageEl = document.getElementById('infoModalMessage');
        const okBtn = document.getElementById('infoModalOk');
        if (!messageEl || !okBtn) {
            alert(message); // Fallback
            if (typeof onOk === 'function') onOk();
            return;
        }
        messageEl.textContent = message;
        const newOkBtn = okBtn.cloneNode(true);
        okBtn.parentNode.replaceChild(newOkBtn, okBtn);
        newOkBtn.addEventListener('click', () => {
            this.close('infoModal');
            if (typeof onOk === 'function') onOk();
        }, { once: true });
        this.open('infoModal');
    },
    showConfirm(message, onConfirm) {
        const messageEl = document.getElementById('confirmModalMessage');
        const confirmBtn = document.getElementById('confirmModalConfirm');
        if (!messageEl || !confirmBtn) {
            if (confirm(message)) onConfirm();
            return;
        }
        messageEl.textContent = message;
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
        newConfirmBtn.addEventListener('click', () => {
            if (typeof onConfirm === 'function') onConfirm();
            this.close('confirmModal');
        }, { once: true });
        this.open('confirmModal');
    },
    confirmFormSubmission(formElement, message) {
        if (!formElement || typeof formElement.submit !== 'function') {
            console.error('confirmFormSubmission: Invalid form element provided.', formElement);
            return;
        }
        this.showConfirm(message, () => {
            formElement.submit();
        });
    }
};

/**
 * @file modules/toast.js
 * @description Toast notification system
 * Populates the App.Toast namespace.
 */
App.Toast = {
    container: null,
    duration: 5000, // Default 5 seconds
    
    /**
     * Initialize the toast system
     */
    init() {
        this.container = document.getElementById('toast-container');
        if (!this.container) {
            console.error('Toast container not found!');
        }
    },
    
    /**
     * Show a toast notification
     * @param {string} message - The message to display
     * @param {string} type - Type: 'success', 'error', 'warning', 'info'
     * @param {number} duration - How long to show (ms), 0 = permanent
     */
    show(message, type = 'info', duration = null) {
        if (!this.container) this.init();
        
        duration = duration ?? this.duration;
        
        // Create toast element
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.setAttribute('role', 'alert');
        
        // Icon HTML based on type
        const icons = {
            success: '<svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>',
            error: '<svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>',
            danger: '<svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>',
            warning: '<svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/></svg>',
            info: '<svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>'
        };
        
        toast.innerHTML = `
            <div class="toast-icon">${icons[type] || icons.info}</div>
            <div class="toast-content">
                <div class="toast-message">${this.escapeHtml(message)}</div>
            </div>
            <button class="toast-close" aria-label="Close">
                <svg width="16" height="16" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
                </svg>
            </button>
        `;
        
        // Add progress bar if auto-dismiss
        if (duration > 0) {
            const progress = document.createElement('div');
            progress.className = 'toast-progress';
            progress.style.animationDuration = `${duration}ms`;
            toast.appendChild(progress);
        }
        
        // Add to container
        this.container.appendChild(toast);
        
        // Close button handler
        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => this.remove(toast));
        
        // Auto-dismiss
        if (duration > 0) {
            setTimeout(() => this.remove(toast), duration);
        }
        
        return toast;
    },
    
    /**
     * Remove a toast with animation
     */
    remove(toast) {
        toast.classList.add('removing');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300); // Match animation duration
    },
    
    /**
     * Helper to escape HTML
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
    
    /**
     * Convenience methods
     */
    success(message, duration) {
        return this.show(message, 'success', duration);
    },
    
    error(message, duration) {
        return this.show(message, 'error', duration);
    },
    
    warning(message, duration) {
        return this.show(message, 'warning', duration);
    },
    
    info(message, duration) {
        return this.show(message, 'info', duration);
    },
    /**
     * Check for and display any pending toasts from sessionStorage
     * Call this after page load
     */
    checkPending() {
        const pending = sessionStorage.getItem('pendingToast');
        if (pending) {
            try {
                const { message, type } = JSON.parse(pending);
                sessionStorage.removeItem('pendingToast');
                // Small delay to ensure page is fully loaded
                setTimeout(() => {
                    this.show(message, type);
                }, 100);
            } catch (e) {
                console.error('Error displaying pending toast:', e);
                sessionStorage.removeItem('pendingToast');
            }
        }
    }
};

/**
 * @file modules/federation.js
 * @description Client-side logic for handling federated sessions.
 * Populates the App.Federation namespace.
 */
App.Federation = {
    async handleViewerToken(token) {
        try {
            const response = await fetch('/federation/api/v1/initiate_viewer_session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ viewer_token: token })
            });

            const currentUrl = new URL(window.location.href);
            currentUrl.searchParams.delete('viewer_token');

            if (response.ok) {
                // Reload the page without the token in the URL to complete session setup
                window.location.replace(currentUrl.toString());
            } else {
                console.error('Failed to initiate viewer session:', await response.json());
                // Silently remove the token from the URL and continue without a federated session
                window.history.replaceState({}, document.title, currentUrl.toString());
            }
        } catch (error) {
            console.error('Error handling viewer token:', error);
        }
    }
};



/**
 * @file modules/media.js
 * @description Manages media browser communication and previews.
 * Populates the App.Media namespace.
 */
App.Media = {
    initCommunicationListener() {
        const handler = (event) => this._handleSelection(event);
        window.addEventListener('message', handler, false);
        const channel = new BroadcastChannel('media_selection_channel');
        channel.onmessage = handler;
    },

    _handleSelection(event) {
        const data = event.data || event;
        const openerMode = data.mode;

        const handlers = {
            'createPost': () => {
                App.state.selectedCreatePostMedia = data.selectedMedia;
                this.Previews.updateCreatePost();
            },
            'editPost': () => {
                App.state.selectedEditPostMedia = data.selectedMedia;
                this.Previews.updateEditPost();
            },
            'newComment': () => {
                if (data.contextId) {
                    App.state.selectedNewCommentMedia[data.contextId] = data.selectedMedia;
                    this.Previews.updateNewComment(data.contextId);
                }
            },
            'editComment': () => {
                App.state.selectedEditCommentMedia = data.selectedMedia;
                this.Previews.updateEditComment();
            },
            'mediaComment': () => {
                // Handle media modal comment attachments
                if (typeof window.updateMediaCommentPreview === 'function') {
                    const hiddenInput = document.getElementById('media-comment-media-files');
                    if (hiddenInput) {
                        hiddenInput.value = JSON.stringify(data.selectedMedia);
                        window.updateMediaCommentPreview(data.selectedMedia);
                    }
                }
            },
            'single_select': () => {
                if (typeof App.Profile.Cropper.updateFromBrowser === 'function') {
                    const path = data.selectedMedia && data.selectedMedia[0] ? data.selectedMedia[0].media_file_path : null;
                    if (path) {
                        App.Profile.Cropper.updateFromBrowser(path);
                    }
                }
            }
        };
        
        if (handlers[openerMode]) {
            handlers[openerMode]();
        } else {
            console.warn('App.Media: Received media selection with unhandled mode.', { data, openerMode });
        }
    },

    openBrowser(mode, context = {}) {
        sessionStorage.setItem('mediaBrowserMode', mode);
        const { url, postId, commentCuid, postCuid, currentSelected = [] } = context;
        
        // Ensure currentSelected is an array of strings (paths), not objects
        const currentPaths = (currentSelected || []).map(item => {
            return typeof item === 'object' && item !== null && item.media_file_path ? item.media_file_path : item;
        });
        const selectedStr = encodeURIComponent(JSON.stringify(currentPaths));
        
        // --- START FIX for Federated Media Browser URL ---
        // Get the base browse URL (e.g., /browse_media/?mode=multi_select)
        const baseBrowseUrl = window.appConfig.browseMediaBaseUrl;
        
        // Check if the base URL already contains a '?' to decide on the separator
        const separator = baseBrowseUrl.includes('?') ? '&' : '?';

        // If a remote URL (url) is provided, prepend it to the baseBrowseUrl.
        // Otherwise, baseBrowseUrl (a relative path) is used as-is for local users.
        let mediaBrowserUrl = url 
            ? `${url}${baseBrowseUrl}${separator}selected=${selectedStr}` 
            : `${baseBrowseUrl}${separator}selected=${selectedStr}`;
        // --- END FIX ---
        
        if (postId) mediaBrowserUrl += `&post_id=${postId}`;
        if (commentCuid) mediaBrowserUrl += `&comment_cuid=${commentCuid}`;
        if (postCuid) mediaBrowserUrl += `&post_cuid=${postCuid}`;
            
        console.log("Opening media browser with URL:", mediaBrowserUrl);
        window.open(mediaBrowserUrl, '_blank', 'width=800,height=600');
    },

    // NEW: Upload handler functions
    async uploadMedia(files, context = {}) {
        if (!files || files.length === 0) {
            App.Utils.flashMessage('No files selected.', 'warning');
            return null;
        }

        // Show loading indicator
        App.Modal.showInfo('Uploading media files...');

        try {
            const formData = new FormData();
            for (let file of files) {
                formData.append('files', file);
            }

            const response = await fetch('/upload_media', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Upload failed');
            }

            const data = await response.json();
            
            // Close loading modal
            App.Modal.close('infoModal');
            
            return data.uploaded_media;

        } catch (error) {
            console.error('Upload error:', error);
            App.Modal.close('infoModal');
            App.Utils.flashMessage(error.message || 'Failed to upload media files. Please try again.', 'danger');
            return null;
        }
    },

    async handleCreatePostUpload(event) {
        const files = event.target.files;
        const uploadedMedia = await this.uploadMedia(files);
        
        if (uploadedMedia) {
            // Add uploaded files to selected media
            if (!App.state.selectedCreatePostMedia) {
                App.state.selectedCreatePostMedia = [];
            }
            App.state.selectedCreatePostMedia.push(...uploadedMedia);
            
            // Update preview
            this.Previews.updateCreatePost();
            
            // Show success message
            App.Utils.flashMessage(`Successfully uploaded ${uploadedMedia.length} file(s)!`, 'success');
            
            // Clear file input
            event.target.value = '';
        }
    },

    async handleCommentUpload(event, postId) {
        const files = event.target.files;
        const uploadedMedia = await this.uploadMedia(files);
        
        if (uploadedMedia) {
            // Add uploaded files to selected media for this comment
            if (!App.state.selectedNewCommentMedia[postId]) {
                App.state.selectedNewCommentMedia[postId] = [];
            }
            App.state.selectedNewCommentMedia[postId].push(...uploadedMedia);
            
            // Update preview
            this.Previews.updateNewComment(postId);
            
            // Show success message
            App.Utils.flashMessage(`Successfully uploaded ${uploadedMedia.length} file(s)!`, 'success');
            
            // Clear file input
            event.target.value = '';
        }
    },

    async handleEditPostUpload(event) {
        const files = event.target.files;
        const uploadedMedia = await this.uploadMedia(files);
        
        if (uploadedMedia) {
            // Add uploaded files to selected media
            if (!App.state.selectedEditPostMedia) {
                App.state.selectedEditPostMedia = [];
            }
            App.state.selectedEditPostMedia.push(...uploadedMedia);
            
            // Update preview
            this.Previews.updateEditPost();
            
            // Show success message
            App.Utils.flashMessage(`Successfully uploaded ${uploadedMedia.length} file(s)!`, 'success');
            
            // Clear file input
            event.target.value = '';
        }
    },

    async handleEditCommentUpload(event) {
        const files = event.target.files;
        const uploadedMedia = await this.uploadMedia(files);
        
        if (uploadedMedia) {
            // Add uploaded files to selected media
            if (!App.state.selectedEditCommentMedia) {
                App.state.selectedEditCommentMedia = [];
            }
            App.state.selectedEditCommentMedia.push(...uploadedMedia);
            
            // Update preview
            this.Previews.updateEditComment();
            
            // Show success message
            App.Utils.flashMessage(`Successfully uploaded ${uploadedMedia.length} file(s)!`, 'success');
            
            // Clear file input
            event.target.value = '';
        }
    },

    Previews: {
        initCreatePost() {
            const input = document.getElementById('selected_media_files');
            if (input && input.value && input.value !== '[]') {
                try {
                    const initialMedia = JSON.parse(input.value);
                    if (Array.isArray(initialMedia)) {
                        App.state.selectedCreatePostMedia = initialMedia;
                        if (initialMedia.length > 0) this.updateCreatePost();
                    }
                } catch(e) { console.error('Error parsing initial create post media', e); }
            }
        },
        initNewComment() {
            document.querySelectorAll('input[name="selected_comment_media_files"]').forEach(input => {
                const postId = input.id.replace('selected_comment_media_files-', '');
                if (input.value && input.value !== '[]') {
                     try {
                        const initialMedia = JSON.parse(input.value);
                        if (Array.isArray(initialMedia)) {
                            App.state.selectedNewCommentMedia[postId] = initialMedia;
                            if (initialMedia.length > 0) this.updateNewComment(postId);
                        }
                    } catch(e) { console.error(`Error parsing initial new comment media for post ${postId}`, e); }
                }
            });
        },
        updateCreatePost() {
            const container = document.getElementById('media-preview');
            const input = document.getElementById('selected_media_files');
            if (!container || !input) return;
            const puid = window.appConfig.loggedInUserPuid;
            // Use viewer_home_url for federated users, default to local origin
            const homeUrl = window.appConfig.isFederatedViewer ? (window.appConfig.viewer_home_url || '') : (window.location.origin);

            this._renderPreview(container, App.state.selectedCreatePostMedia, puid, homeUrl, (path) => {
                App.state.selectedCreatePostMedia = App.state.selectedCreatePostMedia.filter(i => i.media_file_path !== path);
                this.updateCreatePost();
            }, (path, alt) => {
                const item = App.state.selectedCreatePostMedia.find(m => m.media_file_path === path);
                if (item) item.alt_text = alt;
                input.value = JSON.stringify(App.state.selectedCreatePostMedia);
            });
            input.value = JSON.stringify(App.state.selectedCreatePostMedia);
        },
        updateNewComment(postId) {
            const container = document.getElementById(`comment-media-preview-${postId}`);
            const input = document.getElementById(`selected_comment_media_files-${postId}`);
            if (!container || !input) return;
            const puid = window.appConfig.loggedInUserPuid;
            // Use viewer_home_url for federated users, default to local origin
            const homeUrl = window.appConfig.isFederatedViewer ? (window.appConfig.viewer_home_url || '') : (window.location.origin);

            this._renderPreview(container, App.state.selectedNewCommentMedia[postId], puid, homeUrl, (path) => {
                App.state.selectedNewCommentMedia[postId] = App.state.selectedNewCommentMedia[postId].filter(i => i.media_file_path !== path);
                this.updateNewComment(postId);
            });
            input.value = JSON.stringify(App.state.selectedNewCommentMedia[postId] || []);
        },
        updateEditPost() {
            const container = document.getElementById('edit-post-media-preview');
            const input = document.getElementById('edit_selected_post_media_files');
            if (!container || !input) return;

            // --- START FIX ---
            // The newly selected media always belongs to the *viewer* (the logged-in user),
            // regardless of who authored the post. We must use the viewer's PUID
            // and home URL to render the preview of their selected media.
            const puid = window.appConfig.loggedInUserPuid;
            // Use viewer's home URL if they are federated, otherwise local origin
            const homeUrl = window.appConfig.isFederatedViewer ? (window.appConfig.viewer_home_url || '') : (window.location.origin);
            // --- END FIX ---
            
            this._renderPreview(container, App.state.selectedEditPostMedia, puid, homeUrl, (path) => {
                App.state.selectedEditPostMedia = App.state.selectedEditPostMedia.filter(i => i.media_file_path !== path);
                this.updateEditPost();
            }, (path, alt) => {
                const item = App.state.selectedEditPostMedia.find(m => m.media_file_path === path);
                if (item) item.alt_text = alt;
                input.value = JSON.stringify(App.state.selectedEditPostMedia);
            });
            input.value = JSON.stringify(App.state.selectedEditPostMedia);
        },
        updateEditComment() {
            const container = document.getElementById('edit-comment-media-preview');
            const input = document.getElementById('edit_selected_comment_media_files');
            if (!container || !input) return;
            const puid = window.appConfig.loggedInUserPuid;
            // Use the correct home URL (federated or local)
            const homeUrl = App.state.editingComment.isFederated ? (App.state.editingComment.viewerHomeUrl || '') : (window.location.origin);
            
            this._renderPreview(container, App.state.selectedEditCommentMedia, puid, homeUrl, (path) => {
                App.state.selectedEditCommentMedia = App.state.selectedEditCommentMedia.filter(i => i.media_file_path !== path);
                this.updateEditComment();
            }, (path, alt) => {
                const item = App.state.selectedEditCommentMedia.find(m => m.media_file_path === path);
                if (item) item.alt_text = alt;
                 input.value = JSON.stringify(App.state.selectedEditCommentMedia);
            });
            input.value = JSON.stringify(App.state.selectedEditCommentMedia);
        },
        _renderPreview(container, mediaItems, puid, homeUrl, onRemove, onAltChange) {
            container.innerHTML = '';
            if (!puid) {
                container.innerHTML = `<p class="text-red-500 text-xs">Error: User PUID not found.</p>`;
                return;
            }
            (mediaItems || []).forEach(item => {
                const itemDiv = document.createElement('div');
                itemDiv.className = onAltChange ? 'selected-media-preview-item' : 'selected-comment-media-preview-item';
                
                const mediaType = App.Utils.getMediaType(item.media_file_path);
                // Correctly encode each part of the path
                const encodedFilename = item.media_file_path.split('/').map(segment => encodeURIComponent(segment)).join('/');
                
                // Use the provided homeUrl (which is origin-aware)
                const mediaUrl = `${homeUrl}${window.appConfig.serveMediaBaseUrl}${puid}/${encodedFilename}`;
                
                let mediaElement;
                if (mediaType === 'image') {
                    mediaElement = document.createElement('img');
                    mediaElement.src = mediaUrl;
                    mediaElement.alt = item.alt_text || 'Selected media';
                } else if (mediaType === 'video') {
                    mediaElement = document.createElement('video');
                    mediaElement.src = `${mediaUrl}#t=0.1`;
                    mediaElement.preload = 'metadata';
                    mediaElement.muted = true;
                } else {
                    mediaElement = document.createElement('div');
                    mediaElement.textContent = 'Unsupported';
                    mediaElement.className = 'w-full h-full flex items-center justify-center bg-gray-200 text-gray-500 text-xs';
                }
                itemDiv.appendChild(mediaElement);
                
                if (onAltChange) {
                    const altInput = document.createElement('input');
                    altInput.type = 'text';
                    altInput.placeholder = 'Alt text (optional)';
                    altInput.value = item.alt_text || '';
                    altInput.className = 'alt-text-input';
                    altInput.oninput = (e) => onAltChange(item.media_file_path, e.target.value);
                    itemDiv.appendChild(altInput);
                }
                
                const removeBtn = document.createElement('button');
                removeBtn.className = onAltChange ? 'remove-btn' : 'remove-media-btn';
                removeBtn.innerHTML = '&times;';
                removeBtn.onclick = (e) => { e.stopPropagation(); onRemove(item.media_file_path); };
                itemDiv.appendChild(removeBtn);

                container.appendChild(itemDiv);
            });
        }
    }
};




/**
 * @file modules/load_more.js
 * @description Handles "Load More" button pagination for feeds and lists.
 * Populates the App.LoadMore namespace.
 */
App.LoadMore = {
    // Active loaders
    _loaders: new Map(),

    /**
     * Initializes all load more buttons on the page.
     */
    initializeButtons() {
        // Only initialize for containers that exist on the current page
        
        // Main feed
        this.createButton({
            containerId: 'feed-posts-container',
            dataKey: 'posts',
            apiUrl: '/api/feed/posts',
            emptyMessage: 'No more posts to display.'
        });
        
        // Profile timelines
        this.createButton({
            containerId: 'profile-posts-container',
            dataKey: 'posts',
            apiUrl: `/api/profile/${this._getPuidFromUrl()}/posts`,
            emptyMessage: 'No more posts to display.'
        });

        // Public page timelines
        this.createButton({
            containerId: 'page-posts-list-container',
            dataKey: 'posts',
            apiUrl: `/api/page/${this._getPuidFromUrl()}/posts`,
            emptyMessage: 'No more posts to display.'
        });

            // Group timelines
        this.createButton({
            containerId: 'group-posts-list-container',
            dataKey: 'posts',
            apiUrl: `/group/api/group/${this._getPuidFromUrl()}/posts`,
            emptyMessage: 'No more posts to display.'
        });

        // Event timelines
        this.createButton({
            containerId: 'event-posts-list-container',
            dataKey: 'posts',
            apiUrl: `/events/api/event/${this._getPuidFromUrl()}/posts`,
            emptyMessage: 'No more posts to display.'
        });
    },

    /**
     * Creates a load more button for a specific container
     * @param {object} config - Configuration object
     */
    createButton(config) {
        const { containerId, dataKey, apiUrl, emptyMessage } = config;
        const container = document.getElementById(containerId);

        // If the container doesn't exist on this page, do nothing
        if (!container) return;

        // Prevent re-initializing
        if (this._loaders.has(containerId)) return;

        const state = {
            container: container,
            dataKey: dataKey,
            apiUrl: apiUrl,
            emptyMessage: emptyMessage,
            page: 2, // Start at page 2 (page 1 is pre-loaded)
            isLoading: false,
            hasMore: true,
            limit: parseInt(container.dataset.limit) || 20,
        };

        // Check if the pre-loaded items are fewer than the limit
        const initialItemCount = container.children.length;
        if (initialItemCount < state.limit) {
            state.hasMore = false;
        }

        // Create the button element
        const buttonContainer = this._createButton(containerId);
        container.insertAdjacentElement('afterend', buttonContainer);
        state.buttonContainer = buttonContainer;
        state.button = buttonContainer.querySelector('.load-more-btn');
        state.endMessage = buttonContainer.querySelector('.end-message');
        
        // Create back-to-top button for this timeline
        this._createBackToTopButton(containerId);
        
        // Store this loader's state
        this._loaders.set(containerId, state);

        // Attach click handler
        state.button.addEventListener('click', () => this.loadMore(containerId));

        // Hide button if no more items
        if (!state.hasMore) {
            buttonContainer.style.display = 'none';
        }
    },

    /**
     * Creates the button element
     */
    _createButton(containerId) {
        const wrapper = document.createElement('div');
        wrapper.className = 'load-more-container';
        wrapper.dataset.targetId = containerId;
        wrapper.innerHTML = `
            <button class="load-more-btn" type="button">
                <span class="btn-text">Load More</span>
                <svg class="btn-spinner" style="display: none;" width="20" height="20" viewBox="0 0 20 20" fill="none">
                    <circle cx="10" cy="10" r="8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-dasharray="50" stroke-dashoffset="25">
                        <animateTransform attributeName="transform" type="rotate" from="0 10 10" to="360 10 10" dur="1s" repeatCount="indefinite"/>
                    </circle>
                </svg>
            </button>
            <p class="end-message" style="display: none;">That's all for now!</p>
        `;
        return wrapper;
    },

    /**
     * Load more items when button is clicked
     */
    async loadMore(containerId, silent = false) {
        const state = this._loaders.get(containerId);
        if (!state || state.isLoading || !state.hasMore) return;

        state.isLoading = true;
        this._showLoading(state, true);

        try {
            const url = new URL(state.apiUrl, window.location.origin);
            url.searchParams.append('page', state.page);
            url.searchParams.append('limit', state.limit);

            const response = await fetch(url);
            if (!response.ok) throw new Error(`Server responded with status ${response.status}`);
            
            const data = await response.json();
            const items = data[state.dataKey] || [];

            if (items.length > 0) {
                const fragment = document.createDocumentFragment();
                items.forEach(itemHtml => {
                    const tempDiv = document.createElement('div');
                    tempDiv.innerHTML = itemHtml;
                    fragment.appendChild(tempDiv.firstElementChild);
                });
                state.container.appendChild(fragment);
                
                // Re-run timestamp conversion for new items
                if (App.Utils && typeof App.Utils.convertAllUTCTimestamps === 'function') {
                    App.Utils.convertAllUTCTimestamps();
                }
                
                state.page++;
                
                // Show back-to-top button after first load
                if (state.page === 3 && state.backToTopButton) { // page 3 = first "load more" clicked
                    state.backToTopButton.classList.add('visible');
                }
                
                // Show success toast (only if not silent)
                if (!silent && App.Toast) {
                    App.Toast.success(`Loaded ${items.length} more post${items.length > 1 ? 's' : ''}`, 2000);
                }
            }

            // Check if we've reached the end
            if (items.length < state.limit) {
                state.hasMore = false;
                this._showEnd(state);
            }

        } catch (error) {
            console.error(`Failed to load more content for ${containerId}:`, error);
            if (!silent && App.Toast) {
                App.Toast.error('Failed to load more posts. Please try again.');
            }
        } finally {
            state.isLoading = false;
            this._showLoading(state, false);
        }
    },

    /**
     * Show/hide loading state
     */
    _showLoading(state, isLoading) {
        const btnText = state.button.querySelector('.btn-text');
        const spinner = state.button.querySelector('.btn-spinner');
        
        if (isLoading) {
            btnText.textContent = 'Loading...';
            spinner.style.display = 'inline-block';
            state.button.disabled = true;
        } else {
            btnText.textContent = 'Load More';
            spinner.style.display = 'none';
            state.button.disabled = false;
        }
    },

    /**
     * Show end message and hide button
     */
    _showEnd(state) {
        state.button.style.display = 'none';
        state.endMessage.style.display = 'block';
    },

    /**
     * Automatically load pages until a target post or comment is found
     * Used for scroll restoration after page reload or when clicking notification links
     */
    async autoLoadToTarget() {
        console.log('autoLoadToTarget called!');
        console.log('Current hash:', window.location.hash);
        const hash = window.location.hash;
        if (!hash || (!hash.startsWith('#post-') && !hash.startsWith('#comment-'))) {
            console.log('No valid hash found, exiting');
            return;
        }
        
        const targetId = hash.substring(1); // Remove the '#'
        console.log('Looking for target:', targetId);
        let targetElement = document.getElementById(targetId);

        console.log('Target element found?', targetElement ? 'YES' : 'NO');
        
        // Check if element exists AND is visible
        const isVisible = targetElement && targetElement.offsetParent !== null;
        console.log('Target is visible?', isVisible ? 'YES' : 'NO');

        // If target exists AND is visible, scroll to it
        if (targetElement && isVisible) {
            console.log('Target exists and is visible, scrolling to it');
            this._scrollToTarget(targetElement);
            return;
        }

        // If target exists but is hidden, expand comments to reveal it
        if (targetElement && !isVisible) {
            console.log('Target exists but is hidden, expanding comments...');
            if (targetId.startsWith('comment-')) {
                await this._expandCommentsUntilFound(targetId);
            }
            return;
        }

        // Target not on page - need to load more pages
        console.log(`Target ${targetId} not found, loading more pages...`);
        
        // Determine which container we're on (feed, profile, public page, group, or event)
        let containerId = 'feed-posts-container';
        if (document.getElementById('profile-posts-container')) {
            containerId = 'profile-posts-container';
        } else if (document.getElementById('page-posts-list-container')) {
            containerId = 'page-posts-list-container';
        } else if (document.getElementById('group-posts-list-container')) {
            containerId = 'group-posts-list-container';
        } else if (document.getElementById('event-posts-list-container')) {
            containerId = 'event-posts-list-container';
        }
        
        // Find the container state
        const state = this._loaders.get(containerId);
        if (!state || !state.hasMore) {
            console.log('No more posts to load or container not found');
            // Even if we can't load more posts, try expanding comments in case target is hidden
            if (targetId.startsWith('comment-')) {
                await this._expandCommentsUntilFound(targetId);
            }
            return;
        }
        
        // Load pages until we find the target or run out of posts
        while (state.hasMore) {
            await this.loadMore(containerId, true);  // true = silent, no toasts
            
            // Check if target now exists
            targetElement = document.getElementById(targetId);
            if (targetElement) {
                console.log(`Found target ${targetId}, scrolling...`);
                this._scrollToTarget(targetElement);
                return;
            }
            
            // Safety: don't load more than 10 pages (200 posts)
            if (state.page > 11) {
                console.log('Safety limit reached, stopping auto-load');
                // Try expanding comments in case target is hidden
                if (targetId.startsWith('comment-')) {
                    await this._expandCommentsUntilFound(targetId);
                }
                return;
            }
        }
        
        console.log(`Target ${targetId} not found after loading all available posts`);
        // Try expanding comments in case target is hidden
        if (targetId.startsWith('comment-')) {
            await this._expandCommentsUntilFound(targetId);
        }
    },

    /**
     * Helper function to scroll to and highlight a target element
     */
    _scrollToTarget(targetElement) {
        setTimeout(() => {
            targetElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
            // Highlight the target briefly
            targetElement.classList.add('post-highlight');
            setTimeout(() => {
                targetElement.classList.remove('post-highlight');
            }, 3000);
        }, 100);
    },

    /**
     * Expands "show more comments" buttons until the target comment is found
     */
    async _expandCommentsUntilFound(targetId) {
        console.log(`Attempting to expand comments to find ${targetId}...`);
        
        // Find all "show more comments" buttons
        const showMoreButtons = document.querySelectorAll('.show-more-button');
        console.log('Found', showMoreButtons.length, 'show-more buttons');
        
        for (const button of showMoreButtons) {
            console.log('Checking button:', button);
            console.log('Button display style:', button.style.display);
            console.log('Button visible?', button.offsetParent !== null);
            
            // Check if target exists now
            const targetElement = document.getElementById(targetId);
            if (targetElement) {
                const isVisible = targetElement.offsetParent !== null;
                console.log(`Target found! Visible: ${isVisible}`);
                if (isVisible) {
                    console.log(`Found target ${targetId} after expanding comments`);
                    this._scrollToTarget(targetElement);
                    return;
                }
            }
            
            // Click the button to expand more comments
            if (button.style.display !== 'none' && button.offsetParent !== null) {
                console.log('Clicking button to expand comments...');
                button.click();
                // Wait a bit for DOM to update
                await new Promise(resolve => setTimeout(resolve, 300));
            } else {
                console.log('Button is hidden, skipping...');
            }
        }
        
        // Final check after expanding all
        const targetElement = document.getElementById(targetId);
        if (targetElement) {
            const isVisible = targetElement.offsetParent !== null;
            console.log(`Final check - Target found! Visible: ${isVisible}`);
            if (isVisible) {
                console.log(`Found target ${targetId} after expanding all comments`);
                this._scrollToTarget(targetElement);
            } else {
                console.log(`Target ${targetId} exists but still not visible even after expanding all comments`);
            }
        } else {
            console.log(`Target ${targetId} not found even after expanding all comments`);
        }
    },

        /**
     * Gets the PUID from the current URL
     */
    _getPuidFromUrl() {
            const pathSegments = window.location.pathname.split('/');
            // Check for /u/<puid>
            if (pathSegments.length > 2 && pathSegments[1] === 'u') {
                return pathSegments[2];
            }
            // Check for /page/<puid> (public pages)
            if (pathSegments.length > 2 && pathSegments[1] === 'page') {
                return pathSegments[2];
            }
            // Check for /group/<puid> (groups)
            if (pathSegments.length > 2 && pathSegments[1] === 'group') {
                return pathSegments[2];
            }
            // Check for /events/<puid> (events)
            if (pathSegments.length > 2 && pathSegments[1] === 'events') {
                return pathSegments[2];
            }
            return '';
    },
    
    /**
     * Creates a back-to-top button for a specific timeline container
     */
    _createBackToTopButton(containerId) {
        // Check if button already exists
        const existingButton = document.getElementById(`back-to-top-${containerId}`);
        if (existingButton) return;

        const button = document.createElement('button');
        button.id = `back-to-top-${containerId}`;
        button.className = 'back-to-top-button';
        button.setAttribute('aria-label', 'Back to top');
        button.innerHTML = `
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"></path>
            </svg>
        `;

        button.addEventListener('click', () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });

        document.body.appendChild(button);

        // Store reference in loader state
        const state = this._loaders.get(containerId);
        if (state) {
            state.backToTopButton = button;
        }

        // Set up scroll listener to show/hide button
        this._setupBackToTopScroll(containerId, button);
    },

    /**
     * Sets up scroll listener for back-to-top button visibility
     */
    _setupBackToTopScroll(containerId, button) {
        const scrollHandler = () => {
            const scrollPosition = window.pageYOffset || document.documentElement.scrollTop;
            // Show button after scrolling past 800px (roughly after clicking "Load More" once)
            if (scrollPosition > 800) {
                button.classList.add('visible');
            } else {
                button.classList.remove('visible');
            }
        };

        // Add scroll listener
        window.addEventListener('scroll', scrollHandler);

        // Store the handler reference so we can remove it later if needed
        const state = this._loaders.get(containerId);
        if (state) {
            state.scrollHandler = scrollHandler;
        }

        // Run once to check initial state
        scrollHandler();
    }
};

/**
 * @file modules/new_posts_polling.js
 * @description Polls for new posts on timelines and shows indicator
 * Populates the App.NewPostsPolling namespace.
 */
App.NewPostsPolling = {
    pollInterval: 30000, // Poll every 30 seconds
    pollTimer: null,
    isPolling: false,
    currentTimeline: null, // 'feed', 'group', or 'event'
    timelineId: null, // PUID for groups/events, null for main feed
    lastCheckTimestamp: null,

    /**
     * Initialize polling for a specific timeline
     */
        init(timeline, timelineId = null) {
        this.currentTimeline = timeline;
        this.timelineId = timelineId;
        
        // Check if we have a stored timestamp from a recent reload
        const storedTimestamp = localStorage.getItem('lastPostCheck_' + timeline + (timelineId || ''));
        const storedTime = storedTimestamp ? new Date(storedTimestamp) : null;
        const now = new Date();
        
        // If stored timestamp is less than 5 minutes old, use it
        // Otherwise, go back 2 minutes to catch any posts we might have missed
        if (storedTime && (now - storedTime) < 300000) { // 300000ms = 5 minutes
            this.lastCheckTimestamp = storedTime.toISOString();
            console.log('Using stored timestamp from recent reload:', this.lastCheckTimestamp);
        } else {
            const twoMinutesAgo = new Date(Date.now() - 120000); // 120000ms = 2 minutes
            this.lastCheckTimestamp = twoMinutesAgo.toISOString();
            console.log('Initializing new posts polling, checking since:', this.lastCheckTimestamp);
        }
        
        // Create indicator if it doesn't exist
        this._createIndicator();
        
        // Start polling
        this.startPolling();
        
        // Stop/restart polling based on visibility
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopPolling();
            } else {
                // When page becomes visible again, use current timestamp
                this.lastCheckTimestamp = new Date().toISOString();
                this.saveTimestamp(); // Save it
                this.startPolling();
                this.checkForNewPosts();
            }
        });
    },

    /**
     * Create the new posts indicator element
     */
    _createIndicator() {
        // Remove existing indicator if present
        const existing = document.getElementById('new-posts-indicator');
        if (existing) existing.remove();

        const indicator = document.createElement('div');
        indicator.id = 'new-posts-indicator';
        indicator.className = 'new-posts-indicator';
        indicator.innerHTML = `
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path>
            </svg>
            <span>New posts available</span>
        `;
        
        indicator.addEventListener('click', () => {
            // Save current timestamp before reload so we don't show stale notifications
            this.lastCheckTimestamp = new Date().toISOString();
            this.saveTimestamp();
            window.location.reload();
        });

        document.body.appendChild(indicator);
    },

    /**
     * Save the last check timestamp to localStorage
     */
    saveTimestamp() {
        const key = 'lastPostCheck_' + this.currentTimeline + (this.timelineId || '');
        localStorage.setItem(key, this.lastCheckTimestamp);
    },

    /**
     * Start polling for new posts
     */
    startPolling() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        this.pollTimer = setInterval(() => {
            this.checkForNewPosts();
        }, this.pollInterval);
        
        console.log('New posts polling started for', this.currentTimeline);
    },

    /**
     * Stop polling
     */
    stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        this.isPolling = false;
        console.log('New posts polling stopped');
    },

    /**
     * Check if new posts are available
     */
    async checkForNewPosts() {
        if (!this.currentTimeline) return;

        try {
            let apiUrl;
            
            switch(this.currentTimeline) {
                case 'feed':
                    apiUrl = `/api/feed/check_new?since=${encodeURIComponent(this.lastCheckTimestamp)}`;
                    break;
                case 'group':
                    apiUrl = `/group/api/group/${this.timelineId}/check_new?since=${encodeURIComponent(this.lastCheckTimestamp)}`;
                    break;
                case 'event':
                    apiUrl = `/api/event/${this.timelineId}/check_new?since=${encodeURIComponent(this.lastCheckTimestamp)}`;
                    break;
                default:
                    return;
            }

            const response = await fetch(apiUrl);
            if (!response.ok) return;

            const data = await response.json();
            
            if (data.has_new_posts) {
                this.showIndicator();
                // Don't update lastCheckTimestamp here - wait until user actually views the posts
            } else {
                // No new posts, update timestamp to now
                this.lastCheckTimestamp = new Date().toISOString();
                this.saveTimestamp();
            }
        } catch (error) {
            console.error('Error checking for new posts:', error);
        }
    },

    /**
     * Show the new posts indicator
     */
    showIndicator() {
        const indicator = document.getElementById('new-posts-indicator');
        if (indicator) {
            indicator.classList.add('visible');
        }
    },

    /**
     * Hide the indicator
     */
    hideIndicator() {
        const indicator = document.getElementById('new-posts-indicator');
        if (indicator) {
            indicator.classList.remove('visible');
        }
    }
};

/**
 * @file modules/router.js
 * @description Client-side router for the Single-Page Application (SPA).
 * Populates the App.Router namespace.
 */
App.Router = {
    // Defines the page routes.
    // 'path': The URL path to match.
    // 'contentUrl': The API endpoint to fetch the page's HTML content from.
    // 'title': The text to set as the document title.
    // 'modules': (Optional) An array of module names to preload for this page.
    routes: [
        {
            path: '/',
            contentUrl: '/api/page/feed',
            title: 'Main Feed',
            modules: ['post.js', 'comment.js'] // Modules for creating/editing posts/comments
        },
        {
            path: '/friends/',
            contentUrl: '/friends/api/page/connections',
            title: 'My Connections',
            modules: ['actions.js'] // For unfollow button
        },
        {
            path: '/group/my_groups/',
            contentUrl: '/group/api/page/my_groups',
            title: 'My Groups',
            modules: ['group.js'] // For search bar logic
        },
        // NEW: Add the route for "My Events"
        {
            path: '/events/',
            contentUrl: '/events/api/page/my_events',
            title: 'My Events',
            modules: ['events.js'] // For tabs and search logic
        },
        // NEW: Add the route for "My Media"
        {
            path: '/my_media/',
            contentUrl: '/api/page/my_media',
            title: 'My Media Gallery',
            modules: [] // Clicks are handled by media_carousel.js, which is global
        },
        {
            path: '/parental/',
            contentUrl: '/parental/api/page/dashboard',
            title: 'Parental Controls',
            modules: []
        }
    ],

    // The main content container
    contentContainer: null,

    // The currently active page path
    currentPage: null,

    /**
     * Initializes the router.
     * Sets up the content container, listens for popstate events (back/forward buttons),
     * and loads the initial page content.
     */
    init() {
        this.contentContainer = document.getElementById('main-content-container');
        if (!this.contentContainer) {
            console.error('Router init failed: #main-content-container not found.');
            return;
        }

        // Listen for browser back/forward navigation
        window.addEventListener('popstate', (event) => this.handlePopState(event));

        // Hijack clicks on all internal navigation links
        document.body.addEventListener('click', (event) => this.handleNavClick(event));

        // Load the initial page content
        let initialPath = window.location.pathname;
        
        // --- MODIFICATION: Simplified and corrected initial load logic ---
        const matchingRoute = this.routes.find(r => r.path === initialPath);
        const initialContentUrl = window.appConfig.initialContentUrl; // Get URL from Flask

        if (matchingRoute && initialContentUrl) {
            // We are on a valid SPA page (like / or /friends/)
            // and the server told us what content to load.
            this.currentPage = initialPath;
            // Load the content for this page, but don't push to history (it's the initial load)
            this.loadContent(initialContentUrl, matchingRoute.title, matchingRoute.modules, false);
            this.updateActiveNavLink(initialPath);
        } else if (!matchingRoute && initialPath === '/') {
             // This is the case for a logged-out user at '/'
             // 'matchingRoute' is found, but 'initialContentUrl' is not provided by Flask.
             // The HTML is already rendered with the login prompt. We just set the page.
             this.currentPage = '/';
        } else if (matchingRoute) {
            // This is a logged-in user, but initialContentUrl is missing (e.g., on /login page)
            // or an unknown path. Don't load anything.
             console.log('Router: On matching route but no initial content URL. Assuming static page.');
             this.currentPage = initialPath;
        } else {
            // This is a load on an unknown path.
            // Fallback to loading the main feed content at the root path.
            console.warn(`Router: No route found for initial path "${initialPath}". Loading default feed.`);
            const rootRoute = this.routes.find(r => r.path === '/');
            if (rootRoute) {
                this.currentPage = rootRoute.path;
                this.loadContent(rootRoute.contentUrl, rootRoute.title, rootRoute.modules, false);
                this.updateActiveNavLink(rootRoute.path);
            }
        }
        // --- END MODIFICATION ---
    },

    /**
     * Handles clicks on navigation links.
     * Prevents default navigation and calls navigate() instead.
     */
    handleNavClick(event) {
        // Find the closest ancestor link
        const navLink = event.target.closest('a[data-route]');
        
        // Check for various exit conditions
        if (!navLink || 
            event.button !== 0 || // Not a left click
            event.metaKey || event.ctrlKey || event.shiftKey || // Modifier keys
            navLink.target === '_blank' || // Opens in new tab
            navLink.hasAttribute('data-no-spa')) // Explicitly marked to skip router
        {
            return;
        }

        // We have a valid SPA navigation click
        event.preventDefault();
        
        // --- THIS IS THE FIX ---
        // Was: const newPath = navLink.getAttribute('href');
        const newPath = navLink.getAttribute('data-route');
        // --- END FIX ---
        
        // Don't re-navigate if already on the same page
        if (newPath === this.currentPage) {
            return;
        }

        this.navigate(newPath);
    },

    /**
     * Handles the browser's back/forward buttons.
     */
    handlePopState(event) {
        const newPath = window.location.pathname;
        const route = this.routes.find(r => r.path === newPath);
        if (route) {
            this.currentPage = newPath;
            this.loadContent(route.contentUrl, route.title, route.modules, false); // false = don't push state
        }
    },

    /**
     * Main navigation function.
     * Fetches new content, updates the URL, and changes the page title.
     * @param {string} path - The new URL path (e.g., "/friends/").
     */
    async navigate(path) {
        const route = this.routes.find(r => r.path === path);
        if (!route) {
            console.warn(`No route found for path: ${path}. Performing full page load.`);
            window.location.href = path; // Fallback to full reload
            return;
        }

        this.currentPage = path;
        
        try {
            // Load the new content and update the page
            await this.loadContent(route.contentUrl, route.title, route.modules, true); // true = push state
        } catch (error) {
            console.error(`Error loading content for ${path}:`, error);
            // On error, try a full page reload as a fallback
            window.location.href = path;
        }
    },

    /**
     * Fetches and injects new page content into the main container.
     * @param {string} contentUrl - The API URL to fetch HTML from.
     * @param {string} title - The new page title.
     * @param {string[]} [modules=[]] - Optional modules to preload.
     * @param {boolean} [pushState=true] - Whether to push a new state to browser history.
     */
    async loadContent(contentUrl, title, modules = [], pushState = true) {
        App.showLoader(); // Show loader before fetching
        
        let newPath = '/'; // Default path
        const route = this.routes.find(r => r.contentUrl === contentUrl);
        if (route) {
            newPath = route.path;
        }

        try {
            const response = await fetch(contentUrl);
            if (!response.ok) {
                throw new Error(`Failed to fetch content (status: ${response.status})`);
            }
            const html = await response.text();

            // Update browser history and title
            if (pushState) {
                history.pushState({ path: newPath }, '', newPath);
            }
            document.title = title;

            // --- START BUG FIX V3 ---
            // Await the hideLoader promise. This ensures the fade-out
            // animation *completes* before we block the main thread.
            await App.hideLoader();

            // Now, inject the new content. The browser may hang here
            // for a moment, but the loader is already gone.
            this.contentContainer.innerHTML = html; 
            
            // NEW: Update active nav link
            this.updateActiveNavLink(newPath);

            // Run any scripts required for the new content
            this.runPageScripts(modules);
            // --- END BUG FIX V3 ---

            // NEW: Scroll to hash anchor after content is loaded
            this.handleHashScroll();

        } catch (error) {
            console.error('Failed to load page content:', error);
            this.contentContainer.innerHTML = `<p class="text-red-500 text-center p-8">Error: Could not load page content. Please try again.</p>`;
            // Also hide the loader if an error occurs during fetch
            await App.hideLoader(); // Await it here too
        } 
        // No finally block needed
    },

        /**
     * NEW: Scrolls to hash anchor if present in URL
     */
    handleHashScroll() {
        if (window.location.hash) {
            const targetId = window.location.hash.substring(1);
            // Small delay to let the DOM settle
            setTimeout(() => {
                const targetElement = document.getElementById(targetId);
                if (targetElement) {
                    console.log('Scrolling to:', targetId);
                    targetElement.scrollIntoView({
                        behavior: 'smooth',
                        block: 'center'
                    });
                    targetElement.classList.add('post-highlight');
                    setTimeout(() => {
                        targetElement.classList.remove('post-highlight');
                    }, 3000);
                } else {
                    console.log('Hash target not found:', targetId);
                }
            }, 300);
        }
    },
    /**
     * Updates the 'active' class on the main navigation links.
     * @param {string} path - The new active path.
     */
    updateActiveNavLink(path) {
        const nav = document.getElementById('main-navigation');
        if (!nav) return;

        nav.querySelectorAll('a[data-route]').forEach(link => {
            if (link.getAttribute('data-route') === path) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
    },

    /**
     * Preloads and initializes modules for the newly loaded page.
     * Also runs any global functions needed after content injection (like timestamp conversion).
     * @param {string[]} [modules=[]] - An array of module names to load.
     */
    async runPageScripts(modules = []) {
        // Run global utilities that need to re-scan the new DOM
        if (App.Utils && typeof App.Utils.convertAllUTCTimestamps === 'function') {
            App.Utils.convertAllUTCTimestamps();
        }

        // Initialize auto-growing textarea for create post form (SPA pages)
        const createPostTextarea = document.getElementById('content');
        if (createPostTextarea) {
            const adjustTextareaHeight = () => {
                createPostTextarea.style.height = 'auto';
                createPostTextarea.style.height = createPostTextarea.scrollHeight + 'px';
            };
            createPostTextarea.addEventListener('input', adjustTextareaHeight);
            adjustTextareaHeight();
        }

        if (App.LoadMore && typeof App.LoadMore.initializeButtons === 'function') {
            // Small delay to ensure DOM is fully rendered
            setTimeout(() => {
                App.LoadMore.initializeButtons();
            }, 100);
        }
        
        // Initialize new posts polling based on current page
        if (App.NewPostsPolling) {
            setTimeout(() => {
                const pathname = window.location.pathname;
                
                if (pathname === '/') {
                    // Main feed
                    App.NewPostsPolling.init('feed');
                } else if (pathname.startsWith('/group/') && pathname.includes('/profile/')) {
                    // Group profile
                    const puid = App.LoadMore._getPuidFromUrl();
                    if (puid) {
                        App.NewPostsPolling.init('group', puid);
                    }
                } else if (pathname.startsWith('/events/') && pathname.includes('/profile/')) {
                    // Event profile
                    const puid = App.LoadMore._getPuidFromUrl();
                    if (puid) {
                        App.NewPostsPolling.init('event', puid);
                    }
                }
            }, 200);
        }

        // Preload and initialize page-specific modules
        // All modules already loaded in consolidated app.js
        
        try {
            // All modules pre-loaded, initialization happens in initCore
            console.log(`Successfully loaded modules for page: ${modules.join(', ')}`);
            
            // --- HACK/WORKAROUND ---
            // Some partials (_friends_content.html, _my_groups_content.html) have
            // inline <script> tags with functions that need to be globally available
            // *after* their content is injected. We find and re-run them here.
            
            // Re-run the search filter function if it exists
            if (typeof filterConnections === 'function') {
                filterConnections(); // For friends page
                 // Re-bind the search input listener
                const searchInput = document.getElementById('connectionsSearchInput');
                if (searchInput && !searchInput.dataset.listenerAttached) {
                    searchInput.addEventListener('input', () => {
                        clearTimeout(window.connectionsSearchTimeout);
                        window.connectionsSearchTimeout = setTimeout(filterConnections, 200);
                    });
                    searchInput.dataset.listenerAttached = 'true';
                }
            }
            if (typeof filterMyGroups === 'function') {
                filterMyGroups(); // For my_groups page
                // Re-bind the search input listener
                const searchInput = document.getElementById('myGroupsSearchInput');
                if (searchInput && !searchInput.dataset.listenerAttached) {
                    searchInput.addEventListener('input', () => {
                        clearTimeout(window.myGroupsSearchTimeout);
                        window.myGroupsSearchTimeout = setTimeout(filterMyGroups, 200);
                    });
                    searchInput.dataset.listenerAttached = 'true';
                }
            }
            // --- END HACK ---

        } catch (error) {
            console.error('Error loading modules for page:', error);
        }
    }
};

/**
 * @file modules/media_toggle.js
 * @description Handles showing/hiding additional media in posts with many photos.
 * Populates the App.MediaToggle namespace.
 */
App.MediaToggle = {
    /**
     * Show more media items in a post (beyond the first 4)
     * @param {string} postCuid - The CUID of the post
     */
    showMoreMedia(postCuid) {
        const mediaGrid = document.getElementById(`media-grid-${postCuid}`);
        if (!mediaGrid) return;

        // Show all hidden media items
        const hiddenMedia = mediaGrid.querySelectorAll('.extra-media.hidden');
        hiddenMedia.forEach(item => {
            item.classList.remove('hidden');
        });

        // Toggle buttons
        const showMoreBtn = document.querySelector(`.show-more-media-button[data-post-cuid="${postCuid}"]`);
        const showLessBtn = document.querySelector(`.show-less-media-button[data-post-cuid="${postCuid}"]`);
        
        if (showMoreBtn) showMoreBtn.classList.add('hidden');
        if (showLessBtn) showLessBtn.classList.remove('hidden');
    },

    /**
     * Show less media items in a post (collapse back to first 4)
     * @param {string} postCuid - The CUID of the post
     */
    showLessMedia(postCuid) {
        const mediaGrid = document.getElementById(`media-grid-${postCuid}`);
        if (!mediaGrid) return;

        // Hide extra media items (keep only first 4 visible)
        const extraMedia = mediaGrid.querySelectorAll('.extra-media');
        extraMedia.forEach(item => {
            item.classList.add('hidden');
        });

        // Toggle buttons
        const showMoreBtn = document.querySelector(`.show-more-media-button[data-post-cuid="${postCuid}"]`);
        const showLessBtn = document.querySelector(`.show-less-media-button[data-post-cuid="${postCuid}"]`);
        
        if (showMoreBtn) showMoreBtn.classList.remove('hidden');
        if (showLessBtn) showLessBtn.classList.add('hidden');

        // Scroll the post back into view smoothly
        const postCard = document.getElementById(`post-${postCuid}`);
        if (postCard) {
            postCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }
};

/**
 * @file modules/post.js
 * @description Handles logic for the post editing modal.
 * Populates the App.Post namespace.
 */
App.Post = {
    init() {
        const form = document.getElementById('editPostForm');
        if (form) {
            form.addEventListener('submit', (e) => this.submitEditForm(e));
        }
    },
    
    openEditModal(postCuid, authorPuid, content, privacy, media, viewerHomeUrl, isFederated, isGroupPost, isPublicPage, isEventPost, taggedUserPuids, location, currentUserRequiresParentalApproval, profileUserRequiresParentalApproval) {
        const modal = document.getElementById('editPostModal');
        if (!modal) return;
        App.state.editingPost = { cuid: postCuid, authorPuid, viewerHomeUrl, isFederated };
        document.getElementById('editPostCuid').value = postCuid;
        document.getElementById('editPostContent').value = content;
        
        const privacySelect = document.getElementById('editPostPrivacy');
        if (privacySelect) {
            privacySelect.innerHTML = '';
            let options = [];
            if (isEventPost) {
                options = [['Event Invitees Only', 'event']];
            } else if (isGroupPost) {
                if (!requiresParentalApproval) {
                    options.push(['Public', 'public']);
                }
                options.push(['Group Only', 'group']);
            } else if (isPublicPage) {
                if (!requiresParentalApproval) {
                    options.push(['Public', 'public']);
                }
                options.push(['Followers Only', 'followers']);
            } else {
                if (!isFederated) options.push(['Local Only', 'local']);
                if (!currentUserRequiresParentalApproval && !profileUserRequiresParentalApproval) {
                    options.push(['Public', 'public']);
                }
                options.push(['Friends Only', 'friends']);
            }
            options.forEach(([text, value]) => privacySelect.options.add(new Option(text, value)));
            privacySelect.value = privacy;
        }

        try {
            App.state.selectedEditPostMedia = JSON.parse(media);
        } catch (e) {
            console.error("Error parsing media JSON for post edit modal:", e);
            App.state.selectedEditPostMedia = [];
        }
        App.Media.Previews.updateEditPost();
        if (typeof window.initializeEditPostTagging === 'function') {
            window.initializeEditPostTagging(taggedUserPuids || '[]', location || '');
        }
        sessionStorage.setItem('mediaBrowserMode', 'editPost');
        App.Modal.open('editPostModal');
    },
    
    closeEditModal() {
        App.Modal.close('editPostModal');
        App.state.editingPost = { cuid: null, authorPuid: null, viewerHomeUrl: '', isFederated: false };
        App.state.selectedEditPostMedia = [];
        const form = document.getElementById('editPostForm');
        if (form) form.reset();
        App.Media.Previews.updateEditPost();

                // NEW: Reset tagging state
        if (typeof window.resetEditPostTagging === 'function') {
            window.resetEditPostTagging();
        }
        
        sessionStorage.removeItem('mediaBrowserMode');
    },
    
async submitEditForm(event) {
    event.preventDefault();
    const cuid = App.state.editingPost.cuid;
    if (!cuid) {
        App.Toast.error('Error: Invalid post identifier.');
        return;
    }
    const payload = {
        content: document.getElementById('editPostContent').value,
        privacy_setting: document.getElementById('editPostPrivacy').value,
        selected_media_files: JSON.stringify(App.state.selectedEditPostMedia),
        // NEW: Add tagged users and location
        tagged_users: document.getElementById('edit-tagged-users')?.value || '[]',
        location: document.getElementById('edit-location')?.value || ''
    };
    try {
        const response = await fetch(`/edit_post/${cuid}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        
        if (response.ok) {
            // Close the edit modal
            this.closeEditModal();
            
            // Store toast message in sessionStorage to show after reload
            sessionStorage.setItem('pendingToast', JSON.stringify({
                message: result.message || 'Post updated successfully!',
                type: 'success'
            }));
            
            // Reload with hash to scroll back to the post
            window.location.hash = `post-${cuid}`;
            location.reload();
        } else {
            // Show error toast (no reload, so this will display immediately)
            App.Toast.error(result.error || 'Failed to update post.');
        }
    } catch (error) {
        console.error('Error updating post:', error);
        App.Toast.error('An unexpected error occurred while updating the post.');
    }
    }
};

/**
 * @file modules/comment.js
 * @description Handles comment replies and the edit comment modal.
 * Populates the App.Comment namespace.
 */
App.Comment = {
    init() {
        const form = document.getElementById('editCommentForm');
        if (form) {
            form.addEventListener('submit', (e) => this.submitEditForm(e));
        }
    },

    showReplyForm(postId, parentCommentId, replyToUsername) {
        const form = document.getElementById(`commentForm-${postId}`);
        if (!form) return;
        form.querySelector('.parent-comment-id-input').value = parentCommentId;
        const display = form.querySelector('.replying-to-display');
        if (display) {
            display.querySelector('.reply-to-username').textContent = `@${replyToUsername}`;
            display.classList.remove('hidden');
        }
        const textarea = form.querySelector('textarea[name="comment_content"]');
        textarea.value = `@${replyToUsername} `;
        textarea.focus();
        form.scrollIntoView({ behavior: 'smooth', block: 'center' });
    },

    hideReplyForm(postId) {
        const form = document.getElementById(`commentForm-${postId}`);
        if (!form) return;
        form.querySelector('.parent-comment-id-input').value = '';
        const display = form.querySelector('.replying-to-display');
        if (display) display.classList.add('hidden');
        form.querySelector('textarea[name="comment_content"]').value = '';
        
        App.state.selectedNewCommentMedia[postId] = [];
        App.Media.Previews.updateNewComment(postId);
    },

    openEditModal(cuid, content, mediaJson, viewerHomeUrl, isFederated, isMediaComment = false) {
        const modal = document.getElementById('editCommentModal');
        if (!modal) return;
        
        App.state.editingComment = { 
            cuid, 
            viewerHomeUrl, 
            isFederated,
            isMediaComment: isMediaComment  // Add this flag
        };
        
        document.getElementById('editCommentCuid').value = cuid;
        document.getElementById('editCommentContent').value = content;

        try {
            App.state.selectedEditCommentMedia = JSON.parse(mediaJson);
        } catch (e) {
            console.error("Error parsing media JSON for comment edit modal:", e);
            App.state.selectedEditCommentMedia = [];
        }
        
        App.Media.Previews.updateEditComment();
        sessionStorage.setItem('mediaBrowserMode', 'editComment');
        App.Modal.open('editCommentModal');
    },

    closeEditModal() {
        App.Modal.close('editCommentModal');
        App.state.editingComment = { cuid: null, viewerHomeUrl: '', isFederated: false, isMediaComment: false };
        App.state.selectedEditCommentMedia = [];
        const form = document.getElementById('editCommentForm');
        if (form) form.reset();
        App.Media.Previews.updateEditComment();
        sessionStorage.removeItem('mediaBrowserMode');
    },
    
    /**
     * NEW: Shows hidden comments or replies within a specific container.
     * @param {HTMLElement} buttonElement - The "show more" button that was clicked.
     * @param {string} containerId - The ID of the parent container holding the list.
     * @param {string} itemClass - The classname of the items to reveal (e.g., 'extra-comment').
     */
    showMore(buttonElement, containerId, itemClass) {
        const container = document.getElementById(containerId);
        if (!container) {
            console.error(`showMore: Container with ID ${containerId} not found.`);
            return;
        }

        // Find all hidden items with the specified class *within this container*
        const itemsToShow = container.querySelectorAll(`.${itemClass}.hidden`);
        
        itemsToShow.forEach(item => {
            item.classList.remove('hidden');
        });

        // Hide the "show more" button itself
        if (buttonElement) {
            buttonElement.style.display = 'none';
        }
    },

async submitEditForm(event) {
    event.preventDefault();
    const cuid = App.state.editingComment.cuid;
    const isMediaComment = App.state.editingComment.isMediaComment || false;
    
    // Build payload differently based on comment type
    const payload = {
        content: document.getElementById('editCommentContent').value
    };
    
    // For media comments, send as 'media_files' array
    // For regular comments, send as 'selected_comment_media_files' JSON string
    if (isMediaComment) {
        payload.media_files = App.state.selectedEditCommentMedia || [];
    } else {
        payload.selected_comment_media_files = JSON.stringify(App.state.selectedEditCommentMedia || []);
    }

    try {
        // Use different endpoint based on comment type
        const endpoint = isMediaComment 
            ? `/media/comment/${cuid}/edit` 
            : `/edit_comment/${cuid}`;
            
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        
        if (response.ok) {
            // Close the edit modal
            this.closeEditModal();
            
            if (isMediaComment) {
                // For media comments, reload the modal
                if (window.mediaData && window.mediaData.muid) {
                    if (typeof openMediaViewModal === 'function') {
                        openMediaViewModal(window.mediaData.muid);
                    } else {
                        location.reload();
                    }
                }
                
                if (App && App.Toast) {
                    App.Toast.show('Comment updated!', 'success');
                }
            } else {
                // For regular comments, store toast and reload page
                sessionStorage.setItem('pendingToast', JSON.stringify({
                    message: result.message || 'Comment updated successfully!',
                    type: 'success'
                }));
                location.reload();
            }
        } else {
            throw new Error(result.error || 'Failed to update comment');
        }
    } catch (error) {
        console.error('Error updating comment:', error);
        if (App && App.Toast) {
            App.Toast.show(error.message || 'Failed to update comment. Please try again.', 'error');
        } else {
            alert(error.message || 'Failed to update comment. Please try again.');
        }
    }
}
};


/**
 * @file modules/profile.js
 * @description Logic for the user profile page (cropper, info modals, post search).
 * Populates the App.Profile namespace.
 */
App.Profile = {
    _debounceTimeout: null, // For post search

    /**
     * Initializes all functionality for profile pages.
     * This is called by script.js when a profile page is loaded.
     */
    init() {
        // Init Cropper if its form exists
        if (document.getElementById('profilePictureUploadForm')) {
            this.Cropper.init();
        }
        
        // Init Info Modal if its form exists
        if (document.getElementById('profileInfoForm')) {
            this.Info.init();
        }

        // Init Page Post Search if its input exists
        const searchInput = document.getElementById('pagePostSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(this._debounceTimeout);
                this._debounceTimeout = setTimeout(() => this.filterPagePosts(), 300);
            });
        }
    },

    /**
     * Filters posts on the public page timeline based on search input.
     */
    filterPagePosts() {
        const searchInput = document.getElementById('pagePostSearchInput');
        const searchTerm = searchInput.value.trim().toLowerCase();

        const listContainer = document.getElementById('page-posts-list-container');
        const noResultsMsg = document.getElementById('noPagePostResultsMessage');
        const initialNoPostsMsg = document.getElementById('no-page-posts-initial');

        if (!listContainer || !noResultsMsg) {
            console.warn("filterPagePosts: Missing required elements.");
            return;
        }

        let visibleCount = 0;
        const allPosts = listContainer.querySelectorAll('.page-post-item');
        
        allPosts.forEach(post => {
            const searchText = post.dataset.searchText || '';
            if (!searchTerm || searchText.includes(searchTerm)) {
                post.style.display = 'block'; // 'block' since it's a div
                visibleCount++;
            } else {
                post.style.display = 'none';
            }
        });

        const hasAnyPosts = allPosts.length > 0;

        // Toggle "no results" messages
        if (initialNoPostsMsg) {
            // Hide initial message if user is searching or if there are posts
            initialNoPostsMsg.style.display = (searchTerm || hasAnyPosts) ? 'none' : 'block';
        }

        if (visibleCount === 0 && searchTerm) {
            noResultsMsg.textContent = `No posts found matching "${searchTerm}".`;
            noResultsMsg.style.display = 'block';
        } else {
            noResultsMsg.style.display = 'none';
        }

        // Show "no posts" message only if search is clear and there were no posts to begin with
        if (initialNoPostsMsg) {
            if (searchTerm) {
                initialNoPostsMsg.style.display = 'none';
            } else if (hasAnyPosts) {
                 initialNoPostsMsg.style.display = 'none';
            } else {
                initialNoPostsMsg.style.display = 'block';
            }
        }
    },

    Cropper: {
        _cropperInstance: null,
        _originalPath: '',

        init() {
            const fileInput = document.getElementById('profile_picture_file_input');
            const openBtn = document.getElementById('openCropperButton');
            const applyBtn = document.getElementById('applyCropButton');

            if (fileInput) {
                fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
                fileInput.value = ''; // Clear on load
            }
            if (openBtn) {
                openBtn.addEventListener('click', () => this.open());
                openBtn.disabled = true;
            }
            if (applyBtn) {
                applyBtn.addEventListener('click', () => this.apply());
            }
        },

        handleFileSelect(event) {
            this._originalPath = '';
            document.getElementById('original_image_path_from_browser').value = '';
            const openBtn = document.getElementById('openCropperButton');
            if (event.target.files && event.target.files[0]) {
                if (openBtn) openBtn.disabled = false;
                const reader = new FileReader();
                reader.onload = (e) => this._initInstance(e.target.result);
                reader.readAsDataURL(event.target.files[0]);
            } else {
                if (openBtn) openBtn.disabled = true;
            }
        },
        
        open() {
            const fileInput = document.getElementById('profile_picture_file_input');
            if (fileInput && fileInput.files && fileInput.files[0]) {
                const reader = new FileReader();
                reader.onload = (e) => this._initInstance(e.target.result);
                reader.readAsDataURL(fileInput.files[0]);
            } else if (this._originalPath) {
                const imageUrl = `${window.appConfig.serveMediaBaseUrl}${window.appConfig.loggedInUserPuid}/${this._originalPath}`;
                this._initInstance(imageUrl);
            } else {
                App.Modal.showInfo('Please select an image file first.');
            }
        },

        _initInstance(imageUrl) {
            if (this._cropperInstance) this._cropperInstance.destroy();
            const imageEl = document.getElementById('imageToCrop');
            if (!imageEl) return;
            
            imageEl.src = imageUrl;
            imageEl.onload = () => {
                App.Modal.open('cropperModal');
                requestAnimationFrame(() => {
                    this._cropperInstance = new Cropper(imageEl, {
                        aspectRatio: 1, viewMode: 2, dragMode: 'move',
                        cropBoxMovable: true, cropBoxResizable: false,
                        minCropBoxWidth: 100, minCropBoxHeight: 100,
                        toggleDragModeOnDblclick: false, background: false,
                        guides: false, center: false, highlight: false,
                        autoCropArea: 0.8, responsive: true, scalable: true,
                        zoomable: true, movable: true
                    });
                });
            };
            imageEl.onerror = () => {
                App.Modal.showInfo('Failed to load image for adjustment.');
                App.Modal.close('cropperModal');
            };
        },

        apply() {
            if (!this._cropperInstance) {
                App.Modal.showInfo('No image to adjust.');
                return;
            }
            const canvas = this._cropperInstance.getCroppedCanvas({ width: 256, height: 256 });
            if (!canvas || canvas.width === 0) {
                App.Modal.showInfo('Failed to crop image.');
                App.Modal.close('cropperModal');
                return;
            }
            document.getElementById('cropped_image_data').value = canvas.toDataURL('image/png');
            if (this._originalPath) {
                document.getElementById('original_image_path_from_browser').value = this._originalPath;
            }
            App.Modal.close('cropperModal');
            this._cropperInstance.destroy();
            document.getElementById('profilePictureUploadForm').submit();
        },

        updateFromBrowser(selectedPath) {
            if (!selectedPath) {
                App.Modal.showInfo('Please select a picture.');
                return;
            }
            this._originalPath = selectedPath;
            const imageUrl = `${window.appConfig.serveMediaBaseUrl}${window.appConfig.loggedInUserPuid}/${selectedPath}`;
            this._initInstance(imageUrl);
            const openBtn = document.getElementById('openCropperButton');
            if (openBtn) openBtn.disabled = false;
        }
    },

    Info: {
        init() {
            const form = document.getElementById('profileInfoForm');
            if (form) form.addEventListener('submit', (e) => this.submitForm(e));

            const dobEl = document.getElementById('display-dob-value');
            if (dobEl) dobEl.textContent = App.Utils.formatDisplayDate(dobEl.textContent);
            
            const addBtn = document.getElementById('add-family-member-btn');
            if(addBtn) addBtn.addEventListener('click', () => this.addFamilyMemberRow());
        },

        openModal() {
            document.querySelectorAll('#profileInfoForm [data-initial-value]').forEach(el => el.value = el.dataset.initialValue);
            document.querySelectorAll('#profileInfoForm [data-initial-checked]').forEach(el => el.checked = el.dataset.initialChecked === 'true');
            App.Modal.open('profileInfoModal');
        },

        // --- START FIX: Added 'event' argument and event.preventDefault() ---
        async submitForm(event) {
            event.preventDefault(); // Stop the form from submitting normally
            // --- END FIX ---

            const getSafeValue = (id, isCheckbox = false) => {
                const el = document.getElementById(id);
                return el ? (isCheckbox ? el.checked : el.value) : (isCheckbox ? false : null);
            };
            const profileFields = {};
            ['show_username', 'dob', 'hometown', 'occupation', 'bio', 'show_friends', 'website', 'email', 'phone', 'address'].forEach(field => {
                profileFields[field] = {
                    value: getSafeValue(field),
                    privacy_public: getSafeValue(`${field}_public`, true),
                    privacy_local: getSafeValue(`${field}_local`, true),
                    privacy_friends: getSafeValue(`${field}_friends`, true),
                };
            });
            const payload = {
                display_name: document.getElementById('display_name').value,
                profile_fields: profileFields,
                new_family_members: []
            };
            document.querySelectorAll('.new-family-member-row').forEach(row => {
                const relativeUserId = row.querySelector('.family-member-select').value;
                const relationshipType = row.querySelector('.relationship-type-input').value;
                if (relativeUserId && relationshipType) {
                    payload.new_family_members.push({
                        relative_user_id: relativeUserId,
                        relationship_type: relationshipType,
                        anniversary_date: row.querySelector('.anniversary-date-input').value,
                        privacy_public: row.querySelector('.family-public-check').checked,
                        privacy_local: row.querySelector('.family-local-check').checked,
                        privacy_friends: row.querySelector('.family-friends-check').checked
                    });
                }
            });

            try {
                const response = await fetch('/update_profile_info', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (response.ok) {
                    App.Modal.showInfo(result.message, () => window.location.reload());
                } else {
                    App.Modal.showInfo(result.error || 'Failed to update profile.');
                }
            } catch (error) {
                App.Modal.showInfo('An unexpected error occurred.');
            } finally {
                App.Modal.close('profileInfoModal');
            }
        },
        
        addFamilyMemberRow() {
            const container = document.getElementById('new-family-member-container');
            const newRow = document.createElement('div');
            newRow.className = 'new-family-member-row border-t pt-4 mt-4';
            
            let friendOptions = '<option value="">Select a friend</option>';
            if (Array.isArray(window.appConfig.friendsListForJS)) {
                window.appConfig.friendsListForJS.forEach(friend => {
                    friendOptions += `<option value="${friend.id}">${friend.display_name}</option>`;
                });
            }

            newRow.innerHTML = `
                <div class="flex items-end gap-2">
                    <div class="flex-grow">
                        <label class="block text-sm font-medium text-gray-700 mb-1">Family Member</label>
                        <select class="family-member-select mt-1 block w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm">${friendOptions}</select>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-700 mb-1">Relationship</label>
                        <input type="text" class="relationship-type-input mt-1 block w-full px-4 py-2 border border-gray-300 rounded-md shadow-sm" placeholder="e.g., Mother, Son">
                    </div>
                    <button type="button" class="remove-family-row-btn bg-red-500 hover:bg-red-600 text-white font-bold py-2 px-3 rounded-md text-sm">&times;</button>
                </div>
                <div class="anniversary-section-new mt-2" style="display: none;">
                    <label class="block text-sm font-medium text-gray-700 mb-1">Anniversary</label>
                    <input type="date" class="anniversary-date-input mt-1 block w-full px-4 py-2 border rounded-md shadow-sm">
                </div>
                <div class="privacy-toggle-group mt-2">
                    <label><input type="checkbox" class="family-public-check"> Public</label>
                    <label><input type="checkbox" class="family-local-check"> Local</label>
                    <label><input type="checkbox" class="family-friends-check" checked> Friends</label>

                </div>
            `;
            container.appendChild(newRow);

            newRow.querySelector('.remove-family-row-btn').addEventListener('click', () => newRow.remove());
            newRow.querySelector('.relationship-type-input').addEventListener('input', function() {
                const anniversarySection = newRow.querySelector('.anniversary-section-new');
                const partnerTerms = ['spouse', 'husband', 'wife', 'partner', 'civil partner'];
                anniversarySection.style.display = partnerTerms.includes(this.value.toLowerCase().trim()) ? 'block' : 'none';
            });
        },
        
        async removeFamilyMember(relationshipId) {
            App.Modal.showConfirm('Are you sure you want to remove this family member?', async () => {
                try {
                    const response = await fetch(`/remove_family_member/${relationshipId}`, { method: 'POST' });
                    const result = await response.json();
                    if (response.ok) {
                        App.Modal.showInfo(result.message, () => window.location.reload());
                    } else {
                        App.Modal.showInfo(result.error || 'Failed to remove family member.');
                    }
                } catch (error) {
                    App.Modal.showInfo('An unexpected error occurred.');
                }
            });
        },
        
        async openEditFamilyModal(relationshipId) {
            try {
                const response = await fetch(`/get_relationship_details/${relationshipId}`);
                const data = await response.json();
                if (response.ok) {
                    document.getElementById('edit_relationship_id').value = data.id;
                    document.getElementById('edit_family_member').value = data.relative_user_id;
                    document.getElementById('edit_relationship_type').value = data.relationship_type;
                    document.getElementById('edit_anniversary_date').value = data.anniversary_date;
                    document.getElementById('edit_family_public').checked = data.privacy_public === 1;
                    document.getElementById('edit_family_local').checked = data.privacy_local === 1;
                    document.getElementById('edit_family_friends').checked = data.privacy_friends === 1;
                    
                    const anniversarySection = document.getElementById('edit_anniversary-section');
                    const partnerTerms = ['spouse', 'husband', 'wife', 'partner', 'civil partner'];
                    anniversarySection.style.display = partnerTerms.includes(data.relationship_type.toLowerCase().trim()) ? 'block' : 'none';
					
                    const relationshipInput = document.getElementById('edit_relationship_type');
                    if (relationshipInput) {
                        relationshipInput.addEventListener('input', function() {
                            const anniversarySection = document.getElementById('edit_anniversary-section');
                            const partnerTerms = ['spouse', 'husband', 'wife', 'partner', 'civil partner'];
                            anniversarySection.style.display = partnerTerms.includes(this.value.toLowerCase().trim()) ? 'block' : 'none';
                        });
                    }
					
                    App.Modal.open('editFamilyMemberModal');
                } else {
                    App.Modal.showInfo(data.error || 'Failed to fetch details.');
                }
            } catch (error) {
                App.Modal.showInfo('An unexpected error occurred.');
            }
        },

        async submitEditFamilyForm() {
            const form = document.getElementById('editFamilyMemberForm');
            const relationshipId = form.querySelector('#edit_relationship_id').value;
            const payload = {
                relative_user_id: form.querySelector('#edit_family_member').value,
                relationship_type: form.querySelector('#edit_relationship_type').value,
                anniversary_date: form.querySelector('#edit_anniversary_date').value,
                privacy_public: form.querySelector('#edit_family_public').checked,
                privacy_local: form.querySelector('#edit_family_local').checked,
                privacy_friends: form.querySelector('#edit_family_friends').checked,
            };

            try {
                const response = await fetch(`/update_family_member/${relationshipId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (response.ok) {
                    App.Modal.showInfo(result.message, () => window.location.reload());
                } else {
                    App.Modal.showInfo('Error: ' + (result.error || 'Failed to update.'));
                }
            } catch (error) {
                App.Modal.showInfo('An unexpected error occurred.');
            }
        }
    }
};

/**
 * @file modules/group.js
 * @description Contains logic specific to group pages (invites, info edit).
 * Populates the App.Group namespace.
 */
App.Group = {
    _debounceTimeout: null, // NEW: For search debouncing

    // NEW: init function
    init() {
        const searchInput = document.getElementById('groupPostSearchInput');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(this._debounceTimeout);
                this._debounceTimeout = setTimeout(() => this.filterGroupPosts(), 300);
            });
        }
    },

    // NEW: filterGroupPosts function
    filterGroupPosts() {
        const searchInput = document.getElementById('groupPostSearchInput');
        const searchTerm = searchInput.value.trim().toLowerCase();

        const listContainer = document.getElementById('group-posts-list-container');
        const noResultsMsg = document.getElementById('noGroupPostResultsMessage');
        const initialNoPostsMsg = document.getElementById('no-group-posts-initial');

        if (!listContainer || !noResultsMsg) {
            console.warn("filterGroupPosts: Missing required elements.");
            return;
        }

        let visibleCount = 0;
        const allPosts = listContainer.querySelectorAll('.group-post-item');
        
        allPosts.forEach(post => {
            const searchText = post.dataset.searchText || '';
            if (!searchTerm || searchText.includes(searchTerm)) {
                post.style.display = 'block'; // 'block' since it's a div
                visibleCount++;
            } else {
                post.style.display = 'none';
            }
        });

        const hasAnyPosts = allPosts.length > 0;

        // Toggle "no results" messages
        if (initialNoPostsMsg) {
            initialNoPostsMsg.style.display = 'none';
        }

        if (visibleCount === 0 && searchTerm) {
            noResultsMsg.textContent = `No posts found matching "${searchTerm}".`;
            noResultsMsg.style.display = 'block';
        } else {
            noResultsMsg.style.display = 'none';
        }

        // Hide the "No posts in this group yet" message if a search is active
        if (initialNoPostsMsg) {
            if (searchTerm) {
                initialNoPostsMsg.style.display = 'none';
            } else if (hasAnyPosts) {
                 initialNoPostsMsg.style.display = 'none';
            } else {
                initialNoPostsMsg.style.display = 'block';
            }
        }
    },

    async openInviteModal(groupPuid) {
        const list = document.getElementById('inviteFriendsList');
        const loading = document.getElementById('inviteFriendsLoading');
        if (!list || !loading) return;

        App.Modal.open('inviteFriendsModal');
        loading.style.display = 'block';
        list.innerHTML = '';
        list.appendChild(loading);

        try {
            const response = await fetch(`/group/invite_friends/${groupPuid}`);
            if (!response.ok) throw new Error((await response.json()).error || 'Server error.');
            const friends = await response.json();

            loading.style.display = 'none';

            if (friends.length === 0) {
                list.innerHTML = '<p class="text-center text-gray-500 p-4">All friends are in this group or have a pending request.</p>';
            } else {
                friends.forEach(friend => {
                    let picUrl = '/static/images/default_avatar.png';
                    if (friend.profile_picture_path) {
                        picUrl = friend.hostname 
                            ? `${location.protocol}//${friend.hostname}/profile_pictures/${friend.profile_picture_path}` 
                            : `/profile_pictures/${friend.profile_picture_path}`;
                    }
                    list.insertAdjacentHTML('beforeend', `
                        <div class="flex items-center justify-between bg-gray-50 p-3 rounded-lg">
                            <div class="flex items-center">
                                <img src="${picUrl}" alt="${friend.display_name}" class="w-10 h-10 rounded-full mr-3 object-cover" onerror="this.src='/static/images/default_avatar.png';">
                                <div>
                                    <p class="font-bold">${friend.display_name}</p>
                                    <p class="text-sm text-gray-500">@${friend.username}${friend.hostname ? '@' + friend.hostname : ''}</p>
                                </div>
                            </div>
                            <button class="bg-blue-500 text-white font-bold py-1 px-3 rounded-md text-sm hover:bg-blue-600" onclick="App.Group.sendInvite(this, '${groupPuid}', '${friend.puid}')">
                                Send Invitation
                            </button>
                        </div>
                    `);
                });
            }
        } catch (error) {
            loading.style.display = 'none';
            list.innerHTML = `<p class="text-center text-red-500 p-4">Could not load friends: ${error.message}</p>`;
        }
    },

    async sendInvite(button, groupPuid, userPuid) {
        button.disabled = true;
        button.textContent = 'Sending...';
        try {
            const response = await fetch(`/group/invite/${groupPuid}/${userPuid}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.message || result.error || 'Unknown error.');
            button.textContent = 'Sent';
            button.classList.remove('bg-blue-500', 'hover:bg-blue-600');
            button.classList.add('bg-gray-400', 'cursor-not-allowed');
        } catch (error) {
            App.Modal.showInfo(`Error: ${error.message}`);
            button.disabled = false;
            button.textContent = 'Send Invitation';
        }
    },

    async submitInfo(groupPuid) {
        const payload = { profile_fields: {} };
        
        // Process profile fields that have checkboxes (including join_rules now)
        ['website', 'email', 'about', 'show_admins', 'show_members', 'join_rules'].forEach(field => {
            const valueElement = document.getElementById(`group_${field}`);
            const publicCheckbox = document.getElementById(`${field}_public`);
            const membersCheckbox = document.getElementById(`${field}_members`);
            
            // Skip if elements don't exist
            if (!publicCheckbox || !membersCheckbox) return;
            
            const value = (field === 'show_admins' || field === 'show_members') ? 'visible' : (valueElement?.value || '');
            payload.profile_fields[field] = {
                value: value,
                privacy_public: publicCheckbox.checked,
                privacy_members_only: membersCheckbox.checked,
            };
        });

        // Get join_rules privacy settings
        const joinRulesPublic = document.getElementById('join_rules_public')?.checked || false;
        const joinRulesMembers = document.getElementById('join_rules_members')?.checked || true;
        
        // Get join questions
        const validQuestions = this.joinQuestions.filter(q => q.trim());

        try {
            // Save profile fields (including join_rules with privacy)
            const profileResponse = await fetch(`/group/update_info/${groupPuid}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            // Save join questions (and pass join_rules privacy to backend)
            const joinSettingsResponse = await fetch(`/group/update_join_settings/${groupPuid}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    join_rules: payload.profile_fields.join_rules?.value || null,
                    join_rules_public: joinRulesPublic,
                    join_rules_members: joinRulesMembers,
                    join_questions: validQuestions
                })
            });
            
            const profileResult = await profileResponse.json();
            const joinResult = await joinSettingsResponse.json();
            
            if (profileResponse.ok && joinSettingsResponse.ok) {
                App.Modal.showInfo('Group information updated successfully!', () => window.location.reload());
            } else {
                const errorMsg = profileResult.error || joinResult.error || 'Failed to update group information.';
                App.Modal.showInfo(errorMsg);
            }
        } catch (error) {
            console.error('Error updating group info:', error);
            App.Modal.showInfo('An unexpected error occurred.');
        } finally {
            App.Modal.close('editGroupInfoModal');
        }
    },

    // Join request functionality
    currentGroupForJoin: null,
    joinQuestions: [],

    /**
     * Sends a group join request with optional rules/questions modal
     */
    async sendJoinRequest(button, group) {
        try {
            // First, fetch join settings for this group
            const settingsResponse = await fetch(`/group/join_settings/${group.puid}`);
            const settings = await settingsResponse.json();
            
            // Check if there are rules or questions
            const hasRules = settings.join_rules && settings.join_rules.trim();
            const hasQuestions = settings.join_questions && settings.join_questions.length > 0;
            
            if (hasRules || hasQuestions) {
                // Show modal with rules and questions
                this.currentGroupForJoin = group;
                this.openJoinRequestModal(group, settings);
            } else {
                // No rules/questions, send request directly
                await this.sendJoinRequestDirect(group);
            }
        } catch (error) {
            console.error('Error sending join request:', error);
            App.Toast.show('Failed to send join request', 'error');
        }
    },

    /**
     * Opens the join request modal with rules and questions
     */
    openJoinRequestModal(group, settings) {
        const modal = document.getElementById('joinGroupRequestModal');
        const rulesSection = document.getElementById('joinRulesSection');
        const questionsSection = document.getElementById('joinQuestionsSection');
        const rulesText = document.getElementById('joinRulesText');
        const questionsContainer = document.getElementById('joinQuestionsContainer');
        const agreeCheckbox = document.getElementById('agreeToRules');
        
        // Check if modal elements exist
        if (!modal || !rulesSection || !questionsSection || !rulesText || !questionsContainer) {
            console.error('Join request modal elements not found:', {
                modal: !!modal,
                rulesSection: !!rulesSection,
                questionsSection: !!questionsSection,
                rulesText: !!rulesText,
                questionsContainer: !!questionsContainer
            });
            App.Toast.show('Error: Modal not properly loaded. Please refresh the page.', 'error');
            return;
        }
        
        // Reset
        rulesSection.classList.add('hidden');
        questionsSection.classList.add('hidden');
        questionsContainer.innerHTML = '';
        if (agreeCheckbox) agreeCheckbox.checked = false;
        
        // Show rules if they exist
        if (settings.join_rules && settings.join_rules.trim()) {
            rulesText.textContent = settings.join_rules;
            rulesSection.classList.remove('hidden');
        }
        
        // Show questions if they exist
        if (settings.join_questions && settings.join_questions.length > 0) {
            settings.join_questions.forEach((question, index) => {
                const questionDiv = document.createElement('div');
                questionDiv.innerHTML = `
                    <label class="block text-sm font-medium secondary-text mb-1">
                        ${this.escapeHtml(question)}
                    </label>
                    <textarea 
                        id="question_${index}" 
                        class="w-full rounded-md shadow-sm form-input"
                        rows="2"
                        required
                    ></textarea>
                `;
                questionsContainer.appendChild(questionDiv);
            });
            questionsSection.classList.remove('hidden');
        }
        
        App.Modal.open('joinGroupRequestModal');
    },

    /**
     * Submits join request with responses
     */
    async submitJoinRequestWithResponses() {
        const rulesSection = document.getElementById('joinRulesSection');
        const agreeCheckbox = document.getElementById('agreeToRules');
        const questionsContainer = document.getElementById('joinQuestionsContainer');
        
        // Validate rules agreement if shown
        if (!rulesSection.classList.contains('hidden')) {
            if (!agreeCheckbox.checked) {
                App.Toast.show('You must agree to the group rules to join', 'error');
                return;
            }
        }
        
        // Collect question responses
        const questionResponses = {};
        const questions = questionsContainer.querySelectorAll('textarea');
        const labels = questionsContainer.querySelectorAll('label');
        
        for (let i = 0; i < questions.length; i++) {
            const answer = questions[i].value.trim();
            if (!answer) {
                App.Toast.show('Please answer all questions', 'error');
                return;
            }
            const questionText = labels[i].textContent.trim();
            questionResponses[questionText] = answer;
        }
        
        // Send the request with responses
        await this.sendJoinRequestDirect(
            this.currentGroupForJoin, 
            agreeCheckbox?.checked || false, 
            questionResponses
        );
        
        App.Modal.close('joinGroupRequestModal');
    },

    /**
     * Sends join request directly (called by other functions)
     */
    async sendJoinRequestDirect(group, rulesAgreed = false, questionResponses = {}) {
        try {
            const response = await fetch(`/group/join/${group.puid}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...group,
                    rules_agreed: rulesAgreed,
                    question_responses: questionResponses
                })
            });
            
            const data = await response.json();
            
            if (response.ok && data.status === 'success') {
                App.Toast.show(data.message || 'Join request sent successfully', 'success');
                // Reload the page to update button state
                setTimeout(() => window.location.reload(), 1000);
            } else {
                App.Toast.show(data.message || data.error || 'Failed to send join request', 'error');
            }
        } catch (error) {
            console.error('Error:', error);
            App.Toast.show('An error occurred', 'error');
        }
    },

    /**
     * Initialize join questions editor for admin
     */
    initializeJoinQuestionsEditor() {
        // Load existing questions from the group data
        const groupData = window.groupData; // Should be set in template
        if (groupData && groupData.join_questions) {
            try {
                this.joinQuestions = JSON.parse(groupData.join_questions) || [];
            } catch (e) {
                this.joinQuestions = [];
            }
        }
        this.renderJoinQuestions();
    },

    renderJoinQuestions() {
        const container = document.getElementById('joinQuestionsEditor');
        if (!container) return;
        
        container.innerHTML = '';
        this.joinQuestions.forEach((question, index) => {
            const div = document.createElement('div');
            div.className = 'flex items-center space-x-2';
            div.innerHTML = `
                <input type="text" 
                       value="${this.escapeHtml(question)}" 
                       onchange="App.Group.updateJoinQuestion(${index}, this.value)"
                       class="flex-1 rounded-md shadow-sm form-input text-sm"
                       placeholder="Enter question">
                <button type="button" 
                        onclick="App.Group.removeJoinQuestion(${index})"
                        class="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300">
                    <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                        <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                    </svg>
                </button>
            `;
            container.appendChild(div);
        });
    },

    addJoinQuestion() {
        this.joinQuestions.push('');
        this.renderJoinQuestions();
    },

    updateJoinQuestion(index, value) {
        this.joinQuestions[index] = value;
    },

    removeJoinQuestion(index) {
        this.joinQuestions.splice(index, 1);
        this.renderJoinQuestions();
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};

/**
 * @file modules/discover.js
 * @description Handles the "Discover Users/Pages" and "Discover Groups" modals with hide/unhide functionality.
 * Populates the App.Discover namespace.
 */
App.Discover = {
    _debounceTimeout: null,
    currentUsersTab: 'discover',  // 'discover' or 'hidden'
    currentGroupsTab: 'discover', // 'discover' or 'hidden'

    init() {
        // Search input listeners for Discover tab (Users)
        const discoverUsersSearchInput = document.getElementById('discoverUsersSearchInput');
        if (discoverUsersSearchInput) {
            discoverUsersSearchInput.addEventListener('input', () => {
                clearTimeout(this._debounceTimeout);
                this._debounceTimeout = setTimeout(() => this.filterDisplayedItems('discoverUsersList', 'noDiscoverableUsers', 'discoverUsersSearchInput'), 300);
            });
        }

        // Search input listeners for Discover tab (Pages)
        const discoverPagesSearchInput = document.getElementById('discoverPagesSearchInput');
        if (discoverPagesSearchInput) {
            discoverPagesSearchInput.addEventListener('input', () => {
                clearTimeout(this._debounceTimeout);
                this._debounceTimeout = setTimeout(() => this.filterDisplayedItems('discoverPagesList', 'noDiscoverablePages', 'discoverPagesSearchInput'), 300);
            });
        }

        // Search input listeners for Hidden tab (Users)
        const hiddenUsersSearchInput = document.getElementById('hiddenUsersSearchInput');
        if (hiddenUsersSearchInput) {
            hiddenUsersSearchInput.addEventListener('input', () => {
                clearTimeout(this._debounceTimeout);
                this._debounceTimeout = setTimeout(() => this.filterDisplayedItems('hiddenUsersList', 'noHiddenUsers', 'hiddenUsersSearchInput'), 300);
            });
        }

        // Search input listeners for Hidden tab (Pages)
        const hiddenPagesSearchInput = document.getElementById('hiddenPagesSearchInput');
        if (hiddenPagesSearchInput) {
            hiddenPagesSearchInput.addEventListener('input', () => {
                clearTimeout(this._debounceTimeout);
                this._debounceTimeout = setTimeout(() => this.filterDisplayedItems('hiddenPagesList', 'noHiddenPages', 'hiddenPagesSearchInput'), 300);
            });
        }

        // Search input listeners for Groups modal
        const discoverGroupsSearchInput = document.getElementById('discoverGroupsSearchInput');
        if (discoverGroupsSearchInput) {
            discoverGroupsSearchInput.addEventListener('input', () => {
                clearTimeout(this._debounceTimeout);
                this._debounceTimeout = setTimeout(() => this.filterDisplayedItems('discoverGroupsList', 'noDiscoverableGroups', 'discoverGroupsSearchInput'), 300);
            });
        }

        const hiddenGroupsSearchInput = document.getElementById('hiddenGroupsSearchInput');
        if (hiddenGroupsSearchInput) {
            hiddenGroupsSearchInput.addEventListener('input', () => {
                clearTimeout(this._debounceTimeout);
                this._debounceTimeout = setTimeout(() => this.filterDisplayedItems('hiddenGroupsList', 'noHiddenGroups', 'hiddenGroupsSearchInput'), 300);
            });
        }
    },

    // ===== USERS & PAGES MODAL =====
    
    openDiscoverUsersModal() {
        console.log('openDiscoverUsersModal called');
        
        // Reset to discover tab
        this.currentUsersTab = 'discover';
        
        // Open modal FIRST
        console.log('Opening modal');
        App.Modal.open('discoverUsersModal');
        
        // Wait for DOM to be ready, THEN set up and fetch
        setTimeout(() => {
            console.log('Modal opened, setting up');
            
            // Clear search inputs
            const inputs = ['discoverUsersSearchInput', 'discoverPagesSearchInput', 'hiddenUsersSearchInput', 'hiddenPagesSearchInput'];
            inputs.forEach(id => {
                const input = document.getElementById(id);
                if (input) input.value = '';
            });
            
            // DON'T clear lists here - App.Modal.open() does it
            // fetchAndDisplayUsers() will clear them again anyway
            
            // Hide all error/status messages
            const messages = ['noDiscoverableUsers', 'noDiscoverablePages', 'noHiddenUsers', 'noHiddenPages'];
            messages.forEach(id => {
                const msg = document.getElementById(id);
                if (msg) msg.style.display = 'none';
            });
            
            const errors = ['discoverUsersError', 'discoverPagesError', 'hiddenUsersError', 'hiddenPagesError'];
            errors.forEach(id => {
                const err = document.getElementById(id);
                if (err) err.style.display = 'none';
            });
            
            // Hide all loading indicators initially
            const loadingEls = ['discoverUsersLoading', 'discoverPagesLoading', 'hiddenUsersLoading', 'hiddenPagesLoading'];
            loadingEls.forEach(id => {
                const el = document.getElementById(id);
                if (el) el.style.display = 'none';
            });
            
            // Make sure we're on discover tab
            const discoverContent = document.getElementById('discoverUsersDiscoverContent');
            const hiddenContent = document.getElementById('discoverUsersHiddenContent');
            
            if (discoverContent) discoverContent.classList.remove('hidden');
            if (hiddenContent) hiddenContent.classList.add('hidden');
            
            // Update tab buttons
            const discoverBtn = document.getElementById('discoverUsersTabDiscover');
            const hiddenBtn = document.getElementById('discoverUsersTabHidden');
            
            if (discoverBtn) {
                discoverBtn.classList.add('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
                discoverBtn.classList.remove('border-transparent', 'secondary-text');
            }
            if (hiddenBtn) {
                hiddenBtn.classList.remove('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
                hiddenBtn.classList.add('border-transparent', 'secondary-text');
            }
            
            // Show loading for discover tab
            const usersLoading = document.getElementById('discoverUsersLoading');
            const pagesLoading = document.getElementById('discoverPagesLoading');
            
            if (usersLoading) usersLoading.style.display = 'block';
            if (pagesLoading) pagesLoading.style.display = 'block';
            
            // Fetch data - this will clear the lists
            console.log('About to call fetchAndDisplayUsers');
            this.fetchAndDisplayUsers();
        }, 50);
    },

    switchUsersTab(tab) {
        this.currentUsersTab = tab;
        
        // Update tab buttons
        const discoverBtn = document.getElementById('discoverUsersTabDiscover');
        const hiddenBtn = document.getElementById('discoverUsersTabHidden');
        const discoverContent = document.getElementById('discoverUsersDiscoverContent');
        const hiddenContent = document.getElementById('discoverUsersHiddenContent');
        
        // Check if elements exist
        if (!discoverBtn || !hiddenBtn || !discoverContent || !hiddenContent) {
            console.error('Tab elements not found');
            return;
        }
        
        if (tab === 'discover') {
            discoverBtn.classList.add('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            discoverBtn.classList.remove('border-transparent', 'secondary-text');
            hiddenBtn.classList.remove('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            hiddenBtn.classList.add('border-transparent', 'secondary-text');
            
            discoverContent.classList.remove('hidden');
            hiddenContent.classList.add('hidden');
            
            // If lists are empty, fetch data
            const usersList = document.getElementById('discoverUsersList');
            const pagesList = document.getElementById('discoverPagesList');
            if (usersList && usersList.children.length === 0 && pagesList && pagesList.children.length === 0) {
                this.fetchAndDisplayUsers();
            }
        } else {
            hiddenBtn.classList.add('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            hiddenBtn.classList.remove('border-transparent', 'secondary-text');
            discoverBtn.classList.remove('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            discoverBtn.classList.add('border-transparent', 'secondary-text');
            
            discoverContent.classList.add('hidden');
            hiddenContent.classList.remove('hidden');
            
            // If lists are empty, fetch data
            const hiddenUsersList = document.getElementById('hiddenUsersList');
            const hiddenPagesList = document.getElementById('hiddenPagesList');
            if (hiddenUsersList && hiddenUsersList.children.length === 0 && hiddenPagesList && hiddenPagesList.children.length === 0) {
                this.fetchAndDisplayHiddenUsers();
            }
        }
    },

    async fetchAndDisplayUsers() {
        console.log('fetchAndDisplayUsers called');
        const usersList = document.getElementById('discoverUsersList');
        const pagesList = document.getElementById('discoverPagesList');
        const usersLoading = document.getElementById('discoverUsersLoading');
        const pagesLoading = document.getElementById('discoverPagesLoading');
        const usersError = document.getElementById('discoverUsersError');
        const pagesError = document.getElementById('discoverPagesError');
        const noUsers = document.getElementById('noDiscoverableUsers');
        const noPages = document.getElementById('noDiscoverablePages');

        if (!usersList || !pagesList) {
            console.error('Lists not found:', { usersList, pagesList });
            return;
        }

        console.log('Showing loading indicators');
        // Show loading
        if (usersLoading) usersLoading.style.display = 'block';
        if (pagesLoading) pagesLoading.style.display = 'block';
        if (usersError) usersError.style.display = 'none';
        if (pagesError) pagesError.style.display = 'none';
        if (noUsers) noUsers.style.display = 'none';
        if (noPages) noPages.style.display = 'none';

        const loadingStartTime = Date.now();
        const MIN_LOADING_TIME = 300;

        try {
            const timestamp = Date.now();
            console.log('Fetching from /friends/get_discoverable_users');
            const response = await fetch(`/friends/get_discoverable_users?_=${timestamp}`, {
                cache: 'no-store'
            });

            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.error || `Server error: ${response.status}`);
            }
            const profiles = await response.json();
            console.log('Received profiles:', profiles.length);

            // Wait for minimum loading time
            const elapsedTime = Date.now() - loadingStartTime;
            const remainingTime = Math.max(0, MIN_LOADING_TIME - elapsedTime);
            await new Promise(resolve => setTimeout(resolve, remainingTime));

            // RE-GET the lists in case modal was recreated
            const freshUsersList = document.getElementById('discoverUsersList');
            const freshPagesList = document.getElementById('discoverPagesList');
            const freshUsersLoading = document.getElementById('discoverUsersLoading');
            const freshPagesLoading = document.getElementById('discoverPagesLoading');
            const freshNoUsers = document.getElementById('noDiscoverableUsers');
            const freshNoPages = document.getElementById('noDiscoverablePages');
            
            console.log('Re-fetched lists after API call:', { 
                freshUsersList, 
                freshPagesList,
                usersListSame: freshUsersList === usersList,
                pagesListSame: freshPagesList === pagesList 
            });

            if (!freshUsersList || !freshPagesList) {
                console.error('Lists disappeared after API call!');
                return;
            }

            // Clear lists and ensure they're visible
            console.log('Clearing lists');
            freshUsersList.innerHTML = '';
            freshPagesList.innerHTML = '';
            freshUsersList.style.display = 'block';
            freshPagesList.style.display = 'block';
            if (freshUsersLoading) freshUsersLoading.style.display = 'none';
            if (freshPagesLoading) freshPagesLoading.style.display = 'none';

            // Separate users and pages
            const users = profiles.filter(p => p.user_type === 'user' || p.user_type === 'admin');
            const pages = profiles.filter(p => p.user_type === 'public_page');

            console.log('Users:', users.length, 'Pages:', pages.length);

            if (users.length === 0) {
                if (freshNoUsers) {
                    freshNoUsers.style.display = 'block';
                    freshNoUsers.textContent = 'No new users to discover.';
                }
            } else {
                console.log('Rendering', users.length, 'users');
                users.forEach(profile => this.renderUserProfile(freshUsersList, profile, 'hide'));
            }

            if (pages.length === 0) {
                if (freshNoPages) {
                    freshNoPages.style.display = 'block';
                    freshNoPages.textContent = 'No new pages to discover.';
                }
            } else {
                console.log('Rendering', pages.length, 'pages');
                pages.forEach(profile => this.renderUserProfile(freshPagesList, profile, 'hide'));
            }

            console.log('Finished rendering. UsersList children:', freshUsersList.children.length, 'PagesList children:', freshPagesList.children.length);

        } catch (error) {
            console.error('Error fetching users:', error);
            const elapsedTime = Date.now() - loadingStartTime;
            const remainingTime = Math.max(0, MIN_LOADING_TIME - elapsedTime);
            await new Promise(resolve => setTimeout(resolve, remainingTime));
            
            if (usersLoading) usersLoading.style.display = 'none';
            if (pagesLoading) pagesLoading.style.display = 'none';
            if (usersError) {
                usersError.textContent = `Error: ${error.message}`;
                usersError.style.display = 'block';
            }
        }
    },

    async fetchAndDisplayHiddenUsers() {
        const hiddenUsersList = document.getElementById('hiddenUsersList');
        const hiddenPagesList = document.getElementById('hiddenPagesList');
        const usersLoading = document.getElementById('hiddenUsersLoading');
        const pagesLoading = document.getElementById('hiddenPagesLoading');
        const usersError = document.getElementById('hiddenUsersError');
        const pagesError = document.getElementById('hiddenPagesError');
        const noUsers = document.getElementById('noHiddenUsers');
        const noPages = document.getElementById('noHiddenPages');

        if (!hiddenUsersList || !hiddenPagesList) return;

        // Show loading
        if (usersLoading) usersLoading.style.display = 'block';
        if (pagesLoading) pagesLoading.style.display = 'block';
        if (usersError) usersError.style.display = 'none';
        if (pagesError) pagesError.style.display = 'none';
        if (noUsers) noUsers.style.display = 'none';
        if (noPages) noPages.style.display = 'none';

        try {
            const response = await fetch('/api/get_hidden_users', { cache: 'no-store' });
            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }
            const hiddenItems = await response.json();

            // Clear lists
            hiddenUsersList.innerHTML = '';
            hiddenPagesList.innerHTML = '';
            if (usersLoading) usersLoading.style.display = 'none';
            if (pagesLoading) pagesLoading.style.display = 'none';

            // Separate users and pages
            const users = hiddenItems.filter(p => p.user_type === 'user' || p.user_type === 'admin');
            const pages = hiddenItems.filter(p => p.user_type === 'public_page');

            if (users.length === 0) {
                if (noUsers) {
                    noUsers.style.display = 'block';
                    noUsers.textContent = 'No hidden users.';
                }
            } else {
                users.forEach(profile => this.renderUserProfile(hiddenUsersList, profile, 'unhide'));
            }

            if (pages.length === 0) {
                if (noPages) {
                    noPages.style.display = 'block';
                    noPages.textContent = 'No hidden pages.';
                }
            } else {
                pages.forEach(profile => this.renderUserProfile(hiddenPagesList, profile, 'unhide'));
            }

        } catch (error) {
            if (usersLoading) usersLoading.style.display = 'none';
            if (pagesLoading) pagesLoading.style.display = 'none';
            if (usersError) {
                usersError.textContent = `Error: ${error.message}`;
                usersError.style.display = 'block';
            }
        }
    },

    renderUserProfile(listElement, profile, actionType) {
        const protocol = window.location.protocol;
        let picUrl = '/static/images/default_avatar.png';
        if (profile.profile_picture_path) {
            picUrl = (profile.node_hostname && profile.node_hostname !== 'Local' && profile.node_hostname !== window.appConfig.localHostname)
                ? `${protocol}//${profile.node_hostname}/profile_pictures/${profile.profile_picture_path}`
                : `/profile_pictures/${profile.profile_picture_path}`;
        }

        const displayName = profile.display_name || profile.username;
        const escapedDisplayName = displayName.replace(/'/g, "\\'");
        const nodeNickname = profile.node_nickname || profile.node_hostname || 'Local';
        const hostname = profile.hostname || profile.node_hostname || '';

        const searchName = (profile.display_name || '').toLowerCase();
        const searchUsername = (profile.username || '').toLowerCase();
        const searchText = `${searchName} ${searchUsername}`;
        
        // Build profile URL
        let profileUrl = `/u/${profile.puid}`;
        if (profile.node_hostname && profile.node_hostname !== 'Local' && profile.node_hostname !== window.appConfig.localHostname) {
            profileUrl = `${protocol}//${profile.node_hostname}/u/${profile.puid}`;
        }

        // Type badge
        let typeTag = '';
        if (profile.user_type === 'public_page') {
            typeTag = '<span class="ml-2 text-xs bg-purple-500 text-white px-2 py-0.5 rounded-full">Page</span>';
        }

        // Primary action button (friend request or follow)
        let primaryActionButton = '';
        if (actionType === 'hide') {
            // In discover tab, show friend/follow button
            if (profile.user_type === 'public_page') {
                primaryActionButton = `<button class="bg-blue-500 text-white font-bold py-1 px-3 rounded-md text-sm hover:bg-blue-600 transition-colors" onclick="App.Discover.followProfile(this, '${profile.puid}', '${hostname}', '${escapedDisplayName}', '${profile.user_type}')">Follow</button>`;
            } else {
                primaryActionButton = `<button class="bg-green-500 text-white font-bold py-1 px-3 rounded-md text-sm hover:bg-green-600 transition-colors" onclick="App.Discover.sendFriendRequest(this, '${profile.puid}', '${hostname}', '${escapedDisplayName}')">Add Friend</button>`;
            }
        }

        // Hide/Unhide button
        let hideButton = '';
        if (actionType === 'hide') {
            hideButton = `
                <button class="text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 transition-colors p-2 ml-2" 
                        onclick="App.Discover.hideItem(this, 'user', ${profile.id}, '${escapedDisplayName}')"
                        title="Hide this ${profile.user_type === 'public_page' ? 'page' : 'user'}">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                    </svg>
                </button>`;
        } else if (actionType === 'unhide') {
            hideButton = `
                <button class="text-gray-500 hover:text-green-600 dark:text-gray-400 dark:hover:text-green-400 transition-colors p-2" 
                        onclick="App.Discover.unhideItem(this, 'user', ${profile.id}, '${escapedDisplayName}')"
                        title="Unhide this ${profile.user_type === 'public_page' ? 'page' : 'user'}">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                        <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                </button>`;
        }

 // Build bio text if available
        let bioHtml = '';
        if (profile.bio) {
            const bioText = profile.bio.length > 80 ? profile.bio.substring(0, 80) + '...' : profile.bio;
            bioHtml = `<p class="text-xs secondary-text mt-1 discover-bio">${bioText}</p>`;
        }

        listElement.insertAdjacentHTML('beforeend', `
            <div class="p-3 rounded-lg post-card discover-profile-card" data-puid="${profile.puid}" data-item-id="${profile.id}" data-search-text="${searchText.replace(/"/g, '&quot;')}" style="display: block;">
                <div class="flex items-start gap-3">
                    <a href="${profileUrl}" class="flex-shrink-0">
                        <img src="${picUrl}" alt="${displayName}" class="discover-avatar rounded-full object-cover" onerror="this.src='/static/images/default_avatar.png';">
                    </a>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <div class="flex items-center gap-2 flex-wrap">
                                    <a href="${profileUrl}" class="font-bold discover-name text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors">${displayName}</a>
                                    ${typeTag}
                                </div>
                                <p class="text-sm secondary-text discover-username">@${nodeNickname}</p>
                                ${bioHtml}
                            </div>
                            <div class="flex-shrink-0">
                                ${hideButton}
                            </div>
                        </div>
                        <div class="discover-action-button mt-3">
                            ${primaryActionButton}
                        </div>
                    </div>
                </div>
            </div>
        `);
    },

    // Legacy filterDisplayedUsers for backwards compatibility
    filterDisplayedUsers() {
        this.filterDisplayedItems('discoverUsersList', 'noDiscoverableUsers', 'discoverUsersSearchInput');
    },

    // ===== GROUPS MODAL =====
    
    openDiscoverGroupsModal() {
        console.log('openDiscoverGroupsModal called');
        
        // Reset to discover tab
        this.currentGroupsTab = 'discover';
        
        // Open modal FIRST
        console.log('Opening groups modal');
        App.Modal.open('discoverGroupsModal');
        
        // Wait for DOM to be ready, THEN set up and fetch
        setTimeout(() => {
            console.log('Groups modal opened, setting up');
            
            // DON'T clear lists here - App.Modal.open() does it
            // fetchGroups() will clear them again anyway
            
            // Clear search inputs
            const discoverSearchInput = document.getElementById('discoverGroupsSearchInput');
            const hiddenSearchInput = document.getElementById('hiddenGroupsSearchInput');
            if (discoverSearchInput) discoverSearchInput.value = '';
            if (hiddenSearchInput) hiddenSearchInput.value = '';
            
            // Hide all status messages
            const noDiscover = document.getElementById('noDiscoverableGroups');
            const noHidden = document.getElementById('noHiddenGroups');
            if (noDiscover) noDiscover.style.display = 'none';
            if (noHidden) noHidden.style.display = 'none';
            
            // Hide all errors
            const discoverError = document.getElementById('discoverGroupsError');
            const hiddenError = document.getElementById('hiddenGroupsError');
            if (discoverError) discoverError.style.display = 'none';
            if (hiddenError) hiddenError.style.display = 'none';
            
            // Hide all loading initially
            const discoverLoading = document.getElementById('discoverGroupsLoading');
            const hiddenLoading = document.getElementById('hiddenGroupsLoading');
            if (discoverLoading) discoverLoading.style.display = 'none';
            if (hiddenLoading) hiddenLoading.style.display = 'none';
            
            // Make sure we're on discover tab
            const discoverContent = document.getElementById('discoverGroupsDiscoverContent');
            const hiddenContent = document.getElementById('discoverGroupsHiddenContent');
            
            if (discoverContent) discoverContent.classList.remove('hidden');
            if (hiddenContent) hiddenContent.classList.add('hidden');
            
            // Update tab buttons
            const discoverBtn = document.getElementById('discoverGroupsTabDiscover');
            const hiddenBtn = document.getElementById('discoverGroupsTabHidden');
            
            if (discoverBtn) {
                discoverBtn.classList.add('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
                discoverBtn.classList.remove('border-transparent', 'secondary-text');
            }
            if (hiddenBtn) {
                hiddenBtn.classList.remove('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
                hiddenBtn.classList.add('border-transparent', 'secondary-text');
            }
            
            // Show loading
            const loading = document.getElementById('discoverGroupsLoading');
            if (loading) loading.style.display = 'block';
            
            // Fetch data - this will clear the lists
            console.log('About to call fetchGroups');
            this.fetchGroups();
        }, 50);
    },

    switchGroupsTab(tab) {
        this.currentGroupsTab = tab;
        
        // Update tab buttons
        const discoverBtn = document.getElementById('discoverGroupsTabDiscover');
        const hiddenBtn = document.getElementById('discoverGroupsTabHidden');
        const discoverContent = document.getElementById('discoverGroupsDiscoverContent');
        const hiddenContent = document.getElementById('discoverGroupsHiddenContent');
        
        // Check if elements exist
        if (!discoverBtn || !hiddenBtn || !discoverContent || !hiddenContent) {
            console.error('Tab elements not found');
            return;
        }
        
        if (tab === 'discover') {
            discoverBtn.classList.add('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            discoverBtn.classList.remove('border-transparent', 'secondary-text');
            hiddenBtn.classList.remove('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            hiddenBtn.classList.add('border-transparent', 'secondary-text');
            
            discoverContent.classList.remove('hidden');
            hiddenContent.classList.add('hidden');
            
            // If list is empty, fetch data
            const list = document.getElementById('discoverGroupsList');
            if (list && list.children.length === 0) {
                this.fetchGroups();
            }
        } else {
            hiddenBtn.classList.add('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            hiddenBtn.classList.remove('border-transparent', 'secondary-text');
            discoverBtn.classList.remove('border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            discoverBtn.classList.add('border-transparent', 'secondary-text');
            
            discoverContent.classList.add('hidden');
            hiddenContent.classList.remove('hidden');
            
            // If list is empty, fetch data
            const list = document.getElementById('hiddenGroupsList');
            if (list && list.children.length === 0) {
                this.fetchAndDisplayHiddenGroups();
            }
        }
    },

    // Legacy filterDisplayedGroups for backwards compatibility
    filterDisplayedGroups() {
        this.filterDisplayedItems('discoverGroupsList', 'noDiscoverableGroups', 'discoverGroupsSearchInput');
    },

    async fetchGroups() {
        const list = document.getElementById('discoverGroupsList');
        const loading = document.getElementById('discoverGroupsLoading');
        const errorEl = document.getElementById('discoverGroupsError');
        const noResults = document.getElementById('noDiscoverableGroups');

        if (!list || !loading || !errorEl || !noResults) {
            return;
        }

        loading.style.display = 'block';
        list.innerHTML = '';
        list.style.display = 'block';
        errorEl.style.display = 'none';
        noResults.style.display = 'none';

        try {
            const timestamp = Date.now();
            const response = await fetch(`/group/discover?_=${timestamp}`, {
                cache: 'no-store'
            });

            if (!response.ok) throw new Error((await response.json()).error || 'Server error');
            const groups = await response.json();

            loading.style.display = 'none';

            if (groups.length === 0) {
                noResults.style.display = 'block';
                noResults.textContent = 'No new groups to discover.';
            } else {
                const addedGroupPuids = new Set();
                groups.forEach(group => {
                    if (!group.puid || addedGroupPuids.has(group.puid)) return;
                    addedGroupPuids.add(group.puid);
                    this.renderGroupProfile(list, group, 'hide');
                });
            }
            
            setTimeout(() => {
                this.filterDisplayedGroups();
            }, 50);

        } catch (error) {
            loading.style.display = 'none';
            errorEl.textContent = `Error: ${error.message}`;
            errorEl.style.display = 'block';
        }
    },

    async fetchAndDisplayHiddenGroups() {
        const list = document.getElementById('hiddenGroupsList');
        const loading = document.getElementById('hiddenGroupsLoading');
        const errorEl = document.getElementById('hiddenGroupsError');
        const noResults = document.getElementById('noHiddenGroups');

        if (!list || !loading) return;

        if (errorEl) errorEl.style.display = 'none';
        if (noResults) noResults.style.display = 'none';
        loading.style.display = 'block';

        try {
            const response = await fetch('/api/get_hidden_groups', { cache: 'no-store' });
            if (!response.ok) {
                throw new Error(`Server error: ${response.status}`);
            }
            const groups = await response.json();

            list.innerHTML = '';
            loading.style.display = 'none';

            if (groups.length === 0) {
                if (noResults) {
                    noResults.style.display = 'block';
                    noResults.textContent = 'No hidden groups.';
                }
            } else {
                groups.forEach(group => this.renderGroupProfile(list, group, 'unhide'));
            }

        } catch (error) {
            loading.style.display = 'none';
            if (errorEl) {
                errorEl.textContent = `Error: ${error.message}`;
                errorEl.style.display = 'block';
            }
        }
    },

    renderGroupProfile(listElement, group, actionType) {
        const protocol = window.location.protocol;
        let picUrl = '/static/images/default_avatar.png';
        if (group.profile_picture_path) {
            picUrl = (group.node_hostname && group.node_hostname !== 'Local' && group.node_hostname !== window.appConfig.localHostname)
                ? `${protocol}//${group.node_hostname}/profile_pictures/${group.profile_picture_path}`
                : `/profile_pictures/${group.profile_picture_path}`;
        }
        
        const groupName = group.name || 'Unnamed Group';
        const escapedGroupName = groupName.replace(/'/g, "\\'");
        const description = group.description || '';
        const nodeNickname = group.node_nickname || group.node_hostname || 'Local';
        
        // Build group profile URL
        let groupProfileUrl = `/group/${group.puid}`;
        if (group.node_hostname && group.node_hostname !== 'Local' && group.node_hostname !== window.appConfig.localHostname) {
            groupProfileUrl = `${protocol}//${group.node_hostname}/group/${group.puid}`;
        }
        
        const searchName = (group.name || '').toLowerCase();
        const searchDesc = (group.description || '').toLowerCase();
        const searchText = `${searchName} ${searchDesc}`;

        // Primary action button (request to join)
        let primaryActionButton = '';
        if (actionType === 'hide') {
            const groupJson = JSON.stringify(group).replace(/'/g, "&apos;");
            primaryActionButton = `<button class="bg-cyan-500 text-white font-bold py-1 px-3 rounded-md text-sm hover:bg-cyan-600 transition-colors" onclick='App.Discover.sendGroupJoinRequest(this, ${groupJson})'>Request to Join</button>`;
        }

        // Hide/Unhide button
        let hideButton = '';
        if (actionType === 'hide') {
            hideButton = `
                <button class="text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400 transition-colors p-2 ml-2" 
                        onclick="App.Discover.hideItem(this, 'group', ${group.id}, '${escapedGroupName}')"
                        title="Hide this group">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M3.98 8.223A10.477 10.477 0 001.934 12C3.226 16.338 7.244 19.5 12 19.5c.993 0 1.953-.138 2.863-.395M6.228 6.228A10.45 10.45 0 0112 4.5c4.756 0 8.773 3.162 10.065 7.498a10.523 10.523 0 01-4.293 5.774M6.228 6.228L3 3m3.228 3.228l3.65 3.65m7.894 7.894L21 21m-3.228-3.228l-3.65-3.65m0 0a3 3 0 10-4.243-4.243m4.242 4.242L9.88 9.88" />
                    </svg>
                </button>`;
        } else if (actionType === 'unhide') {
            hideButton = `
                <button class="text-gray-500 hover:text-green-600 dark:text-gray-400 dark:hover:text-green-400 transition-colors p-2" 
                        onclick="App.Discover.unhideItem(this, 'group', ${group.id}, '${escapedGroupName}')"
                        title="Unhide this group">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-5 h-5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
                        <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                    </svg>
                </button>`;
        }

        // Build description text if available
        let descriptionHtml = '';
        if (group.description) {
            const descText = group.description.length > 100 ? group.description.substring(0, 100) + '...' : group.description;
            descriptionHtml = `<p class="text-xs secondary-text mt-1 discover-group-description">${descText}</p>`;
        }

        // Build member count display
        let memberCountHtml = '';
        if (group.member_count !== undefined && group.member_count !== null) {
            memberCountHtml = `<p class="text-xs secondary-text mt-1">
                <svg class="w-3 h-3 inline-block mr-1" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"/>
                </svg>
                ${group.member_count} member${group.member_count !== 1 ? 's' : ''}
            </p>`;
        }

        listElement.insertAdjacentHTML('beforeend', `
            <div class="p-3 rounded-lg post-card discover-group-card" data-puid="${group.puid}" data-item-id="${group.id}" data-search-text="${searchText.replace(/"/g, '&quot;')}" style="display: block;">
                <div class="flex items-start gap-3">
                    <a href="${groupProfileUrl}" class="flex-shrink-0">
                        <img src="${picUrl}" alt="${groupName}" class="discover-group-avatar rounded-full object-cover" onerror="this.src='/static/images/default_avatar.png';">
                    </a>
                    <div class="flex-1 min-w-0">
                        <div class="flex items-start justify-between gap-2">
                            <div class="flex-1 min-w-0">
                                <a href="${groupProfileUrl}" class="font-bold discover-group-name text-gray-900 dark:text-white hover:text-blue-600 dark:hover:text-blue-400 transition-colors block">${groupName}</a>
                                <p class="text-sm secondary-text discover-group-host">@${nodeNickname}</p>
                                ${memberCountHtml}
                                ${descriptionHtml}
                            </div>
                            <div class="flex-shrink-0">
                                ${hideButton}
                            </div>
                        </div>
                        <div class="discover-group-action-button mt-3">
                            ${primaryActionButton}
                        </div>
                    </div>
                </div>
            </div>
        `);
    },

    // ===== HIDE/UNHIDE FUNCTIONS =====
    
    async hideItem(button, itemType, itemId, itemName) {
        button.disabled = true;
        
        try {
            const response = await fetch('/api/hide_item', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    item_type: itemType,
                    item_id: itemId
                })
            });

            const result = await response.json();
            
            if (response.ok && result.status === 'success') {
                // Remove the item from the list
                const itemElement = button.closest('.post-card');
                if (itemElement) {
                    itemElement.remove();
                }
                
                // Refresh the appropriate filter
                if (itemType === 'group') {
                    this.filterDisplayedItems('discoverGroupsList', 'noDiscoverableGroups', 'discoverGroupsSearchInput');
                } else {
                    // For users/pages, check which list we're in
                    const listId = itemElement?.parentElement?.id;
                    if (listId === 'discoverUsersList') {
                        this.filterDisplayedItems('discoverUsersList', 'noDiscoverableUsers', 'discoverUsersSearchInput');
                    } else if (listId === 'discoverPagesList') {
                        this.filterDisplayedItems('discoverPagesList', 'noDiscoverablePages', 'discoverPagesSearchInput');
                    }
                }
                
                App.Modal.showInfo(`Hidden successfully`);
            } else {
                throw new Error(result.error || 'Failed to hide item');
            }
        } catch (error) {
            App.Modal.showInfo(`Error: ${error.message}`);
            button.disabled = false;
        }
    },

    async unhideItem(button, itemType, itemId, itemName) {
        button.disabled = true;
        
        try {
            const response = await fetch('/api/unhide_item', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    item_type: itemType,
                    item_id: itemId
                })
            });

            const result = await response.json();
            
            if (response.ok && result.status === 'success') {
                // Remove the item from the hidden list
                const itemElement = button.closest('.post-card');
                if (itemElement) {
                    itemElement.remove();
                }
                
                // Refresh the appropriate filter
                if (itemType === 'group') {
                    this.filterDisplayedItems('hiddenGroupsList', 'noHiddenGroups', 'hiddenGroupsSearchInput');
                } else {
                    // For users/pages, check which list we're in
                    const listId = itemElement?.parentElement?.id;
                    if (listId === 'hiddenUsersList') {
                        this.filterDisplayedItems('hiddenUsersList', 'noHiddenUsers', 'hiddenUsersSearchInput');
                    } else if (listId === 'hiddenPagesList') {
                        this.filterDisplayedItems('hiddenPagesList', 'noHiddenPages', 'hiddenPagesSearchInput');
                    }
                }
                
                App.Modal.showInfo(`Unhidden successfully`);
            } else {
                throw new Error(result.error || 'Failed to unhide item');
            }
        } catch (error) {
            App.Modal.showInfo(`Error: ${error.message}`);
            button.disabled = false;
        }
    },

    // ===== FILTERING =====
    
    filterDisplayedItems(listId, noResultsId, searchInputId) {
        const list = document.getElementById(listId);
        const noResults = document.getElementById(noResultsId);
        const searchInput = document.getElementById(searchInputId);
        
        if (!list || !noResults || !searchInput) return;

        const searchTerm = searchInput.value.trim().toLowerCase();
        let visibleCount = 0;
        const itemsToFilter = list.querySelectorAll('.post-card');

        itemsToFilter.forEach(item => {
            const searchText = item.dataset.searchText || '';
            if (!searchTerm || searchText.includes(searchTerm)) {
                item.style.display = 'flex';
                visibleCount++;
            } else {
                item.style.display = 'none';
            }
        });

        // Check if we're in a loading state
        const loadingEl = document.getElementById(listId.replace('List', 'Loading'));
        const isLoading = loadingEl && loadingEl.style.display !== 'none';
        const hasItemsInDOM = itemsToFilter.length > 0;

        if (!isLoading && visibleCount === 0) {
            noResults.style.display = 'block';
            if (hasItemsInDOM && searchTerm) {
                noResults.textContent = `No items found matching "${searchTerm}".`;
            } else {
                // Keep original "no items" text
                if (!noResults.textContent || noResults.textContent.includes('matching')) {
                    if (listId.includes('User')) {
                        noResults.textContent = listId.includes('hidden') ? 'No hidden users.' : 'No new users to discover.';
                    } else if (listId.includes('Page')) {
                        noResults.textContent = listId.includes('hidden') ? 'No hidden pages.' : 'No new pages to discover.';
                    } else if (listId.includes('Group')) {
                        noResults.textContent = listId.includes('hidden') ? 'No hidden groups.' : 'No new groups to discover.';
                    }
                }
            }
        } else {
            noResults.style.display = 'none';
        }
    },

    // Legacy methods (kept for compatibility with existing action buttons)
    async sendFriendRequest(button, puid, hostname, displayName) {
        const isRemote = hostname && hostname !== 'Local' && hostname !== window.appConfig.localHostname;
        const url = isRemote ? "/friends/send_remote_request" : `/friends/send_friend_request/${puid}`;
        const options = { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' } };
        if (isRemote) { options.body = JSON.stringify({ target_puid: puid, target_hostname: hostname, target_display_name: displayName }); }

        button.disabled = true;
        button.textContent = 'Sending...';

        try {
            const response = await fetch(url, options);
            const result = await response.json();
            if (response.ok && (result.status === 'success' || result.status === 'info')) {
                App.Modal.showInfo(result.message);
                const itemElement = button.closest('.post-card');
                if (itemElement) itemElement.remove();
                this.filterDisplayedUsers();
            } else {
                throw new Error(result.message || result.error || 'Unknown error');
            }
        } catch (error) {
            App.Modal.showInfo(`Error: ${error.message}`);
            if (document.body.contains(button)) {
                button.disabled = false;
                button.textContent = 'Add Friend';
            }
        }
    },

    async followProfile(button, puid, hostname, displayName, userType) {
        const isRemote = hostname && hostname !== 'Local' && hostname !== window.appConfig.localHostname;
        const url = isRemote ? "/follow_remote" : `/follow/${puid}`;
        const options = { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' } };
        if (isRemote) { options.body = JSON.stringify({ target_puid: puid, target_hostname: hostname, target_display_name: displayName, target_user_type: userType }); }

        button.disabled = true;
        button.textContent = 'Following...';
        try {
            const response = await fetch(url, options);
            const result = await response.json();
            if (response.ok && (result.status === 'success' || result.status === 'info')) {
                App.Modal.showInfo(result.message);
                const itemElement = button.closest('.post-card');
                if (itemElement) itemElement.remove();
                this.filterDisplayedUsers();
            } else {
                throw new Error(result.message || result.error || 'Unknown error');
            }
        } catch (error) {
            App.Modal.showInfo(`Error: ${error.message}`);
            if (document.body.contains(button)) {
                button.disabled = false;
                button.textContent = 'Follow';
            }
        }
    },

async sendGroupJoinRequest(button, groupData) {
        // Route to the Group module's function that checks for rules/questions
        await App.Group.sendJoinRequest(button, groupData);
    }
};

/**
 * @file modules/admin.js
 * @description Contains UI logic for modals in the admin panel.
 * Populates the App.Admin namespace.
 */
App.Admin = {
    openSetMediaPathModal(username, currentMediaPath, currentUploadsPath) {
        document.getElementById('setMediaPathUsername').textContent = username;
        document.getElementById('setMediaPathTargetUsername').value = username;
        document.getElementById('media_path').value = currentMediaPath || '';
        document.getElementById('uploads_path').value = currentUploadsPath || '';
        App.Modal.open('setMediaPathModal');
    },

    async submitSetMediaPathForm() {
        const username = document.getElementById('setMediaPathTargetUsername').value;
        const mediaPath = document.getElementById('media_path').value;
        const uploadsPath = document.getElementById('uploads_path').value;

        try {
            const response = await fetch(`/admin/set_user_media_path/${username}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ 
                    'media_path': mediaPath, 
                    'uploads_path': uploadsPath 
                })
            });
            const result = await response.json();
            if (response.ok) {
                App.Modal.close('setMediaPathModal');
                App.Utils.flashMessage(result.message, 'success', () => window.location.reload());
            } else {
                App.Utils.flashMessage(result.error || 'Failed to update media paths.', 'danger');
            }
        } catch (error) {
            console.error('Error:', error);
            App.Utils.flashMessage('An unexpected error occurred.', 'danger');
        }
    },

    openResetPasswordModal(username) {
        document.getElementById('resetPasswordUsername').textContent = username;
        document.getElementById('resetPasswordTargetUsername').value = username;
        document.getElementById('new_password').value = '';
        App.Modal.open('resetPasswordModal');
    },

    async submitResetPasswordForm() {
        const username = document.getElementById('resetPasswordTargetUsername').value;
        const newPassword = document.getElementById('new_password').value;
        const confirmPassword = document.getElementById('confirm_new_password').value;

        // Check if passwords match
        if (newPassword !== confirmPassword) {
            App.Utils.flashMessage('Passwords do not match.', 'danger');
            return;
        }

        try {
            const response = await fetch(`/admin/reset_password/${username}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: new URLSearchParams({ 'new_password': newPassword })
            });
            const result = await response.json();
            if (response.ok) {
                App.Utils.flashMessage(result.message, 'success');
                App.Modal.close('resetPasswordModal');
                // Clear the form fields
                document.getElementById('new_password').value = '';
                document.getElementById('confirm_new_password').value = '';
            } else {
                App.Utils.flashMessage(result.error || 'Failed to reset password.', 'danger');
            }
        } catch (error) {
            console.error('Error:', error);
            App.Utils.flashMessage('An unexpected error occurred.', 'danger');
        }
    },
    
    openChangeUsernameModal(username) {
        document.getElementById('changeUsernameCurrent').textContent = username;
        document.getElementById('changeUsernameTarget').value = username;
        document.getElementById('new_username_input').value = username;
        App.Modal.open('changeUsernameModal');
    },

    async submitChangeUsernameForm() {
        const username = document.getElementById('changeUsernameTarget').value;
        const newUsername = document.getElementById('new_username_input').value;

        try {
            const response = await fetch(`/admin/change_username/${username}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    'new_username': newUsername
                })
            });
            const result = await response.json();
            if (response.ok) {
                App.Modal.close('changeUsernameModal');
                App.Utils.flashMessage(result.message, 'success', () => {
                    window.location.reload();
                });
            } else {
                App.Utils.flashMessage(result.error || 'Failed to change username.', 'danger');
            }
        } catch (error) {
            console.error('Error:', error);
            App.Utils.flashMessage('An unexpected error occurred.', 'danger');
        }
    },

    async openParentalControlsModal(userId, username) {
        document.getElementById('pcUsername').textContent = username;
        document.getElementById('pcUserId').value = userId;
        document.getElementById('pcMessage').classList.add('hidden');
        
        
        try {
            // Fetch current parental control settings
            const response = await fetch(`/admin/get_parental_controls/${userId}`);
            const data = await response.json();
            
            if (response.ok) {
                // Display age if available
                const ageSpan = document.getElementById('pcUserAge');
                if (data.age !== null && data.age !== undefined) {
                    ageSpan.textContent = `(Age: ${data.age})`;
                } else {
                    ageSpan.textContent = '(Age: Unknown)';
                }
                // Update status display based on whether parents are assigned
                const hasParents = data.parents && data.parents.length > 0;
                const statusContainer = document.getElementById('pcStatusContainer');
                const statusIcon = document.getElementById('pcStatusIcon');
                const statusText = document.getElementById('pcStatusText');
                const statusDescription = document.getElementById('pcStatusDescription');
                
                if (hasParents) {
                    // Active status
                    statusContainer.className = 'mb-6 p-4 rounded-lg bg-green-50 border border-green-200';
                    statusIcon.innerHTML = `
                        <svg class="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                    `;
                    statusText.textContent = 'Active';
                    statusText.className = 'text-green-700 font-semibold';
                    statusDescription.textContent = 'Parental controls are active. Remote interactions require parent approval.';
                } else {
                    // Disabled status
                    statusContainer.className = 'mb-6 p-4 rounded-lg bg-gray-50 border border-gray-200';
                    statusIcon.innerHTML = `
                        <svg class="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                        </svg>
                    `;
                    statusText.textContent = 'Disabled';
                    statusText.className = 'text-gray-600 font-semibold';
                    statusDescription.textContent = 'No parents assigned. Assign a parent to enable parental controls.';
                }
                
                // Populate current parents
                const currentParentsDiv = document.getElementById('pcCurrentParents');
                if (data.parents && data.parents.length > 0) {
                    currentParentsDiv.innerHTML = data.parents.map(parent => `
                        <div class="flex items-center justify-between p-3 bg-white border border-gray-200 rounded-lg">
                            <div class="flex items-center gap-2">
                                <svg class="w-5 h-5 text-blue-500" fill="currentColor" viewBox="0 0 20 20">
                                    <path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"/>
                                </svg>
                                <span class="font-medium">${parent.display_name || parent.username}</span>
                            </div>
                            <button type="button" onclick="removeParentFromChild(${userId}, ${parent.parent_user_id})" 
                                    class="text-red-500 hover:text-red-700">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                </svg>
                            </button>
                        </div>
                    `).join('');
                } else {
                    currentParentsDiv.innerHTML = '<p class="text-sm text-gray-500 italic">No parents assigned</p>';
                }
                
                // Populate available parents dropdown
                const parentSelect = document.getElementById('pcParentSelect');
                parentSelect.innerHTML = '<option value="">-- Select a user --</option>';
                if (data.available_parents) {
                    data.available_parents.forEach(user => {
                        parentSelect.innerHTML += `<option value="${user.id}">${user.display_name || user.username}</option>`;
                    });
                }
                
                App.Modal.open('parentalControlsModal');
            } else {
                throw new Error(data.error || 'Failed to load parental controls');
            }
        } catch (error) {
            console.error('Error loading parental controls:', error);
            App.Modal.showInfo(`Error: ${error.message}`);
        }
    }
};


async function addParentToChild() {
    const userId = document.getElementById('pcUserId').value;
    const parentId = document.getElementById('pcParentSelect').value;
    const messageDiv = document.getElementById('pcMessage');
    
    if (!parentId) {
        messageDiv.textContent = 'Please select a parent to add';
        messageDiv.className = 'mb-4 p-3 rounded-lg bg-yellow-100 text-yellow-800';
        messageDiv.classList.remove('hidden');
        return;
    }
    
    try {
        const response = await fetch(`/admin/add_parent_to_child`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                child_user_id: parseInt(userId),
                parent_user_id: parseInt(parentId)
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            // Reload the modal to show updated parents
            const username = document.getElementById('pcUsername').textContent;
            App.Admin.openParentalControlsModal(userId, username);
            
            messageDiv.textContent = result.message || 'Parent added successfully!';
            messageDiv.className = 'mb-4 p-3 rounded-lg bg-green-100 text-green-800';
            messageDiv.classList.remove('hidden');
        } else {
            throw new Error(result.error || 'Failed to add parent');
        }
    } catch (error) {
        messageDiv.textContent = `Error: ${error.message}`;
        messageDiv.className = 'mb-4 p-3 rounded-lg bg-red-100 text-red-800';
        messageDiv.classList.remove('hidden');
    }
}

async function removeParentFromChild(childUserId, parentUserId) {
    const messageDiv = document.getElementById('pcMessage');
    
    App.Modal.showConfirm('Remove this parent assignment?', async () => {
        try {
            const response = await fetch(`/admin/remove_parent_from_child`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    child_user_id: parseInt(childUserId),
                    parent_user_id: parseInt(parentUserId)
                })
            });
            
            const result = await response.json();
            
            if (response.ok) {
                // Reload the modal
                const username = document.getElementById('pcUsername').textContent;
                App.Admin.openParentalControlsModal(childUserId, username);
                
                messageDiv.textContent = result.message || 'Parent removed successfully!';
                messageDiv.className = 'mb-4 p-3 rounded-lg bg-green-100 text-green-800';
                messageDiv.classList.remove('hidden');
            } else {
                throw new Error(result.error || 'Failed to remove parent');
            }
        } catch (error) {
            messageDiv.textContent = `Error: ${error.message}`;
            messageDiv.className = 'mb-4 p-3 rounded-lg bg-red-100 text-red-800';
            messageDiv.classList.remove('hidden');
        }
    });
};

/**
 * @file modules/actions.js
 * @description Contains handlers for common user actions like follow/unfollow.
 * Populates the App.Actions namespace.
 */
App.Actions = {
    async followPage(buttonElement, puid) {
        buttonElement.disabled = true;
        buttonElement.textContent = 'Following...';
        try {
            const response = await fetch(`/follow/${puid}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.message || 'An unknown error occurred.');

            const container = document.getElementById('follow-unfollow-container');
            if (container) {
                container.innerHTML = `<button type="button" onclick="App.Actions.unfollowPage(this, '${puid}')" class="bg-gray-500 hover:bg-gray-600 text-white font-semibold py-2 px-6 rounded-full text-sm">Unfollow</button>`;
            }
            App.Modal.showInfo(result.message);
        } catch (error) {
            App.Modal.showInfo(`Error: ${error.message}`);
            buttonElement.disabled = false;
            buttonElement.textContent = 'Follow';
        }
    },

    async unfollowPage(buttonElement, puid) {
        App.Modal.showConfirm('Are you sure you want to unfollow this page?', async () => {
            buttonElement.disabled = true;
            buttonElement.textContent = 'Unfollowing...';
            try {
                const response = await fetch(`/unfollow/${puid}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.message || 'An unknown error occurred.');

                const container = document.getElementById('follow-unfollow-container');
                if (container) {
                    container.innerHTML = `<button type="button" onclick="App.Actions.followPage(this, '${puid}')" class="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded-full text-sm">Follow</button>`;
                }
                App.Modal.showInfo(result.message);
            } catch (error) {
                App.Modal.showInfo(`Error: ${error.message}`);
                buttonElement.disabled = false;
                buttonElement.textContent = 'Unfollow';
            }
        });
    },

    async unfollowPageFromList(buttonElement, puid) {
        App.Modal.showConfirm('Are you sure you want to unfollow this page?', async () => {
            buttonElement.disabled = true;
            buttonElement.textContent = 'Unfollowing...';
            try {
                const response = await fetch(`/unfollow/${puid}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }
                });
                const result = await response.json();
                if (!response.ok) throw new Error(result.message || 'An unknown error occurred.');

                const listItem = document.getElementById(`followed-page-${puid}`);
                if (listItem) {
                    listItem.style.transition = 'opacity 0.5s ease';
                    listItem.style.opacity = '0';
                    setTimeout(() => listItem.remove(), 500);
                }
                App.Modal.showInfo(result.message);
            } catch (error) {
                App.Modal.showInfo(`Error: ${error.message}`);
                buttonElement.disabled = false;
                buttonElement.textContent = 'Unfollow';
            }
        });
    }
};



/**
 * @file modules/notifications.js
 * @description Manages the notification bell and modal.
 * Populates the App.Notifications namespace.
 */
App.Notifications = {
    init() {
        const bell = document.getElementById('notification-bell-button');
        const markAll = document.getElementById('mark-all-read-button');

        if(bell) bell.addEventListener('click', () => this.openModal());
        if(markAll) markAll.addEventListener('click', () => this.markAllAsRead());
    },

    async openModal() {
        const list = document.getElementById('notification-list');
        const loading = document.getElementById('notification-loading');
        
        App.Modal.open('notificationModal');
        loading.style.display = 'block';
        list.innerHTML = '';
        list.appendChild(loading);

        try {
            const response = await fetch('/notifications');
            if (!response.ok) throw new Error('Failed to fetch notifications');
            const notifications = await response.json();
            
            loading.style.display = 'none';

            if (notifications.length === 0) {
                list.innerHTML = '<p class="text-center secondary-text p-4">You have no notifications.</p>';
            } else {
                notifications.forEach(n => {
                    const item = document.createElement('div');
                    item.className = 'notification-item';
                    if (!n.is_read) item.classList.add('unread');
                    item.dataset.notificationId = n.id;
                    item.dataset.url = n.url;
                    
                    const pic = `<img src="${n.actor_profile_picture_url}" alt="Profile Picture" class="w-10 h-10 rounded-full object-cover" onerror="this.src='/static/images/default_avatar.png';">`;
                    item.innerHTML = `
                        ${pic}
                        <div class="notification-item-content">
                            <p class="text-sm primary-text">${n.text}</p>
                            <p class="text-xs secondary-text mt-1"><span class="utc-timestamp" data-timestamp="${n.timestamp}">${new Date(n.timestamp + ' UTC').toLocaleString()}</span></p>
                        </div>
                    `;
                    item.addEventListener('click', (e) => this.handleClick(e));
                    list.appendChild(item);
                });
                App.Utils.convertAllUTCTimestamps();
            }
        } catch (error) {
            console.error('Failed to fetch notifications:', error);
            loading.style.display = 'none';
            list.innerHTML = '<p class="text-center text-red-500 p-4">Could not load notifications.</p>';
        }
    },

    async handleClick(event) {
        const item = event.currentTarget;
        const { notificationId, url } = item.dataset;
        if (!url) return;

        try {
            await fetch(`/notifications/mark_read/${notificationId}`, { method: 'POST' });
            
            // Update badge count
            const badge = document.getElementById('notification-badge');
            if (badge) {
                const currentCount = parseInt(badge.textContent) || 0;
                if (currentCount > 1) {
                    badge.textContent = currentCount - 1;
                } else {
                    badge.remove();
                }
            }
        } catch (error) {
            console.error('Failed to mark notification as read:', error);
        } finally {
            window.location.href = url;
        }
    },

    async markAllAsRead() {
        try {
            await fetch('/notifications/mark_all_read', { method: 'POST' });
            document.querySelectorAll('.notification-item.unread').forEach(item => item.classList.remove('unread'));
            const badge = document.getElementById('notification-badge');
            if (badge) badge.style.display = 'none';
            
            // Reset polling timestamp so we don't show old notifications again
            if (App.NotificationPolling) {
                App.NotificationPolling.lastCheckTimestamp = new Date().toISOString();
            }
            
            App.Modal.close('notificationModal');
        } catch (error) {
            App.Modal.showInfo('Could not mark all notifications as read.');
        }
    }
};



/**
 * @file modules/notification_polling.js
 * @description Polls for new notifications and updates the UI in real-time
 * Populates the App.NotificationPolling namespace.
 */
App.NotificationPolling = {
    pollInterval: 15000, // Poll every 15 seconds
    pollTimer: null,
    lastCheckTimestamp: null,
    isPolling: false,

    /**
     * Initialize the notification polling system
     */
    init() {
        // Set initial timestamp to now
        this.lastCheckTimestamp = new Date().toISOString();
        
        // Start polling
        this.startPolling();
        
        // Stop polling when page is hidden to save resources
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.stopPolling();
            } else {
                // Restart polling and check immediately when page becomes visible again
                this.lastCheckTimestamp = new Date().toISOString();
                this.startPolling();
                this.checkForNewNotifications();
            }
        });
    },

    /**
     * Start the polling timer
     */
    startPolling() {
        if (this.isPolling) return;
        
        this.isPolling = true;
        this.pollTimer = setInterval(() => {
            this.checkForNewNotifications();
        }, this.pollInterval);
        
        console.log('Notification polling started');
    },

    /**
     * Stop the polling timer
     */
    stopPolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        this.isPolling = false;
        console.log('Notification polling stopped');
    },

    /**
     * Check for new notifications since last check
     */
    async checkForNewNotifications() {
        try {
            const response = await fetch(`/notifications/check_new?since_timestamp=${encodeURIComponent(this.lastCheckTimestamp)}`);
            
            if (!response.ok) {
                console.error('Failed to check for new notifications');
                return;
            }

            const data = await response.json();
            
            // Update the unread count badge
            this.updateBadge(data.unread_count);
            
            // Show toast notifications for new notifications
            if (data.new_notifications && data.new_notifications.length > 0) {
                data.new_notifications.forEach(notification => {
                    this.showNotificationToast(notification);
                });
                
                // Update timestamp to now after processing new notifications
                this.lastCheckTimestamp = new Date().toISOString();
            }
        } catch (error) {
            console.error('Error checking for new notifications:', error);
        }
    },

    /**
     * Update the notification badge with the unread count
     */
    updateBadge(count) {
        const badge = document.getElementById('notification-badge');
        
        if (count > 0) {
            if (badge) {
                // Update existing badge
                badge.textContent = count;
            } else {
                // Create badge if it doesn't exist
                const bell = document.getElementById('notification-bell-button');
                if (bell) {
                    const newBadge = document.createElement('span');
                    newBadge.id = 'notification-badge';
                    newBadge.className = 'notification-badge';
                    newBadge.textContent = count;
                    bell.appendChild(newBadge);
                }
            }
        } else {
            // Remove badge if count is 0
            if (badge) {
                badge.remove();
            }
        }
    },

    /**
     * Show a toast notification for a new notification
     */

    showNotificationToast(notification) {
        // Don't use App.Toast.show with HTML - create toast directly
        const container = document.getElementById('toast-container');
        if (!container) return;

        // Create toast element
        const toast = document.createElement('div');
        toast.className = 'toast info';
        toast.setAttribute('role', 'alert');
        toast.style.cursor = 'pointer';
        
        // Build the toast content
        toast.innerHTML = `
            <div class="toast-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
                </svg>
            </div>
            <div class="toast-content">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <img src="${notification.actor_profile_picture_url}" 
                        alt="Profile Picture" 
                        style="width: 40px; height: 40px; border-radius: 50%; object-fit: cover;"
                        onerror="this.src='/static/images/default_avatar.png';">
                    <div>
                        <div class="toast-message">${notification.text}</div>
                        <div style="font-size: 12px; opacity: 0.7; margin-top: 4px;">Just now</div>
                    </div>
                </div>
            </div>
            <div class="toast-close">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
                    <path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/>
                </svg>
            </div>
        `;
        
        // Add click handler to navigate to notification URL
        toast.addEventListener('click', (e) => {
            // Don't navigate if clicking the close button
            if (e.target.closest('.toast-close')) {
                return;
            }
            window.location.href = notification.url;
        });
        
        // Add close button handler
        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            toast.classList.add('removing');
            setTimeout(() => toast.remove(), 300);
        });
        
        // Add to container
        container.appendChild(toast);
        
        // Auto-remove after 8 seconds
        setTimeout(() => {
            if (toast.parentElement) {
                toast.classList.add('removing');
                setTimeout(() => toast.remove(), 300);
            }
        }, 8000);
    }
};

/**
 * @file modules/settings.js
 * @description Handles the main settings modal, including display, account, and notification settings.
 * Populates the App.Settings namespace.
 */
App.Settings = {
    init() {
        // Add event listeners for accordion functionality
        document.querySelectorAll('.settings-accordion-button').forEach(button => {
            button.addEventListener('click', () => {
                button.classList.toggle('active');
                const panel = button.nextElementSibling;
                panel.style.display = panel.style.display === 'block' ? 'none' : 'block';
                const icon = button.querySelector('.accordion-icon');
                if (icon) icon.style.transform = panel.style.display === 'block' ? 'rotate(180deg)' : 'rotate(0deg)';
            });
        });

        // Add event listeners to the save buttons
        const saveDisplayButton = document.getElementById('saveDisplaySettingsBtn');
        if (saveDisplayButton) saveDisplayButton.addEventListener('click', () => this.save());

        const saveNotificationsButton = document.getElementById('saveNotificationSettingsBtn');
        if (saveNotificationsButton) saveNotificationsButton.addEventListener('click', () => this.save());
        
        const saveAccountButton = document.getElementById('saveAccountSettingsBtn');
        if(saveAccountButton) saveAccountButton.addEventListener('click', () => this.saveAccount());

        const logoutAllButton = document.getElementById('logoutAllSessionsBtn');
        if(logoutAllButton) logoutAllButton.addEventListener('click', () => this.Sessions.logoutAll());
    },

    openModal() {
        const { userSettings } = window.appConfig;
        if (!userSettings) return;

        // --- Populate Display Settings ---
        const textSizeSlider = document.getElementById('textSizeSlider');
        const textSizeValue = document.getElementById('textSizeValue');
        const themeToggle = document.getElementById('themeToggle');
        const timezoneSelector = document.getElementById('timezoneSelector');

        if (textSizeSlider && textSizeValue) {
            // Use text_size (snake_case) to match what's saved, with textSize fallback
            const currentTextSize = userSettings.text_size || userSettings.textSize || 100;
            textSizeSlider.value = currentTextSize;
            textSizeValue.textContent = `${textSizeSlider.value}%`;
            textSizeSlider.oninput = () => {
                const newSize = textSizeSlider.value;
                textSizeValue.textContent = `${newSize}%`;
                document.documentElement.style.fontSize = `${newSize}%`; // Live preview
            };
        }
        if (themeToggle) themeToggle.checked = userSettings.theme === 'dark';
        if (timezoneSelector) timezoneSelector.value = userSettings.timezone;

        // --- Populate Notification Settings ---
        const userEmailInput = document.getElementById('userEmailAddress');
        const enableNotificationsToggle = document.getElementById('emailNotificationsEnabled');
        const specificNotificationsDiv = document.getElementById('specificEmailNotifications');

        if (userEmailInput) userEmailInput.value = userSettings.user_email_address || '';
        
        if (enableNotificationsToggle) {
            // BUG FIX: Check for boolean `true`, not the string 'True'
            enableNotificationsToggle.checked = userSettings.email_notifications_enabled === true;

            const toggleSubSettings = () => {
                const isEnabled = enableNotificationsToggle.checked;
                if (specificNotificationsDiv) {
                    specificNotificationsDiv.style.opacity = isEnabled ? '1' : '0.5';
                    specificNotificationsDiv.querySelectorAll('input').forEach(input => input.disabled = !isEnabled);
                }
            };
            enableNotificationsToggle.onchange = toggleSubSettings;
            toggleSubSettings(); // Set initial state
        }
        
        const notificationKeys = {
            'emailOnFriendRequest': 'email_on_friend_request',
            'emailOnFriendAccept': 'email_on_friend_accept',
            'emailOnWallPost': 'email_on_wall_post',
            'emailOnMention': 'email_on_mention',
            'emailOnEventInvite': 'email_on_event_invite',
            'emailOnEventUpdate': 'email_on_event_update',
            'emailOnMediaTag': 'email_on_media_tag',
            'emailOnPostTag': 'email_on_post_tag',
            'emailOnMediaMention': 'email_on_media_mention',
            'emailOnParentalApproval': 'email_on_parental_approval'
        };

        for (const [elementId, settingKey] of Object.entries(notificationKeys)) {
            const toggle = document.getElementById(elementId);
            if (toggle) {
                // BUG FIX: Check for boolean `true`, not the string 'True'
                toggle.checked = userSettings[settingKey] === true;
            }
        }

        this.Sessions.fetch();
        App.Modal.open('settingsModal');

        // Load 2FA status
        this.TwoFactor.loadStatus();
    },

    validatePassword(password) {
        // Password requirements
        const minLength = 12;
        const hasUppercase = /[A-Z]/.test(password);
        const hasLowercase = /[a-z]/.test(password);
        const hasNumber = /\d/.test(password);
        const hasSpecial = /[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]/.test(password);
        
        if (!password) {
            return { valid: false, error: 'Password is required.' };
        }
        
        if (password.length < minLength) {
            return { valid: false, error: `Password must be at least ${minLength} characters long.` };
        }
        
        if (!hasUppercase) {
            return { valid: false, error: 'Password must contain at least one uppercase letter (A-Z).' };
        }
        
        if (!hasLowercase) {
            return { valid: false, error: 'Password must contain at least one lowercase letter (a-z).' };
        }
        
        if (!hasNumber) {
            return { valid: false, error: 'Password must contain at least one number (0-9).' };
        }
        
        if (!hasSpecial) {
            return { valid: false, error: 'Password must contain at least one special character (!@#$%^&*()_+-=[]{}|;:,.<>?).' };
        }
        
        return { valid: true, error: null };
    },

    async save() {
        const settingsPayload = {
            'text_size': document.getElementById('textSizeSlider').value,
            'timezone': document.getElementById('timezoneSelector').value,
            'theme': document.getElementById('themeToggle').checked ? 'dark' : 'light',
            'user_email_address': document.getElementById('userEmailAddress').value,
            'email_notifications_enabled': document.getElementById('emailNotificationsEnabled').checked,
            'email_on_friend_request': document.getElementById('emailOnFriendRequest').checked,
            'email_on_friend_accept': document.getElementById('emailOnFriendAccept').checked,
            'email_on_wall_post': document.getElementById('emailOnWallPost').checked,
            'email_on_mention': document.getElementById('emailOnMention').checked,
            'email_on_event_invite': document.getElementById('emailOnEventInvite').checked,
            'email_on_event_update': document.getElementById('emailOnEventUpdate').checked,
            'email_on_media_tag': document.getElementById('emailOnMediaTag').checked,
            'email_on_post_tag': document.getElementById('emailOnPostTag').checked,
            'email_on_media_mention': document.getElementById('emailOnMediaMention').checked,
            'email_on_parental_approval': document.getElementById('emailOnParentalApproval')?.checked || false
        };

        try {
            const response = await fetch(window.appConfig.saveSettingsUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settingsPayload)
            });
            const result = await response.json();

            if (response.ok) {
                // Update the in-memory config with the correct data types
                window.appConfig.userSettings.text_size = settingsPayload.text_size;
                window.appConfig.userSettings.timezone = settingsPayload.timezone;
                window.appConfig.userSettings.theme = settingsPayload.theme;
                window.appConfig.userSettings.user_email_address = settingsPayload.user_email_address;
                window.appConfig.userSettings.email_notifications_enabled = settingsPayload.email_notifications_enabled;
                window.appConfig.userSettings.email_on_friend_request = settingsPayload.email_on_friend_request;
                window.appConfig.userSettings.email_on_friend_accept = settingsPayload.email_on_friend_accept;
                window.appConfig.userSettings.email_on_wall_post = settingsPayload.email_on_wall_post;
                window.appConfig.userSettings.email_on_mention = settingsPayload.email_on_mention;
                window.appConfig.userSettings.email_on_event_invite = settingsPayload.email_on_event_invite;
                window.appConfig.userSettings.email_on_event_update = settingsPayload.email_on_event_update;
                window.appConfig.userSettings.email_on_media_tag = settingsPayload.email_on_media_tag;
                window.appConfig.userSettings.email_on_media_mention = settingsPayload.email_on_media_mention;
                window.appConfig.userSettings.email_on_post_tag = settingsPayload.email_on_post_tag;
                window.appConfig.userSettings.email_on_parental_approval = settingsPayload.email_on_parental_approval;


                // Apply visual changes immediately
                document.documentElement.style.fontSize = `${window.appConfig.userSettings.text_size}%`;
                document.documentElement.classList.toggle('dark', window.appConfig.userSettings.theme === 'dark');
                App.Utils.convertAllUTCTimestamps();
                
                App.Modal.showInfo('Settings saved successfully!');
            } else {
                throw new Error(result.error || 'Failed to save settings.');
            }
        } catch (error) {
            console.error('Error saving settings:', error);
            App.Modal.showInfo(`Error: ${error.message}`);
            // Revert visual changes on failure
            document.documentElement.style.fontSize = `${window.appConfig.userSettings.text_size}%`;
        }
    },
    
    async saveAccount() {
        const form = document.getElementById('accountSettingsForm');
        const messageDiv = document.getElementById('accountSettingsMessage');
        if (!form || !messageDiv) return;

        const formData = new FormData(form);
        const payload = Object.fromEntries(formData.entries());

        messageDiv.classList.add('hidden'); 

        // Validate password if provided
        if (payload.password) {
            const validation = this.validatePassword(payload.password);
            if (!validation.valid) {
                messageDiv.textContent = validation.error;
                messageDiv.className = 'flash-message flash-danger';
                messageDiv.classList.remove('hidden');
                return;
            }
            
            if (payload.password !== payload.confirm_password) {
                messageDiv.textContent = 'New passwords do not match.';
                messageDiv.className = 'flash-message flash-danger';
                messageDiv.classList.remove('hidden');
                return;
            }
        }

        try {
            const response = await fetch(window.appConfig.saveAccountSettingsUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            
            if (response.ok && result.relogin) {
                // Password or username changed - show modal before logout
                App.Modal.showInfo(
                    'Account settings updated successfully! You will be logged out and need to log in again with your new credentials.',
                    () => {
                        window.location.href = window.appConfig.logoutUrl;
                    }
                );
            } else if (response.ok) {
                // Other settings changed - show success and reload
                messageDiv.textContent = result.message || 'Settings updated successfully!';
                messageDiv.className = 'flash-message flash-success';
                messageDiv.classList.remove('hidden');
                setTimeout(() => location.reload(), 2000);
            } else {
                // Error occurred
                messageDiv.textContent = result.error || 'Failed to update settings.';
                messageDiv.className = 'flash-message flash-danger';
                messageDiv.classList.remove('hidden');
            }
        } catch (error) {
            console.error('Error saving account settings:', error);
            messageDiv.textContent = 'An unexpected network error occurred.';
            messageDiv.className = 'flash-message flash-danger';
        }
    },

    Sessions: {
        async fetch() {
            const listContainer = document.getElementById('activeSessionsList');
            if (!listContainer || !window.appConfig.getSessionsUrl) return;
            listContainer.innerHTML = '<p class="secondary-text">Loading sessions...</p>';

            try {
                const response = await fetch(window.appConfig.getSessionsUrl);
                if (!response.ok) throw new Error((await response.json()).error || 'Failed to fetch');
                const sessions = await response.json();

                listContainer.innerHTML = '';
                if (sessions.length === 0) {
                    listContainer.innerHTML = '<p class="secondary-text">No active sessions found.</p>';
                    return;
                }
                sessions.forEach(session => listContainer.insertAdjacentHTML('beforeend', this._renderSession(session)));
                App.Utils.convertAllUTCTimestamps();
            } catch (error) {
                console.error('Error fetching sessions:', error);
                listContainer.innerHTML = `<p class="text-red-500">${error.message}</p>`;
            }
        },

        async logout(sessionId) {
            App.Modal.showConfirm('Are you sure you want to log out this session?', async () => {
                try {
                    const url = window.appConfig.logoutSessionUrlBase.replace('DUMMY_ID', sessionId);
                    const response = await fetch(url, { method: 'POST' });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.error);
                    
                    App.Modal.showInfo(result.message);
                    if (result.logout_self) {
                        window.location.href = window.appConfig.logoutUrl;
                    } else {
                        this.fetch();
                    }
                } catch (error) {
                    App.Modal.showInfo(`Error: ${error.message}`);
                }
            });
        },

        async logoutAll() {
            App.Modal.showConfirm('Are you sure you want to log out all other sessions?', async () => {
                try {
                    const response = await fetch(window.appConfig.logoutAllSessionsUrl, { method: 'POST' });
                    const result = await response.json();
                    if (!response.ok) throw new Error(result.error);

                    App.Modal.showInfo(result.message);
                    this.fetch();
                } catch (error) {
                    App.Modal.showInfo(`Error: ${error.message}`);
                }
            });
        },

        _renderSession(session) {
            const { os, browser } = this._parseUserAgent(session.user_agent);
            const icon = this._getDeviceIcon(os);
            const controls = session.is_current
                ? `<span class="text-xs bg-green-200 text-green-800 px-2 py-1 rounded-full font-medium">Current</span>`
                : `<button onclick="App.Settings.Sessions.logout('${session.session_id}')" class="bg-red-500 hover:bg-red-600 text-white font-semibold py-1 px-3 rounded-lg text-xs transition-colors duration-200" aria-label="Log out session">
                     <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path></svg>
                   </button>`;

            return `
                <div class="flex items-center justify-between p-3 rounded-lg border post-card">
                    <div class="flex items-center gap-3">
                        ${icon}
                        <div>
                            <p class="text-sm font-semibold primary-text">${os} &middot; ${browser}</p>
                            <p class="text-xs secondary-text">Last Seen: <span class="utc-timestamp" data-timestamp="${session.last_seen}">${session.last_seen}</span></p>
                        </div>
                    </div>
                    ${controls}
                </div>`;
        },

        _parseUserAgent(ua) {
            if (!ua) return { os: 'Unknown', browser: 'Device' };
            let os = 'Unknown', browser = 'Device';
            if (/Windows/i.test(ua)) os = 'Windows';
            else if (/Macintosh|Mac OS X/i.test(ua)) os = 'macOS';
            else if (/Android/i.test(ua)) os = 'Android';
            else if (/Linux/i.test(ua)) os = 'Linux';
            else if (/iPhone|iPad|iPod/i.test(ua)) os = 'iOS';
            if (/Chrome/i.test(ua) && !/Chromium/i.test(ua)) browser = 'Chrome';
            else if (/Firefox/i.test(ua)) browser = 'Firefox';
            else if (/Safari/i.test(ua) && !/Chrome/i.test(ua)) browser = 'Safari';
            else if (/MSIE|Trident/i.test(ua)) browser = 'IE';
            else if (/Edge/i.test(ua)) browser = 'Edge';
            return { os, browser };
        },

        _getDeviceIcon(os) {
            const icons = {
                'Windows': '<svg class="w-6 h-6 text-gray-600" fill="currentColor" viewBox="0 0 24 24"><path d="M3,12V3H12V12H3M12,21H3V12H12V21M21,12V3H12V12H21M21,21H12V12H21V21Z" /></svg>',
                'macOS': '<svg class="w-6 h-6 text-gray-600" fill="currentColor" viewBox="0 0 24 24"><path d="M20.94,13.2A6.76,6.76,0,0,0,19,12.42C19,12.42,18.95,12.42,18.95,12.42A6.4,6.4,0,0,0,14.22,8.1C13.13,7,11.5,6.5,10.2,6.5A4.6,4.6,0,0,0,5.8,11.23C3.6,11.5,2,13.44,2,15.65A4.14,4.14,0,0,0,6.18,19.8L10,19.8C10.5,20.5,11.2,21,12,21A2,2,0,0,0,14,19C14,17.89,13.1,17,12,17C10.9,17,10,17.9,10,19H6.18A2.14,2.14,0,0,1,4,16.85C4,15.4,5,14.2,6.3,14C6.4,11.3,8,9.5,10.2,9.5C11.2,9.5,12,10,12.5,10.61A4.4,4.4,0,0,1,16.8,13.8C16.85,13.8,16.9,13.8,16.9,13.8A4.13,4.13,0,0,1,21,17.94C21,18,21,18.05,21,18.1L23,18.1C23,17.8,23,17.5,23,17.21A4.27,4.27,0,0,0,20.94,13.2Z" /></svg>',
                'Android': '<svg class="w-6 h-6 text-gray-600" fill="currentColor" viewBox="0 0 24 24"><path d="M15,6H14V4H10V6H9A1,1,0,0,0,8,7V17A1,1,0,0,0,9,18H15A1,1,0,0,0,16,17V7A1,1,0,0,0,15,6M12,16A2,2,0,0,1,10,14A2,2,0,0,1,12,12A2,2,0,0,1,14,14A2,2,0,0,1,12,16M14.5,9H9.5A0.5,0.5,0,0,1,9,8.5A0.5,0.5,0,0,1,9.5,8H14.5A0.5,0.5,0,0,1,15,8.5A0.5,0.5,0,0,1,14.5,9Z" /></svg>',
                'Linux': '<svg class="w-6 h-6 text-gray-600" fill="currentColor" viewBox="0 0 24 24"><path d="M12.4,3.62C12.25,3.5,12.12,3.38,12,3.25C11.88,3.38,11.75,3.5,11.6,3.62C11.27,4,11.07,4.42,11,4.87C11,5.33,11.12,5.73,11.35,6.07C11.5,6.31,11.7,6.5,11.95,6.65C12.2,6.79,12.47,6.88,12.75,6.88H13C13.22,6.88,13.43,6.83,13.62,6.75C14.12,6.53,14.5,6.12,14.65,5.62C14.72,5.33,14.75,5.03,14.75,4.75C14.75,4.22,14.59,3.75,14.28,3.38C14,3,13.62,2.72,13.13,2.56C12.75,2.44,12.38,2.38,12,2.38C11.62,2.38,11.25,2.44,10.87,2.56C10.38,2.72,10,3,9.72,3.38C9.41,3.75,9.25,4.22,9.25,4.75C9.25,5.03,9.28,5.33,9.35,5.62C9.5,6.12,9.88,6.53,10.38,6.75C10.57,6.83,10.78,6.88,11,6.88H11.25C11.53,6.88,11.8,6.79,12.05,6.65C12.3,6.5,12.5,6.31,12.65,6.07C12.88,5.73,13,5.33,13,4.87C13,4.42,12.73,4,12.4,3.62M12,7.12C10.22,7.12,8.75,8.59,8.75,10.38V12.62C8.75,14.41,10.22,15.88,12,15.88C13.78,15.88,15.25,14.41,15.25,12.62V10.38C15.25,8.59,13.78,7.12,12,7.12M12,14.38C11.03,14.38,10.25,13.59,10.25,12.62V10.38C10.25,9.41,11.03,8.62,12,8.62C12.97,8.62,13.75,9.41,13.75,10.38V12.62C13.75,13.59,12.97,14.38,12,14.38M12,21.62C7.2,21.62,3.25,17.67,3.25,12.88C3.25,8.59,6.5,5.12,10.88,4.5V2.38H13.12V4.5C17.5,5.12,20.75,8.59,20.75,12.88C20.75,17.67,16.8,21.62,12,21.62Z" /></svg>',
                'iOS': '<svg class="w-6 h-6 text-gray-600" fill="currentColor" viewBox="0 0 24 24"><path d="M15.5,13.5C15.5,14.9,16.6,16,18,16C19.4,16,20.5,14.9,20.5,13.5C20.5,12.1,19.4,11,18,11C16.6,11,15.5,12.1,15.5,13.5M12,2C15.9,2,19,5.1,19,9C19,12.4,16.5,15.4,13.3,16.6C12.9,18,11.6,19,10,19C8.4,19,7.1,18,6.7,16.6C3.5,15.4,1,12.4,1,9C1,5.1,4.1,2,8,2C8.8,2,9.5,2.1,10.2,2.3C10.7,2.1,11.3,2,12,2M12,4C11.5,4,11.1,4,10.7,4.1C10.8,4.1,10.9,4.1,11,4.1C11.3,4.1,11.5,4.1,11.7,4.2C11.5,4.3,11.3,4.4,11.1,4.5C10.1,5.1,9.4,6,9.1,7C9,7.3,9,7.7,9,8C9,8.7,9.2,9.4,9.5,10C9.8,10.6,10.2,11.2,10.8,11.6C11.4,12,12,12.3,12.7,12.4C13,12.4,13.2,12.4,13.5,12.4C14.5,12.4,15.5,12,16.2,11.2C16.9,10.5,17.3,9.5,17.3,8.5C17.3,7.9,17.2,7.3,16.9,6.8C16.7,6.3,16.3,5.8,15.8,5.4C15.4,5.1,14.9,4.8,14.3,4.6C13.8,4.4,13.2,4.3,12.6,4.3C12.4,4.3,12.2,4.3,12,4Z" /></svg>'
            };
            return icons[os] || '<svg class="w-6 h-6 text-gray-600" fill="currentColor" viewBox="0 0 24 24"><path d="M19,11.5A2.5,2.5,0,0,1,16.5,14A2.5,2.5,0,0,1,14,11.5A2.5,2.5,0,0,1,16.5,9A2.5,2.5,0,0,1,19,11.5M19,18H14A2,2,0,0,1,12,16V5A2,2,0,0,1,14,3H19A2,2,0,0,1,21,5V16A2,2,0,0,1,19,18M9,18H4A2,2,0,0,1,2,16V5A2,2,0,0,1,4,3H9A2,2,0,0,1,11,5V16A2,2,0,0,1,9,18Z" /></svg>';
        }
    },

    TwoFactor: {
        currentBackupCodes: [],
        
        async loadStatus() {
            const container = document.getElementById('twofa-status-container');
            if (!container) return;
            
            try {
                const response = await fetch('/settings/2fa/status');
                if (!response.ok) throw new Error('Failed to load 2FA status');
                
                const data = await response.json();
                const isEnabled = data.enabled || false;
                
                container.innerHTML = isEnabled 
                    ? this._renderEnabled() 
                    : this._renderDisabled();
            } catch (error) {
                console.error('Error loading 2FA status:', error);
                container.innerHTML = `
                    <p class="text-red-500 text-sm">Failed to load 2FA status. Please refresh the page.</p>
                `;
            }
        },
        
        _renderEnabled() {
            return `
                <div class="bg-green-50 dark:bg-green-900 border border-green-200 dark:border-green-700 rounded p-4 mb-4">
                    <p class="text-sm text-green-800 dark:text-green-200 font-semibold flex items-center">
                        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                        </svg>
                        Two-factor authentication is enabled
                    </p>
                </div>
                <button type="button" onclick="App.Settings.TwoFactor.openManageModal()" 
                        class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg">
                    Manage 2FA Settings
                </button>
            `;
        },
        
        _renderDisabled() {
            return `
                <p class="secondary-text mb-4">
                    Protect your account with two-factor authentication using an authenticator app.
                </p>
                <button type="button" onclick="App.Settings.TwoFactor.openSetupModal()" 
                        class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg">
                    Enable 2FA
                </button>
            `;
        },
        
        openSetupModal() {
            openModal('setup2faModal');
            // Reset to step 1
            document.getElementById('setup2fa-step1').classList.remove('hidden');
            document.getElementById('setup2fa-step2').classList.add('hidden');
            document.getElementById('setup2fa-step3').classList.add('hidden');
            document.getElementById('setup2fa-password').value = '';
        },
        
        openManageModal() {
            openModal('manage2faModal');
        }
    }
};



/**
 * @file modules/events.js
 * @description Handles logic for the events feature, including the profile picture cropper.
 * Populates the App.Events namespace.
 */
App.Events = {
    _discoverDebounceTimeout: null, // Debounce timer for discover search
    _pastEventsDebounceTimeout: null, // NEW: Debounce timer for past events search
    _eventPostSearchTimeout: null, // NEW: Debounce timer for event wall search

    // Cropper object for the event profile picture
    Cropper: {
        _cropperInstance: null,
        _originalPath: '',

        init() {
            const fileInput = document.getElementById('event_picture_file_input');
            const openBtn = document.getElementById('openEventCropperButton');
            const applyBtn = document.getElementById('applyCropButton');
            const cancelBtn = document.getElementById('cancelCropButton');
            const cropperModal = document.getElementById('cropperModal');

            if (fileInput) fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
            if (openBtn) openBtn.addEventListener('click', () => this.open());
            if (applyBtn) applyBtn.addEventListener('click', () => this.apply());
            if (cancelBtn) cancelBtn.addEventListener('click', () => this.close());
            if (cropperModal) cropperModal.querySelector('.close-button').addEventListener('click', () => this.close());
        },

        handleFileSelect(event) {
            this._originalPath = '';
            const originalPathInput = document.getElementById('original_image_path_from_browser');
            if(originalPathInput) originalPathInput.value = '';

            const openBtn = document.getElementById('openEventCropperButton');
            if (event.target.files && event.target.files[0]) {
                if (openBtn) openBtn.disabled = false;
                this.open(); // Directly open cropper when a file is selected
            } else {
                if (openBtn) openBtn.disabled = true;
            }
        },

        open() {
            const fileInput = document.getElementById('event_picture_file_input');
            if (fileInput && fileInput.files && fileInput.files[0]) {
                const reader = new FileReader();
                reader.onload = (e) => this._initInstance(e.target.result);
                reader.readAsDataURL(fileInput.files[0]);
            } else if (this._originalPath) {
                // Ensure appConfig and necessary properties exist before constructing URL
                if (window.appConfig && window.appConfig.serveMediaBaseUrl && window.appConfig.loggedInUserPuid) {
                    const imageUrl = `${window.appConfig.serveMediaBaseUrl}${window.appConfig.loggedInUserPuid}/${this._originalPath}`;
                    this._initInstance(imageUrl);
                } else {
                     console.error("Cannot open cropper: appConfig or required properties missing.");
                     App.Modal.showInfo('Error: Application configuration is missing.');
                }
            } else {
                if (App.Modal && App.Modal.showInfo) {
                    App.Modal.showInfo('Please select an image file first.');
                }
            }
        },

        _initInstance(imageUrl) {
            if (this._cropperInstance) this._cropperInstance.destroy();
            const imageEl = document.getElementById('imageToCrop');
            if (!imageEl) return;

            imageEl.src = imageUrl;
            imageEl.onload = () => {
                App.Modal.open('cropperModal');
                this._cropperInstance = new Cropper(imageEl, {
                    aspectRatio: 1, viewMode: 2, dragMode: 'move',
                    cropBoxMovable: true, cropBoxResizable: false,
                    toggleDragModeOnDblclick: false, autoCropArea: 0.8
                });
            };
            imageEl.onerror = () => App.Modal.showInfo('Failed to load image for adjustment.');
        },

        apply() {
            if (!this._cropperInstance) return;
            const canvas = this._cropperInstance.getCroppedCanvas({ width: 400, height: 400 });
            if (!canvas) {
                App.Modal.showInfo('Failed to crop image.');
                this.close();
                return;
            }
            document.getElementById('cropped_image_data').value = canvas.toDataURL('image/png');
            if (this._originalPath) {
                document.getElementById('original_image_path_from_browser').value = this._originalPath;
            }
            this.close();
            const form = document.getElementById('eventPictureUploadForm');
            if(form) form.submit();
        },

        close() {
            App.Modal.close('cropperModal');
            if (this._cropperInstance) {
                this._cropperInstance.destroy();
                this._cropperInstance = null;
            }
        },

        updateFromBrowser(selectedPath) {
            if (!selectedPath) {
                App.Modal.showInfo('Please select a picture.');
                return;
            }
            this._originalPath = selectedPath;
            const fileInput = document.getElementById('event_picture_file_input');
            if(fileInput) fileInput.value = ''; // Clear file input if selecting from browser
            const openBtn = document.getElementById('openEventCropperButton');
            if (openBtn) openBtn.disabled = false;
            this.open(); // Open cropper with the selected media path
        }
    },

    init() {
        // Init cropper if the necessary elements exist (on event profile page)
        if (document.getElementById('eventPictureUploadForm')) {
            this.Cropper.init();
        }

        // Shim for media browser to correctly call this cropper instance
        // It expects App.Profile.Cropper.updateFromBrowser, so we create a pointer.
        App.Profile = App.Profile || {};
        App.Profile.Cropper = App.Profile.Cropper || {};
        App.Profile.Cropper.updateFromBrowser = (selectedPath) => {
             // Check if we are potentially trying to update the *event* picture
            if (document.getElementById('eventPictureUploadForm') && this.Cropper && typeof this.Cropper.updateFromBrowser === 'function') {
                this.Cropper.updateFromBrowser(selectedPath);
            }
            // Add similar check if *user* profile picture cropper exists on the page
            else if (document.getElementById('profilePictureUploadForm') && App.Profile.Cropper && typeof App.Profile.Cropper.updateFromBrowser === 'function') {
                 // Call the *actual* profile cropper's function if it's defined elsewhere
                 // This assumes App.Profile.Cropper is populated by profile.js when needed
                 if (App.Profile.Cropper.updateFromBrowser !== this.Cropper.updateFromBrowser) {
                      App.Profile.Cropper.updateFromBrowser(selectedPath);
                 }
            }
        };

        // Check if we are on the events home page (by checking for the tab container)
        // This init() is now called by the router *after* the content is loaded.
        if (document.getElementById('tab-content')) {
            this.switchTab('my_upcoming'); // Default to 'My Upcoming'

            // Bind listeners for the search bars on the 'Discover' and 'Past' tabs
            const discoverSearchInput = document.getElementById('discoverEventsSearchInput');
            if (discoverSearchInput) {
                discoverSearchInput.addEventListener('input', () => {
                    clearTimeout(this._discoverDebounceTimeout);
                    this._discoverDebounceTimeout = setTimeout(() => this.filterDiscoverEvents(), 300);
                });
            }
            
            const pastSearchInput = document.getElementById('pastEventsSearchInput');
            if (pastSearchInput) {
                pastSearchInput.addEventListener('input', () => {
                    clearTimeout(this._pastEventsDebounceTimeout);
                    this._pastEventsDebounceTimeout = setTimeout(() => this.filterPastEvents(), 300);
                });
            }
        }

        // NEW: Check if we are on an event profile page (with post search)
        const eventPostSearchInput = document.getElementById('eventPostSearchInput');
        if (eventPostSearchInput) {
            eventPostSearchInput.addEventListener('input', () => {
                clearTimeout(this._eventPostSearchTimeout);
                this._eventPostSearchTimeout = setTimeout(() => this.filterEventPosts(), 300);
            });
        }
    },

    switchTab(tabId) {
        document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.add('hidden'));
        document.querySelectorAll('.tab-button').forEach(button => button.classList.remove('active'));

        const contentPane = document.getElementById(`${tabId}-content`);
        if (contentPane) {
            contentPane.classList.remove('hidden');
        } else {
            console.warn(`Content pane for tab ${tabId} not found.`);
        }

        const button = document.querySelector(`[onclick="App.Events.switchTab('${tabId}')"]`);
        if (button) {
            button.classList.add('active');
        } else {
             console.warn(`Button for tab ${tabId} not found.`);
        }

        // --- MODIFICATION: Attach listeners when tab is switched ---
        if (tabId === 'discover_public') {
            const discoverSearchInput = document.getElementById('discoverEventsSearchInput');
            if (discoverSearchInput) {
                // Clear previous listener to avoid duplicates if any
                discoverSearchInput.oninput = null; 
                discoverSearchInput.oninput = () => {
                    clearTimeout(this._discoverDebounceTimeout);
                    this._discoverDebounceTimeout = setTimeout(() => this.filterDiscoverEvents(), 300);
                };
            }
            
            // Check if it has already been loaded or is loading
            if (contentPane && !contentPane.dataset.loaded) {
                this.loadDiscoverEvents(contentPane);
            }
        } else if (tabId === 'past') {
            const pastSearchInput = document.getElementById('pastEventsSearchInput');
            if (pastSearchInput) {
                // Clear previous listener to avoid duplicates
                pastSearchInput.oninput = null; 
                pastSearchInput.oninput = () => {
                    clearTimeout(this._pastEventsDebounceTimeout);
                    this._pastEventsDebounceTimeout = setTimeout(() => this.filterPastEvents(), 300);
                };
            } else {
                console.warn("Could not find 'pastEventsSearchInput' on switching to tab.");
            }
        }
    },

    // Function to fetch and render discoverable public events
    async loadDiscoverEvents(contentPane) {
        // NEW: Clear search input on load/reload
        const searchInput = document.getElementById('discoverEventsSearchInput');
        if (searchInput) searchInput.value = '';

        contentPane.dataset.loaded = 'loading'; // Mark as loading
        contentPane.innerHTML = '<p class="text-center secondary-text py-8">Discovering public events from connected nodes...</p>';

        try {
            // --- THIS IS THE FIX ---
            // Fetch from the new API endpoint instead of the main page
            const response = await fetch('/events/api/page/discover_public');
            // --- END FIX ---
            
            if (!response.ok) {
                 const errorText = await response.text();
                 console.error("Fetch error:", response.status, errorText);
                throw new Error(`Failed to fetch event data. Status: ${response.status}`);
            }

            // We expect the full HTML page, so we parse it
            const htmlString = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(htmlString, 'text/html');

            // Find the discover_public content from the fetched page
            // This works because the API route renders the _my_events_content.html partial
            const discoverContent = doc.getElementById('discover_public-content');

            // Check if the original page actually had discoverable events
            const initialNoEventsMsg = doc.getElementById('no-discoverable-events-initial');

            if (!discoverContent || (initialNoEventsMsg && !discoverContent.querySelector('.event-card-item'))) {
                contentPane.innerHTML = '<p class="text-center secondary-text py-8">There are no public events to discover right now.</p>';
                // Ensure search input is added even if no events initially
                if (searchInput) {
                    contentPane.prepend(searchInput.parentElement); // Move the search bar div
                }
            } else {
                // Replace the loading message with the actual content (which includes the search bar)
                contentPane.innerHTML = discoverContent.innerHTML;
                // Re-run timestamp conversion for the new content
                if (App.Utils && typeof App.Utils.convertAllUTCTimestamps === 'function') {
                    App.Utils.convertAllUTCTimestamps();
                }
                 // Re-add event listener after replacing innerHTML
                const newSearchInput = document.getElementById('discoverEventsSearchInput');
                if (newSearchInput) {
                    // MODIFICATION: Use oninput for consistency
                    newSearchInput.oninput = null;
                    newSearchInput.oninput = () => {
                        clearTimeout(this._discoverDebounceTimeout);
                        this._discoverDebounceTimeout = setTimeout(() => this.filterDiscoverEvents(), 300);
                    };
                }
            }
            contentPane.dataset.loaded = 'true'; // Mark as successfully loaded

            // Run initial filter after loading
            this.filterDiscoverEvents();

        } catch (error) {
            console.error('Error loading discoverable events:', error);
            contentPane.innerHTML = `<p class="text-center text-red-500 py-8">Could not load discoverable events: ${error.message}. Please try again later.</p>`;
            // Ensure search input is still present on error
            if (searchInput) {
                 contentPane.prepend(searchInput.parentElement);
            }
            delete contentPane.dataset.loaded; // Allow retry on next click
        }
    },

    // NEW: Function to filter displayed discoverable events
    filterDiscoverEvents() {
        const contentPane = document.getElementById('discover_public-content');
        const searchInput = document.getElementById('discoverEventsSearchInput');
        const noResultsMsg = document.getElementById('noDiscoverResultsMessage');
        const initialNoEventsMsg = document.getElementById('no-discoverable-events-initial'); // The original message if no events were loaded

        if (!contentPane || !searchInput || !noResultsMsg) {
            console.warn("filterDiscoverEvents: Missing required elements.");
            return;
        }

        const searchTerm = searchInput.value.trim().toLowerCase();
        let visibleCount = 0;
        // Select the direct children .space-y-4 divs containing event cards, skipping the search bar div
        const eventLists = contentPane.querySelectorAll(':scope > div.space-y-4');
        const allEventCards = contentPane.querySelectorAll('.event-card-item'); // Get all cards for easier counting

        // Hide year/month headers initially
        contentPane.querySelectorAll('h2, h3').forEach(header => header.style.display = 'none');

        eventLists.forEach(list => {
            let listHasVisibleItems = false;
            list.querySelectorAll('.event-card-item').forEach(item => {
                const searchText = item.dataset.searchText || '';
                if (!searchTerm || searchText.includes(searchTerm)) {
                    item.style.display = 'flex';
                    visibleCount++;
                    listHasVisibleItems = true;
                } else {
                    item.style.display = 'none';
                }
            });

            // Show month header if its list has visible items
            const monthHeader = list.previousElementSibling;
            if (listHasVisibleItems && monthHeader && monthHeader.tagName === 'H3') {
                monthHeader.style.display = 'block';
                // Show year header if its month header is visible
                const yearHeader = monthHeader.previousElementSibling;
                if (yearHeader && yearHeader.tagName === 'H2') {
                    yearHeader.style.display = 'block';
                } else {
                    // Find the preceding H2 if there are multiple H3s under one H2
                     let currentElement = monthHeader.previousElementSibling;
                     while (currentElement) {
                         if (currentElement.tagName === 'H2') {
                             currentElement.style.display = 'block';
                             break;
                         }
                         currentElement = currentElement.previousElementSibling;
                     }
                }
            }
        });

        const isLoading = contentPane.dataset.loaded === 'loading';
        const hasAnyEvents = allEventCards.length > 0;

        // Handle visibility of "no results" messages
        if (initialNoEventsMsg) {
            initialNoEventsMsg.style.display = 'none'; // Always hide initial message after first load/filter
        }

        if (!isLoading) {
            if (visibleCount === 0 && searchTerm) {
                noResultsMsg.textContent = `No events found matching "${searchTerm}".`;
                noResultsMsg.style.display = 'block';
            } else if (visibleCount === 0 && !searchTerm && !hasAnyEvents) {
                // Show the *initial* no events message if search is clear and there were no events to begin with
                if(initialNoEventsMsg) initialNoEventsMsg.style.display = 'block';
                noResultsMsg.style.display = 'none';
            }
             else {
                noResultsMsg.style.display = 'none';
            }
        } else {
            noResultsMsg.style.display = 'none'; // Hide while loading
        }
    },

    // NEW: Function to filter displayed past events
    filterPastEvents() {
        const contentPane = document.getElementById('past-content');
        const searchInput = document.getElementById('pastEventsSearchInput');
        const noResultsMsg = document.getElementById('noPastResultsMessage');
        const initialNoEventsMsg = document.getElementById('no-past-events-initial'); // The original message if no events were loaded

        if (!contentPane || !searchInput || !noResultsMsg) {
            console.warn("filterPastEvents: Missing required elements.");
            return;
        }

        const searchTerm = searchInput.value.trim().toLowerCase();
        let visibleCount = 0;
        // Select the direct children .space-y-4 divs containing event cards, skipping the search bar div
        const eventLists = contentPane.querySelectorAll(':scope > div.space-y-4');
        const allEventCards = contentPane.querySelectorAll('.event-card-item'); // Get all cards for easier counting

        // Hide year/month headers initially
        contentPane.querySelectorAll('h2, h3').forEach(header => header.style.display = 'none');

        eventLists.forEach(list => {
            let listHasVisibleItems = false;
            list.querySelectorAll('.event-card-item').forEach(item => {
                const searchText = item.dataset.searchText || '';
                if (!searchTerm || searchText.includes(searchTerm)) {
                    item.style.display = 'flex';
                    visibleCount++;
                    listHasVisibleItems = true;
                } else {
                    item.style.display = 'none';
                }
            });

            // Show month header if its list has visible items
            const monthHeader = list.previousElementSibling;
            if (listHasVisibleItems && monthHeader && monthHeader.tagName === 'H3') {
                monthHeader.style.display = 'block';
                // Show year header if its month header is visible
                const yearHeader = monthHeader.previousElementSibling;
                if (yearHeader && yearHeader.tagName === 'H2') {
                    yearHeader.style.display = 'block';
                } else {
                    // Find the preceding H2 if there are multiple H3s under one H2
                     let currentElement = monthHeader.previousElementSibling;
                     while (currentElement) {
                         if (currentElement.tagName === 'H2') {
                             currentElement.style.display = 'block';
                             break;
                         }
                         currentElement = currentElement.previousElementSibling;
                     }
                }
            }
        });
        
        const hasAnyEvents = allEventCards.length > 0;

        // Handle visibility of "no results" messages
        if (initialNoEventsMsg) {
            initialNoEventsMsg.style.display = 'none'; // Always hide initial message after first load/filter
        }

        if (visibleCount === 0 && searchTerm) {
            noResultsMsg.textContent = `No past events found matching "${searchTerm}".`;
            noResultsMsg.style.display = 'block';
        } else if (visibleCount === 0 && !searchTerm && !hasAnyEvents) {
            // Show the *initial* no events message if search is clear and there were no events to begin with
            if(initialNoEventsMsg) initialNoEventsMsg.style.display = 'block';
            noResultsMsg.style.display = 'none';
        }
         else {
            noResultsMsg.style.display = 'none';
        }
    },

    // NEW: Function to filter posts on the event wall
    filterEventPosts() {
        const searchInput = document.getElementById('eventPostSearchInput');
        const searchTerm = searchInput.value.trim().toLowerCase();

        const listContainer = document.getElementById('event-posts-list-container');
        const noResultsMsg = document.getElementById('noEventPostResultsMessage');
        const initialNoPostsMsg = document.getElementById('no-event-posts-initial');

        if (!listContainer || !noResultsMsg) {
            console.warn("filterEventPosts: Missing required elements.");
            return;
        }

        let visibleCount = 0;
        const allPosts = listContainer.querySelectorAll('.event-post-item');
        
        allPosts.forEach(post => {
            const searchText = post.dataset.searchText || '';
            if (!searchTerm || searchText.includes(searchTerm)) {
                post.style.display = 'block'; // 'block' since it's a div
                visibleCount++;
            } else {
                post.style.display = 'none';
            }
        });

        const hasAnyPosts = allPosts.length > 0;

        // Toggle "no results" messages
        if (initialNoPostsMsg) {
            initialNoPostsMsg.style.display = 'none';
        }

        if (visibleCount === 0 && searchTerm) {
            noResultsMsg.textContent = `No posts found matching "${searchTerm}".`;
            noResultsMsg.style.display = 'block';
        } else {
            noResultsMsg.style.display = 'none';
        }

        // Show "no posts" message only if search is clear and there were no posts to begin with
        if (initialNoPostsMsg) {
            if (searchTerm) {
                initialNoPostsMsg.style.display = 'none';
            } else if (hasAnyPosts) {
                 initialNoPostsMsg.style.display = 'none';
            } else {
                initialNoPostsMsg.style.display = 'block';
            }
        }
    },


    openCreateModal(sourceType, sourcePuid, sourceName) {
        const modal = document.getElementById('createEventModal');
        if (!modal) return;

        modal.querySelector('#createEventTitle').textContent = `Create Event for ${sourceName}`;
        modal.querySelector('#source_type').value = sourceType;
        modal.querySelector('#source_puid').value = sourcePuid;
        modal.querySelector('#event_title').value = '';
        modal.querySelector('#event_date').value = '';
        modal.querySelector('#event_time').value = '';
        modal.querySelector('#event_end_date').value = '';
        modal.querySelector('#event_end_time').value = '';
        modal.querySelector('#event_location').value = '';
        modal.querySelector('#event_details').value = '';

        const publicToggle = modal.querySelector('#public-event-toggle');
        if(publicToggle) {
            publicToggle.style.display = (sourceType === 'public_page') ? 'flex' : 'none';
            modal.querySelector('#is_public').checked = false;
        }

        App.Modal.open('createEventModal');
    },

    async submitCreateForm() {
        const modal = document.getElementById('createEventModal');
        if (!modal) return;
        const payload = {
            source_type: modal.querySelector('#source_type').value,
            source_puid: modal.querySelector('#source_puid').value,
            title: modal.querySelector('#event_title').value,
            event_date: modal.querySelector('#event_date').value,
            event_time: modal.querySelector('#event_time').value,
            event_end_date: modal.querySelector('#event_end_date').value,
            event_end_time: modal.querySelector('#event_end_time').value,
            location: modal.querySelector('#event_location').value,
            details: modal.querySelector('#event_details').value,
            is_public: modal.querySelector('#is_public') ? modal.querySelector('#is_public').checked : false,
        };

        try {
            const response = await fetch('/events/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            if (response.ok) {
                App.Modal.close('createEventModal'); // Close modal on success
                App.Modal.showInfo(result.message, () => {
                    // Use the router to navigate to the new event profile
                    if (result.event_url) {
                        // We can't use App.Router.navigate because it's a full URL
                        // to a different page (/events/<puid>)
                        window.location.href = result.event_url;
                    }
                });
            } else { throw new Error(result.error || 'Failed to create event.'); }
        } catch (error) { App.Modal.showInfo(`Error: ${error.message}`); }
    },

async respond(eventPuid, response) {
        try {
            const fetchResponse = await fetch(`/events/${eventPuid}/respond`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ response })
            });
            const result = await fetchResponse.json();
            if (!fetchResponse.ok) throw new Error(result.error);

            // Check which page we're on
            const isMyEventsPage = window.location.pathname === '/events/';
            const isIndexPage = window.location.pathname === '/';
            
            if (isMyEventsPage) {
                // On My Events page: reload the entire page content from the server
                console.log('Reloading My Events page content...');
                
                // Fetch fresh content from the server
                const contentResponse = await fetch('/events/api/page/my_events');
                if (!contentResponse.ok) throw new Error('Failed to reload events');
                
                const newContent = await contentResponse.text();
                
                // Replace the main content
                const mainContentContainer = document.getElementById('main-content-container');
                if (mainContentContainer) {
                    mainContentContainer.innerHTML = newContent;
                    
                    // Re-initialize the events module for the new content
                    if (typeof this.init === 'function') {
                        this.init();
                    }
                    
                    console.log('Page content reloaded successfully');
                } else {
                    console.warn('Could not find main-content-container, doing full page reload');
                    window.location.reload();
                }
            } else if (isIndexPage) {
                // On the main feed page: force reload to refresh feed
                console.log('Reloading main feed after event response change...');
                window.location.reload();
            } else {
                // On other pages (event profile, etc.): just reload
                window.location.reload();
            }

        } catch (error) {
            App.Modal.showInfo(`Error: ${error.message}`);
        }
    },

    openEditModal(eventPuid, eventDataJson) {
         // Populate the form fields before opening
        const titleEl = document.getElementById('edit_event_title');
        const dateEl = document.getElementById('edit_event_date');
        const timeEl = document.getElementById('edit_event_time');
        const endDateEl = document.getElementById('edit_event_end_date');
        const endTimeEl = document.getElementById('edit_event_end_time');
        const locationEl = document.getElementById('edit_event_location');
        const detailsEl = document.getElementById('edit_event_details');
        const puidInput = document.getElementById('edit_event_puid');

        let eventData = null;

        if (eventDataJson) {
             try {
                 // Replace ' with " for valid JSON parsing
                 const cleanJson = eventDataJson.replace(/'/g, '"');
                 eventData = JSON.parse(cleanJson);
             } catch(e) {
                  console.error("Error parsing event data from button attribute:", e, "Original data:", eventDataJson);
             }
        }

        if (!eventData) {
            console.error("Cannot open edit modal: Original event data not found or invalid.");
            App.Modal.showInfo("Error: Could not load event data for editing.");
            return;
        }

        try {
            if (puidInput) puidInput.value = eventPuid;
            if (titleEl) titleEl.value = eventData.title || '';
            if (locationEl) locationEl.value = eventData.location || '';
            if (detailsEl) detailsEl.value = eventData.details || '';

            if (eventData.event_datetime && dateEl && timeEl) {
                 // Convert ISO string or timestamp string back to YYYY-MM-DD and HH:MM
                 // Handle strings from DB (YYYY-MM-DD HH:MM:SS) or from JS (ISO)
                 const dtStr = eventData.event_datetime.replace(' ', 'T') + (eventData.event_datetime.includes('Z') ? '' : 'Z');
                 const dt = new Date(dtStr); 
                 if (!isNaN(dt)) {
                     // Get local timezone offset
                     const offset = dt.getTimezoneOffset();
                     const localDt = new Date(dt.getTime() - (offset * 60000)); // Adjust to local
                     dateEl.value = localDt.toISOString().split('T')[0];
                     timeEl.value = localDt.toISOString().split('T')[1].substring(0, 5);
                 }
            }
             if (eventData.event_end_datetime && endDateEl && endTimeEl) {
                 const endDtStr = eventData.event_end_datetime.replace(' ', 'T') + (eventData.event_end_datetime.includes('Z') ? '' : 'Z');
                 const endDt = new Date(endDtStr);
                 if (!isNaN(endDt)) {
                     const offset = endDt.getTimezoneOffset();
                     const localEndDt = new Date(endDt.getTime() - (offset * 60000)); // Adjust to local
                     endDateEl.value = localEndDt.toISOString().split('T')[0];
                     endTimeEl.value = localEndDt.toISOString().split('T')[1].substring(0, 5);
                 }
            } else {
                 // Clear end date/time if not set
                 if (endDateEl) endDateEl.value = '';
                 if (endTimeEl) endTimeEl.value = '';
            }

            App.Modal.open('editEventModal');
        } catch(e) {
            console.error("Error parsing event data for edit modal:", e);
            App.Modal.showInfo("Error: Could not load event data.");
        }
    },


    async submitEditForm() {
        const puid = document.getElementById('edit_event_puid').value;
        const payload = {
            title: document.getElementById('edit_event_title').value,
            event_date: document.getElementById('edit_event_date').value,
            event_time: document.getElementById('edit_event_time').value,
            event_end_date: document.getElementById('edit_event_end_date').value,
            event_end_time: document.getElementById('edit_event_end_time').value,
            location: document.getElementById('edit_event_location').value,
            details: document.getElementById('edit_event_details').value,
        };

        try {
            const response = await fetch(`/events/${puid}/edit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const result = await response.json();
            if (response.ok) {
                 App.Modal.close('editEventModal'); // Close on success
                App.Modal.showInfo(result.message, () => window.location.reload());
            } else { throw new Error(result.error); }
        } catch (error) { App.Modal.showInfo(`Error: ${error.message}`); }
    },

    async openInviteModal(eventPuid) {
        const list = document.getElementById('inviteFriendsList');
        const loading = document.getElementById('inviteFriendsLoading');
        if (!list || !loading) return; // Basic check

        App.Modal.open('inviteFriendsModal');
        loading.style.display = 'block';
        list.innerHTML = '';
        list.appendChild(loading);

        try {
            const response = await fetch(`/events/${eventPuid}/invite_friends`);
            if (!response.ok) throw new Error((await response.json()).error || 'Server error.');
            const friends = await response.json();

            loading.style.display = 'none';

            if (friends.length === 0) {
                list.innerHTML = '<p class="text-center text-gray-500 p-4">All friends have been invited or are already attending.</p>';
            } else {
                friends.forEach(friend => {
                    let picUrl = '/static/images/default_avatar.png';
                    if (friend.profile_picture_path) {
                        if (friend.hostname) {
                            // Assume HTTPS unless insecure mode is explicitly configured (less common)
                            const protocol = window.location.protocol; // Use current protocol
                            picUrl = `${protocol}//${friend.hostname}/profile_pictures/${friend.profile_picture_path}`;
                        } else {
                            picUrl = `/profile_pictures/${friend.profile_picture_path}`; // Correct local path
                        }
                    }

                    const nodeDisplay = friend.node_nickname || friend.hostname;
                    const hostnameDisplay = friend.hostname ? `<p class="text-sm text-gray-500">@${nodeDisplay}</p>` : '';

                    list.insertAdjacentHTML('beforeend', `
                        <div class="flex items-center justify-between p-3 rounded-lg post-card">
                            <div class="flex items-center">
                                <img src="${picUrl}" alt="${friend.display_name}" class="w-10 h-10 rounded-full mr-3 object-cover" onerror="this.src='/static/images/default_avatar.png';">
                                <div>
                                    <p class="font-bold primary-text">${friend.display_name}</p>
                                    ${hostnameDisplay}
                                </div>
                            </div>
                            <button class="bg-blue-500 text-white font-bold py-1 px-3 rounded-md text-sm hover:bg-blue-600" onclick="App.Events.sendInvite(this, '${eventPuid}', '${friend.puid}')">
                                Invite
                            </button>
                        </div>`);
                });
            }
        } catch (error) {
            loading.style.display = 'none';
            list.innerHTML = `<p class="text-center text-red-500 p-4">Could not load friends: ${error.message}</p>`;
        }
    },

    async sendInvite(button, eventPuid, userPuid) {
        button.disabled = true;
        button.textContent = 'Sending...';
        try {
            const response = await fetch(`/events/${eventPuid}/invite/${userPuid}`, { method: 'POST' });
            const result = await response.json();
            if (!response.ok) throw new Error(result.message || result.error);
            button.textContent = 'Sent';
            button.classList.remove('bg-blue-500', 'hover:bg-blue-600');
            button.classList.add('bg-gray-400', 'cursor-not-allowed');
        } catch (error) {
            App.Modal.showInfo(`Error: ${error.message}`);
            button.disabled = false;
            button.textContent = 'Invite';
        }
    },
};

/**
 * @module Parental
 * @description Handles parental control approval/denial actions
 */
App.Parental = {
    /**
     * Update the parental controls badge count in the sidebar
     */
    updateBadgeCount() {
        fetch('/parental/api/badge_count')
            .then(response => response.json())
            .then(data => {
                const badge = document.querySelector('a[href*="parental"] span.bg-red-500');
                if (data.count > 0) {
                    if (badge) {
                        badge.textContent = data.count < 100 ? data.count : '99+';
                    } else {
                        // Badge doesn't exist, create it
                        const parentalLink = document.querySelector('a[href*="parental"]');
                        if (parentalLink) {
                            const newBadge = document.createElement('span');
                            newBadge.className = 'absolute -top-1 -right-1 bg-red-500 text-white text-xs font-bold rounded-full h-5 w-5 flex items-center justify-center';
                            newBadge.textContent = data.count < 100 ? data.count : '99+';
                            parentalLink.appendChild(newBadge);
                        }
                    }
                } else {
                    // No pending approvals, remove badge
                    if (badge) {
                        badge.remove();
                    }
                }
            })
            .catch(error => {
                console.error('Error updating badge count:', error);
            });
    },

    /**
     * Approve a parental approval request
     */
    approveRequest(approvalId) {
        fetch(`/parental/approve/${approvalId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                App.Toast.error(data.error);
            } else {
                App.Toast.success(data.message || 'Request approved and sent!');
                // Update badge count
                this.updateBadgeCount();
                // Reload the page content to refresh the list
                setTimeout(() => {
                    App.Router.navigate('/parental/');
                }, 1500);
            }
        })
        .catch(error => {
            console.error('Error approving parental request:', error);
            App.Toast.error('Failed to approve request');
        });
    },

    /**
     * Deny a parental approval request
     */
    denyRequest(approvalId) {
        App.Modal.showConfirm(
            'Deny this request? Your child will be notified.',
            () => {
                // This callback runs if user clicks "Confirm"
                fetch(`/parental/deny/${approvalId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                })
                .then(response => response.json())
                .then(data => {
                    if (data.error) {
                        App.Toast.error(data.error);
                    } else {
                        App.Toast.success(data.message || 'Request denied');
                        // Update badge count
                        this.updateBadgeCount();
                        // Reload the page content to refresh the list
                        setTimeout(() => {
                            App.Router.navigate('/parental/');
                        }, 1500);
                    }
                })
                .catch(error => {
                    console.error('Error denying parental request:', error);
                    App.Toast.error('Failed to deny request');
                });
            }
        );
    }
};

/**
 * @file modules/privacy.js
 * @description Handles privacy actions: remove tags, remove mentions, and hide content
 * Populates the App.Privacy namespace.
 */
App.Privacy = {
    /**
     * Initialize privacy actions
     */
    init() {
        console.log('Privacy module initialized');
    },

    /**
     * Remove the current user's tag from a post
     * @param {string} postCuid - The CUID of the post
     */
    async removeTag(postCuid) {
        // Show confirmation modal
        App.Modal.showConfirm(
            'Are you sure you want to remove your tag from this post? This action cannot be undone.',
            async () => {
                try {
                    const response = await fetch(`/remove_tag_from_post/${postCuid}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        // Store toast message for after reload
                        sessionStorage.setItem('pendingToast', JSON.stringify({
                            message: 'Your tag has been removed from this post',
                            type: 'success'
                        }));
                        // Reload to show updated post
                        location.reload();
                    } else {
                        App.Toast.error(data.error || 'Failed to remove tag');
                    }
                } catch (error) {
                    console.error('Error removing tag:', error);
                    App.Toast.error('An error occurred while removing your tag');
                }
            }
        );
    },

    /**
     * Remove the current user's @mention from a post
     * @param {string} postCuid - The CUID of the post
     */
    async removeMentionFromPost(postCuid) {
        // Show confirmation modal
        App.Modal.showConfirm(
            'Are you sure you want to remove your @mention from this post? This action cannot be undone.',
            async () => {
                try {
                    const response = await fetch(`/remove_mention_from_post/${postCuid}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        sessionStorage.setItem('pendingToast', JSON.stringify({
                            message: 'Your mention has been removed from this post',
                            type: 'success'
                        }));
                        location.reload();
                    } else {
                        App.Toast.error(data.error || 'Failed to remove mention');
                    }
                } catch (error) {
                    console.error('Error removing mention from post:', error);
                    App.Toast.error('An error occurred while removing your mention');
                }
            }
        );
    },

    /**
     * Remove the current user's @mention from a comment
     * @param {string} commentCuid - The CUID of the comment
     */
    async removeMentionFromComment(commentCuid) {
        // Show confirmation modal
        App.Modal.showConfirm(
            'Are you sure you want to remove your @mention from this comment? This action cannot be undone.',
            async () => {
                try {
                    const response = await fetch(`/remove_mention_from_comment/${commentCuid}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        sessionStorage.setItem('pendingToast', JSON.stringify({
                            message: 'Your mention has been removed from this comment',
                            type: 'success'
                        }));
                        location.reload();
                    } else {
                        App.Toast.error(data.error || 'Failed to remove mention');
                    }
                } catch (error) {
                    console.error('Error removing mention from comment:', error);
                    App.Toast.error('An error occurred while removing your mention');
                }
            }
        );
    },

    /**
     * Hide a post from the user's timeline
     * @param {string} postCuid - The CUID of the post
     */
    async hidePost(postCuid) {
        // Show confirmation modal
        App.Modal.showConfirm(
            'Are you sure you want to hide this post? You will not be able to see it again or receive notifications about it. This action cannot be undone.',
            async () => {
                try {
                    const response = await fetch(`/hide_post/${postCuid}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        // Remove the post from the DOM immediately
                        const postElement = document.getElementById(`post-${postCuid}`);
                        if (postElement) {
                            // Add fade-out animation
                            postElement.style.transition = 'opacity 0.3s ease';
                            postElement.style.opacity = '0';
                            
                            // Remove after animation
                            setTimeout(() => {
                                postElement.remove();
                            }, 300);
                        }
                        
                        App.Toast.success('Post hidden successfully');
                    } else {
                        App.Toast.error(data.error || 'Failed to hide post');
                    }
                } catch (error) {
                    console.error('Error hiding post:', error);
                    App.Toast.error('An error occurred while hiding the post');
                }
            }
        );
    },

    /**
     * Hide a comment from the user's view
     * @param {string} commentCuid - The CUID of the comment
     */
    async hideComment(commentCuid) {
        // Show confirmation modal
        App.Modal.showConfirm(
            'Are you sure you want to hide this comment and all its replies? You will not be able to see them again or receive notifications about them. This action cannot be undone.',
            async () => {
                try {
                    const response = await fetch(`/hide_comment/${commentCuid}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        // Remove the comment from the DOM immediately
                        const commentElement = document.getElementById(`comment-${commentCuid}`);
                        if (commentElement) {
                            // Add fade-out animation
                            commentElement.style.transition = 'opacity 0.3s ease';
                            commentElement.style.opacity = '0';
                            
                            // Remove after animation
                            setTimeout(() => {
                                commentElement.remove();
                            }, 300);
                        }
                        
                        App.Toast.success('Comment and replies hidden successfully');
                    } else {
                        App.Toast.error(data.error || 'Failed to hide comment');
                    }
                } catch (error) {
                    console.error('Error hiding comment:', error);
                    App.Toast.error('An error occurred while hiding the comment');
                }
            }
        );
    }
};

// Make functions globally available for onclick handlers
window.removeTagFromPost = (postCuid) => App.Privacy.removeTag(postCuid);
window.removeMentionFromPost = (postCuid) => App.Privacy.removeMentionFromPost(postCuid);
window.removeMentionFromComment = (commentCuid) => App.Privacy.removeMentionFromComment(commentCuid);
window.hidePost = (postCuid) => App.Privacy.hidePost(postCuid);
window.hideComment = (commentCuid) => App.Privacy.hideComment(commentCuid);

/**
 * Initializes the core application components that are needed on every page.
 */
App.initCore = async function() {
    this.showLoader();
    console.log("App core initializing...");
    
    try {
        // All modules are now pre-loaded, just initialize them
        this.Modal.injectHTML();
        this.bindGlobalEventListeners();
        this.Utils.autoHideFlashMessages();
        this.Utils.convertAllUTCTimestamps();
        this.Media.initCommunicationListener();
        
        // Initialize router on SPA pages
        if (window.appConfig && window.appConfig.isSpaPage === true) {
            console.log("SPA Page detected. Initializing router.");
            this.Router.init();
            
            setTimeout(async () => {
                if (this.LoadMore && typeof this.LoadMore.initializeButtons === 'function') {
                    console.log("Initializing LoadMore buttons after router...");
                    this.LoadMore.initializeButtons();
                    await this.LoadMore.autoLoadToTarget();
                }
            }, 500);
        } else {
            console.log("Non-SPA page detected. Skipping router initialization.");
            this.hideLoader();
            
            if (this.LoadMore && typeof this.LoadMore.initializeButtons === 'function') {
                this.LoadMore.initializeButtons();
                setTimeout(async () => {
                    await this.LoadMore.autoLoadToTarget();
                }, 500);
            }
            
            // Initialize new posts polling for non-SPA pages (groups, events, profiles)
            if (this.NewPostsPolling) {
                setTimeout(() => {
                    const pathname = window.location.pathname;
                    console.log('Checking pathname for polling init:', pathname);
                    
                    if (pathname === '/') {
                        // Main feed
                        console.log('Initializing polling for main feed');
                        this.NewPostsPolling.init('feed');
                    } else if (pathname.startsWith('/group/') && pathname.split('/').length >= 3) {
                        // Group profile - URL is /group/{puid}
                        const puid = this.LoadMore._getPuidFromUrl();
                        console.log('Initializing polling for group:', puid);
                        if (puid) {
                            this.NewPostsPolling.init('group', puid);
                        }
                    } else if (pathname.startsWith('/events/') && pathname.split('/').length >= 3) {
                        // Event profile - URL is /events/{puid}
                        const puid = this.LoadMore._getPuidFromUrl();
                        console.log('Initializing polling for event:', puid);
                        if (puid) {
                            this.NewPostsPolling.init('event', puid);
                        }
                    }
                }, 500);
            }
        }
        
        // Initialize media previews
        this.Media.Previews.initCreatePost();
        this.Media.Previews.initNewComment();

        // Initialize auto-growing textarea for create post form
        const createPostTextarea = document.getElementById('content');
        if (createPostTextarea) {
            const adjustTextareaHeight = () => {
                createPostTextarea.style.height = 'auto';
                createPostTextarea.style.height = createPostTextarea.scrollHeight + 'px';
            };
            createPostTextarea.addEventListener('input', adjustTextareaHeight);
            adjustTextareaHeight();
        }

        // Initialize notifications if present
        if (document.getElementById('notification-bell-button')) {
            if (this.Notifications && typeof this.Notifications.init === 'function') {
                this.Notifications.init();
            }
        }
        
        // Handle federation viewer token
        if (window.appConfig && window.appConfig.viewerToken) {
            this.Federation.handleViewerToken(window.appConfig.viewerToken);
        }
        
        // Initialize toast
        if (this.Toast && typeof this.Toast.init === 'function') {
            this.Toast.init();
            this.Toast.checkPending();
        }
        
        // Initialize notification polling if on SPA page
        if (window.appConfig && window.appConfig.isSpaPage === true) {
            if (this.NotificationPolling && typeof this.NotificationPolling.init === 'function') {
                this.NotificationPolling.init();
            }
        }

        // Conditionally initialize page-specific modules based on DOM
        try {
            // Post module - if edit form exists
            if (document.getElementById('editPostForm') && this.Post && typeof this.Post.init === 'function') {
                this.Post.init();
            }
            // Comment module - if edit form exists
            if (document.getElementById('editCommentForm') && this.Comment && typeof this.Comment.init === 'function') {
                this.Comment.init();
            }
            // Events module - if event elements exist
            if ((document.getElementById('eventPictureUploadForm') || 
                 document.getElementById('response-buttons') ||
                 document.querySelector('.event-card-item')) && 
                 this.Events && typeof this.Events.init === 'function') {
                this.Events.init();
            }
            // Group module - if group search exists
            if (document.getElementById('groupPostSearchInput') && this.Group && typeof this.Group.init === 'function') {
                this.Group.init();
            }
            // Profile module - if profile forms exist
            if ((document.getElementById('profileInfoForm') || document.getElementById('profilePictureUploadForm')) && 
                this.Profile && typeof this.Profile.init === 'function') {
                this.Profile.init();
            }
            // Settings module - if settings accordion exists (in settings modal)
            if (document.querySelector('.settings-accordion-button') && 
                this.Settings && typeof this.Settings.init === 'function') {
                this.Settings.init();
            }
            // Discover module - if discover search inputs exist
            if ((document.getElementById('discoverUsersSearchInput') || 
                 document.getElementById('discoverPagesSearchInput') || 
                 document.getElementById('discoverGroupsSearchInput')) && 
                 this.Discover && typeof this.Discover.init === 'function') {
                this.Discover.init();
            }
            
            console.log("Page-specific modules initialized.");
        } catch (error) {
            console.error('Failed to initialize page-specific modules:', error);
        }

        console.log("App core initialization complete.");
    } catch (error) {
        console.error('Failed to load core application modules:', error);
        document.body.innerHTML = '<div style="text-align: center; padding: 50px; font-family: sans-serif;"><h1>Error</h1><p>The application could not be loaded.</p></div>';
    }
};

App.bindGlobalEventListeners = function() {
    window.addEventListener('click', (event) => {
        // Close dropdowns
        if (!event.target.closest('[id^="options-menu-"], [id^="comment-options-"], [id^="options-menu-profile-"], .dropdown-menu')) {
            document.querySelectorAll(".dropdown-menu").forEach(dropdown => {
                if (dropdown.style.display === 'block') dropdown.style.display = 'none';
            });
        }
    });

    // Close modals on overlay click
    document.body.addEventListener('click', (event) => {
        if (event.target.classList.contains('modal')) {
            this.Modal.close(event.target.id);
        }
    });

    // Disable context menu on media - using event delegation for dynamic content
    document.body.addEventListener('contextmenu', (event) => {
        // Check if the clicked element or any of its parents match our media selectors
        const target = event.target;
        
        // Check if target is a media element or inside a media container
        if (target.closest('.post-media-item-link') || 
            target.closest('.comment-media-item-link') || 
            target.closest('.gallery-media-item-link') ||
            target.closest('.post-media-item') ||
            target.closest('.comment-media-grid-item') ||
            target.closest('.gallery-media-item') ||
            (target.tagName === 'IMG' && target.closest('.media-grid')) ||
            (target.tagName === 'VIDEO' && target.closest('.media-grid')) ||
            (target.tagName === 'IMG' && target.closest('.comment-media-grid')) ||
            (target.tagName === 'VIDEO' && target.closest('.comment-media-grid')) ||
            // Media view modal protection
            (target.tagName === 'IMG' && target.closest('#mediaViewModal')) ||
            (target.tagName === 'VIDEO' && target.closest('#mediaViewModal')) ||
            // Additional catch-all for any img/video with media-related alt text or in modal contexts
            (target.tagName === 'IMG' && (target.alt === 'Post Media' || target.alt === 'Photo' || target.alt === 'Group Media' || target.closest('.bg-black.rounded-lg'))) ||
            (target.tagName === 'VIDEO' && target.closest('.bg-black.rounded-lg'))) {
            event.preventDefault();
            return false;
        }
    });
    // NEW: Initialize mobile sidebar toggle
    this.initMobileSidebar();
};

/**
 * Initializes mobile sidebar toggle functionality
 */
App.initMobileSidebar = function() {
    const sidebar = document.querySelector('aside.lg\\:col-span-3');
    const toggleButton = document.getElementById('mobile-sidebar-toggle');
    const overlay = document.getElementById('sidebar-overlay');
    
    if (!sidebar || !toggleButton || !overlay) return;
    
    const toggleSidebar = () => {
        sidebar.classList.toggle('sidebar-open');
        overlay.classList.toggle('active');
    };
    
    const closeSidebar = () => {
        sidebar.classList.remove('sidebar-open');
        overlay.classList.remove('active');
    };
    
    toggleButton.addEventListener('click', toggleSidebar);
    overlay.addEventListener('click', closeSidebar);
    
    // Close sidebar on escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && sidebar.classList.contains('sidebar-open')) {
            closeSidebar();
        }
    });
};

// =================================================================================
// DYNAMIC GLOBAL WRAPPERS
// These functions are called by onclick attributes. They now dynamically
// load their required modules before executing the action.
// =================================================================================

function openModal(modalId) { App.Modal.open(modalId); }
function closeModal(modalId) { App.Modal.close(modalId); }
function showInfoModal(message, onOk) { App.Modal.showInfo(message, onOk); }
function showConfirmationModal(message, onConfirm) { App.Modal.showConfirm(message, onConfirm); }
function confirmFormSubmission(form, message) { App.Modal.confirmFormSubmission(form, message); }

function toggleDropdown(event, menuId) {
    event.stopPropagation();
    const dropdownMenu = document.getElementById(menuId);
    if (!dropdownMenu) return;
    
    const isVisible = dropdownMenu.style.display === 'block';
    
    // Close all dropdowns first
    document.querySelectorAll(".dropdown-menu").forEach(d => {
        d.style.display = 'none';
        d.style.position = '';
        d.style.top = '';
        d.style.left = '';
        d.style.right = '';
    });
    
    if (!isVisible) {
        // Calculate position relative to the button
        const button = event.currentTarget;
        const buttonRect = button.getBoundingClientRect();
        
        // Check if dropdown has fixed positioning
        const computedStyle = window.getComputedStyle(dropdownMenu);
        if (computedStyle.position === 'fixed') {
            // Position it below and to the right of the button
            dropdownMenu.style.top = `${buttonRect.bottom + 2}px`;
            dropdownMenu.style.left = `${buttonRect.right - 224}px`; // 224px = 14rem (w-56)
        }
        
        dropdownMenu.style.display = 'block';
    }
}

function confirmDelete(event) {
    event.preventDefault();
    App.Modal.confirmFormSubmission(event.target, 'Are you sure you want to delete this post? This action cannot be undone.');
}

// --- About Modal ---
function openAboutModal() {
    App.Modal.open('aboutModal');
}

function closeAboutModal() {
    App.Modal.close('aboutModal');
}

// --- Media ---
// --- FIX: Changed function signature to match comment media button ---
function openCreatePostMediaBrowser(isFederated, viewerHomeUrl) { 
    App.Media.openBrowser('createPost', { url: isFederated ? viewerHomeUrl : '', currentSelected: App.state.selectedCreatePostMedia }); 
}
// --- END FIX ---
function removeCreatePostMedia(path) { App.state.selectedCreatePostMedia = App.state.selectedCreatePostMedia.filter(i => i.media_file_path !== path); App.Media.Previews.updateCreatePost(); }
function openMediaBrowserForProfilePicture() { App.Media.openBrowser('single_select'); }

// --- Post ---
async function openEditPostModal(postCuid, authorPuid, content, privacy, media, viewerHomeUrl, isFederated, isGroupPost, isPublicPage, isEventPost, taggedUserPuids, location, currentUserRequiresParentalApproval, profileUserRequiresParentalApproval) {
    // Module pre-loaded
    App.Post.openEditModal(postCuid, authorPuid, content, privacy, media, viewerHomeUrl, isFederated, isGroupPost, isPublicPage, isEventPost, taggedUserPuids, location, currentUserRequiresParentalApproval, profileUserRequiresParentalApproval);
}
async function closeEditPostModal() {
    // Module pre-loaded
    // --- START FIX: Corrected function name ---
    // Was: App.Post.closeEditPostModal();
    App.Post.closeEditModal();
    // --- END FIX ---
}
async function openEditPostMediaBrowser() {
    // Module pre-loaded
    // Relies on post.js state
    App.Media.openBrowser('editPost', { postCuid: App.state.editingPost.cuid, currentSelected: App.state.selectedEditPostMedia, url: App.state.editingPost.viewerHomeUrl });
}
function removeEditPostMedia(path) {
    App.state.selectedEditPostMedia = App.state.selectedEditPostMedia.filter(item => item.media_file_path !== path);
    App.Media.Previews.updateEditPost();
}

// --- Comment ---
async function openCommentMediaBrowser(postId, isFederated, viewerHomeUrl) {
    // Module pre-loaded
    // Ensures comment state is ready
    App.Media.openBrowser('newComment', { postId, currentSelected: App.state.selectedNewCommentMedia[postId] || [], url: isFederated ? viewerHomeUrl : '' });
}
function removeNewCommentMedia(postId, path) {
    if (App.state.selectedNewCommentMedia[postId]) {
        App.state.selectedNewCommentMedia[postId] = App.state.selectedNewCommentMedia[postId].filter(i => i.media_file_path !== path);
        App.Media.Previews.updateNewComment(postId);
    }
}
async function showReplyForm(postId, parentCommentId, replyToUsername) {
    // Module pre-loaded
    App.Comment.showReplyForm(postId, parentCommentId, replyToUsername);
}
async function hideReplyForm(postId) {
    // Module pre-loaded
    App.Comment.hideReplyForm(postId);
}
async function openEditCommentModal(cuid, content, media, viewerHomeUrl, isFederated) {
    // Module pre-loaded
    App.Comment.openEditModal(cuid, content, media, viewerHomeUrl, isFederated);
}
async function closeEditCommentModal() {
    // Module pre-loaded
    App.Comment.closeEditModal();
}
async function openEditCommentMediaBrowser() {
    // Module pre-loaded
    // Relies on comment.js state
    // --- FIX: Changed commentCuid to comment_cuid ---
    App.Media.openBrowser('editComment', { comment_cuid: App.state.editingComment.cuid, currentSelected: App.state.selectedEditCommentMedia, url: App.state.editingComment.viewerHomeUrl });
}
function removeEditCommentMedia(path) {
    App.state.selectedEditCommentMedia = App.state.selectedEditCommentMedia.filter(item => item.media_file_path !== path);
    App.Media.Previews.updateEditComment();
}
function confirmDeleteComment(event) {
    event.preventDefault();
    App.Modal.confirmFormSubmission(event.target, 'Are you sure you want to delete this comment? This action cannot be undone.');
}
// Media upload wrappers
async function handleCreatePostMediaUpload(event) {
    // Module pre-loaded
    App.Media.handleCreatePostUpload(event);
}

async function handleCommentMediaUpload(event, postId) {
    // Module pre-loaded
    App.Media.handleCommentUpload(event, postId);
}

async function handleEditPostMediaUpload(event) {
    // Module pre-loaded
    App.Media.handleEditPostUpload(event);
}

async function handleEditCommentMediaUpload(event) {
    // Module pre-loaded
    App.Media.handleEditCommentUpload(event);
}

// --- Profile ---
async function openProfileInfoModal() {
    // Module pre-loaded
    App.Profile.Info.openModal();
}
async function removeFamilyMember(id) {
    // Module pre-loaded
    App.Profile.Info.removeFamilyMember(id);
}
async function openEditFamilyMemberModal(id) {
    // Module pre-loaded
    App.Profile.Info.openEditFamilyModal(id);
}
async function handleEditFamilyMemberSubmit(event) {
    event.preventDefault();
    // Module pre-loaded
    App.Profile.Info.submitEditFamilyForm();
}

// --- Discover ---
async function fetchDiscoverableUsers() {
    // Module pre-loaded
    App.Discover.openDiscoverUsersModal();
}
async function fetchDiscoverableGroups() {
    // Module pre-loaded
    App.Discover.fetchGroups();
}
async function sendFriendRequest(btn, puid, host, name) {
    // Module pre-loaded
    App.Discover.sendFriendRequest(btn, puid, host, name);
}
async function followProfile(btn, puid, host, name, type) {
    // Module pre-loaded
    App.Discover.followProfile(btn, puid, host, name, type);
}

// --- Group ---
async function openInviteFriendsModal(puid) {
    // Module pre-loaded
    App.Group.openInviteModal(puid);
}
async function sendGroupInvite(btn, groupPuid, userPuid) {
    // Module pre-loaded
    App.Group.sendInvite(btn, groupPuid, userPuid);
}
async function submitEditGroupInfo(puid) {
    // Module pre-loaded
    App.Group.submitInfo(puid);
}

// --- Group Join Request Functions ---
async function sendGroupJoinRequest(button, group) {
    // Module pre-loaded
    App.Group.sendJoinRequest(button, group);
}
async function submitJoinRequestWithResponses() {
    // Module pre-loaded
    App.Group.submitJoinRequestWithResponses();
}
async function addJoinQuestion() {
    // Module pre-loaded
    App.Group.addJoinQuestion();
}
async function openEditGroupInfoModal() {
    // Module pre-loaded
    App.Group.initializeJoinQuestionsEditor();
    App.Modal.open('editGroupInfoModal');
}

// --- Admin ---
async function openSetMediaPathModal(username, currentMediaPath, currentUploadsPath) {
    // Module pre-loaded
    App.Admin.openSetMediaPathModal(username, currentMediaPath, currentUploadsPath);
}
async function submitSetMediaPathForm(event) {
    event.preventDefault();
    // Module pre-loaded
    App.Admin.submitSetMediaPathForm();
}
async function openChangeUsernameModal(user) {
    // Module pre-loaded
    App.Admin.openChangeUsernameModal(user);
}
async function submitChangeUsernameForm(event) {
    event.preventDefault();
    // Module pre-loaded
    App.Admin.submitChangeUsernameForm();
}
async function openResetPasswordModal(user) {
    // Module pre-loaded
    App.Admin.openResetPasswordModal(user);
}
async function submitResetPasswordForm(event) {
    event.preventDefault();
    // Module pre-loaded
    App.Admin.submitResetPasswordForm();
}

// --- Actions ---
async function followPage(btn, puid) {
    // Module pre-loaded
    App.Actions.followPage(btn, puid);
}
async function unfollowPage(btn, puid) {
    // Module pre-loaded
    App.Actions.unfollowPage(btn, puid);
}
async function unfollowPageFromList(btn, puid) {
    // Module pre-loaded
    App.Actions.unfollowPageFromList(btn, puid);
}

// --- Settings ---
async function openSettingsModal() {
    // Module pre-loaded
    App.Settings.openModal();
}
async function saveSettings() {
    // Module pre-loaded
    App.Settings.save();
}
async function saveAccountSettings() {
    // Module pre-loaded
    App.Settings.saveAccount();
}
async function logoutSession(id) {
    // Module pre-loaded
    App.Settings.Sessions.logout(id);
}
async function logoutAllSessions() {
    // Module pre-loaded
    App.Settings.Sessions.logoutAll();
}

// --- Events ---
async function openCreateEventModal(sourceType, sourcePuid, sourceName) {
    // Module pre-loaded
    App.Events.openCreateModal(sourceType, sourcePuid, sourceName);
}

// =================================================================================
// MEDIA GALLERY FILTERS
// =================================================================================

/**
 * Filters media items in gallery views by type (all, photos, videos)
 * @param {string} type - Filter type: 'all', 'photos', or 'videos'
 */
function filterMedia(type) {
    const allItems = document.querySelectorAll('.gallery-media-item-link');
    const buttons = document.querySelectorAll('.filter-button');
    
    // Update active button state
    buttons.forEach(btn => {
        if (btn.dataset.filter === type) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    // Filter media items based on type
    allItems.forEach(item => {
        const mediaItem = item.querySelector('.gallery-media-item');
        if (!mediaItem) return;
        
        const mediaType = mediaItem.dataset.mediaType;
        const isTagged = mediaItem.dataset.isTagged === '1';
        
        if (type === 'all') {
            item.style.display = '';
        } else if (type === 'photos' && mediaType === 'image') {
            item.style.display = '';
        } else if (type === 'videos' && mediaType === 'video') {
            item.style.display = '';
        } else if (type === 'tagged' && isTagged) {
            item.style.display = '';
        } else {
            item.style.display = 'none';
        }
    });
    
    // Hide/show empty year sections when filtered
    document.querySelectorAll('.year-section').forEach(section => {
        const hasVisibleItems = Array.from(section.querySelectorAll('.gallery-media-item-link'))
            .some(item => item.style.display !== 'none');
        section.style.display = hasVisibleItems ? '' : 'none';
    });
}

// =================================================================================
// ALBUMS FUNCTIONALITY
// =================================================================================

let currentAlbumData = null;
let allAlbumsData = [];

/**
 * Shows the albums view and hides the media grid
 */
async function showAlbumsView() {
    // Update active button state
    document.querySelectorAll('.filter-button').forEach(btn => {
        btn.classList.remove('active');
    });
    const albumsBtn = document.querySelector('[data-filter="albums"]');
    if (albumsBtn) {
        albumsBtn.classList.add('active');
    }
    
    // Hide media grid, show albums container
    const mediaGridContainer = document.getElementById('media-grid-container');
    const albumsContainer = document.getElementById('albums-container');
    const singleAlbumView = document.getElementById('single-album-view');
    const albumsGrid = document.getElementById('albums-grid');
    
    if (mediaGridContainer) {
        mediaGridContainer.classList.add('hidden');
    }
    
    if (albumsContainer) {
        albumsContainer.classList.remove('hidden');
    }
    
    // Make sure we're showing the albums list, not a single album
    if (singleAlbumView) {
        singleAlbumView.classList.add('hidden');
    }
    
    if (albumsGrid) {
        albumsGrid.classList.remove('hidden');
        // Show the header too
        const headerDiv = albumsGrid.previousElementSibling;
        if (headerDiv) {
            headerDiv.classList.remove('hidden');
        }
    }
    
    // Reset current album data
    currentAlbumData = null;
    
    // Load albums (or re-render if already loaded)
    if (allAlbumsData.length === 0) {
        await loadAlbums();
    } else {
        // Re-render existing data
        renderAlbumsGrid();
    }
}

/**
 * Loads all albums for the current profile or group
 */
async function loadAlbums() {
    try {
        let endpoint;
        
        // Check if we're in a group context
        if (window.groupPuid) {
            endpoint = `/api/albums/group/${window.groupPuid}`;
        } else {
            // Check if we're on "My Media" page
            const currentPath = window.location.pathname;
            
            if (currentPath.includes('/my_media')) {
                // Use the simpler endpoint that gets albums from session
                endpoint = '/api/albums/my';
            } else {
                // Extract PUID from URL path /u/PUID/gallery
                const pathParts = currentPath.split('/');
                const uIndex = pathParts.indexOf('u');
                
                let puid = null;
                if (uIndex !== -1) {
                    puid = pathParts[uIndex + 1];
                }
                
                if (!puid) {
                    throw new Error('Could not determine user PUID from URL');
                }
                
                endpoint = `/api/albums/user/${puid}`;
            }
        }
        
        console.log('Loading albums from:', endpoint);
        
        const response = await fetch(endpoint);
        
        if (!response.ok) {
            throw new Error('Failed to load albums');
        }
        
        allAlbumsData = await response.json();
        renderAlbumsGrid();
    } catch (error) {
        console.error('Error loading albums:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to load albums: ' + error.message, 'error');
        }
    }
}

/**
 * Renders the albums grid
 */
function renderAlbumsGrid() {
    const grid = document.getElementById('albums-grid');
    
    if (!grid) return;
    
    if (allAlbumsData.length === 0) {
        grid.innerHTML = `
            <div class="col-span-full text-center py-12">
                <svg class="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                </svg>
                <p class="text-gray-500 dark:text-gray-400">No albums yet</p>
                ${window.isOwner ? '<p class="text-sm text-gray-400 mt-2">Create your first album to organize your media</p>' : ''}
            </div>
        `;
        return;
    }
    
    grid.innerHTML = allAlbumsData.map(album => {
        const coverImage = album.cover_image;
        let coverImageHtml = '';
        
        if (coverImage) {
            const displayUrl = getMediaDisplayUrl(coverImage, true);
            const fullUrl = getFederatedMediaUrl(coverImage);
            
            if (coverImage.media_type === 'image') {
                // Use thumbnail with fallback to full image
                coverImageHtml = `<img src="${displayUrl}" alt="${escapeHtml(album.title)}" class="w-full h-full object-cover" loading="lazy" onerror="this.src='${fullUrl}'">`;
            } else if (coverImage.media_type === 'video') {
                coverImageHtml = `<video class="w-full h-full object-cover" muted><source src="${fullUrl}" type="video/mp4"></video>`;
            }
        } else {
            coverImageHtml = `
                <div class="aspect-square bg-gray-300 dark:bg-gray-600 flex items-center justify-center">
                    <svg class="w-12 h-12 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                    </svg>
                </div>
            `;
        }
        
        return `
            <div class="cursor-pointer rounded-lg overflow-hidden shadow-md hover:shadow-lg transition-shadow post-card"
                 onclick="viewAlbum('${album.album_uid}')">
                <div class="aspect-square bg-gray-200 dark:bg-gray-700">
                    ${coverImageHtml}
                </div>
                <div class="p-4">
                    <h3 class="font-semibold primary-text truncate">${escapeHtml(album.title)}</h3>
                    <p class="text-sm secondary-text">${album.media_count} ${album.media_count === 1 ? 'item' : 'items'}</p>
                    ${window.groupPuid && album.owner_display_name ? `<p class="text-xs text-gray-500 dark:text-gray-400 mt-1">By ${escapeHtml(album.owner_display_name)}</p>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

/**
 * Views a specific album's contents
 */
async function viewAlbum(albumUid) {
    try {
        const response = await fetch(`/api/albums/${albumUid}`);
        
        if (!response.ok) {
            throw new Error('Failed to load album');
        }
        
        currentAlbumData = await response.json();
        
        // Hide albums grid, show single album view
        const albumsGrid = document.getElementById('albums-grid');
        const singleAlbumView = document.getElementById('single-album-view');
        
        // Hide the grid and the header (previous sibling)
        if (albumsGrid) {
            albumsGrid.classList.add('hidden');
            // Also hide the header with "Albums" title and "Create Album" button
            const headerDiv = albumsGrid.previousElementSibling;
            if (headerDiv) {
                headerDiv.classList.add('hidden');
            }
        }
        if (singleAlbumView) {
            singleAlbumView.classList.remove('hidden');
        }
        
        // Update album info
        const titleEl = document.getElementById('current-album-title');
        const descEl = document.getElementById('current-album-description');
        const ownerEl = document.getElementById('current-album-owner');
        
        if (titleEl) titleEl.textContent = currentAlbumData.title;
        if (descEl) descEl.textContent = currentAlbumData.description || '';
        
        // Show owner name for group albums
        if (ownerEl) {
            if (window.groupPuid && currentAlbumData.owner_display_name) {
                ownerEl.textContent = `By ${currentAlbumData.owner_display_name}`;
                ownerEl.style.display = 'block';
            } else {
                ownerEl.style.display = 'none';
            }
        }
        
        // Render media
        renderAlbumMedia();
        
        // NEW: Update action buttons visibility based on permissions
        updateAlbumActionButtons();
    } catch (error) {
        console.error('Error loading album:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to load album', 'error');
        }
    }
}

/**
 * Updates visibility of album action buttons based on user permissions
 */
function updateAlbumActionButtons() {
    if (!currentAlbumData) return;
    
    const actionButtonsDiv = document.getElementById('album-action-buttons');
    const editBtn = document.getElementById('edit-album-btn');
    const deleteBtn = document.getElementById('delete-album-btn');
    const addMediaBtn = document.getElementById('add-media-btn');
    
    // Hide all by default
    if (actionButtonsDiv) actionButtonsDiv.style.display = 'none';
    if (editBtn) editBtn.style.display = 'none';
    if (deleteBtn) deleteBtn.style.display = 'none';
    if (addMediaBtn) addMediaBtn.style.display = 'none';
    
    // Determine if current user is the owner
    const currentUserPuid = window.viewerPuid || (window.appConfig && window.appConfig.currentUserPuid);
    const isOwner = currentAlbumData.owner_puid === currentUserPuid;
    
    if (window.groupPuid) {
        // Group album - check permissions
        const isModOrAdmin = window.isModeratorOrAdmin || false;
        
        if (isOwner) {
            // Owner can edit, delete, and add media
            if (editBtn) editBtn.style.display = 'block';
            if (deleteBtn) deleteBtn.style.display = 'block';
            if (addMediaBtn) addMediaBtn.style.display = 'inline-flex';
            if (actionButtonsDiv) actionButtonsDiv.style.display = 'flex';
        } else if (isModOrAdmin) {
            // Mods/admins can only delete
            if (deleteBtn) deleteBtn.style.display = 'block';
            if (actionButtonsDiv) actionButtonsDiv.style.display = 'flex';
        }
    } else if (window.isOwner || isOwner) {
        // User album - owner can do everything
        if (editBtn) editBtn.style.display = 'block';
        if (deleteBtn) deleteBtn.style.display = 'block';
        if (addMediaBtn) addMediaBtn.style.display = 'inline-flex';
        if (actionButtonsDiv) actionButtonsDiv.style.display = 'flex';
    }
}

/**
 * Renders media items within an album
 */
function renderAlbumMedia() {
    const grid = document.getElementById('album-media-grid');
    
    if (!grid) return;
    
    if (!currentAlbumData.media || currentAlbumData.media.length === 0) {
        grid.innerHTML = `
            <div class="col-span-full text-center py-12">
                <p class="text-gray-500 dark:text-gray-400">No media in this album yet</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = currentAlbumData.media.map(media => {
        const displayUrl = getMediaDisplayUrl(media, true);
        const fullUrl = getFederatedMediaUrl(media);
        const currentUserPuid = window.viewerPuid || (window.appConfig && window.appConfig.currentUserPuid);
        const isAlbumOwner = currentAlbumData.owner_puid === currentUserPuid;
        const canRemoveMedia = window.isOwner || isAlbumOwner;
        
        return `
            <a href="/media/${media.muid}" class="gallery-media-item-link">
                <div class="relative w-full h-48 rounded-lg overflow-hidden shadow-md cursor-pointer hover:opacity-90 transition-opacity">
                    ${media.media_type === 'image' ? `
                        <img src="${displayUrl}" alt="${escapeHtml(media.alt_text || 'Media')}" class="w-full h-full object-cover" loading="lazy" onerror="this.src='${fullUrl}'">
                    ` : media.media_type === 'video' ? `
                        <video preload="metadata" muted class="w-full h-full object-cover">
                            <source src="${fullUrl}#t=0.1" type="video/mp4">
                        </video>
                        <div class="absolute inset-0 flex items-center justify-center bg-black bg-opacity-30 pointer-events-none">
                            <svg class="w-12 h-12 text-white" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z"/>
                            </svg>
                        </div>
                    ` : `
                        <div class="w-full h-full flex items-center justify-center bg-gray-200 dark:bg-gray-700">
                            <span class="text-gray-500">Unsupported</span>
                        </div>
                    `}
                    ${canRemoveMedia ? `
                        <button onclick="event.preventDefault(); event.stopPropagation(); removeFromAlbum(${media.id})" 
                                class="absolute top-2 right-2 p-2 bg-red-600 text-white rounded-full hover:bg-red-700 transition-colors z-10">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                            </svg>
                        </button>
                    ` : ''}
                </div>
            </a>
        `;
    }).join('');
}

/**
 * Returns to the albums list view
 */
function backToAlbumsList() {
    currentAlbumData = null;
    const singleAlbumView = document.getElementById('single-album-view');
    const albumsGrid = document.getElementById('albums-grid');
    
    if (singleAlbumView) {
        singleAlbumView.classList.add('hidden');
    }
    if (albumsGrid) {
        albumsGrid.classList.remove('hidden');
        // Show the header too
        const headerDiv = albumsGrid.previousElementSibling;
        if (headerDiv) {
            headerDiv.classList.remove('hidden');
        }
    }
}

/**
 * Opens the create album modal
 */
function openCreateAlbumModal() {
    const titleInput = document.getElementById('album-title');
    const descInput = document.getElementById('album-description');
    
    if (titleInput) titleInput.value = '';
    if (descInput) descInput.value = '';
    
    openModal('create-album-modal');
}

/**
 * Creates a new album
 */
async function createAlbum(event) {
    event.preventDefault();
    
    const titleInput = document.getElementById('album-title');
    const descInput = document.getElementById('album-description');
    
    const title = titleInput ? titleInput.value.trim() : '';
    const description = descInput ? descInput.value.trim() : '';
    
    if (!title) {
        if (App && App.Toast) {
            App.Toast.show('Please enter an album title', 'error');
        }
        return;
    }
    
    try {
        const payload = { title, description };
        
        // Add group_puid if we're in a group context
        if (window.groupPuid) {
            payload.group_puid = window.groupPuid;
        }
        
        const response = await fetch('/api/albums/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to create album');
        }
        
        closeModal('create-album-modal');
        if (App && App.Toast) {
            App.Toast.show('Album created successfully!', 'success');
        }
        
        const result = await response.json();
        
        // If we have a pending media item to add, add it now
        if (window.pendingMediaIdForNewAlbum && result.album_uid) {
            try {
                await fetch(`/api/albums/${result.album_uid}/media`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        media_id: parseInt(window.pendingMediaIdForNewAlbum)
                    })
                });
                window.pendingMediaIdForNewAlbum = null;
                if (App && App.Toast) {
                    App.Toast.show('Media added to new album!', 'success');
                }
            } catch (error) {
                console.error('Error adding media to new album:', error);
            }
        }
        
        // Only reload albums if we're on the albums view
        if (document.getElementById('albums-container') && !document.getElementById('albums-container').classList.contains('hidden')) {
            await loadAlbums();
        }
    } catch (error) {
        console.error('Error creating album:', error);
        if (App && App.Toast) {
            App.Toast.show(error.message || 'Failed to create album', 'error');
        }
    }
}

/**
 * Opens the edit album modal
 */
function openEditAlbumModal() {
    if (!currentAlbumData) return;
    
    const titleInput = document.getElementById('edit-album-title');
    const descInput = document.getElementById('edit-album-description');
    
    if (titleInput) titleInput.value = currentAlbumData.title;
    if (descInput) descInput.value = currentAlbumData.description || '';
    
    openModal('edit-album-modal');
}

/**
 * Saves album edits
 */
async function saveAlbumEdit(event) {
    event.preventDefault();
    
    if (!currentAlbumData) return;
    
    const titleInput = document.getElementById('edit-album-title');
    const descInput = document.getElementById('edit-album-description');
    
    const title = titleInput ? titleInput.value.trim() : '';
    const description = descInput ? descInput.value.trim() : '';
    
    if (!title) {
        if (App && App.Toast) {
            App.Toast.show('Please enter an album title', 'error');
        }
        return;
    }
    
    try {
        const response = await fetch(`/api/albums/${currentAlbumData.album_uid}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ title, description })
        });
        
        if (!response.ok) {
            throw new Error('Failed to update album');
        }
        
        closeModal('edit-album-modal');
        if (App && App.Toast) {
            App.Toast.show('Album updated successfully!', 'success');
        }
        
        // Update current album data
        currentAlbumData.title = title;
        currentAlbumData.description = description;
        
        // Update display
        const titleEl = document.getElementById('current-album-title');
        const descEl = document.getElementById('current-album-description');
        
        if (titleEl) titleEl.textContent = title;
        if (descEl) descEl.textContent = description;
        
        // Reload albums list
        await loadAlbums();
    } catch (error) {
        console.error('Error updating album:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to update album', 'error');
        }
    }
}

/**
 * Deletes the current album
 */
async function deleteCurrentAlbum() {
    if (!currentAlbumData) return;
    
    App.Modal.showConfirm(
        `Are you sure you want to delete "${currentAlbumData.title}"? This will not delete the media items themselves.`,
        async () => {
            try {
                const response = await fetch(`/api/albums/${currentAlbumData.album_uid}`, {
                    method: 'DELETE'
                });
                
                if (!response.ok) {
                    throw new Error('Failed to delete album');
                }
                
                if (App && App.Toast) {
                    App.Toast.show('Album deleted successfully!', 'success');
                }
                
                // Go back to albums list and reload
                backToAlbumsList();
                await loadAlbums();
            } catch (error) {
                console.error('Error deleting album:', error);
                if (App && App.Toast) {
                    App.Toast.show('Failed to delete album', 'error');
                }
            }
        }
    );
}

/**
 * Removes media from the current album
 */
/**
 * Removes media from the current album with confirmation
 */
function removeFromAlbum(mediaId) {
    if (!currentAlbumData) return;
    
    // Use the existing App.Modal.showConfirm
    App.Modal.showConfirm(
        'Remove this item from the album? This won\'t delete the media itself, only remove it from this album.',
        async () => {
            try {
                const response = await fetch(`/api/albums/${currentAlbumData.album_uid}/media`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ media_id: mediaId })
                });
                
                if (!response.ok) {
                    throw new Error('Failed to remove media');
                }
                
                if (App && App.Toast) {
                    App.Toast.show('Media removed from album', 'success');
                }
                
                // Remove from current album data
                currentAlbumData.media = currentAlbumData.media.filter(m => m.id !== mediaId);
                
                // Re-render
                renderAlbumMedia();
            } catch (error) {
                console.error('Error removing media:', error);
                if (App && App.Toast) {
                    App.Toast.show('Failed to remove media', 'error');
                }
            }
        }
    );
}

/**
 * Opens the "Add to Album" modal and loads user's albums
 * @param {number} mediaId - Optional media ID, if not provided will try to find it
 */
async function openAddToAlbumModal(mediaId) {
    // Use passed mediaId if provided, otherwise try to find it from the page
    if (!mediaId) {
        const mediaElement = document.querySelector('[data-media-id]');
        if (!mediaElement) {
            if (App && App.Toast) {
                App.Toast.show('Could not find media information', 'error');
            }
            return;
        }
        mediaId = mediaElement.dataset.mediaId;
    }
    
    window.currentMediaIdForAlbum = mediaId;
    
    try {
        // Determine the correct endpoint - check for group context first
        let endpoint;
        let isGroupContext = false;
        
        // Check if we're viewing a media item from a group post (in media view modal)
        if (window.mediaData && window.mediaData.group_puid) {
            // This is a group post - load group albums
            endpoint = `/api/albums/group/${window.mediaData.group_puid}`;
            window.currentAlbumGroupContext = window.mediaData.group_puid;
            isGroupContext = true;
        }
        
        // If not from mediaData, check if we're in a group gallery page
        if (!isGroupContext && window.groupPuid) {
            endpoint = `/api/albums/group/${window.groupPuid}`;
            window.currentAlbumGroupContext = window.groupPuid;
            isGroupContext = true;
        }
        
        // Fall back to user albums if not in group context
        if (!isGroupContext) {
            window.currentAlbumGroupContext = null;
            
            if (window.location.pathname.includes('/my_media')) {
                // Use the session-based endpoint for My Media
                endpoint = '/api/albums/my';
            } else {
                // Get current user's PUID from various sources
                let userPuid = window.viewer_puid || 
                              window.viewer_puid_for_js ||
                              document.querySelector('[data-current-user-puid]')?.dataset.currentUserPuid ||
                              document.querySelector('meta[name="user-puid"]')?.content;
                
                if (!userPuid) {
                    // Fallback: use the session-based endpoint
                    endpoint = '/api/albums/my';
                } else {
                    endpoint = `/api/albums/user/${userPuid}`;
                }
            }
        }
        
        const response = await fetch(endpoint);
        
        if (!response.ok) {
            throw new Error('Failed to load albums');
        }
        
        const albums = await response.json();
        renderAlbumSelectionList(albums);
        openModal('add-to-album-modal');
    } catch (error) {
        console.error('Error loading albums for selection:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to load albums', 'error');
        }
    }
}

/**
 * Renders the list of albums for selection
 */
function renderAlbumSelectionList(albums) {
    const list = document.getElementById('album-selection-list');
    
    if (!list) return;
    
    if (albums.length === 0) {
        list.innerHTML = `
            <div class="text-center py-8">
                <p class="text-gray-500 dark:text-gray-400 mb-4">You don't have any albums yet</p>
                <p class="text-sm text-gray-400">Create your first album to organize your media</p>
            </div>
        `;
        return;
    }
    
    list.innerHTML = albums.map(album => `
        <div class="flex items-center justify-between p-3 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
             onclick="addMediaToAlbumFromModal('${album.album_uid}', '${escapeHtml(album.title)}')">
            <div class="flex items-center gap-3">
                <div class="w-12 h-12 rounded overflow-hidden bg-gray-200 dark:bg-gray-600 flex-shrink-0">
                    ${album.cover_image ? `
                        <img src="${getFederatedMediaUrl(album.cover_image)}" class="w-full h-full object-cover" alt="">
                    ` : `
                        <svg class="w-full h-full p-2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
                        </svg>
                    `}
                </div>
                <div>
                    <h4 class="font-medium primary-text">${escapeHtml(album.title)}</h4>
                    <p class="text-sm secondary-text">${album.media_count} ${album.media_count === 1 ? 'item' : 'items'}</p>
                </div>
            </div>
            <svg class="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path>
            </svg>
        </div>
    `).join('');
}

/**
 * Adds the current media to the selected album
 */
async function addMediaToAlbumFromModal(albumUid, albumTitle) {
    if (!window.currentMediaIdForAlbum) {
        if (App && App.Toast) {
            App.Toast.show('Media information not available', 'error');
        }
        return;
    }
    
    try {
        const response = await fetch(`/api/albums/${albumUid}/media`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                media_id: parseInt(window.currentMediaIdForAlbum)
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to add media to album');
        }
        
        closeModal('add-to-album-modal');
        if (App && App.Toast) {
            App.Toast.show(`Added to "${albumTitle}"`, 'success');
        }
    } catch (error) {
        console.error('Error adding media to album:', error);
        if (App && App.Toast) {
            App.Toast.show(error.message || 'Failed to add to album', 'error');
        }
    }
}

/**
 * Creates a new album and adds the current media to it
 */
function createNewAlbumFromMedia() {
    closeModal('add-to-album-modal');
    
    // Set group context if we're in a group so the new album is created there
    if (window.currentAlbumGroupContext) {
        window.groupPuid = window.currentAlbumGroupContext;
    }
    
    openCreateAlbumModal();
    
    // Store the media ID so we can add it after creating the album
    window.pendingMediaIdForNewAlbum = window.currentMediaIdForAlbum;
}

/**
 * Opens modal to bulk add multiple media items to the current album
 */
async function openBulkAddMediaModal() {
    if (!currentAlbumData) {
        if (App && App.Toast) {
            App.Toast.show('No album selected', 'error');
        }
        return;
    }
    
    try {
        // Get media - for groups, only get current user's group media
        let endpoint;
        
        if (window.groupPuid) {
            // For groups, get only the current user's media from the group
            endpoint = `/api/albums/group-media/${window.groupPuid}`;
        } else if (window.location.pathname.includes('/my_media')) {
            endpoint = '/api/my-media-for-album';
        } else {
            endpoint = `/api/user-media-for-album/${window.viewer_puid || document.querySelector('[data-viewer-puid]')?.dataset.viewerPuid}`;
        }
        
        const response = await fetch(endpoint);
        
        if (!response.ok) {
            throw new Error('Failed to load media');
        }
        
        const allMedia = await response.json();
        
        // Filter out media already in this album
        const albumMediaIds = new Set(currentAlbumData.media.map(m => m.id));
        const availableMedia = allMedia.filter(m => !albumMediaIds.has(m.id));
        
        window.availableMediaForAlbum = availableMedia;
        window.selectedMediaForAlbum = [];
        
        renderBulkMediaSelectionGrid(availableMedia);
        openModal('bulk-add-media-modal');
    } catch (error) {
        console.error('Error loading media for album:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to load media', 'error');
        }
    }
}

/**
 * Renders the bulk media selection grid
 */
function renderBulkMediaSelectionGrid(mediaItems) {
    const grid = document.getElementById('bulk-media-selection-grid');
    
    if (!grid) return;
    
    if (mediaItems.length === 0) {
        grid.innerHTML = `
            <div class="col-span-full text-center py-12">
                <p class="text-gray-500 dark:text-gray-400">No additional media available</p>
                <p class="text-sm text-gray-400 mt-2">All your media is already in this album</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = mediaItems.map(media => {
        const displayUrl = getMediaDisplayUrl(media, true);
        const fullUrl = getFederatedMediaUrl(media);
        const isSelected = window.selectedMediaForAlbum.includes(media.id);
        
        return `
            <div class="media-selection-item ${isSelected ? 'selected' : ''}" 
                 data-media-id="${media.id}"
                 data-media-type="${media.media_type}"
                 onclick="toggleBulkMediaSelection(${media.id})">
                <div class="selection-checkbox">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7"></path>
                    </svg>
                </div>
                ${media.media_type === 'image' ? `
                    <img src="${displayUrl}" class="w-full h-full object-cover" alt="" loading="lazy" onerror="this.src='${fullUrl}'">
                ` : `
                    <video class="w-full h-full object-cover" muted>
                        <source src="${fullUrl}" type="video/mp4">
                    </video>
                    <div class="absolute inset-0 flex items-center justify-center bg-black bg-opacity-30 pointer-events-none">
                        <svg class="w-8 h-8 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z"/>
                        </svg>
                    </div>
                `}
            </div>
        `;
    }).join('');
    
    updateBulkSelectedCount();
}

/**
 * Toggles selection of a media item in bulk selection
 */
function toggleBulkMediaSelection(mediaId) {
    const index = window.selectedMediaForAlbum.indexOf(mediaId);
    
    if (index > -1) {
        window.selectedMediaForAlbum.splice(index, 1);
    } else {
        window.selectedMediaForAlbum.push(mediaId);
    }
    
    // Update UI
    const element = document.querySelector(`.media-selection-item[data-media-id="${mediaId}"]`);
    if (element) {
        if (index > -1) {
            element.classList.remove('selected');
        } else {
            element.classList.add('selected');
        }
    }
    
    updateBulkSelectedCount();
}

/**
 * Filters media in the bulk selection modal
 */
function filterBulkModalMedia(type) {
    // Update button states
    document.querySelectorAll('.active-modal-filter').forEach(btn => {
        btn.classList.remove('active-modal-filter');
    });
    document.querySelector(`[data-filter="${type}"]`)?.classList.add('active-modal-filter');
    
    // Filter media items
    const items = document.querySelectorAll('.media-selection-item');
    items.forEach(item => {
        const mediaType = item.dataset.mediaType;
        
        if (type === 'all' || mediaType === type) {
            item.style.display = '';
        } else {
            item.style.display = 'none';
        }
    });
}

/**
 * Updates the selected media count display
 */
function updateBulkSelectedCount() {
    const countElement = document.getElementById('bulk-selected-count');
    if (countElement) {
        countElement.textContent = window.selectedMediaForAlbum.length;
    }
}

/**
 * Adds all selected media to the current album
 */
async function addBulkSelectedMedia() {
    if (!currentAlbumData) {
        if (App && App.Toast) {
            App.Toast.show('No album selected', 'error');
        }
        return;
    }
    
    if (window.selectedMediaForAlbum.length === 0) {
        if (App && App.Toast) {
            App.Toast.show('Please select at least one media item', 'error');
        }
        return;
    }
    
    try {
        // Add each selected media item
        const promises = window.selectedMediaForAlbum.map(mediaId => 
            fetch(`/api/albums/${currentAlbumData.album_uid}/media`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ media_id: mediaId })
            })
        );
        
        const results = await Promise.all(promises);
        
        const failedCount = results.filter(r => !r.ok).length;
        const successCount = results.length - failedCount;
        
        closeModal('bulk-add-media-modal');
        
        if (successCount > 0) {
            if (App && App.Toast) {
                App.Toast.show(`Added ${successCount} item${successCount > 1 ? 's' : ''} to album`, 'success');
            }
            
            // Reload the album view
            await viewAlbum(currentAlbumData.album_uid);
        }
        
        if (failedCount > 0) {
            if (App && App.Toast) {
                App.Toast.show(`Failed to add ${failedCount} item${failedCount > 1 ? 's' : ''}`, 'error');
            }
        }
    } catch (error) {
        console.error('Error adding media to album:', error);
        if (App && App.Toast) {
            App.Toast.show('Failed to add media', 'error');
        }
    }
}

/**
 * Helper function to get federated media URL
 */
function getFederatedMediaUrl(media) {
    // Use the same path-based URL that works for galleries
    const encodedPath = media.media_file_path.split('/').map(encodeURIComponent).join('/');
    if (media.origin_hostname && media.origin_hostname !== window.location.hostname) {
        const protocol = window.location.protocol;
        return `${protocol}//${media.origin_hostname}/media/${media.puid}/${encodedPath}`;
    }
    return `/media/${media.puid}/${encodedPath}`;
}

/**
 * Gets the appropriate URL for media display - thumbnail for local images, full URL for remote or videos
 * @param {Object} media - Media object with puid, media_file_path, media_type, origin_hostname
 * @param {boolean} useThumbnail - Whether to use thumbnail (default true for images)
 * @returns {string} URL to use for displaying the media
 */
function getMediaDisplayUrl(media, useThumbnail = true) {
    const isRemote = media.origin_hostname && media.origin_hostname !== window.location.hostname;
    const isImage = media.media_type === 'image';
    
    // For remote media or videos, always use full URL
    if (isRemote || !isImage || !useThumbnail) {
        return getFederatedMediaUrl(media);
    }
    
    // For local images, use thumbnail with full URL as fallback
    return `/thumbnails/${media.puid}/${media.media_file_path}`;
}

/**
 * Helper function to escape HTML
 */
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Modify the existing filterMedia function to handle returning from albums view
(function() {
    const originalFilterMedia = window.filterMedia;
    
    window.filterMedia = function(type) {
        // If we're in albums view, hide it and show media grid
        const albumsContainer = document.getElementById('albums-container');
        const mediaGridContainer = document.getElementById('media-grid-container');
        
        if (albumsContainer && !albumsContainer.classList.contains('hidden')) {
            albumsContainer.classList.add('hidden');
            
            // Also hide single album view if it's showing
            const singleAlbumView = document.getElementById('single-album-view');
            if (singleAlbumView && !singleAlbumView.classList.contains('hidden')) {
                singleAlbumView.classList.add('hidden');
                const albumsGrid = document.getElementById('albums-grid');
                if (albumsGrid && albumsGrid.parentElement) {
                    albumsGrid.parentElement.classList.remove('hidden');
                }
            }
            
            if (mediaGridContainer) {
                mediaGridContainer.classList.remove('hidden');
            }
        }
        
        // Call original filter function
        if (originalFilterMedia) {
            originalFilterMedia(type);
        }
    };
})();

// =================================================================================
// CONNECTION TABS (Friends Page)
// =================================================================================

/**
 * Switches between tabs on the connections/friends page
 * @param {string} tabName - The name of the tab to switch to ('friends', 'pages', 'requests', 'blocked')
 */
function switchConnectionTab(tabName) {
    // Hide all tabs
    document.querySelectorAll('.connection-tab-content').forEach(tab => {
        tab.classList.add('hidden');
    });
    
    // Remove active state from all buttons (support both old and new class names)
    document.querySelectorAll('.connection-tab-button, .tab-button').forEach(btn => {
        // Only process buttons that have a data-tab attribute (connection tabs)
        if (btn.hasAttribute('data-tab')) {
            btn.classList.remove('active');
        }
    });
    
    // Show selected tab
    const selectedTab = document.getElementById(tabName + '-tab');
    if (selectedTab) {
        selectedTab.classList.remove('hidden');
    }
    
    // Add active state to selected button
    const activeButton = document.querySelector(`[data-tab="${tabName}"]`);
    if (activeButton) {
        activeButton.classList.add('active');
    }
    
    // Show/hide search bar based on tab
    const searchBar = document.querySelector('.connections-search-bar');
    if (searchBar) {
        if (tabName === 'friends' || tabName === 'pages') {
            searchBar.style.display = '';
        } else {
            searchBar.style.display = 'none';
        }
    }
    
    // Clear search when switching tabs
    const searchInput = document.getElementById('connectionsSearchInput');
    if (searchInput) {
        searchInput.value = '';
        const event = new Event('input', { bubbles: true });
        searchInput.dispatchEvent(event);
    }
}

/**
 * Initialize connections page search functionality
 * This is called when the connections page content is loaded
 */
function initConnectionsSearch() {
    const searchInput = document.getElementById('connectionsSearchInput');
    if (!searchInput) return;
    
    // Remove any existing listeners to avoid duplicates
    const newSearchInput = searchInput.cloneNode(true);
    searchInput.parentNode.replaceChild(newSearchInput, searchInput);
    
    // Add the search listener
    newSearchInput.addEventListener('input', function() {
        const searchTerm = this.value.toLowerCase().trim();
        const items = document.querySelectorAll('.connection-item');
        const noResultsMessage = document.getElementById('no-search-results-message');
        let visibleCount = 0;

        items.forEach(item => {
            const searchText = item.getAttribute('data-search-text') || '';
            if (searchText.includes(searchTerm)) {
                item.style.display = '';
                visibleCount++;
            } else {
                item.style.display = 'none';
            }
        });

        if (visibleCount === 0 && searchTerm) {
            noResultsMessage.textContent = `No results found for "${searchTerm}"`;
            noResultsMessage.style.display = 'block';
        } else {
            noResultsMessage.style.display = 'none';
        }
    });
}

// ========================================
// 2FA FUNCTIONS
// ========================================

// 2FA Setup Functions
async function start2FASetup() {
    const password = document.getElementById('setup2fa-password').value;
    const errorDiv = document.getElementById('setup2fa-step1-error');
    
    if (!password) {
        errorDiv.textContent = 'Please enter your password';
        errorDiv.classList.remove('hidden');
        return;
    }
    
    try {
        const response = await fetch('/settings/2fa/setup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: password })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Show step 2
            document.getElementById('setup2fa-step1').classList.add('hidden');
            document.getElementById('setup2fa-step2').classList.remove('hidden');
            
            // Display QR code
            document.getElementById('setup2fa-qr-container').innerHTML = 
                `<img src="data:image/png;base64,${data.qr_code}" alt="QR Code" class="mx-auto">`;
            document.getElementById('setup2fa-secret').textContent = data.secret;
            
            // Store backup codes for later
            App.Settings.TwoFactor.currentBackupCodes = data.backup_codes;
            
            errorDiv.classList.add('hidden');
        } else {
            errorDiv.textContent = data.error;
            errorDiv.classList.remove('hidden');
        }
    } catch (error) {
        errorDiv.textContent = 'An error occurred. Please try again.';
        errorDiv.classList.remove('hidden');
    }
}

async function verify2FASetup() {
    const code = document.getElementById('setup2fa-otp').value;
    const errorDiv = document.getElementById('setup2fa-step2-error');
    
    if (code.length !== 6) {
        errorDiv.textContent = 'Please enter a 6-digit code';
        errorDiv.classList.remove('hidden');
        return;
    }
    
    try {
        const response = await fetch('/settings/2fa/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ otp_code: code })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            // Show step 3 with backup codes
            document.getElementById('setup2fa-step2').classList.add('hidden');
            document.getElementById('setup2fa-step3').classList.remove('hidden');
            
            // Display backup codes
            const codesContainer = document.getElementById('setup2fa-backup-codes');
            codesContainer.innerHTML = App.Settings.TwoFactor.currentBackupCodes
                .map(code => `<code class="text-sm font-mono bg-gray-100 dark:bg-gray-700 p-2 rounded text-center">${code}</code>`)
                .join('');
            
            errorDiv.classList.add('hidden');
        } else {
            errorDiv.textContent = data.error;
            errorDiv.classList.remove('hidden');
        }
    } catch (error) {
        errorDiv.textContent = 'An error occurred. Please try again.';
        errorDiv.classList.remove('hidden');
    }
}

function cancel2FASetup() {
    closeModal('setup2faModal');
}

function finish2FASetup() {
    closeModal('setup2faModal');
    // Reload 2FA status
    App.Settings.TwoFactor.loadStatus();
    App.Modal.showInfo('Two-factor authentication has been enabled successfully!');
}

function download2FABackupCodes() {
    const codes = App.Settings.TwoFactor.currentBackupCodes;
    const text = 'Nebulae Two-Factor Authentication Backup Codes\n' +
                 '==============================================\n\n' +
                 'IMPORTANT: Keep these codes in a safe place!\n' +
                 'Each code can only be used once.\n\n' +
                 'Generated: ' + new Date().toLocaleString() + '\n\n' +
                 'Backup Codes:\n' +
                 codes.map((code, i) => `${i + 1}. ${code}`).join('\n');
    
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'nebulae-backup-codes-' + Date.now() + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// 2FA Management Functions
function show2FADisableModal() {
    closeModal('manage2faModal');
    openModal('disable2faModal');
    document.getElementById('disable2fa-password').value = '';
    document.getElementById('disable2fa-otp').value = '';
}

function show2FARegenerateModal() {
    closeModal('manage2faModal');
    openModal('regenerate2faModal');
    document.getElementById('regenerate2fa-password').value = '';
    document.getElementById('regenerate2fa-otp').value = '';
    document.getElementById('regenerate2fa-success').classList.add('hidden');
}

async function confirmDisable2FA() {
    const password = document.getElementById('disable2fa-password').value;
    const otp = document.getElementById('disable2fa-otp').value;
    const errorDiv = document.getElementById('disable2fa-error');
    
    if (!password || !otp) {
        errorDiv.textContent = 'Please fill in all fields';
        errorDiv.classList.remove('hidden');
        return;
    }
    
    try {
        const response = await fetch('/settings/2fa/disable', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: password, otp_code: otp })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            closeModal('disable2faModal');
            App.Settings.TwoFactor.loadStatus();
            App.Modal.showInfo('Two-factor authentication has been disabled.');
        } else {
            errorDiv.textContent = data.error;
            errorDiv.classList.remove('hidden');
        }
    } catch (error) {
        errorDiv.textContent = 'An error occurred. Please try again.';
        errorDiv.classList.remove('hidden');
    }
}

async function confirmRegenerate2FA() {
    const password = document.getElementById('regenerate2fa-password').value;
    const otp = document.getElementById('regenerate2fa-otp').value;
    const errorDiv = document.getElementById('regenerate2fa-error');
    const successDiv = document.getElementById('regenerate2fa-success');
    
    if (!password || !otp) {
        errorDiv.textContent = 'Please fill in all fields';
        errorDiv.classList.remove('hidden');
        return;
    }
    
    try {
        const response = await fetch('/settings/2fa/regenerate_backup_codes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_password: password, otp_code: otp })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            errorDiv.classList.add('hidden');
            
            // Display new codes
            let codesHTML = '<div class="bg-yellow-50 dark:bg-yellow-900 border border-yellow-200 dark:border-yellow-700 rounded p-4">';
            codesHTML += '<h4 class="font-semibold text-yellow-800 dark:text-yellow-200 mb-2">Your New Backup Codes:</h4>';
            codesHTML += '<div class="grid grid-cols-2 gap-2 mb-3">';
            data.backup_codes.forEach(code => {
                codesHTML += `<code class="text-sm font-mono bg-white dark:bg-gray-800 p-2 rounded text-center">${code}</code>`;
            });
            codesHTML += '</div>';
            codesHTML += '<button onclick="downloadRegeneratedCodes(' + JSON.stringify(data.backup_codes) + ')" class="w-full bg-yellow-600 hover:bg-yellow-700 text-white font-semibold py-2 px-4 rounded-lg">Download Codes</button>';
            codesHTML += '</div>';
            
            successDiv.innerHTML = codesHTML;
            successDiv.classList.remove('hidden');
            
            // Hide the regenerate button
            document.getElementById('regenerate2fa-btn').classList.add('hidden');
        } else {
            errorDiv.textContent = data.error;
            errorDiv.classList.remove('hidden');
        }
    } catch (error) {
        errorDiv.textContent = 'An error occurred. Please try again.';
        errorDiv.classList.remove('hidden');
    }
}

function downloadRegeneratedCodes(codes) {
    const text = 'Nebulae Two-Factor Authentication Backup Codes\n' +
                 '==============================================\n\n' +
                 'IMPORTANT: Keep these codes in a safe place!\n' +
                 'Each code can only be used once.\n\n' +
                 'Generated: ' + new Date().toLocaleString() + '\n\n' +
                 'Backup Codes:\n' +
                 codes.map((code, i) => `${i + 1}. ${code}`).join('\n');
    
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'nebulae-backup-codes-' + Date.now() + '.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Make functions globally available
window.switchConnectionTab = switchConnectionTab;
window.initConnectionsSearch = initConnectionsSearch;

// =================================================================================
// KICK-OFF
// =================================================================================
document.addEventListener('DOMContentLoaded', () => {
    // Initialize only the core components
    App.initCore();

});