// CUSTOMER DASHBOARD: my orders, with pay / check-payment actions.
// one async function so I can use await at the top level
(async function () {
    // the saved login token
    const token = localStorage.getItem('shamba_token');
    // not logged in: go to the login page
    if (!token) { window.location.href = 'login.html'; return; }
    // sent with every request so the backend knows who is calling
    const authHeaders = { 'Authorization': `Bearer ${token}` };

    // the box the orders table is drawn into
    const container = document.getElementById('customer-orders');
    // the line for success and error messages
    const notice = document.getElementById('orders-msg');

    // shows a message above the table, in green or red
    function say(text, ok) {
        notice.textContent = text;
        notice.className = 'feedback ' + (ok ? 'success' : 'error');
    }
    // adds one table cell to a row; text goes in as plain text so nothing typed by anybody can run as code
    function cell(row, content) {
        // the cell
        const td = document.createElement('td');
        // a ready-made element (badge, buttons) is placed as it is...
        if (content instanceof Node) td.appendChild(content);
        // ...text is placed as plain text
        else td.textContent = content;
        // add the cell to the row
        row.appendChild(td);
        // some callers add more to the cell
        return td;
    }

    // ---- who is this? ----
    // find out who is logged in
    try {
        // ask the backend
        const res = await fetch(`${API_BASE}/api/me`, { headers: authHeaders });
        // login expired: log in again
        if (res.status === 401) { clearSession(); window.location.href = 'login.html'; return; }
        // my details
        const me = await res.json();
        // farmers have their own dashboard
        if (me.role === 'farmer') { window.location.href = 'dashboard.html'; return; }
        // show my name in the top bar
        document.getElementById('dash-username').textContent = me.username;
    // backend unreachable
    } catch {
        container.innerHTML = '<p class="empty-note">Cannot connect to the backend. Is uvicorn running?</p>';
        // nothing can be loaded
        return;
    }

    // gets my orders from the backend
    async function fetchOrders() {
        // the reply
        const res = await fetch(`${API_BASE}/api/my-orders/buying`, { headers: authHeaders });
        // any error status is a failure
        if (!res.ok) throw new Error('Failed to load orders');
        // the list of orders
        return res.json();
    }

    // Send the customer (back) to Pesapal for an unpaid order
    // 'Pay now': asks the backend for a new payment attempt and sends the customer to Pesapal
    async function payNow(order, btn) {
        // block double clicks
        btn.disabled = true;
        // ask the backend
        try {
            // POST /api/orders/<id>/pay
            const res = await fetch(`${API_BASE}/api/orders/${order.id}/pay`, { method: 'POST', headers: authHeaders });
            // the reply with the Pesapal address
            const data = await res.json();
            // show the backend's reason below
            if (!res.ok) throw new Error(errorMessage(data, 'Could not start the payment.'));
            // go to Pesapal
            window.location.href = data.redirect_url;
        // something failed
        } catch (err) {
            // NEW: Show inline error
            say(err.message, false);
            // allow another try
            btn.disabled = false;
        }
    }

    // 'Check payment': asks the backend to re-check with Pesapal, then redraws the table
    async function checkPayment(order, btn) {
        // block double clicks
        btn.disabled = true;
        // feedback while waiting
        btn.textContent = 'Checking…';
        // ask the backend
        try {
            // POST /api/orders/<id>/verify
            const res = await fetch(`${API_BASE}/api/orders/${order.id}/verify`, { method: 'POST', headers: authHeaders });
            // the order with its newest status
            const data = await res.json();
            // show the backend's reason below
            if (!res.ok) throw new Error(errorMessage(data, 'Could not check the payment.'));
            
            // NEW: Show inline message instead of toast
            say(data.order.status === 'pending'
                ? `Order #${order.id} is still waiting for payment.`
                : `Order #${order.id} is confirmed. Thank you!`, data.order.status !== 'pending');
            
            // reload the orders and redraw the table
            render(await fetchOrders());
        // something failed
        } catch (err) {
            // NEW: Show inline error
            say(err.message, false);
            // allow another try
            btn.disabled = false;
            // reset the label
            btn.textContent = 'Check payment';
        }
    }

    // draws the whole orders table (or the 'no orders yet' box)
    function render(orders) {
        // clear the old table
        container.textContent = '';
        // no orders yet
        if (orders.length === 0) {
            // friendly empty state with a button to the shop
            const box = document.createElement('div');
            // CSS class
            box.className = 'empty-note';
            // the sentence
            const p = document.createElement('p');
            // spacing
            p.style.marginBottom = '15px';
            // the text
            p.textContent = "You haven't placed any orders yet.";
            // the link
            const a = document.createElement('a');
            // to the shop
            a.href = 'products.html';
            // styled as a button
            a.className = 'btn main';
            // label
            a.textContent = 'Browse Marketplace';
            // put both in the box
            box.append(p, a);
            // show it
            container.appendChild(box);
            // nothing more to draw
            return;
        }

        // scroll wrapper so the table fits small screens
        const wrap = document.createElement('div');
        // CSS class
        wrap.className = 'dash-table-scroll';
        // the table
        const table = document.createElement('table');
        // CSS class
        table.className = 'dash-table';

        // the header row, one cell per column
        const headRow = document.createElement('tr');
        // the column titles (the last one is empty: it holds the buttons)
        ['Order', 'Product', 'Qty', 'Total', 'Date', 'Status', ''].forEach(h => {
            // a header cell
            const th = document.createElement('th');
            // its title
            th.textContent = h;
            // add it
            headRow.appendChild(th);
        });
        // wrap the header row
        const thead = document.createElement('thead');
        // add it
        thead.appendChild(headRow);
        // the table body
        const tbody = document.createElement('tbody');

        // one row per order
        orders.forEach(o => {
            // the row
            const tr = document.createElement('tr');
            // order number in bold
            const idStrong = document.createElement('strong');
            // #3, #4...
            idStrong.textContent = `#${o.id}`;
            // column 1: order number
            cell(tr, idStrong);
            // column 2: product name (plain text, because the farmer chose it)
            cell(tr, o.product_name);                       // plain text: farmers choose this value
            // column 3: quantity and unit
            cell(tr, o.qty ? `${o.qty} ${o.unit || ''}`.trim() : '—');
            // column 4: total
            cell(tr, formatKES(o.amount));
            // column 5: date
            cell(tr, o.created_at ? new Date(o.created_at).toLocaleDateString() : 'N/A');

            // column 6: the coloured status badge
            const statusCell = cell(tr, statusPill(o.status));
            // an unpaid order whose last attempt failed gets a small hint
            if (o.status === 'pending' && o.payment_status === 'failed') {
                // the hint text
                const hint = document.createElement('small');
                // CSS class
                hint.className = 'hint';
                // on its own line
                hint.style.display = 'block';
                // the message
                hint.textContent = 'Last payment attempt failed';
                // put it under the badge
                statusCell.appendChild(hint);
            }

            // column 7: buttons
            const actions = document.createElement('div');
            // CSS class
            actions.className = 'table-actions';
            // buttons only for unpaid orders
            if (o.status === 'pending') {
                // 'Pay now' button
                const pay = document.createElement('button');
                // CSS classes
                pay.className = 'btn main small';
                // label
                pay.textContent = 'Pay now';
                // start a payment for this order
                pay.addEventListener('click', () => payNow(o, pay));
                // add it
                actions.appendChild(pay);
                // 'Check payment' only makes sense once a payment was started
                if (o.payment_status) {
                    // the button
                    const check = document.createElement('button');
                    // CSS classes
                    check.className = 'btn alt small';
                    // label
                    check.textContent = 'Check payment';
                    // re-check this order
                    check.addEventListener('click', () => checkPayment(o, check));
                    // add it
                    actions.appendChild(check);
                }
            }
            // add the buttons cell
            cell(tr, actions);
            // add the row
            tbody.appendChild(tr);
        });

        // assemble the table
        table.append(thead, tbody);
        // put it in the scroll wrapper
        wrap.appendChild(table);
        // show it on the page
        container.appendChild(wrap);
    }

    // If a payment notification was missed, quietly re-check the newest unpaid orders.
    // if Pesapal's notification never reached me, this re-checks the newest unpaid orders when the page opens
    async function autoVerify(orders) {
        // up to 3 unpaid orders that have a payment attempt
        const waiting = orders.filter(o => o.status === 'pending' && o.payment_status).slice(0, 3);
        // becomes true if any order turns out to be paid
        let changed = false;
        // check them one after another
        for (const o of waiting) {
            // a failure on one order shouldn't stop the others
            try {
                // POST /api/orders/<id>/verify
                const res = await fetch(`${API_BASE}/api/orders/${o.id}/verify`, { method: 'POST', headers: authHeaders });
                // the order is no longer pending
                if (res.ok && (await res.json()).order.status !== 'pending') {
                    // remember to redraw
                    changed = true;
                    // NEW: Alert instead of toast
                    alert(`Order #${o.id} is confirmed. Thank you!`);
                }
            // ignore this order and carry on
            } catch {}
        }
        // reload and redraw if anything changed
        if (changed) render(await fetchOrders());
    }

    // first load of the page
    try {
        // get my orders
        const orders = await fetchOrders();
        // draw them
        render(orders);
        // then quietly re-check unpaid ones in the background
        autoVerify(orders);
    // couldn't load the orders
    } catch {
        // show an error message
        container.innerHTML = '<p class="empty-note" style="color: #d93025;">Error loading orders. Please try again later.</p>';
    }
})();