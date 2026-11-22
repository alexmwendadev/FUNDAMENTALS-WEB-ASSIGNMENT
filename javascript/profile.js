// PROFILE PAGE (customers and farmers)
// one async function so I can use await at the top level
(async function () {
    // the saved login token
    const token = localStorage.getItem('shamba_token');
    // not logged in: go to the login page
    if (!token) { window.location.href = 'login.html'; return; }
    // sent with every request so the backend knows who is calling
    const authHeaders = { 'Authorization': `Bearer ${token}` };

    // largest picture accepted, 2 MB (the backend checks too)
    const MAX_AVATAR = 2 * 1024 * 1024;
    // picture types accepted
    const AVATAR_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

    // the page elements this script reads and writes
    const preview = document.getElementById('avatar-preview');
    const fileInput = document.getElementById('avatar-file');
    const removeBtn = document.getElementById('avatar-remove');
    const avatarMsg = document.getElementById('avatar-msg');
    const form = document.getElementById('profile-form');
    const msg = document.getElementById('profile-msg');
    const farmerFields = document.getElementById('farmer-profile-fields');
    const saveBtn = form.querySelector('button[type="submit"]');

    // shows a message in green or red under a section
    function say(target, text, ok) {
        target.textContent = text;
        target.className = 'feedback ' + (ok ? 'success' : 'error');
    }

    // my current details, kept so the save handler knows my role
    let me = null;

    // draws my picture (or my initial) and keeps the saved copy in step
    function showAvatar(user) {
        // clear the old content
        preview.textContent = '';
        // there is a picture
        if (user.profile_picture) {
            // an <img> built with the DOM
            const img = document.createElement('img');
            // alt text
            img.alt = 'Profile picture';
            // full address of the picture
            img.src = assetUrl(user.profile_picture);
            // show it
            preview.appendChild(img);
            // the header on other pages reads this saved copy
            localStorage.setItem('shamba_avatar', user.profile_picture);
        // no picture
        } else {
            // show my first letter instead
            const span = document.createElement('span');
            // CSS id the stylesheet uses for the letter
            span.id = 'avatar-initial';
            // first letter in capitals
            span.textContent = user.username.charAt(0).toUpperCase();
            // show it
            preview.appendChild(span);
            // forget the saved picture
            localStorage.removeItem('shamba_avatar');
        }
        // the Remove button only appears when there is a picture to remove
        removeBtn.hidden = !user.profile_picture;
    }

    // puts my details into the form
    function fill(user) {
        // remember them
        me = user;
        // username is shown but can't be edited
        document.getElementById('prof-username').value = user.username;
        // email, empty for older accounts
        document.getElementById('prof-email').value = user.email || '';
        // phone shown as 07...
        document.getElementById('prof-phone').value = localPhone(user.phone);
        // draw the picture
        showAvatar(user);

        // true for farmers
        const isFarmer = user.role === 'farmer';
        // payout fields are shown to farmers only
        farmerFields.style.display = isFarmer ? 'block' : 'none';
        // fill in the payout details
        if (isFarmer) {
            // saved payout method (M-Pesa if none)
            const method = user.payment_method || 'mpesa';
            // select it in the dropdown
            document.getElementById('prof-payment-method').value = method;
            // mobile numbers as 07..., till numbers as they are
            document.getElementById('prof-payment-number').value =
                method === 'till' ? (user.payment_number || '') : localPhone(user.payment_number);
        }
        // keep the saved role and name up to date for the header
        localStorage.setItem('shamba_role', user.role);
        localStorage.setItem('shamba_username', user.username);
    }

    // load my details when the page opens
    try {
        // GET /api/me
        const res = await fetch(`${API_BASE}/api/me`, { headers: authHeaders });
        // login expired
        if (res.status === 401) { clearSession(); window.location.href = 'login.html'; return; }
        // any other error counts as a failure
        if (!res.ok) throw new Error();
        // show my details
        fill(await res.json());
    // couldn't load them
    } catch {
        // tell me
        alert('Error loading profile. Please log in again.');
        window.location.href = 'login.html';
        // can't continue
        return;
    }

    // ---- profile picture ----
    // runs when a picture is chosen
    fileInput.addEventListener('change', async () => {
        // the chosen file
        const file = fileInput.files[0];
        // reset the input so the same file can be chosen again later
        fileInput.value = '';
        // the dialog was cancelled
        if (!file) return;
        // hide any old message
        avatarMsg.className = 'feedback';

        // wrong file type: refuse before uploading
        if (!AVATAR_TYPES.includes(file.type)) { say(avatarMsg, 'Choose a JPG, PNG or WEBP image.', false); return; }
        // too big: refuse before uploading
        if (file.size > MAX_AVATAR) { say(avatarMsg, 'That image is over 2 MB. Choose a smaller one.', false); return; }

        // a form containing the file
        const fd = new FormData();
        // the picture itself
        fd.append('file', file);
        // send it
        try {
            // POST /api/me/avatar
            const res = await fetch(`${API_BASE}/api/me/avatar`, { method: 'POST', headers: authHeaders, body: fd });
            // the updated profile
            const data = await res.json();
            // the backend refused it: show why
            if (!res.ok) { say(avatarMsg, errorMessage(data, 'Could not upload the picture.'), false); return; }
            // keep the new details
            me = data;
            // show the new picture
            showAvatar(data);
            // confirm
            say(avatarMsg, 'Picture updated.', true);
        // couldn't reach the backend
        } catch {
            say(avatarMsg, 'Cannot connect to backend.', false);
        }
    });

    // runs when 'Remove' is pressed
    removeBtn.addEventListener('click', async () => {
        // ask first
        if (!confirm('Remove your profile picture?')) return;
        // hide any old message
        avatarMsg.className = 'feedback';
        // send it
        try {
            // DELETE /api/me/avatar
            const res = await fetch(`${API_BASE}/api/me/avatar`, { method: 'DELETE', headers: authHeaders });
            // the updated profile
            const data = await res.json();
            // refused: show why
            if (!res.ok) { say(avatarMsg, errorMessage(data, 'Could not remove the picture.'), false); return; }
            // keep the new details
            me = data;
            // show my initial instead
            showAvatar(data);
            // confirm
            say(avatarMsg, 'Picture removed.', true);
        // couldn't reach the backend
        } catch {
            say(avatarMsg, 'Cannot connect to backend.', false);
        }
    });

    // ---- details ----
    // runs when 'Save Changes' is pressed
    form.addEventListener('submit', async (e) => {
        // stop the normal submit
        e.preventDefault();
        // hide any old message
        msg.className = 'feedback';

        // the details to save: email and phone for everyone...
        const body = {
            email: document.getElementById('prof-email').value.trim(),
            phone: document.getElementById('prof-phone').value.trim(),
        };
        // ...plus the payout details for farmers
        if (me.role === 'farmer') {
            body.payment_method = document.getElementById('prof-payment-method').value;
            body.payment_number = document.getElementById('prof-payment-number').value.trim();
        }

        // block double clicks
        saveBtn.disabled = true;
        // send it
        try {
            // PUT /api/me
            const res = await fetch(`${API_BASE}/api/me`, {
                method: 'PUT',
                headers: { ...authHeaders, 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            // the updated profile, or an error
            const data = await res.json();
            // the backend refused it (e.g. an invalid phone): show why
            if (!res.ok) { say(msg, errorMessage(data, 'Failed to update.'), false); return; }

            // show what was saved
            fill(data);
            // confirm
            say(msg, 'Profile updated successfully!', true);
            // after a moment, go back to where I came from
            setTimeout(() => {
                // default: my own dashboard or the shop
                let back = me.role === 'farmer' ? 'dashboard.html' : 'products.html';
                // reading the referrer can fail
                try {
                    // the previous page, if any
                    const ref = document.referrer ? new URL(document.referrer) : null;
                    // only go back to a page on this site, and never to this page itself
                    if (ref && ref.origin === window.location.origin && !ref.pathname.endsWith('/profile.html')) back = ref.href;
                // ignore a bad referrer
                } catch (e2) {}
                // go
                window.location.href = back;
            }, 1500);
        // couldn't reach the backend
        } catch {
            say(msg, 'Cannot connect to backend.', false);
        // runs whatever happened
        } finally {
            // unblock the button
            saveBtn.disabled = false;
        }
    });
})();
