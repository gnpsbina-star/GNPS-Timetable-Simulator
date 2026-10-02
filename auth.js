/**
 * auth.js - Client-Side Authentication & Session Management
 * Handles Google Identity Services (GSI) OAuth2, JWT decoding, role verification, and session state.
 */

const AUTH_STORAGE_KEY = 'tt_auth_user';

// Read current user session
function getAuthUser() {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    console.warn('Error reading auth state:', e);
    return null;
  }
}

// Persist user session
function setAuthUser(user) {
  if (!user) {
    localStorage.removeItem(AUTH_STORAGE_KEY);
  } else {
    localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(user));
  }
}

// Check authentication
function isAuthenticated() {
  const user = getAuthUser();
  return Boolean(user && user.email);
}

// Check role
function isTimetableAdmin() {
  const user = getAuthUser();
  if (!user) return false;
  const role = (user.role || '').toLowerCase();
  return role.includes('admin') || role.includes('coordinator') || role.includes('principal');
}

// Safely decode Google Identity JWT credential
function decodeJwtResponse(credentialToken) {
  try {
    const base64Url = credentialToken.split('.')[1];
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(jsonPayload);
  } catch (e) {
    console.error('Failed to decode JWT response:', e);
    return null;
  }
}

// Google Sign-In Callback Handler
function handleGoogleCredentialResponse(response) {
  if (!response || !response.credential) {
    console.error('No credential received from Google Identity Services.');
    alert('Google sign-in did not return a valid credential. Please try again or use Demo Login.');
    return;
  }

  const payload = decodeJwtResponse(response.credential);
  if (!payload || !payload.email) {
    alert('Could not parse Google user profile information.');
    return;
  }

  // Build application user model
  const user = {
    id: payload.sub,
    name: payload.name || payload.email.split('@')[0],
    email: payload.email,
    picture: payload.picture || '',
    role: 'Timetable Admin', // Default privileged role for school administration
    authProvider: 'google',
    signedInAt: new Date().toISOString()
  };

  setAuthUser(user);

  // Redirect to original target or index.html
  const urlParams = new URLSearchParams(window.location.search);
  const returnUrl = urlParams.get('returnUrl') || 'index.html';
  window.location.href = returnUrl;
}

// Quick demo sign-in for local or unconfigured Google Client ID environments
function handleDemoSignIn(role, name, email, picture) {
  const user = {
    id: 'demo_' + Math.random().toString(36).substring(2, 9),
    name: name || (role === 'admin' ? 'Academic Coordinator' : 'Faculty Member'),
    email: email || (role === 'admin' ? 'admin@gnps.ac.in' : 'faculty@gnps.ac.in'),
    picture: picture || '',
    role: role === 'admin' ? 'Timetable Admin' : 'Faculty Member',
    authProvider: 'demo',
    signedInAt: new Date().toISOString()
  };

  setAuthUser(user);

  const urlParams = new URLSearchParams(window.location.search);
  const returnUrl = urlParams.get('returnUrl') || 'index.html';
  window.location.href = returnUrl;
}

// Universal Sign-Out
function handleSignOut(redirectUrl = 'login.html') {
  localStorage.removeItem(AUTH_STORAGE_KEY);
  if (typeof renderNavUserProfile === 'function') {
    renderNavUserProfile();
  }
  if (redirectUrl) {
    window.location.href = redirectUrl;
  }
}
