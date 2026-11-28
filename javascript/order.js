// CHECKOUT: pick a quantity, then continue to Pesapal's secure payment page.
// the whole page logic is wrapped in one function that runs immediately, so my variables don't leak into other scripts
(async function () {
    // the login token saved by the login page; no token means they aren't logged in
    const token = localStorage.getItem('shamba_token');
    // send them to the login page and stop this script
    if (!token) { window.location.href = 'login.html'; return; }
    // the header that proves who the buyer is on every API call
    const authHeaders = { 'Authorization': `Bearer ${token}` };

    // the product id comes from the address, e.g. order.html?product=5
    const productId = new URLSearchParams(window.location.search).get('product');
    // no product chosen: back to the shop
    if (!productId) { window.location.href = 'products.html'; return; }

    // grab the page elements once: summary text, form, quantity box, error text, total, location, email, pay button and message line
    const summary = document.getElementById('product-summary');
    const form = document.getElementById('checkout-form');
    const qtyInput = document.getElementById('order-qty');
    const qtyError = document.getElementById('qty-error');
    const totalEl = document.getElementById('order-total');
    const locationInput = document.getElementById('location');
    const emailInput = document.getElementById('email');
    const btn = document.getElementById('pay-btn');
    const msg = document.getElementById('checkout-msg');

    // shows a green (ok) or red (error) message under the form
    function say(text, ok) {
        msg.textContent = text;
        msg.className = 'feedback ' + (ok ? 'success' : 'error');
    }

    // product = what is being bought, me = the logged-in user
    let product, me;
    // load the product and the user at the same time (faster than one after the other)
    try {
        const [pRes, meRes] = await Promise.all([
            fetch(`${API_BASE}/api/products/${encodeURIComponent(productId)}`),
            fetch(`${API_BASE}/api/me`, { headers: authHeaders }),
        ]);
        // token expired or invalid: clear it and log in again
        if (meRes.status === 401) { clearSession(); window.location.href = 'login.html'; return; }
        // the product was deleted: tell them and go back to the shop
        if (!pRes.ok) { say('That product is no longer available. Taking you back to the shop...', false); setTimeout(() => { window.location.href = 'products.html'; }, 2000); return; }
        product = await pRes.json();
        me = await meRes.json();
    // network error: the server can't be reached
    } catch {
        summary.textContent = 'Cannot connect to the backend. Is uvicorn running?';
        btn.disabled = true;
        return;
    }

    // farmers sell, they can't buy (the server blocks this too)
    if (me.role === 'farmer') {
        say("Farmers can't place orders. Log in with a customer account to buy.", false);
        btn.disabled = true;
        setTimeout(() => { window.location.href = 'dashboard.html'; }, 2500);
        return;
    }
    
    // sold out: switch ordering off
    if (product.stock <= 0) {
        // e.g. 'Tomatoes · KES 90 / kg · by mary'
        summary.textContent = `${product.item_name} is out of stock.`;
        btn.disabled = true;
        qtyInput.disabled = true;
        return;
    }

    summary.textContent = `${product.item_name} · ${formatKES(product.unit_price)} / ${product.unit} · by ${product.farmer_username || 'the farmer'}`;
    // the quantity box allows 1 up to the stock available, and starts at 1
    qtyInput.min = 1;
    qtyInput.max = product.stock;
    qtyInput.value = 1;
    
    // show the unit and how much is left next to the box
    document.getElementById('qty-unit').textContent = product.unit;
    document.getElementById('qty-hint').textContent = `${product.stock} ${product.unit} available`;
    
    // pre-fill their email if the account has one
    emailInput.value = me.email || '';

    // reads the quantity box and returns a valid whole number, or null (and shows an error) when it's invalid
    function currentQty() {
        const n = parseInt(qtyInput.value, 10);
        
        // asking for more than is in stock
        if (n > product.stock) {
            qtyError.textContent = `Only ${product.stock} ${product.unit} available in stock!`;
            qtyError.className = 'feedback error';
            qtyError.style.display = 'block';
            return null;
        }
        
        // valid: clear any error and return the number
        if (Number.isInteger(n) && n >= 1 && n <= product.stock) {
            qtyError.textContent = '';
            qtyError.style.display = 'none';
            return n;
        }
        return null;
    }
    
    // recalculates price x quantity and shows it (a dash when the quantity is invalid)
    function updateTotal() {
        const qty = currentQty();
        totalEl.textContent = qty ? formatKES(product.unit_price * qty) : '—';
    }
    
    // update the total every time the quantity changes
    qtyInput.addEventListener('input', updateTotal);
    // and once now for the starting value
    updateTotal(); 

    // if the buyer presses Back from the payment page the browser may restore this page frozen, so re-enable the button
    window.addEventListener('pageshow', (e) => {
        if (e.persisted) { resetBtn(btn); }
    });

    // runs when the buyer presses the pay button
    form.addEventListener('submit', async (e) => {
        // stop the browser's normal form submit (I send it myself with fetch)
        e.preventDefault();
        msg.className = 'feedback';
        msg.textContent = '';

        // the validated quantity
        const qty = currentQty();
        // invalid quantity: put the cursor back in the box
        if (!qty) { 
            qtyInput.focus();
            return; 
        }

        // disable the button so they can't click twice
        setBtn(btn, 'Preparing payment...');

        try {
            // ask the backend to create the order and start the Pesapal payment
            const res = await fetch(`${API_BASE}/api/checkout`, {
                method: 'POST',
                headers: { ...authHeaders, 'Content-Type': 'application/json' },
                // only ids and what the buyer typed are sent; the price is looked up on the server so it can't be tampered with
                body: JSON.stringify({
                    product_id: product.id,
                    quantity: qty,
                    location: locationInput.value.trim(),
                    email: emailInput.value.trim() || null,
                }),
            });
            const data = await res.json();
            // turn an API error into a readable message (caught below)
            if (!res.ok) throw new Error(errorMessage(data, 'Could not start the payment.'));

            say('Taking you to the secure payment page…', true);
            setBtn(btn, 'Redirecting...');
            // go to Pesapal's secure page to pay
            window.location.href = data.redirect_url;
        // show the problem and let them try again
        } catch (error) {
            say(error.message, false);
            resetBtn(btn);
        }
    });
})();