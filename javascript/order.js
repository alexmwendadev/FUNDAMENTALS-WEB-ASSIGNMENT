// CHECKOUT: pick a quantity, then continue to Pesapal's secure payment page.
// everything is wrapped in one async function so I can use await at the top level
(async function () {
    // the saved login token
    const token = localStorage.getItem('shamba_token');
    // not logged in: go to the login page
    if (!token) { window.location.href = 'login.html'; return; }
    // sent with every request so the backend knows who is calling
    const authHeaders = { 'Authorization': `Bearer ${token}` };

    // the product comes from the address, e.g. order.html?product=3
    const productId = new URLSearchParams(window.location.search).get('product');
    // no product chosen: back to the shop
    if (!productId) { window.location.href = 'products.html'; return; }

    // the page elements this script reads and writes
    const summary = document.getElementById('product-summary');
    const form = document.getElementById('checkout-form');
    const qtyInput = document.getElementById('order-qty');
    const totalEl = document.getElementById('order-total');
    const phoneInput = document.getElementById('phone');
    const locationInput = document.getElementById('location');
    const emailInput = document.getElementById('email');
    const btn = document.getElementById('pay-btn');
    const msg = document.getElementById('checkout-msg');

    // shows a message under the button, in red or green
    function say(text, ok) {
        msg.textContent = text;
        msg.className = 'feedback ' + (ok ? 'success' : 'error');
    }

    // ---- load the product and the signed-in customer ----
    // filled in below
    let product, me;
    // load both things at the same time to save a round trip
    try {
        // the product (fresh price and stock) and the logged in customer
        const [pRes, meRes] = await Promise.all([
            fetch(`${API_BASE}/api/products/${encodeURIComponent(productId)}`),
            fetch(`${API_BASE}/api/me`, { headers: authHeaders }),
        ]);
        // login expired: log in again
        if (meRes.status === 401) { clearSession(); window.location.href = 'login.html'; return; }
        // product was deleted or never existed
        if (!pRes.ok) { say('That product is no longer available. Taking you back to the shop...', false); setTimeout(() => { window.location.href = 'products.html'; }, 2000); return; }
        // read both replies
        product = await pRes.json();
        me = await meRes.json();
    // backend unreachable
    } catch {
        summary.textContent = 'Cannot connect to the backend. Is uvicorn running?';
        // nothing can be ordered without the backend
        btn.disabled = true;
        return;
    }

    // farmers can't buy (the backend refuses too)
    if (me.role === 'farmer') {
        say("Farmers can't place orders. Log in with a customer account to buy.", false);
        // leave the message on screen for a moment before moving on
        btn.disabled = true;
        setTimeout(() => { window.location.href = 'dashboard.html'; }, 2500);
        return;
    }
    // sold out: disable the form
    if (product.stock <= 0) {
        // 'Maize · KES 90 / kg · by <farmer>'
        summary.textContent = `${product.item_name} is out of stock.`;
        btn.disabled = true;
        qtyInput.disabled = true;
        return;
    }

    summary.textContent = `${product.item_name} · ${formatKES(product.unit_price)} / ${product.unit} · by ${product.farmer_username || 'the farmer'}`;
    // quantity can't go below 1...
    qtyInput.min = 1;
    // ...or above what is in stock
    qtyInput.max = product.stock;
    // start with one
    qtyInput.value = 1;
    // show the unit next to the label
    document.getElementById('qty-unit').textContent = product.unit;
    // how many are left
    document.getElementById('qty-hint').textContent = `${product.stock} ${product.unit} available`;
    // fill in the saved phone number as people write it (07...)
    phoneInput.value = localPhone(me.phone);
    // and the saved email, if the account has one
    emailInput.value = me.email || '';

    // the quantity typed, or null if it isn't a whole number within stock
    function currentQty() {
        // read it as a whole number
        const n = parseInt(qtyInput.value, 10);
        
        // NEW: Show immediate inline feedback if they try to order more than what's available
        if (n > product.stock) {
            say(`Only ${product.stock} ${product.unit} available in stock!`, false);
            return null;
        }
        
        // valid only if whole, at least 1 and not above the stock
        if (Number.isInteger(n) && n >= 1 && n <= product.stock) {
            // Clear any previous max stock error if they fix it
            if (msg.textContent.includes("Only")) { msg.className = 'feedback'; msg.textContent = ''; }
            return n;
        }
        return null;
    }
    
    // shows price x quantity. This is only a preview; the real total is worked out again by the server
    function updateTotal() {
        // current valid quantity
        const qty = currentQty();
        // a dash when the quantity isn't valid
        totalEl.textContent = qty ? formatKES(product.unit_price * qty) : '—';
    }
    // update the total on every keystroke
    qtyInput.addEventListener('input', updateTotal);
    // and once at the start
    updateTotal();

    // Coming back from Pesapal with the browser's Back button: let them try again
    window.addEventListener('pageshow', (e) => {
        // restored from the browser's cache: re-enable the button
        if (e.persisted) { resetBtn(btn); }
    });

    // ---- place the order ----
    // runs when 'Continue to payment' is pressed
    form.addEventListener('submit', async (e) => {
        // stop the normal form submit
        e.preventDefault();
        // hide any old message
        msg.className = 'feedback';

        // check the quantity again
        const qty = currentQty();
        // invalid: stop
        if (!qty) { say(`Enter a quantity between 1 and ${product.stock}.`, false); return; }

        // block double clicks, which would create two orders. The button says what is happening
        setBtn(btn, 'Preparing payment...');

        // send the order
        try {
            // POST to the backend. Only the product id and quantity are sent: no price and no total
            const res = await fetch(`${API_BASE}/api/checkout`, {
                method: 'POST',
                headers: { ...authHeaders, 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    // which product
                    product_id: product.id,
                    // how many (a whole number)
                    quantity: qty,
                    // contact phone
                    phone: phoneInput.value.trim(),
                    // delivery location
                    location: locationInput.value.trim(),
                    // receipt email (null if empty)
                    email: emailInput.value.trim() || null,
                }),
            });
            // the reply: order id and the Pesapal page address
            const data = await res.json();
            // turn a backend error into the catch below
            if (!res.ok) throw new Error(errorMessage(data, 'Could not start the payment.'));

            // tell the customer what is happening
            say('Taking you to the secure payment page…', true);
            // button says 'Redirecting...' while the browser leaves for Pesapal
            setBtn(btn, 'Redirecting...');
            // send the customer to Pesapal's secure payment page
            window.location.href = data.redirect_url;
        // anything went wrong
        } catch (error) {
            // NEW: Show reason inline instead of popup
            say(error.message, false);
            // let them try again: put the normal label back
            resetBtn(btn);
        }
    });
})();