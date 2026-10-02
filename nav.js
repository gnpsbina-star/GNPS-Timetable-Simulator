/**
 * nav.js - Global Top Navigation
 * Handles dropdown toggles and click-outside closures.
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
  if (!e.target.closest('#nav-dropdown-export-container')) {
    closeAllNavDropdowns();
  }
});

// Escape key listener to close dropdowns
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    closeAllNavDropdowns();
  }
});
