// PRODUCTS LOGIC
// the empty box on products.html that the cards are put into
const productGrid = document.getElementById('product-grid');

// fetches the products and builds one card for each
async function loadProducts() {
    // this page has no grid
    if (!productGrid) return;

    // the backend may be down
    try {
        // ask the backend for the product list (public, no login needed)
        const response = await fetch(`${API_BASE}/api/products`);
        // any error status counts as a failure
        if (!response.ok) throw new Error("Failed to fetch products");

        // the list of products
        const products = await response.json();
        // remove the 'Loading...' text
        productGrid.innerHTML = '';

        // nothing listed yet
        if (products.length === 0) {
            productGrid.innerHTML = '<p>No products available yet. Check back later!</p>';
            // nothing more to draw
            return;
        }

        // one card per product
        products.forEach(product => {
            // true when at least one unit is left
            const inStock = product.stock > 0;

            // the card
            const card = document.createElement('article');
            // CSS class for the card style
            card.className = 'product-card';

            // the photo area
            const imgDiv = document.createElement('div');
            // CSS class for the photo area
            imgDiv.className = 'product-img';
            // the photo is a CSS background image
            imgDiv.style.backgroundImage = `url("${assetUrl(product.image_url)}")`;

            // the small label over the photo
            const badge = document.createElement('span');
            // an extra 'out' class makes it grey when sold out
            badge.className = 'availability-badge' + (inStock ? '' : ' out');
            // '59 kg available' or 'Out of stock'
            badge.textContent = inStock ? `${product.stock} ${product.unit} available` : 'Out of stock';
            // put the label on the photo
            imgDiv.appendChild(badge);

            // the text area under the photo
            const infoDiv = document.createElement('div');
            // CSS class
            infoDiv.className = 'product-info';

            // product name
            const title = document.createElement('h3');
            // textContent (not innerHTML) so a product name can never run as code
            title.textContent = product.item_name;

            // who sells it
            const farmer = document.createElement('p');
            // CSS class
            farmer.className = 'farmer';
            // 'By <farmer name>'
            farmer.textContent = `By ${product.farmer_username || 'Unknown'}`;

            // price line
            const price = document.createElement('p');
            // CSS class
            price.className = 'price';
            // 'KES 90 / kg'
            price.textContent = `${formatKES(product.unit_price)} / ${product.unit}`;

            // the order button
            const btn = document.createElement('button');
            // CSS classes
            btn.className = 'btn main order-btn';
            // 'Order Now', or 'Out of stock' when sold out
            btn.textContent = inStock ? 'Order Now' : 'Out of stock';
            // can't be clicked when sold out
            btn.disabled = !inStock;

            // what happens when 'Order Now' is pressed
            btn.addEventListener('click', () => {
                // saved login token, if any
                const token = localStorage.getItem('shamba_token');
                // not logged in
                if (!token) {
                    // NEW: Redirect to login silently (the login page will send them back after)
                    window.location.href = 'login.html';
                // farmers can't buy, so say so (the backend refuses too)
                } else if (localStorage.getItem('shamba_role') === 'farmer') {
                    // NEW: Just redirect them away quietly, no popup needed.
                    window.location.href = 'dashboard.html';
                // a logged in customer
                } else {
                    // open the checkout page for this product; only the product id is passed, the price is read fresh there
                    window.location.href = `order.html?product=${encodeURIComponent(product.id)}`;
                }
            });

            // put the name, farmer, price and button in the text area
            infoDiv.append(title, farmer, price, btn);
            // put photo and text in the card
            card.append(imgDiv, infoDiv);
            // add the card to the page
            productGrid.appendChild(card);
        });

    // couldn't load the products
    } catch (error) {
        // show a message instead
        productGrid.innerHTML = '<p>Error loading products. Is the backend running?</p>';
        // details for the browser console
        console.error(error);
    }
}

// run it as soon as the page loads
loadProducts();