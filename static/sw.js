// Service Worker for NODE PWA
// Version 1.0.2 - Update this when you make changes to force updates

const CACHE_NAME = 'node-pwa-v2';
const RUNTIME_CACHE = 'node-runtime-v2';

// Assets to cache immediately on install
// Only include assets that we KNOW exist and won't fail
const PRECACHE_ASSETS = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/images/default_avatar.png',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
];

// Optional assets to cache (won't block if they fail)
const OPTIONAL_ASSETS = [
  '/offline',
  '/static/js/media_carousel.js',
  'https://cdn.tailwindcss.com',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap'
];

// Install event - cache core assets
self.addEventListener('install', (event) => {
  console.log('[Service Worker] Installing...');
  
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('[Service Worker] Precaching essential assets');
        
        // Cache essential assets (fail if any fail)
        return cache.addAll(PRECACHE_ASSETS)
          .then(() => {
            console.log('[Service Worker] Essential assets cached');
            
            // Try to cache optional assets (don't fail if they fail)
            return Promise.allSettled(
              OPTIONAL_ASSETS.map(url => 
                cache.add(url).catch(err => {
                  console.warn('[Service Worker] Failed to cache optional asset:', url, err);
                })
              )
            );
          });
      })
      .then(() => {
        console.log('[Service Worker] Installation complete, skipping waiting');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('[Service Worker] Installation failed:', error);
        // Still skip waiting so we don't block forever
        return self.skipWaiting();
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('[Service Worker] Activating...');
  
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME && cacheName !== RUNTIME_CACHE) {
            console.log('[Service Worker] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('[Service Worker] Claiming clients');
      return self.clients.claim();
    })
  );
});

// Fetch event - serve from cache when offline, otherwise network
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip cross-origin requests (except fonts and CDN)
  if (url.origin !== location.origin && 
      !url.host.includes('fonts.googleapis.com') &&
      !url.host.includes('fonts.gstatic.com') &&
      !url.host.includes('cdn.tailwindcss.com') &&
      !url.host.includes('cdnjs.cloudflare.com')) {
    return;
  }

  // Skip POST, PUT, DELETE requests (database writes)
  if (request.method !== 'GET') {
    return;
  }

  // Strategy: Network First with Cache Fallback
  // This is crucial for a social media app - always try to get fresh content
  event.respondWith(
    fetch(request)
      .then((response) => {
        // If we got a valid response, clone it and cache it
        if (response && response.status === 200) {
          const responseToCache = response.clone();
          
          caches.open(RUNTIME_CACHE).then((cache) => {
            // Don't cache API calls that modify data
            if (!url.pathname.includes('/api/') || request.method === 'GET') {
              cache.put(request, responseToCache);
            }
          });
        }
        
        return response;
      })
      .catch(() => {
        // Network failed, try cache
        return caches.match(request).then((cachedResponse) => {
          if (cachedResponse) {
            console.log('[Service Worker] Serving from cache:', request.url);
            return cachedResponse;
          }
          
          // If it's a navigation request and we have nothing cached, show offline page
          if (request.mode === 'navigate') {
            return caches.match('/offline').then((offlineResponse) => {
              if (offlineResponse) {
                return offlineResponse;
              }
              return new Response('Offline - NODE is not available', {
                status: 503,
                statusText: 'Service Unavailable',
                headers: new Headers({
                  'Content-Type': 'text/plain'
                })
              });
            });
          }
          
          // For other resources, return a generic offline response
          return new Response('Offline', {
            status: 503,
            statusText: 'Service Unavailable'
          });
        });
      })
  );
});

// Push notification event handler
self.addEventListener('push', (event) => {
  console.log('[Service Worker] Push notification received');
  
  let notificationData = {
    title: 'New Notification',
    body: 'You have a new notification',
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-192x192.png',
    url: '/'
  };
  
  // Parse the push payload if available
  if (event.data) {
    try {
      const data = event.data.json();
      notificationData = {
        title: data.title || notificationData.title,
        body: data.body || notificationData.body,
        icon: data.icon || notificationData.icon,
        badge: data.badge || notificationData.badge,
        url: data.url || notificationData.url,
        timestamp: data.timestamp || Date.now()
      };
    } catch (e) {
      console.error('[Service Worker] Error parsing push data:', e);
      // Try text format
      if (event.data.text) {
        notificationData.body = event.data.text();
      }
    }
  }
  
  // Show the notification
  event.waitUntil(
    self.registration.showNotification(notificationData.title, {
      body: notificationData.body,
      icon: notificationData.icon,
      badge: notificationData.badge,
      data: {
        url: notificationData.url,
        timestamp: notificationData.timestamp
      },
      tag: 'node-notification',
      requireInteraction: false,
      vibrate: [200, 100, 200]
    })
  );
});

// Handle notification clicks
self.addEventListener('notificationclick', (event) => {
  console.log('[Service Worker] Notification clicked');
  
  event.notification.close();
  
  const urlToOpen = event.notification.data?.url || '/';
  
  // Focus existing window or open new one
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Try to find an existing window
        for (const client of clientList) {
          if (client.url.includes(new URL(urlToOpen, self.location).pathname) && 'focus' in client) {
            return client.focus();
          }
        }
        // Open a new window if none found
        if (clients.openWindow) {
          return clients.openWindow(urlToOpen);
        }
      })
  );
});

// Message event - handle commands from the main thread
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    console.log('[Service Worker] Received SKIP_WAITING message');
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CLEAR_CACHE') {
    console.log('[Service Worker] Received CLEAR_CACHE message');
    event.waitUntil(
      caches.keys().then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => caches.delete(cacheName))
        );
      })
    );
  }
});