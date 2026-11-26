// CHECKOUT: pick a quantity, then continue to Pesapal's secure payment page.
(async function () {
    const token = localStorage.getItem('shamba_token');
    if (!token) { window.location.href = 'login.html'; return; }
    const authHeaders = { 'Authorization': `Bearer ${token}` };

    const productId = new URLSearchParams(window.location.search).get('product');
    if (!productId) { window.location.href = 'products.html'; return; }

    const summary = document.getElementById('product-summary');
    const form = document.getElementById('checkout-form');
    const qtyInput = document.getElementById('order-qty');
    const qtyError = document.getElementById('qty-error');
    const totalEl = document.getElementById('order-total');
    const locationInput = document.getElementById('location');
    const emailInput = document.getElementById('email');
    const btn = document.getElementById('pay-btn');
    const msg = document.getElementById('checkout-msg');

    function say(text, ok) {
        msg.textContent = text;
        msg.className = 'feedback ' + (ok ? 'success' : 'error');
    }

    let product, me;
    try {
        const [pRes, meRes] = await Promise.all([
            fetch(`${API_BASE}/api/products/${encodeURIComponent(productId)}`),
            fetch(`${API_BASE}/api/me`, { headers: authHeaders }),
        ]);
        if (meRes.status === 401) { clearSession(); window.location.href = 'login.html'; return; }
        if (!pRes.ok) { say('That product is no longer available. Taking you back to the shop...', false); setTimeout(() => { window.location.href = 'products.html'; }, 2000); return; }
        product = await pRes.json();
        me = await meRes.json();
    } catch {
        summary.textContent = 'Cannot connect to the backend. Is uvicorn running?';
        btn.disabled = true;
        return;
    }

    if (me.role === 'farmer') {
        say("Farmers can't place orders. Log in with a customer account to buy.", false);
        btn.disabled = true;
        setTimeout(() => { window.location.href = 'dashboard.html'; }, 2500);
        return;
    }
    
    if (product.stock <= 0) {
        summary.textContent = `${product.item_name} is out of stock.`;
        btn.disabled = true;
        qtyInput.disabled = true;
        return;
    }

    summary.textContent = `${product.item_name} · ${formatKES(product.unit_price)} / ${product.unit} · by ${product.farmer_username || 'the farmer'}`;
    qtyInput.min = 1;
    qtyInput.max = product.stock;
    qtyInput.value = 1;
    
    document.getElementById('qty-unit').textContent = product.unit;
    document.getElementById('qty-hint').textContent = `${product.stock} ${product.unit} available`;
    
    emailInput.value = me.email || '';

    function currentQty() {
        const n = parseInt(qtyInput.value, 10);
        
        if (n > product.stock) {
            qtyError.textContent = `Only ${product.stock} ${product.unit} available in stock!`;
            qtyError.className = 'feedback error';
            qtyError.style.display = 'block';
            return null;
        }
        
        if (Number.isInteger(n) && n >= 1 && n <= product.stock) {
            qtyError.textContent = '';
            qtyError.style.display = 'none';
            return n;
        }
        return null;
    }
    
    function updateTotal() {
        const qty = currentQty();
        totalEl.textContent = qty ? formatKES(product.unit_price * qty) : '—';
    }
    
    qtyInput.addEventListener('input', updateTotal);
    updateTotal(); 

    window.addEventListener('pageshow', (e) => {
        if (e.persisted) { resetBtn(btn); }
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        msg.className = 'feedback';
        msg.textContent = '';

        const qty = currentQty();
        if (!qty) { 
            qtyInput.focus();
            return; 
        }

        setBtn(btn, 'Preparing payment...');

        try {
            const res = await fetch(`${API_BASE}/api/checkout`, {
                method: 'POST',
                headers: { ...authHeaders, 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    product_id: product.id,
                    quantity: qty,
                    location: locationInput.value.trim(),
                    email: emailInput.value.trim() || null,
                }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(errorMessage(data, 'Could not start the payment.'));

            say('Taking you to the secure payment page…', true);
            setBtn(btn, 'Redirecting...');
            window.location.href = data.redirect_url;
        } catch (error) {
            say(error.message, false);
            resetBtn(btn);
        }
    });
})();