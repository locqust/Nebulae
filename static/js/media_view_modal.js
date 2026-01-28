// media_view_modal.js - Opens media in a modal overlay

/**
 * Open media in modal view
 * @param {string} muid - The media MUID to display
 */
function openMediaViewModal(muid) {
    // Ensure modal exists
    let modal = document.getElementById('mediaViewModal');
    if (!modal) {
        // Create modal structure dynamically
        modal = document.createElement('div');
        modal.id = 'mediaViewModal';
        modal.className = 'fixed inset-0 bg-black bg-opacity-90 z-50 overflow-y-auto hidden';
        modal.innerHTML = `
            <div class="min-h-screen px-0 sm:px-4 py-2 sm:py-8 relative">
                <!-- Close Button -->
                <button onclick="closeMediaViewModal()" class="absolute top-2 right-2 sm:top-4 sm:right-4 z-[60] text-white hover:text-gray-300 transition-colors bg-black bg-opacity-70 rounded-full p-2 shadow-lg">
                    <svg class="w-6 h-6 sm:w-8 sm:h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
                
                <!-- Content Container -->
                <div id="mediaViewModalContent" class="relative w-full overflow-x-hidden">
                    <div class="flex items-center justify-center min-h-screen">
                        <div class="loader-spinner"></div>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        // Add event listeners
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeMediaViewModal();
            }
        });
    }
    
    const content = document.getElementById('mediaViewModalContent');
    
    // Show modal with loading spinner
    modal.classList.remove('hidden');
    content.innerHTML = `
        <div class="flex items-center justify-center min-h-screen">
            <div class="loader-spinner"></div>
        </div>
    `;
    
    // Prevent body scroll
    document.body.style.overflow = 'hidden';
    
    // Fetch the media view content
    fetch(`/api/media/${muid}/modal`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Failed to load media');
            }
            return response.text();
        })
        .then(html => {
            content.innerHTML = html;
            
            // Execute any inline scripts in the loaded content
            const scripts = content.querySelectorAll('script');
            scripts.forEach(script => {
                const newScript = document.createElement('script');
                if (script.src) {
                    newScript.src = script.src;
                } else {
                    newScript.textContent = script.textContent;
                }
                document.body.appendChild(newScript);
                // Remove the script after execution to avoid duplicates
                setTimeout(() => newScript.remove(), 100);
            });
            
            // Convert UTC timestamps to user's timezone
            if (App && App.Utils && typeof App.Utils.convertAllUTCTimestamps === 'function') {
                App.Utils.convertAllUTCTimestamps();
            }
        })
        .catch(error => {
            console.error('Error loading media view:', error);
            content.innerHTML = `
                <div class="flex flex-col items-center justify-center min-h-screen text-white">
                    <svg class="w-16 h-16 mb-4 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <p class="text-xl mb-2">Failed to load media</p>
                    <button onclick="closeMediaViewModal()" class="text-blue-400 hover:underline">Close</button>
                </div>
            `;
        });
}

/**
 * Close the media view modal
 */
function closeMediaViewModal() {
    const modal = document.getElementById('mediaViewModal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = '';
    }
}

/**
 * Navigate to another media item within the modal
 * @param {string} muid - The media MUID to navigate to
 */
function navigateToMediaInModal(muid) {
    openMediaViewModal(muid);
}

/**
 * Initialize media view modal - intercept media links
 */
document.addEventListener('DOMContentLoaded', function() {
    // Intercept clicks on post media links
    document.addEventListener('click', function(e) {
        const mediaLink = e.target.closest('.post-media-item-link, .comment-media-item-link, .gallery-media-item-link');
        if (mediaLink) {
            e.preventDefault();
            e.stopPropagation();
            
            const href = mediaLink.getAttribute('href');
            const muidMatch = href.match(/\/media\/([a-f0-9-]+)/);
            if (muidMatch) {
                openMediaViewModal(muidMatch[1]);
            }
        }
    });
    
    // Handle ESC key to close modal
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            const modal = document.getElementById('mediaViewModal');
            if (modal && !modal.classList.contains('hidden')) {
                closeMediaViewModal();
            }
        }
    });
    
    // Check for auto-open parameter (from notifications)
    const urlParams = new URLSearchParams(window.location.search);
    const openMedia = urlParams.get('open_media');
    if (openMedia) {
        // Small delay to ensure page is loaded
        setTimeout(() => openMediaViewModal(openMedia), 100);
    }
});