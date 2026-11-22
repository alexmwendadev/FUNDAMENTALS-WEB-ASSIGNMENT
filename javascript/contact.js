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
                // thank the user
                alert("Thank you! Your message has been sent successfully.");
                // empty the form
                contactForm.reset();
            // the backend refused it
            } else {
                // generic failure message
                alert("Something went wrong. Please try again.");
            }
        // couldn't reach the backend
        } catch (error) {
            // tell the user
            alert("Cannot connect to the Python backend. Is uvicorn running?");
        }
    });
}