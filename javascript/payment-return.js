// Pesapal sends the customer here after paying. We never trust the address bar:
// we ask our server, which asks Pesapal, what really happened.
// one async function so I can use await at the top level
(async function () {
    // the saved login token
    const token = localStorage.getItem('shamba_token');
    // Pesapal adds ?OrderTrackingId=... to the address when it sends the customer back
    const trackingId = new URLSearchParams(window.location.search).get('OrderTrackingId');

    // the page elements that show the result
    const icon = document.getElementById('result-icon');
    const title = document.getElementById('result-title');
    const text = document.getElementById('result-text');
    const detail = document.getElementById('result-detail');
    const actions = document.getElementById('result-actions');

    // opened without a payment reference: go to My Orders
    if (!trackingId) { window.location.href = 'customer-dashboard.html'; return; }

    // builds a link styled as a button
    function link(label, href, cls) {
        // the <a> element
        const a = document.createElement('a');
        // where it goes
        a.href = href;
        // CSS classes, e.g. 'btn main'
        a.className = 'btn ' + cls;
        // its label
        a.textContent = label;
        // hand it back
        return a;
    }
    // builds a button that runs a function when clicked
    function button(label, onClick) {
        // the <button> element
        const b = document.createElement('button');
        // a plain button, not a submit button
        b.type = 'button';
        // CSS classes
        b.className = 'btn alt';
        // its label
        b.textContent = label;
        // run the given function on click
        b.addEventListener('click', onClick);
        // hand it back
        return b;
    }
    // draws one result state: icon, heading, message, order summary and buttons
    function show(state, heading, message, order, extraActions) {
        // colour of the round icon: ok (green), bad (red) or wait (amber)
        icon.className = 'result-icon ' + state;
        // tick, exclamation mark or dots
        icon.textContent = { ok: '✓', bad: '!', wait: '…' }[state];
        // the heading
        title.textContent = heading;
        // the explanation
        text.textContent = message;
        // 'Order #3: 2 kg × Maize · KES 180' when an order is known
        detail.textContent = order
            ? `Order #${order.id}: ${order.qty} ${order.unit || ''} × ${order.product_name} · ${formatKES(order.amount)}`
            : '';
        // remove the old buttons
        actions.textContent = '';
        // add the new ones
        extraActions.forEach(a => actions.appendChild(a));
    }

    // not logged in: the server can't tell who this payment belongs to
    if (!token) {
        // ask them to log in
        show('wait', 'Please log in', 'Log in to see the result of your payment.', null,
             [link('Log in', 'login.html', 'main')]);
        // stop
        return;
    }

    // waits a number of milliseconds
    const sleep = ms => new Promise(r => setTimeout(r, ms));

    // asks my server (which asks Pesapal) what happened, retrying a few times
    async function check() {
        // show the 'checking' state first
        show('wait', 'Checking your payment…', 'This only takes a moment.', null, []);

        // up to 8 tries, 3 seconds apart, because M-Pesa can take a moment to confirm
        for (let attempt = 0; attempt < 8; attempt++) {
            // filled in by the request
            let res, data;
            // the request may fail
            try {
                // POST the tracking id to my backend
                res = await fetch(`${API_BASE}/api/payments/verify`, {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ order_tracking_id: trackingId }),
                });
                // read the reply
                data = await res.json();
            // no connection
            } catch {
                // the payment isn't lost; offer to check again
                show('bad', "Can't reach the server", 'Your payment is safe. Check again in a moment.', null,
                     [button('Check again', check), link('My orders', 'customer-dashboard.html', 'alt')]);
                // stop retrying
                return;
            }

            // login expired
            if (res.status === 401) {
                // forget the old login
                clearSession();
                // ask them to log in again
                show('wait', 'Please log in again', 'Your session expired. Log in to see your payment.', null,
                     [link('Log in', 'login.html', 'main')]);
                // stop
                return;
            }
            // the backend couldn't check (e.g. Pesapal unreachable)
            if (!res.ok) {
                // show its message and offer to retry
                show('bad', "We couldn't check the payment", errorMessage(data, 'Please try again shortly.'), null,
                     [button('Check again', check), link('My orders', 'customer-dashboard.html', 'alt')]);
                // stop
                return;
            }

            // what the backend decided about the payment
            const status = data.payment_status;
            // paid and confirmed
            if (status === 'completed') {
                // success screen with the order summary
                show('ok', 'Payment received', 'Thank you! The farmer has been notified and will arrange delivery.',
                     data.order, [link('View my orders', 'customer-dashboard.html', 'main'),
                                  link('Keep shopping', 'products.html', 'alt')]);
                // done
                return;
            }
            // the attempt failed
            if (status === 'failed') {
                // no charge; the order is kept so they can retry from My Orders
                show('bad', "Payment didn't go through", 'You have not been charged for this attempt. Your order is saved, so you can try again.',
                     data.order, [link('Go to My orders', 'customer_dashboard.html', 'main')]);
                // done
                return;
            }
            // money arrived but didn't match the order
            if (status === 'review') {
                // ask them to contact me with the order number
                show('bad', 'We need to double-check this payment',
                     'The amount we received did not match your order. Please contact us with your order number.',
                     data.order, [link('Contact us', 'contact.html', 'main'), link('My orders', 'customer-dashboard.html', 'alt')]);
                // done
                return;
            }
            // payment was reversed
            if (status === 'reversed') {
                // explain the refund
                show('bad', 'Payment reversed', 'This payment was reversed, so the order is refunded.', data.order,
                     [link('My orders', 'customer_dashboard.html', 'main')]);
                // done
                return;
            }
            // still pending: wait 3 seconds and ask again
            await sleep(3000); // still pending: M-Pesa can take a few seconds
        }

        // tried 8 times without an answer: explain that the order will update by itself
        show('wait', 'Still waiting for confirmation',
             "We haven't heard back yet. This can take a minute. You don't need to pay again: your order will update by itself.",
             null, [button('Check again', check), link('My orders', 'customer_dashboard.html', 'main')]);
    }

    // start checking as soon as the page loads
    check();
})();