/**
 * nav.js - Global Top Navigation & User State Manager
 * Handles dropdown toggles, click-outside closures, and user authentication pill.
 */

function toggleNavDropdown(id) {
  const dropdown = document.getElementById('nav-dropdown-' + id);
  if (!dropdown) return;
  const isHidden = dropdown.classList.contains('hidden');
  closeAllNavDropdowns();
  if (isHidden) {
    dropdown.classList.remove('hidden');
    const chevron = document.getElementById(id + '-chevron');
    if (chevron) chevron.classList.add('rotate-180');
  }
}

function closeAllNavDropdowns() {
  document.querySelectorAll('[id^="nav-dropdown-"]').forEach(el => {
    if (el.tagName === 'DIV' && el.id.startsWith('nav-dropdown-') && !el.id.endsWith('-container')) {
      el.classList.add('hidden');
    }
  });
  document.querySelectorAll('[id$="-chevron"]').forEach(c => c.classList.remove('rotate-180'));
}

// Global click-outside listener
document.addEventListener('click', function(e) {
  if (!e.target.closest('#nav-dropdown-studio-container') && 
      !e.target.closest('#nav-dropdown-export-container') &&
      !e.target.closest('#nav-dropdown-user-container')) {
    closeAllNavDropdowns();
  }
});

// Escape key listener to close dropdowns
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    closeAllNavDropdowns();
  }
});

// Render user profile pill into #nav-user-container
function renderNavUserProfile() {
  const container = document.getElementById('nav-user-container');
  if (!container) return;

  let user = null;
  try {
    const stored = localStorage.getItem('tt_auth_user');
    if (stored) user = JSON.parse(stored);
  } catch (e) {
    console.warn("Could not read auth user:", e);
  }

  if (user && user.email) {
    const avatarHtml = user.picture
      ? `<img src="${user.picture}" alt="${user.name || 'User'}" class="w-7 h-7 rounded-full object-cover border border-indigo-400">`
      : `<div class="w-7 h-7 rounded-full bg-gradient-to-tr from-amber-400 to-indigo-600 text-white font-black text-xs flex items-center justify-center">${(user.name || user.email || 'U')[0].toUpperCase()}</div>`;

    container.innerHTML = `
      <div class="relative" id="nav-dropdown-user-container">
        <button onclick="toggleNavDropdown('user')" class="flex items-center space-x-2 bg-indigo-900/80 hover:bg-indigo-800 text-white px-2.5 py-1 rounded-xl text-xs font-bold transition border border-indigo-700/80 shadow-sm">
          ${avatarHtml}
          <span class="max-w-[100px] truncate text-indigo-100 hidden sm:inline">${user.name ? user.name.split(' ')[0] : 'User'}</span>
          <svg class="w-3 h-3 text-indigo-400" id="user-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 9l-7 7-7-7"></path></svg>
        </button>

        <div id="nav-dropdown-user" class="hidden absolute right-0 mt-2 w-56 bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl py-2 z-50 divide-y divide-slate-800">
          <div class="px-3 py-2">
            <div class="text-xs font-black text-white truncate">${user.name || 'Faculty Member'}</div>
            <div class="text-[11px] text-slate-400 truncate">${user.email}</div>
            <div class="mt-1.5">
              <span class="text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800">
                ${user.role || 'Timetable Admin'}
              </span>
            </div>
          </div>
          <div class="py-1">
            <button onclick="handleNavLogout()" class="w-full text-left px-3 py-1.5 text-xs text-rose-400 hover:bg-rose-500/10 font-bold transition flex items-center gap-2">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </div>
    `;
  } else {
    container.innerHTML = `
      <a href="login.html" class="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-black transition shadow-sm border border-indigo-400/30">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path></svg>
        <span>Sign In</span>
      </a>
    `;
  }
}

function handleNavLogout() {
  localStorage.removeItem('tt_auth_user');
  renderNavUserProfile();
  // Optional redirect if page is protected
  if (window.location.pathname.includes('creator') || window.location.pathname.includes('prerequisites')) {
    window.location.href = 'index.html';
  } else {
    window.location.reload();
  }
}

// Auto-run on DOMContentLoaded
document.addEventListener('DOMContentLoaded', function() {
  renderNavUserProfile();
});
