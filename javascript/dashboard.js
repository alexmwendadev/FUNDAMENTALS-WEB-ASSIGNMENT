// DASHBOARD LOGIC (Farmer)
// largest product photo accepted, in bytes (5 MB). The backend checks the same limit
const MAX_PRODUCT_IMAGE = 5 * 1024 * 1024;

// the header that tells the backend who I am
function authHeaders(token) {
    // 'Bearer <token>' is the standard format
    return { 'Authorization': `Bearer ${token}` };
}

// ---------- Tab switching ----------
// makes the sidebar buttons and the 'Add New Product' buttons switch tabs
function initTabs() {
    // every sidebar tab (the Home/Marketplace links have no data-tab, so they are skipped)
    document.querySelectorAll('.dash-tab[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });
    // buttons elsewhere that jump to a tab
    document.querySelectorAll('[data-goto-tab]').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.gotoTab));
    });
}

// shows one tab panel and highlights its button
function switchTab(name) {
    // highlight the matching sidebar button only
    document.querySelectorAll('.dash-tab[data-tab]').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
    // show the matching panel only
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.toggle('active', p.id === `tab-${name}`));
}

// ---------- Helpers ----------
// builds a table from a list of column titles and rows. Each cell is text or a ready-made element
function buildTable(headers, rows) {
    // scroll wrapper so wide tables fit small screens
    const wrap = document.createElement('div');
    wrap.className = 'dash-table-scroll';
    // the table itself
    const table = document.createElement('table');
    table.className = 'dash-table';
    // the header section
    const thead = document.createElement('thead');
    // the header row
    const trH = document.createElement('tr');
    // one header cell per title
    headers.forEach(h => {
        const th = document.createElement('th');
        th.textContent = h;
        trH.appendChild(th);
    });
    // put the header row in the header section
    thead.appendChild(trH);
    table.appendChild(thead);

    // the body section
    const tbody = document.createElement('tbody');
    // one table row per data row
    rows.forEach(cells => {
        const tr = document.createElement('tr');
        // one cell per value
        cells.forEach(cell => {
            const td = document.createElement('td');
            // an element (badge, button, image) is placed as it is...
            if (cell instanceof Node) td.appendChild(cell);
            // ...text is placed as plain text, so it can never run as code
            else td.textContent = cell;
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
}

// '2 kg', or a dash when the order has no quantity
function qtyText(o) {
    return o.qty ? `${o.qty} ${o.unit || ''}`.trim() : '—';
}

// -------- Loaders --------
// fills the Overview tab: the four stat cards and the three newest orders
async function loadOverview(token) {
    // fetch my products and my orders at the same time
    const [prodRes, ordRes] = await Promise.all([
        fetch(`${API_BASE}/api/my-products`, { headers: authHeaders(token) }),
        fetch(`${API_BASE}/api/my-orders`, { headers: authHeaders(token) }),
    ]);
    // empty list if the request failed
    const products = prodRes.ok ? await prodRes.json() : [];
    // farmers only ever receive paid orders from the backend
    const orders = ordRes.ok ? await ordRes.json() : [];

    // paid, waiting for me to deliver
    const toDeliver = orders.filter(o => o.status === 'paid');
    // already delivered
    const delivered = orders.filter(o => o.status === 'delivered');
    // money received so far = total of paid and delivered orders (before I pay the farmer out)
    const earned = [...toDeliver, ...delivered].reduce((sum, o) => sum + (o.amount || 0), 0);

    // number of products listed
    document.getElementById('stat-products').textContent = products.length;
    // number of orders to deliver
    document.getElementById('stat-to-deliver').textContent = toDeliver.length;
    // number of delivered orders
    document.getElementById('stat-delivered').textContent = delivered.length;
    // total earned, formatted as money
    document.getElementById('stat-earned').textContent = formatKES(earned);

    // Make the Product Stat Card clickable to jump to My Products tab
    const statCard = document.getElementById('stat-products-card');
    if (statCard) {
        statCard.onclick = () => switchTab('products');
    }

    // only the 3 newest orders
    const recent = orders.slice(0, 3);
    // where the recent orders go
    const box = document.getElementById('recent-orders');
    // clear the old content
    box.innerHTML = '';
    // no paid orders yet
    if (!recent.length) {
        box.innerHTML = '<p class="empty-note">No paid orders yet.</p>';
        // nothing to draw
        return;
    }
    // table of the newest orders
    box.appendChild(buildTable(
        ['Buyer', 'Product', 'Qty', 'Total', 'Status'],
        recent.map(o => [o.buyer_username, o.product_name, qtyText(o), formatKES(o.amount), statusPill(o.status)])
    ));
}

// fills the My Products tab
async function loadMyProducts(token) {
    // where the table goes
    const box = document.getElementById('my-products');
    box.innerHTML = '<p class="empty-note">Loading…</p>';
    // ask the backend for my products
    const res = await fetch(`${API_BASE}/api/my-products`, { headers: authHeaders(token) });
    // couldn't load them
    if (!res.ok) {
        box.innerHTML = '<p class="empty-note">Could not load products.</p>';
        // stop
        return;
    }
    // the list
    const products = await res.json();
    // none listed yet
    if (!products.length) {
        box.innerHTML = '<p class="empty-note">You have not listed any products yet. Click <strong>Add New Product</strong>.</p>';
        // stop
        return;
    }

    // one table row per product
    const rows = products.map(p => {
        // small preview photo
        const thumb = document.createElement('img');
        // full address of the photo
        thumb.src = assetUrl(p.image_url);
        // CSS class for the thumbnail size
        thumb.className = 'thumb';
        // alt text for screen readers
        thumb.alt = p.item_name;

        // the Remove button
        const del = document.createElement('button');
        // red button styling
        del.className = 'btn danger small';
        // label
        del.textContent = 'Remove';
        // what happens when Remove is pressed
        del.addEventListener('click', async () => {
            // ask first, so a slip doesn't delete a product
            if (!confirm(`Remove "${p.item_name}" from the marketplace?`)) return;
            // DELETE the product on the backend
            const r = await fetch(`${API_BASE}/api/products/${p.id}`, {
                method: 'DELETE',
                headers: authHeaders(token),
            });
            // removed: reload the table and the stats
            if (r.ok) {
                // redraw the products table
                loadMyProducts(token);
                // update the product count
                loadOverview(token);
            // the backend refused
            } else {
                // NEW: Use alert instead of toast
                showToast('Could not remove product.');
            }
        });

        // Edit Stock Button
        const editBtn = document.createElement('button');
        editBtn.className = 'btn alt small';
        editBtn.textContent = 'Edit Stock';
        editBtn.style.marginRight = '8px';
        
        // NEW: Open the modal instead of using prompt()
        editBtn.addEventListener('click', () => {
            const modal = document.getElementById('edit-stock-modal');
            const nameDisplay = document.getElementById('modal-product-name');
            const stockInput = document.getElementById('modal-stock-input');
            const saveBtn = document.getElementById('modal-save-btn');
            const cancelBtn = document.getElementById('modal-cancel-btn');

            // Set up modal data
            nameDisplay.textContent = p.item_name;
            stockInput.value = p.stock;
            modal.style.display = 'flex';

            // Handle Cancel
            const closeModal = () => { modal.style.display = 'none'; };
            cancelBtn.onclick = closeModal;

            // Handle Save
            saveBtn.onclick = async () => {
                const newStock = stockInput.value.trim();
                if (newStock === '' || Number(newStock) < 0) {
                    showToast("Please enter a valid stock amount."); return;
                }

                // button says 'Saving...' while the change is sent
                setBtn(saveBtn, 'Saving...');
                const body = new URLSearchParams({ stock: newStock });
                const r = await fetch(`${API_BASE}/api/products/${p.id}`, {
                    method: 'PATCH',
                    headers: { ...authHeaders(token), 'Content-Type': 'application/x-www-form-urlencoded' },
                    body
                });

                if (r.ok) {
                    // 'Saved!' for a moment, then close the box and put the label back
                    setBtn(saveBtn, 'Saved!');
                    await pause(700);
                    closeModal();
                    resetBtn(saveBtn);
                    loadMyProducts(token);
                    loadOverview(token);
                } else {
                    showToast(errorMessage(await r.json().catch(() => null), 'Failed to update stock.'));
                    resetBtn(saveBtn);
                }
            };
        });

        // Group the buttons together
        const actionCell = document.createElement('div');
        actionCell.append(editBtn, del);

        // the row: photo, name, price per unit, stock left (or 'Out of stock') and the Action buttons
        return [thumb, p.item_name, `${formatKES(p.unit_price)} / ${p.unit}`,
                p.stock > 0 ? `${p.stock} ${p.unit}` : 'Out of stock', actionCell];
    });

    // clear 'Loading…'
    box.innerHTML = '';
    // draw the table
    box.appendChild(buildTable(['Image', 'Product', 'Price', 'In stock', 'Action'], rows));
}

// fills the Orders tab
async function loadMyOrders(token) {
    // where the table goes
    const box = document.getElementById('my-orders');
    box.innerHTML = '<p class="empty-note">Loading…</p>';
    // ask the backend for my paid orders
    const res = await fetch(`${API_BASE}/api/my-orders`, { headers: authHeaders(token) });
    // couldn't load them
    if (!res.ok) {
        box.innerHTML = '<p class="empty-note">Could not load orders.</p>';
        // stop
        return;
    }
    // the list
    const orders = await res.json();
    // no paid orders yet
    if (!orders.length) {
        box.innerHTML = '<p class="empty-note">No paid orders yet. When a customer pays for one of your products, it will appear here.</p>';
        // stop
        return;
    }

    // one table row per order
    const rows = orders.map(o => {
        // holds the 'Mark delivered' button (empty for orders that are already delivered)
        const action = document.createElement('span');
        // only a paid order can be marked delivered
        if (o.status === 'paid') {
            // the button
            const btn = document.createElement('button');
            // styling
            btn.className = 'btn main small';
            // label
            btn.textContent = 'Mark delivered';
            // what happens when it is pressed
            btn.addEventListener('click', async () => {
                // ask first
                if (!confirm(`Mark order #${o.id} as delivered?`)) return;
                // block double clicks
                setBtn(btn, 'Saving...');
                // the backend expects form-style data; 'delivered' is the only value it accepts
                const body = new URLSearchParams({ new_status: 'delivered' });
                // PATCH the order's status
                const r = await fetch(`${API_BASE}/api/orders/${o.id}/status`, {
                    method: 'PATCH',
                    headers: { ...authHeaders(token), 'Content-Type': 'application/x-www-form-urlencoded' },
                    body,
                });
                // done: reload the orders and the stats
                if (r.ok) {
                    // redraw the orders table
                    loadMyOrders(token);
                    // update the stat cards
                    loadOverview(token);
                // the backend refused
                } else {
                    // allow another try
                    resetBtn(btn);
                    // NEW: Use alert instead of toast
                    showToast('Could not update the order.');
                }
            });
            // put the button in the cell
            action.appendChild(btn);
        }

        // the row: order number, buyer, product, quantity, total, phone, location, status badge, date and the button.
        return [
            `#${o.id}`,
            o.buyer_username,
            o.product_name,
            qtyText(o),
            formatKES(o.amount),
            o.phone,
            o.location,
            statusPill(o.status),
            o.created_at ? o.created_at.slice(0, 10) : '—',
            action,
        ];
    });

    // clear 'Loading…'
    box.innerHTML = '';
    // draw the table
    box.appendChild(buildTable(
        ['Order', 'Buyer', 'Product', 'Qty', 'Total', 'Phone', 'Location', 'Status', 'Date', ''],
        rows
    ));
}

// ---------- Photo picker (upload a file OR use the live camera) ----------
// the photo that will be sent to the backend, whichever way it was chosen
let selectedPhoto = null;
// the running camera stream (null when the camera is off)
let cameraStream = null;
// which camera is in use: 'environment' = back camera, 'user' = front camera
let cameraFacing = 'environment';
// address of the preview image, so it can be released from memory
let previewUrl = null;

// turns the camera off
function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(t => t.stop());
        cameraStream = null;
    }
    const video = document.getElementById('camera-video');
    if (video) { video.srcObject = null; video.classList.remove('live'); }
    const start = document.getElementById('camera-start');
    const capture = document.getElementById('camera-capture');
    const flip = document.getElementById('camera-flip');
    if (start) start.style.display = '';
    if (capture) capture.style.display = 'none';
    if (flip) flip.style.display = 'none';
}

// shows a message under the photo picker (empty text clears it)
function setPhotoError(text) {
    const el = document.getElementById('photo-error');
    if (!el) return;
    el.textContent = text;
    el.className = text ? 'feedback error' : 'feedback';
}

// remembers the chosen photo and shows its preview
function setSelectedPhoto(file) {
    selectedPhoto = file;
    if (previewUrl) { URL.revokeObjectURL(previewUrl); previewUrl = null; }
    const picker = document.getElementById('photo-upload-box');
    const camBox = document.getElementById('photo-camera-box');
    const options = document.querySelector('.photo-options');
    const prevBox = document.getElementById('photo-preview-box');
    if (file) {
        previewUrl = URL.createObjectURL(file);
        document.getElementById('photo-preview').src = previewUrl;
        // hide the two options, show only the preview
        picker.style.display = 'none';
        camBox.style.display = 'none';
        options.style.display = 'none';
        prevBox.style.display = 'flex';
    } else {
        document.getElementById('photo-preview').removeAttribute('src');
        prevBox.style.display = 'none';
        options.style.display = 'flex';
    }
}

// switches between the 'Upload Image' and 'Use Camera' options
function showPhotoOption(which) {
    const isCamera = which === 'camera';
    document.getElementById('opt-upload').classList.toggle('active', !isCamera);
    document.getElementById('opt-camera').classList.toggle('active', isCamera);
    document.getElementById('photo-upload-box').style.display = isCamera ? 'none' : 'flex';
    document.getElementById('photo-camera-box').style.display = isCamera ? 'flex' : 'none';
    // leaving the camera option turns the camera off
    if (!isCamera) stopCamera();
    setPhotoError('');
}

// opens the camera and shows the live picture
async function startCamera() {
    setPhotoError('');
    // browsers only allow the camera on https:// pages (or localhost)
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setPhotoError('Camera is not available here. Use "Upload Image" instead (the camera needs a secure https page).');
        return;
    }
    // close any camera already running (e.g. when switching front/back)
    stopCamera();
    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { ideal: cameraFacing } },
            audio: false,
        });
    } catch (e) {
        // permission denied, or no camera found
        setPhotoError(e && e.name === 'NotAllowedError'
            ? 'Camera access was blocked. Allow it in your browser settings, or use "Upload Image".'
            : 'Could not open the camera. Use "Upload Image" instead.');
        return;
    }
    const video = document.getElementById('camera-video');
    video.srcObject = cameraStream;
    video.classList.add('live');
    document.getElementById('camera-start').style.display = 'none';
    document.getElementById('camera-capture').style.display = '';
    document.getElementById('camera-flip').style.display = '';
}

// takes a still picture from the live camera and turns it into a file
function capturePhoto() {
    const video = document.getElementById('camera-video');
    // camera not ready yet
    if (!video.videoWidth) { setPhotoError('Camera is still loading. Try again in a second.'); return; }

    // draws the current video frame, scaled down so the file stays under the 5 MB limit
    const draw = (maxSide) => {
        const scale = Math.min(1, maxSide / Math.max(video.videoWidth, video.videoHeight));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(video.videoWidth * scale);
        canvas.height = Math.round(video.videoHeight * scale);
        canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas;
    };

    // tries 2000px at 90% quality first, then smaller until it fits
    const attempts = [[2000, 0.9], [1600, 0.85], [1200, 0.8], [800, 0.75]];
    const tryNext = (i) => {
        draw(attempts[i][0]).toBlob((blob) => {
            if (!blob) { setPhotoError('Could not capture the photo. Try again.'); return; }
            // too big and smaller sizes are left: try the next one
            if (blob.size > MAX_PRODUCT_IMAGE && i < attempts.length - 1) { tryNext(i + 1); return; }
            const file = new File([blob], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' });
            stopCamera();
            setPhotoError('');
            setSelectedPhoto(file);
        }, 'image/jpeg', attempts[i][1]);
    };
    tryNext(0);
}

// brings the picker back to its starting state (used after a successful upload)
function resetPhotoPicker() {
    stopCamera();
    document.getElementById('image').value = '';
    setSelectedPhoto(null);
    showPhotoOption('upload');
}

// makes the photo picker buttons work
function setupPhotoPicker() {
    // not on this page
    if (!document.getElementById('opt-upload')) return;

    document.getElementById('opt-upload').addEventListener('click', () => showPhotoOption('upload'));
    document.getElementById('opt-camera').addEventListener('click', () => showPhotoOption('camera'));
    document.getElementById('camera-start').addEventListener('click', startCamera);
    document.getElementById('camera-capture').addEventListener('click', capturePhoto);
    document.getElementById('camera-flip').addEventListener('click', () => {
        cameraFacing = cameraFacing === 'environment' ? 'user' : 'environment';
        startCamera();
    });

    // a file picked from the device
    document.getElementById('image').addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (!file) return;
        setPhotoError('');
        setSelectedPhoto(file);
    });

    // 'Retake / Change' goes back to the two options
    document.getElementById('photo-retake').addEventListener('click', () => {
        document.getElementById('image').value = '';
        setSelectedPhoto(null);
        showPhotoOption('upload');
    });

    // turn the camera off when the farmer leaves the Add tab or closes the page
    document.querySelectorAll('.dash-tab[data-tab], [data-goto-tab]').forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.dataset.tab || btn.dataset.gotoTab;
            if (target !== 'add') stopCamera();
        });
    });
    window.addEventListener('beforeunload', stopCamera);
}

// ---------- Upload ----------
// makes the Add New Product form send the new product to the backend
function setupUploadForm(token) {
    // the form
    const form = document.getElementById('upload-form');
    // not on this page
    if (!form) return;
    // the line for error messages
    const err = document.getElementById('upload-error');
    // the submit button
    const submit = form.querySelector('button[type="submit"]');

    // runs when 'Upload to Marketplace' is pressed
    form.addEventListener('submit', async (e) => {
        // stop the normal submit; I send it with fetch
        e.preventDefault();
        // clear the old message
        err.className = 'feedback';
        err.textContent = '';

        // the chosen photo (uploaded from the device or captured with the camera)
        const file = selectedPhoto;
        // no photo chosen
        if (!file) { showToast('Upload a photo or take one with the camera.'); return; }
        // photo too big
        if (file.size > MAX_PRODUCT_IMAGE) { showToast('That photo is over 5 MB. Choose a smaller one.'); return; }

        // a form made of text fields plus the photo file
        const fd = new FormData();
        // product name
        fd.append('item_name', document.getElementById('item_name').value.trim());
        // price per unit (typed as text, the backend turns it into an exact number)
        fd.append('unit_price', document.getElementById('unit_price').value.trim());
        // kg, bag, bunch...
        fd.append('unit', document.getElementById('unit').value);
        // how many are available
        fd.append('stock', document.getElementById('stock').value.trim());
        // the photo itself
        fd.append('file', file);

        // block double clicks, which would list the product twice
        // button says 'Uploading...' and can't be clicked twice
        setBtn(submit, 'Uploading...');
        // NEW: Removed 'Uploading...' text change

        // send it
        try {
            // POST to the backend
            const res = await fetch(`${API_BASE}/api/upload`, {
                method: 'POST',
                headers: authHeaders(token),
                body: fd,
            });
            // saved
            if (res.ok) {
                // empty the form
                form.reset();
                // clear the chosen photo and put the picker back to the start
                resetPhotoPicker();
                // refresh the products table
                await loadMyProducts(token);
                // refresh the stats
                await loadOverview(token);
                // show the products tab so the new product is visible
                switchTab('products');
            // the backend refused it
            } else {
                // NEW: Show inline error
                const data = await res.json();
                err.textContent = errorMessage(data, 'Upload failed.');
                err.className = 'feedback error';
            }
        // couldn't reach the backend
        } catch (e2) {
            // NEW: Show inline error
            err.textContent = 'Cannot connect to backend.';
            err.className = 'feedback error';
        // runs whatever happened
        } finally {
            // unblock the button
            resetBtn(submit);
        }
    });
}

// ---------- Init ----------
// runs when the page opens: checks the login, then loads everything
async function initDashboard() {
    // saved login token
    const token = localStorage.getItem('shamba_token');
    // not logged in: go to the login page
    if (!token) { window.location.href = 'login.html'; return; }

    // my details, filled in below
    let me;
    // ask the backend who I am
    try {
        // GET /api/me
        const res = await fetch(`${API_BASE}/api/me`, { headers: authHeaders(token) });
        // login expired
        if (res.status === 401) { clearSession(); window.location.href = 'login.html'; return; }
        // any other error counts as a failure
        if (!res.ok) throw new Error();
        // read my details
        me = await res.json();
    // backend unreachable
    } catch {
        // NEW: Alert instead of toast
        showToast('Cannot connect to backend.');
        // can't continue
        return;
    }

    // customers don't belong here
    if (me.role !== 'farmer') {
        // NEW: Alert instead of toast
        showToast('Access denied. Farmers only.');
        // leave the message visible for a moment before moving on
        setTimeout(() => { window.location.href = 'products.html'; }, 1500);
        return;
    }

    // keep the saved role and name up to date
    localStorage.setItem('shamba_role', me.role);
    localStorage.setItem('shamba_username', me.username);
    // 'Welcome, <name>' in the top bar
    document.getElementById('dash-username').textContent = me.username;

    // the line showing where my payouts go
    const payout = document.getElementById('payout-info');
    // only if payout details exist
    if (payout && me.payment_number) {
        // readable names for the payout methods
        const labels = { mpesa: 'M-Pesa', 'airtel money': 'Airtel Money', till: 'Till' };
        // the readable name of mine
        const method = labels[me.payment_method] || 'M-Pesa';
        // mobile numbers shown as 07...; till numbers as they are
        const number = me.payment_method === 'till' ? me.payment_number : localPhone(me.payment_number);
        // 'Payouts go to: M-Pesa 0712345678 | Contact: 0712345678'
        payout.textContent = `Payouts go to: ${method} ${number} | Contact: ${localPhone(me.phone)}`;
    }

    // make the tabs work
    initTabs();
    // make the photo picker (upload / camera) work
    setupPhotoPicker();
    // make the upload form work
    setupUploadForm(token);
    // load the three tabs at the same time
    await Promise.all([loadOverview(token), loadMyProducts(token), loadMyOrders(token)]);
}

// start everything as soon as the page loads
initDashboard();