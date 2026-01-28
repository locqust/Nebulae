// PWA Service Worker Registration and Install Prompt
// This handles PWA installation, offline capabilities, and push notifications

(function() {
  'use strict';

  let deferredPrompt = null;
  let installButton = null;
  let serviceWorkerRegistration = null;

  // Check if service workers are supported
  if ('serviceWorker' in navigator) {
    // Register the service worker
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/static/sw.js')
        .then((registration) => {
          console.log('[PWA] Service Worker registered:', registration.scope);
          serviceWorkerRegistration = registration;
          
          // Wait for service worker to be active before initializing push
          waitForServiceWorkerActivation(registration).then(() => {
            // Initialize push notifications after service worker is ready
            // Only if user is logged in (check for appConfig)
            if (window.appConfig && window.appConfig.loggedInUsername) {
              console.log('[PWA] User is logged in, initializing push notifications');
              initializePushNotifications(registration);
            } else {
              console.log('[PWA] No logged in user, skipping push notification setup');
            }
          });
          
          // Check for updates periodically
          setInterval(() => {
            registration.update();
          }, 60000); // Check every minute
          
          // Listen for updates
          registration.addEventListener('updatefound', () => {
            const newWorker = registration.installing;
            
            newWorker.addEventListener('statechange', () => {
              if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                // New service worker available
                showUpdateNotification();
              }
            });
          });
        })
        .catch((error) => {
          console.error('[PWA] Service Worker registration failed:', error);
        });
    });
  }

  // ========================================
  // SERVICE WORKER ACTIVATION HELPER
  // ========================================

  /**
   * Wait for the service worker to be fully active
   */
  function waitForServiceWorkerActivation(registration) {
    return new Promise((resolve) => {
      if (registration.active) {
        console.log('[PWA] Service Worker already active');
        resolve();
      } else if (registration.installing) {
        console.log('[PWA] Service Worker installing, waiting for activation...');
        registration.installing.addEventListener('statechange', function() {
          if (this.state === 'activated') {
            console.log('[PWA] Service Worker activated');
            resolve();
          }
        });
      } else if (registration.waiting) {
        console.log('[PWA] Service Worker waiting, waiting for activation...');
        registration.waiting.addEventListener('statechange', function() {
          if (this.state === 'activated') {
            console.log('[PWA] Service Worker activated');
            resolve();
          }
        });
      } else {
        // Fallback: wait a bit and check again
        console.log('[PWA] Service Worker state unknown, waiting 1 second...');
        setTimeout(() => resolve(), 1000);
      }
    });
  }

  // ========================================
  // PUSH NOTIFICATION FUNCTIONS
  // ========================================

/**
   * Initialize push notifications for logged-in users
   */
  async function initializePushNotifications(registration) {
    console.log('[Push] Initializing push notifications');
    
    // Check if push notifications are supported
    if (!('PushManager' in window)) {
      console.log('[Push] Push notifications not supported in this browser');
      return;
    }
    
    // If denied, we can't do anything
    if (Notification.permission === 'denied') {
      console.log('[Push] Notification permission denied');
      return;
    }
    
    try {
      // Check current subscription status
      const subscription = await registration.pushManager.getSubscription();
      
      if (subscription) {
        console.log('[Push] Already subscribed');
        await sendSubscriptionToServer(subscription);
      } else if (Notification.permission === 'granted') {
        await subscribeToPush(registration);
      } else if (Notification.permission === 'default') {
        const permission = await Notification.requestPermission();
        
        if (permission === 'granted') {
          await subscribeToPush(registration);
        }
      }
    } catch (error) {
      console.error('[Push] Error initializing:', error);
    }
  }

  /**
   * Subscribe to push notifications
   */
  async function subscribeToPush(registration) {
    try {
      // Get VAPID public key from server
      const response = await fetch('/push/vapid_public_key');
      if (!response.ok) {
        throw new Error(`Failed to get VAPID public key: ${response.status}`);
      }
      
      const data = await response.json();
      const vapidPublicKey = data.public_key;
      
      // Convert VAPID key to Uint8Array
      const convertedVapidKey = urlBase64ToUint8Array(vapidPublicKey);
      
      // Subscribe
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: convertedVapidKey
      });
      
      console.log('[Push] Successfully subscribed');
      
      // Send subscription to server
      await sendSubscriptionToServer(subscription);
      
      return subscription;
    } catch (error) {
      console.error('[Push] Failed to subscribe:', error);
      throw error;
    }
  }

  /**
   * Send subscription to server
   */
  async function sendSubscriptionToServer(subscription) {
    try {
      const response = await fetch('/push/subscribe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(subscription.toJSON())
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to save subscription');
      }
      
      console.log('[Push] Subscription saved');
      
      // Show success message
      if (window.App && window.App.Toast) {
        window.App.Toast.success('Push notifications enabled! You\'ll receive notifications even when the app is closed.');
      }
    } catch (error) {
      console.error('[Push] Error saving subscription:', error);
    }
  }

  /**
   * Helper function to convert VAPID key from base64 to Uint8Array
   */
  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
      .replace(/\-/g, '+')
      .replace(/_/g, '/');
    
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  /**
   * Request notification permission and subscribe
   * This function is exposed globally for use in settings or other UI
   */
  async function requestNotificationPermission() {
    console.log('[Push] Manual permission request triggered');
    
    if (!('Notification' in window)) {
      console.log('[Push] Notifications not supported');
      alert('Push notifications are not supported in your browser.');
      return false;
    }
    
    if (Notification.permission === 'granted') {
      console.log('[Push] Permission already granted');
      if (serviceWorkerRegistration) {
        await subscribeToPush(serviceWorkerRegistration);
      }
      return true;
    }
    
    if (Notification.permission !== 'denied') {
      const permission = await Notification.requestPermission();
      console.log('[Push] Permission result:', permission);
      
      if (permission === 'granted' && serviceWorkerRegistration) {
        await subscribeToPush(serviceWorkerRegistration);
        return true;
      }
    } else {
      alert('Notification permission has been denied. Please enable it in your browser settings.');
    }
    
    return false;
  }

  // Expose function globally for settings page or manual subscription
  window.requestNotificationPermission = requestNotificationPermission;

  // ========================================
  // PWA INSTALL FUNCTIONS
  // ========================================

  // Listen for the beforeinstallprompt event
  window.addEventListener('beforeinstallprompt', (e) => {
    console.log('[PWA] Install prompt available');
    
    // Prevent the default prompt
    e.preventDefault();
    
    // Store the event for later use
    deferredPrompt = e;
    
    // Show custom install button
    showInstallButton();
  });

  // Listen for successful installation
  window.addEventListener('appinstalled', () => {
    console.log('[PWA] App installed successfully');
    
    // Clear the deferred prompt
    deferredPrompt = null;
    
    // Hide install button
    hideInstallButton();
    
    // Show success toast
    if (window.App && window.App.Toast) {
      window.App.Toast.success('NODE installed successfully! You can now use it like a native app.');
    }
  });

  // Function to show the install button
  function showInstallButton() {
    // Check if button already exists
    installButton = document.getElementById('pwa-install-button');
    
    if (!installButton) {
      // Create install button
      installButton = document.createElement('button');
      installButton.id = 'pwa-install-button';
      installButton.innerHTML = `
        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path>
        </svg>
        Install App
      `;
      installButton.className = 'fixed bottom-4 right-4 z-50 flex items-center px-4 py-3 bg-blue-600 text-white rounded-lg shadow-lg hover:bg-blue-700 transition-all duration-200 font-medium text-sm';
      installButton.style.display = 'none';
      
      installButton.addEventListener('click', installApp);
      
      document.body.appendChild(installButton);
    }
    
    // Show the button with animation
    setTimeout(() => {
      installButton.style.display = 'flex';
      installButton.style.animation = 'slideInUp 0.3s ease-out';
    }, 2000); // Wait 2 seconds before showing
  }

  // Function to hide the install button
  function hideInstallButton() {
    if (installButton) {
      installButton.style.display = 'none';
    }
  }

  // Function to trigger installation
  async function installApp() {
    if (!deferredPrompt) {
      console.log('[PWA] Install prompt not available');
      return;
    }
    
    // Show the install prompt
    deferredPrompt.prompt();
    
    // Wait for the user's response
    const { outcome } = await deferredPrompt.userChoice;
    
    console.log('[PWA] User response:', outcome);
    
    if (outcome === 'accepted') {
      console.log('[PWA] User accepted the install prompt');
    } else {
      console.log('[PWA] User dismissed the install prompt');
    }
    
    // Clear the deferred prompt
    deferredPrompt = null;
    
    // Hide the button
    hideInstallButton();
  }

  // Function to show update notification
  function showUpdateNotification() {
    if (window.App && window.App.Toast) {
      const toast = window.App.Toast.info('A new version is available!', 10000);
      
      // Add update button to toast
      if (toast) {
        const updateBtn = document.createElement('button');
        updateBtn.textContent = 'Update Now';
        updateBtn.className = 'ml-4 px-3 py-1 bg-white text-blue-600 rounded font-medium hover:bg-gray-100';
        updateBtn.onclick = () => {
          // Tell the service worker to skip waiting
          if (navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({ type: 'SKIP_WAITING' });
          }
          // Reload the page
          window.location.reload();
        };
        toast.appendChild(updateBtn);
      }
    }
  }

  // Add slideInUp animation
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideInUp {
      from {
        transform: translateY(100px);
        opacity: 0;
      }
      to {
        transform: translateY(0);
        opacity: 1;
      }
    }
  `;
  document.head.appendChild(style);

  // Expose install function globally
  window.installPWA = installApp;
})();