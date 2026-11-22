// AUTHENTICATION LOGIC

// 1. SIGN UP LOGIC
// the pieces of the signup page that this script talks to (all null on the login page)
const signupForm = document.getElementById('signup-form');
const usernameFeedback = document.getElementById('username-feedback');
const signupError = document.getElementById('signup-error');

// everything inside only runs on the signup page
if (signupForm) {
    // the extra block shown only to farmers...
    const farmerFields = document.getElementById('farmer-fields');
    // ...with the contact number, the payout method and the payout number
    const phoneInput = document.getElementById('phone');
    const paymentMethod = document.getElementById('payment_method');
    const paymentNumber = document.getElementById('payment_number');
    const paymentLabel = document.getElementById('payment_number_label');

    // NEW: Live password validation
    const passwordInput = document.getElementById('password');
    const passwordFeedback = document.getElementById('password-feedback');

    // NEW: Listen to typing in the password field to show what is missing
    passwordInput.addEventListener('input', () => {
        const val = passwordInput.value;
        let missing = [];
        
        if (val.length < 8) missing.push("8+ characters");
        if (!/[A-Z]/.test(val)) missing.push("uppercase letter");
        if (!/[a-z]/.test(val)) missing.push("lowercase letter");
        if (!/\d/.test(val)) missing.push("number");
        if (!/[!@#$%^&*(),.?":{}|<>]/.test(val)) missing.push("special character");

        if (missing.length === 0) {
            passwordFeedback.textContent = "Strong password!";
            passwordFeedback.className = "feedback success";
            passwordFeedback.style.display = "block";
        } else if (val.length > 0) {
            passwordFeedback.textContent = "Missing: " + missing.join(", ");
            passwordFeedback.className = "feedback error";
            passwordFeedback.style.display = "block";
        } else {
            passwordFeedback.textContent = "";
            passwordFeedback.style.display = "none";
        }
    });

    // shows or hides the farmer-only fields when the role changes
    function updateFarmerFields() {
        // true when 'I am a Farmer' is selected
        const isFarmer = document.querySelector('input[name="role"]:checked').value === 'farmer';
        // show the block for farmers, hide it for customers
        farmerFields.classList.toggle('show', isFarmer);
        // CSS class used to lay the form out differently for farmers
        document.querySelector('.auth-right').classList.toggle('farmer-mode', isFarmer);
        // farmer fields are only 'required' when they are visible
        [phoneInput, paymentMethod, paymentNumber].forEach(el => el.required = isFarmer);
    }

    // changes the label and example text to match the chosen payout method
    function updatePaymentLabel() {
        // Till number
        if (paymentMethod.value === 'till') {
            paymentLabel.textContent = 'Till Number';
            paymentNumber.placeholder = 'e.g. 123456';
        // Airtel Money number
        } else if (paymentMethod.value === 'Airtel Money') {
            paymentLabel.textContent = 'Airtel Money Number';
            paymentNumber.placeholder = '0733 123 456';
        // M-Pesa number
        } else {
            paymentLabel.textContent = 'M-Pesa Number';
            paymentNumber.placeholder = '0712 345 678';
        }
    }

    // whenever the role is changed, update the farmer fields
    document.querySelectorAll('input[name="role"]').forEach(r => r.addEventListener('change', updateFarmerFields));
    // whenever the payout method is changed, update the label
    paymentMethod.addEventListener('change', updatePaymentLabel);
    // set the correct starting state when the page loads
    updateFarmerFields();
    // same for the payout label
    updatePaymentLabel();

    // keeps the form anchored at the same top position for both roles
    document.querySelector('.auth-right').classList.add('signup-mode');

    // runs when 'Create Account' is pressed
    signupForm.addEventListener('submit', async (e) => {
        // stop the browser's normal form submit; I send it myself with fetch
        e.preventDefault();

        // clear any old error messages
        usernameFeedback.className = 'feedback';
        signupError.className = 'feedback';

        // read what was typed
        const username = document.getElementById('username').value.trim();
        // passwords aren't trimmed
        const password = document.getElementById('password').value;
        // 'buyer' (customer) or 'farmer'
        const selectedRole = document.querySelector('input[name="role"]:checked').value;

        // the email the backend now stores for receipts
        const email = document.getElementById('email').value.trim();
        
        // NEW: Check if password is strong enough before sending
        if (password.length < 8 || !/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password) || !/[!@#$%^&*(),.?":{}|<>]/.test(password)) {
            // Don't submit, the live feedback is already showing the error
            return; 
        }

        // the data sent to the backend
        const body = { username: username, email: email, password: password, role: selectedRole };

        // farmers also send contact and payout details
        if (selectedRole === 'farmer') {
            body.phone = phoneInput.value.trim();
            body.payment_method = paymentMethod.value;
            body.payment_number = paymentNumber.value.trim();
        }

        // NEW: get the button and disable it, but keep the text same
        const submitBtn = signupForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;

        // send the request; a network failure is caught below
        try {
            // POST the new account to the backend
            const response = await fetch(`${API_BASE}/api/signup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });

            // the backend's reply
            const data = await response.json();

            // account created
            if (response.ok) {
                // NEW: Redirect immediately, no popups
                window.location.href = 'login.html';
            // the backend refused it
            } else {
                // readable text from the reply
                const message = errorMessage(data, "Please check your details and try again.");
                
                // NEW: Show error inline instead of popup
                if (message.toLowerCase().includes('username')) {
                    usernameFeedback.textContent = message;
                    usernameFeedback.className = 'feedback error';
                } else {
                    signupError.textContent = message;
                    signupError.className = 'feedback error';
                }
                submitBtn.disabled = false;
            }
        // couldn't reach the backend at all
        } catch (error) {
            // NEW: Show inline error
            signupError.textContent = "Cannot connect to the Python backend.";
            signupError.className = 'feedback error';
            submitBtn.disabled = false;
        }
    });
}

// 2. LOGIN LOGIC
// the login form (null on the signup page)
const loginForm = document.getElementById('login-form');

// everything inside only runs on the login page
if (loginForm) {
    // runs when 'Log In' is pressed
    loginForm.addEventListener('submit', async (e) => {
        // stop the normal submit
        e.preventDefault();
        
        // read the username
        const username = document.getElementById('login-id').value.trim();
        // and the password
        const password = document.getElementById('login-password').value;
        
        // NEW: Get the error container
        const loginError = document.getElementById('login-error');
        loginError.className = 'feedback';
        loginError.textContent = '';

        // the backend's login endpoint expects form-style fields, not JSON
        const formData = new URLSearchParams();
        // username field
        formData.append('username', username);
        // password field
        formData.append('password', password);

        // NEW: Disable button but don't change text
        const submitBtn = loginForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;

        // send the request
        try {
            // POST the login
            const response = await fetch(`${API_BASE}/api/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData
            });

            // the reply: token, role, username, picture
            const data = await response.json();

            // login succeeded
            if (response.ok) {
                // save the token; every later request sends it
                localStorage.setItem('shamba_token', data.access_token);
                // save role...
                localStorage.setItem('shamba_role', data.role);
                // ...and username for the header
                localStorage.setItem('shamba_username', data.username);
                
                // save the picture too, or forget an old one from a previous login
                if (data.profile_picture) {
                    localStorage.setItem('shamba_avatar', data.profile_picture);
                } else {
                    localStorage.removeItem('shamba_avatar');
                }

                // Go back to the page the user came from, but only if it is on our own site
                // where to go next: home unless there's a better place
                let targetUrl = 'index.html';
                // reading the referrer can fail
                try {
                    // the page the user came from, if any
                    const ref = document.referrer ? new URL(document.referrer) : null;
                    // only use it if it's on this site and isn't the login/signup page
                    if (ref && ref.origin === window.location.origin && !/\/(login|signup)\.html$/.test(ref.pathname)) {
                        // go back to where they were
                        targetUrl = ref.href;
                    }
                // ignore a bad referrer and go home
                } catch (e) {}

                // NEW: Redirect immediately without popup
                window.location.href = targetUrl;

            // wrong username or password
            } else {
                // NEW: Show inline error instead of popup
                loginError.textContent = "Login failed: " + errorMessage(data, "Please try again.");
                loginError.className = 'feedback error';
                submitBtn.disabled = false;
            }
        // couldn't reach the backend
        } catch (error) {
            // NEW: Show inline error
            loginError.textContent = "Cannot connect to the Python backend.";
            loginError.className = 'feedback error';
            submitBtn.disabled = false;
        }
    });
}