// static/js/media_carousel.js
console.log('media_carousel.js script loaded.');

const mediaCarouselModal = document.getElementById('mediaCarouselModal');
// FIX: Changed selector from '.media-carousel-close-button' to '.media-carousel-close'
const closeCarouselButton = mediaCarouselModal.querySelector('.media-carousel-close');
const mediaCarouselDisplay = mediaCarouselModal.querySelector('.media-carousel-display');
const mediaCarouselCaption = mediaCarouselModal.querySelector('.media-carousel-caption');
const prevButton = mediaCarouselModal.querySelector('.prev-button');
const nextButton = mediaCarouselModal.querySelector('.next-button');

const mediaCarouselContent = mediaCarouselModal.querySelector('.media-carousel-content');

// Create and append Edit Alt Text button
const editAltTextButton = document.createElement('button');
editAltTextButton.classList.add('edit-alt-text-button', 'bg-gray-700', 'text-white', 'py-1', 'px-3', 'rounded-full', 'text-sm', 'hover:bg-gray-600', 'transition-colors', 'duration-200', 'flex', 'items-center', 'gap-1', 'mt-2');
editAltTextButton.innerHTML = `<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.38-2.828-2.829z"></path></svg> Edit Alt Text`;
// Append this button to the carousel content area, typically below the media display
if (mediaCarouselContent) {
    mediaCarouselContent.appendChild(editAltTextButton);
} else {
    console.warn("mediaCarouselContent not found, cannot append editAltTextButton.");
}


// Create and append Alt Text Edit Container
const altTextEditContainer = document.createElement('div');
altTextEditContainer.classList.add('alt-text-edit-container', 'hidden', 'flex', 'flex-col', 'items-center', 'gap-2', 'mt-4', 'w-full', 'max-w-md');
const altTextTextarea = document.createElement('textarea');
altTextTextarea.classList.add('alt-text-textarea', 'w-full', 'p-2', 'rounded-md', 'bg-gray-800', 'text-white', 'border', 'border-gray-600', 'focus:outline-none', 'focus:border-blue-500', 'resize-vertical');
altTextTextarea.rows = 3;
altTextTextarea.placeholder = 'Enter alt text for this media...';
const altTextButtons = document.createElement('div');
altTextButtons.classList.add('flex', 'gap-2');
const saveAltTextButton = document.createElement('button');
saveAltTextButton.classList.add('save-alt-text-button', 'bg-green-500', 'text-white', 'py-2', 'px-4', 'rounded-full', 'hover:bg-green-700', 'transition-colors', 'duration-200');
saveAltTextButton.textContent = 'Save';
const cancelAltTextButton = document.createElement('button');
cancelAltTextButton.classList.add('cancel-alt-text-button', 'bg-red-500', 'text-white', 'py-2', 'px-4', 'rounded-full', 'hover:bg-red-700', 'transition-colors', 'duration-200');
cancelAltTextButton.textContent = 'Cancel';

altTextButtons.appendChild(saveAltTextButton);
altTextButtons.appendChild(cancelAltTextButton);
altTextEditContainer.appendChild(altTextTextarea);
altTextEditContainer.appendChild(altTextButtons);
if (mediaCarouselContent) {
    mediaCarouselContent.appendChild(altTextEditContainer);
} else {
    console.warn("mediaCarouselContent not found, cannot append altTextEditContainer.");
}


let currentMediaItems = [];
let currentMediaIndex = 0;

function openMediaCarousel(mediaArray, clickedIndex) {
    console.log('openMediaCarousel called with mediaArray:', mediaArray, 'clickedIndex:', clickedIndex);
    currentMediaItems = mediaArray;
    currentMediaIndex = clickedIndex;

    renderMediaInCarousel();
    if (mediaCarouselModal) {
        mediaCarouselModal.style.display = 'flex';
    } else {
        console.error("mediaCarouselModal not found. Cannot open carousel.");
    }
}

function renderMediaInCarousel() {
    if (!mediaCarouselDisplay) {
        console.error("mediaCarouselDisplay not found. Cannot render media.");
        return;
    }
    mediaCarouselDisplay.innerHTML = '';
    mediaCarouselCaption.textContent = '';

    if (currentMediaItems.length === 0) {
        const noMediaText = document.createElement('p');
        noMediaText.classList.add('text-white');
        noMediaText.textContent = 'No media to display.';
        if (mediaCarouselDisplay) mediaCarouselDisplay.appendChild(noMediaText);
        if (editAltTextButton) editAltTextButton.style.display = 'none';
        if (altTextEditContainer) altTextEditContainer.classList.add('hidden');
        return;
    }

    const mediaItem = currentMediaItems[currentMediaIndex];
    
    let mediaSrc = mediaItem.media_url;
    if (mediaSrc && !mediaSrc.startsWith('http')) {
        mediaSrc = `${window.location.origin}${mediaSrc}`;
    }
    
    const altText = mediaItem.alt_text || (mediaItem.media_type === 'video' ? 'Full size video' : 'Full size image');

    let mediaElement;
    if (mediaItem.media_type === 'image') {
        mediaElement = document.createElement('img');
        mediaElement.src = mediaSrc;
        mediaElement.alt = altText;
    } else if (mediaItem.media_type === 'video') {
        mediaElement = document.createElement('video');
        mediaElement.src = mediaSrc;
        mediaElement.controls = true;
        mediaElement.autoplay = true;
        mediaElement.loop = true;
        mediaElement.setAttribute('playsinline', '');
        mediaElement.setAttribute('aria-label', altText);
        mediaElement.setAttribute('title', altText);
    } else {
        mediaElement = document.createElement('div');
        mediaElement.textContent = `Unsupported media type: ${mediaItem.media_type}`;
        mediaElement.classList.add('text-white', 'text-center', 'p-4');
    }

    mediaCarouselDisplay.appendChild(mediaElement);
    if (mediaCarouselCaption) mediaCarouselCaption.textContent = altText;

    updateCarouselNavButtons();
    
    // BUG FIX: Referenced window.appConfig object for logged in user data.
    const isOwner = (mediaItem.username === (window.appConfig && window.appConfig.loggedInUsername) || mediaItem.puid === (window.appConfig && window.appConfig.loggedInUserPuid));
    console.log(`Media owner check: mediaItem.puid (${mediaItem.puid}) vs window.loggedInUserPuid (${window.appConfig && window.appConfig.loggedInUserPuid}). Is owner: ${isOwner}`);


    if ((isOwner || (window.appConfig && window.appConfig.isCurrentUserAdmin)) && mediaItem.id) {
        if (editAltTextButton) editAltTextButton.style.display = 'block';
        if (altTextEditContainer) altTextEditContainer.classList.add('hidden');
    } else {
        if (editAltTextButton) editAltTextButton.style.display = 'none';
        if (altTextEditContainer) altTextEditContainer.classList.add('hidden');
    }
}

function updateCarouselNavButtons() {
    if (currentMediaItems.length > 1) {
        if (prevButton) prevButton.style.display = 'block';
        if (nextButton) nextButton.style.display = 'block';
    } else {
        if (prevButton) prevButton.style.display = 'none';
        if (nextButton) nextButton.style.display = 'none';
    }
}

function closeMediaCarousel() {
    const videoElement = mediaCarouselDisplay.querySelector('video');
    if (videoElement) {
        videoElement.pause();
        videoElement.currentTime = 0;
    }
    if (mediaCarouselModal) {
        mediaCarouselModal.style.display = 'none';
        if (mediaCarouselCaption) mediaCarouselCaption.style.display = 'block';
        if (editAltTextButton) editAltTextButton.style.display = 'block';
        if (altTextEditContainer) altTextEditContainer.classList.add('hidden');
    }
}

function nextMedia() {
    if (currentMediaItems.length === 0) return;
    currentMediaIndex = (currentMediaIndex === currentMediaItems.length - 1) ? 0 : currentMediaIndex + 1;
    renderMediaInCarousel();
}

function prevMedia() {
    if (currentMediaItems.length === 0) return;
    currentMediaIndex = (currentMediaIndex === 0) ? currentMediaItems.length - 1 : currentMediaIndex - 1;
    renderMediaInCarousel();
}

if (editAltTextButton) {
    editAltTextButton.addEventListener('click', () => {
        console.log('Edit Alt Text button clicked!');
        if (currentMediaItems.length === 0) {
            console.log('No media to edit. currentMediaItems is empty.');
            return;
        }

        const mediaItem = currentMediaItems[currentMediaIndex];
        if (!mediaItem || mediaItem.id === undefined) {
            console.error('Current media item or its ID is undefined. Cannot edit alt text.');
            alert('Cannot edit alt text: Media ID not found.');
            return;
        }
        altTextTextarea.value = mediaItem.alt_text || '';
        if (mediaCarouselCaption) mediaCarouselCaption.style.display = 'none';
        if (editAltTextButton) editAltTextButton.style.display = 'none';
        if (altTextEditContainer) {
            altTextEditContainer.classList.remove('hidden');
            altTextTextarea.focus();
            altTextTextarea.style.height = 'auto';
            altTextTextarea.style.height = (altTextTextarea.scrollHeight) + 'px';
        }
    });
} else {
    console.warn("editAltTextButton not found, alt text editing will not work.");
}


if (saveAltTextButton) {
    saveAltTextButton.addEventListener('click', async () => {
        console.log('Save Alt Text button clicked!');
        if (currentMediaItems.length === 0) return;

        const mediaItem = currentMediaItems[currentMediaIndex];
        const mediaId = mediaItem.id;
        const newAltText = altTextTextarea.value;

        try {
            const response = await fetch(`/update_media_alt_text/${mediaId}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ alt_text: newAltText }),
            });

            const result = await response.json();
            if (response.ok) {
                mediaItem.alt_text = newAltText;
                if (mediaCarouselCaption) mediaCarouselCaption.textContent = newAltText;
                alert('Alt text updated successfully!');

                const originalMediaElement = document.querySelector(`[data-muid="${mediaItem.muid}"]`);
                if (originalMediaElement) {
                    originalMediaElement.dataset.altText = newAltText;
                    const altTextDisplay = originalMediaElement.querySelector('.alt-text-display');
                    if (altTextDisplay) {
                        altTextDisplay.textContent = newAltText || 'No alt text';
                    }
                }

            } else {
                alert(result.error || 'Failed to update alt text.');
            }
        } catch (error) {
            console.error('Error updating alt text:', error);
            alert('An unexpected error occurred while updating alt text.');
        } finally {
            if (mediaCarouselCaption) mediaCarouselCaption.style.display = 'block';
            if (editAltTextButton) editAltTextButton.style.display = 'block';
            if (altTextEditContainer) altTextEditContainer.classList.add('hidden');
        }
    });
} else {
    console.warn("saveAltTextButton not found, alt text saving will not work.");
}


if (cancelAltTextButton) {
    cancelAltTextButton.addEventListener('click', () => {
        console.log('Cancel Alt Text button clicked!');
        if (mediaCarouselCaption) mediaCarouselCaption.style.display = 'block';
        if (editAltTextButton) editAltTextButton.style.display = 'block';
        if (altTextEditContainer) altTextEditContainer.classList.add('hidden');
        alert('Alt text edit cancelled.');
    });
} else {
    console.warn("cancelAltTextButton not found, alt text cancelling will not work.");
}


if (closeCarouselButton) {
    closeCarouselButton.addEventListener('click', closeMediaCarousel);
}
if (prevButton) {
    prevButton.addEventListener('click', prevMedia);
}
if (nextButton) {
    nextButton.addEventListener('click', nextMedia);
}

if (mediaCarouselModal) {
    mediaCarouselModal.addEventListener('click', (event) => {
        if (event.target === mediaCarouselModal) {
            closeMediaCarousel();
        }
    });
}

document.addEventListener('keydown', (event) => {
    if (mediaCarouselModal && mediaCarouselModal.style.display === 'flex') {
        if (event.key === 'Escape') {
            closeMediaCarousel();
        } else if (event.key === 'ArrowLeft') {
            prevMedia();
        } else if (event.key === 'ArrowRight') {
            nextMedia();
        }
    }
});

// Universal event listener for all media items on the page using event delegation
document.addEventListener('click', (event) => {
    const clickedLink = event.target.closest('.post-media-item-link, .comment-media-item-link, .gallery-media-item-link');
    if (clickedLink) {
        // NEW: Only open carousel if explicitly requested
        if (clickedLink.hasAttribute('data-use-carousel')) {
            event.preventDefault();
            // Continue to carousel logic below
        } else {
            // Let the link navigate to media view page
            return;
        }
    }

    const clickedPostMediaItem = event.target.closest('.post-media-item');
    const clickedGalleryMediaItem = event.target.closest('.gallery-media-item');
    const clickedCommentMediaItem = event.target.closest('.comment-media-grid-item');
    
    let mediaData = [];
    let clickedIndex = 0;

    if (clickedPostMediaItem) {
        const postCard = clickedPostMediaItem.closest('.post-card'); 
        if (postCard) {
            const mediaElementsInPost = Array.from(postCard.querySelectorAll('.post-media-item'));
            mediaData = mediaElementsInPost.map(item => ({
                id: parseInt(item.dataset.mediaId),
                muid: item.dataset.muid,
                media_url: item.dataset.mediaUrl,
                media_type: item.dataset.mediaType,
                alt_text: item.dataset.altText,
                username: item.dataset.username,
                puid: item.dataset.puid,
                origin_hostname: item.dataset.originHostname
            }));
            clickedIndex = parseInt(clickedPostMediaItem.dataset.mediaIndex);
        } else {
            console.error("Error: post-media-item clicked but its parent .post-card was not found.");
            return;
        }
    } else if (clickedGalleryMediaItem) {
        const allGalleryItems = Array.from(document.querySelectorAll('.gallery-media-item'));
        mediaData = allGalleryItems.map(item => ({
            id: parseInt(item.dataset.mediaId),
            muid: item.dataset.muid,
            media_url: item.dataset.mediaUrl,
            media_type: item.dataset.mediaType,
            alt_text: item.dataset.altText,
            username: item.dataset.username,
            puid: item.dataset.puid,
            origin_hostname: item.dataset.originHostname
        }));
        clickedIndex = allGalleryItems.findIndex(item => item === clickedGalleryMediaItem);
        
        if (clickedIndex === -1) {
            console.error("Error: Clicked gallery item not found in the collected gallery media data.");
            return;
        }
    } else if (clickedCommentMediaItem) {
        const commentId = clickedCommentMediaItem.dataset.commentId;
        const allCommentMediaItems = Array.from(document.querySelectorAll(`.comment-media-grid-item[data-comment-id="${commentId}"]`));
        mediaData = allCommentMediaItems.map(item => ({
            id: parseInt(item.dataset.mediaId),
            muid: item.dataset.muid,
            media_url: item.dataset.mediaUrl,
            media_type: item.dataset.mediaType,
            alt_text: item.dataset.altText,
            username: item.dataset.username,
            puid: item.dataset.puid,
            origin_hostname: item.dataset.originHostname,
            comment_id: parseInt(item.dataset.commentId)
        }));
        clickedIndex = allCommentMediaItems.findIndex(item => item === clickedCommentMediaItem);

        if (clickedIndex === -1) {
            console.error("Error: Clicked comment media item not found in the collected comment media data.");
            return;
        }
    }
    else {
        return;
    }
    
    if (mediaData.length > 0) {
        window.openMediaCarousel(mediaData, clickedIndex);
    } else {
        console.warn("Attempted to open carousel with empty mediaData array.");
    }
});


// NEW: Function to open media carousel for group profile pictures
// MOVED HERE FROM script.js for better code organization and to fix scope issues.
function openProfilePictureCarouselFromGroupProfile(element) {
    if (!element) return;

    const originalPath = element.dataset.originalProfilePath;
    const adminPuid = element.dataset.pictureAdminPuid; // Use the new attribute

    if (!originalPath || !adminPuid) {
        console.warn("Cannot open group profile picture carousel: missing original path or admin PUID.");
        return;
    }

    // BUG FIX: Referenced window.appConfig object for the base URL.
    const mediaUrl = `${window.appConfig.serveMediaBaseUrl}${adminPuid}/${originalPath}`;

    const mediaItem = {
        id: null,
        muid: element.dataset.muid || '',
        media_url: mediaUrl,
        media_type: 'image',
        alt_text: 'Group Profile Picture',
        puid: adminPuid, 
    };

    const mediaArray = [mediaItem];
    openMediaCarousel(mediaArray, 0);
}


// *** PROFILE PICTURE CAROUSEL FIX ***
// This function is called by the `onclick` on the profile picture.
// It now reads the raw data attributes and constructs the correct URL to the original media file.
function openProfilePictureCarouselFromProfile(element) {
    if (!element) return;

    const originalPath = element.dataset.originalProfilePath;
    const puid = element.dataset.profilePuid;

    // If there's no original path, we can't (and shouldn't) open the carousel.
    if (!originalPath) {
        console.warn("Cannot open profile picture carousel: data-original-profile-path is missing.");
        return;
    }

    // Build the correct URL to the original media file on the user's mapped volume.
    // BUG FIX: Referenced window.appConfig object for the base URL.
    const mediaUrl = `${window.appConfig.serveMediaBaseUrl}${puid}/${originalPath}`;

    const mediaItem = {
        id: null, // We don't have the media ID for a profile pic, but it's not needed for display.
        muid: element.dataset.muid || '',
        media_url: mediaUrl,
        media_type: 'image',
        alt_text: 'Profile Picture', // Alt text can be simple here.
        username: element.dataset.username,
        puid: puid,
    };

    // The mediaArray should contain only this single item.
    const mediaArray = [mediaItem];

    // Open the carousel with this single item at index 0.
    openMediaCarousel(mediaArray, 0);
}


// Expose functions globally so they can be called from HTML
window.openMediaCarousel = openMediaCarousel;
window.openProfilePictureCarouselFromProfile = openProfilePictureCarouselFromProfile;
// BUG FIX: Expose the new group profile picture function to the global scope as well.
window.openProfilePictureCarouselFromGroupProfile = openProfilePictureCarouselFromGroupProfile;