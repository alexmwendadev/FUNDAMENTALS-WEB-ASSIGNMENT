// CONTACT FORM LOGIC (Connects to FastAPI Backend)
// the contact form on contact.html
const contactForm = document.getElementById('contact-form');

// only runs on the contact page
if (contactForm) {
    // runs when 'Send Message' is pressed
    contactForm.addEventListener('submit', async (e) => {
        // stop the normal submit; I send it with fetch
        e.preventDefault();

        // read what was typed
        const name = document.getElementById('contact-name').value.trim();
        // the sender's email
        const email = document.getElementById('contact-email').value.trim();
        // the message text
        const message = document.getElementById('contact-message').value.trim();

        // button says 'Sending...' and can't be clicked twice
        const sendBtn = contactForm.querySelector('button[type="submit"]');
        setBtn(sendBtn, 'Sending...');

        // the backend may be down
        try {
            // POST the message to the backend
            const response = await fetch(`${API_BASE}/api/contact`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, email: email, message: message })
            });

            // saved
            if (response.ok) {
                // button says 'Sent!', a small popup thanks the user, the form empties
                setBtn(sendBtn, 'Sent!');
                showToast('Thank you! Your message has been sent.', 'success');
                contactForm.reset();
                // leave 'Sent!' visible for a moment, then put the normal label back
                await pause(1500);
                resetBtn(sendBtn);
            // the backend refused it
            } else {
                showToast('Something went wrong. Please try again.');
                resetBtn(sendBtn);
            }
        // couldn't reach the backend
        } catch (error) {
            showToast('Cannot connect to the server. Please try again.');
            resetBtn(sendBtn);
        }
    });
}
