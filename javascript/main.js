// 1. Mobile Nav
// the Menu button (shown on phones)
const menuBtn = document.querySelector(".menu-btn");
// the navigation list the button opens
const nav = document.querySelector("#main-nav");
// only runs on pages that have both
if (menuBtn && nav) {
  // each click shows or hides the menu by toggling the 'open' class
  menuBtn.addEventListener("click", () => {
    // true if the menu is open after the toggle
    const isOpen = nav.classList.toggle("open");
    // tells screen readers whether it is open
    menuBtn.setAttribute("aria-expanded", isOpen);
  });
}

// 2. Footer Year
// the year in the footer
const yearSpan = document.querySelector("#year");
// write the current year so the footer never goes out of date
if (yearSpan) yearSpan.textContent = new Date().getFullYear();

// 3. Dynamic Navigation
// Shows the profile photo if there is one, otherwise the first letter of the username.
// draws the profile picture in an element, or the first letter of the username when there is no picture
function paintAvatar(el, username, avatarPath) {
  // the page has no such element
  if (!el) return;
  // first letter of the username, in capitals
  const initial = (username || 'U').charAt(0).toUpperCase();
  // clear whatever was there
  el.textContent = '';
  // a picture exists (the stored value can be the text 'null' after a bad save, so that's checked too)
  if (avatarPath && avatarPath !== 'null' && avatarPath !== 'undefined') {
    // an <img> built with the DOM, not pasted in as HTML
    const img = document.createElement('img');
    // decorative, so no alt text
    img.alt = '';
    // full address of the picture
    img.src = assetUrl(avatarPath);
    // if the picture can't load, show the letter instead
    img.addEventListener('error', () => { el.textContent = initial; });
    // put the picture in the circle
    el.appendChild(img);
  // no picture: show the letter
  } else {
    el.textContent = initial;
  }
}

// decides what the header shows: the logged-in items or Log In / Sign Up
function renderNav() {
  // values saved at login
  const token = localStorage.getItem('shamba_token');
  // 'customer' or 'farmer'
  const role = localStorage.getItem('shamba_role');
  // used for the avatar letter
  const username = localStorage.getItem('shamba_username');
  // saved picture path, if any
  const avatarPath = localStorage.getItem('shamba_avatar');

  // the header pieces; a page that doesn't have one just gives null
  const navDashboard = document.getElementById('nav-dashboard');
  const navProfile = document.getElementById('nav-profile');
  const navAuth = document.getElementById('nav-auth');

  // logged in
  if (token) {
    // hide Log In / Sign Up
    if (navAuth) navAuth.style.display = 'none';
    // show the avatar button
    if (navProfile) navProfile.style.display = 'block';

    // Both roles get a dashboard link, each to their own dashboard
    // show the dashboard link
    if (navDashboard) {
      navDashboard.style.display = 'block';
      // the link points to the right dashboard for the role
      const link = document.createElement('a');
      link.href = role === 'farmer' ? 'dashboard.html' : 'customer_dashboard.html';
      link.textContent = 'My Dashboard';
      // remove the old link, then add the new one
      navDashboard.textContent = '';
      navDashboard.appendChild(link);
    }

    // draw the picture or the letter
    paintAvatar(document.getElementById('user-avatar'), username, avatarPath);
  // logged out: show Log In / Sign Up and hide the rest
  } else {
    if (navAuth) navAuth.style.display = 'flex';
    if (navDashboard) navDashboard.style.display = 'none';
    if (navProfile) navProfile.style.display = 'none';
  }
}

// 4. Keep role, username and photo up to date from the server
// asks the server who I am and refreshes the saved role, name and picture. Also notices an expired login
async function syncAccount() {
  // the saved login token
  const token = localStorage.getItem('shamba_token');
  // not logged in: nothing to refresh
  if (!token) return;

  // the server may be down, so everything is wrapped
  try {
    // ask the server (it reads the token and replies with my details)
    const res = await fetch(`${API_BASE}/api/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    // success: save the fresh details
    if (res.ok) {
      // my details
      const me = await res.json();
      // role and username are saved for the header
      localStorage.setItem('shamba_role', me.role);
      localStorage.setItem('shamba_username', me.username);
      // keep the picture, or forget it if it was removed on another device
      if (me.profile_picture) localStorage.setItem('shamba_avatar', me.profile_picture);
      else localStorage.removeItem('shamba_avatar');
    // the token has expired or is invalid
    } else if (res.status === 401) {
      // log out locally so the header shows Log In again
      clearSession(); // token expired: show the logged-out header
    }
  // server unreachable: keep what is already saved
  } catch (error) {}
  // redraw the header with the fresh details
  renderNav();
}

// draw the header straight away from the saved values, without waiting for the server
renderNav();
// then refresh from the server in the background
syncAccount();

// 5. Profile Dropdown Click
// one click handler for the whole page that opens and closes the profile dropdown
document.addEventListener('click', (e) => {
  // the avatar button
  const profileBtn = document.getElementById('profile-btn');
  // the menu under it
  const profileDropdown = document.getElementById('profile-dropdown');

  // this page has no profile menu
  if (!profileBtn || !profileDropdown) return;

  // the avatar button was clicked: open or close the menu
  if (profileBtn.contains(e.target)) {
    // so the same click isn't also treated as 'click elsewhere'
    e.stopPropagation();
    // true if it is open after the toggle
    const isOpen = profileDropdown.classList.toggle('show');
    // keeps the accessibility state in step
    profileBtn.setAttribute('aria-expanded', isOpen);
  // a click anywhere else closes the menu
  } else if (!profileDropdown.contains(e.target)) {
    profileDropdown.classList.remove('show');
    profileBtn.setAttribute('aria-expanded', 'false');
  }
});

// 6. Logout
// forgets the login and goes back to the home page
function logout() {
  // remove token, role, username and picture
  clearSession();
  // NEW: Removed the alert() popup. Just redirect silently.
  // go home
  window.location.href = 'index.html';
}

// 7. Custom Toast Notification System
// shows a popup message in the top right corner instead of using browser alerts
function showToast(message, type = 'error') {
  // find or create the container for popups
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }
  // create the popup itself
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  
  // remove it after 4 seconds
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// 8. Show/Hide Password Toggle
// toggles the input type between password and text
// NEW: Updated to accept the button ID and swap the eye emoji
function togglePassword(inputId, btnId) {
  const input = document.getElementById(inputId);
  const btn = document.getElementById(btnId);
  if (input.type === 'password') {
    input.type = 'text';
    if (btn) btn.textContent = '👁️'; // Open eye when visible
  } else {
    input.type = 'password';
    if (btn) btn.textContent = '🙈'; // Crossed eye when hidden
  }
}