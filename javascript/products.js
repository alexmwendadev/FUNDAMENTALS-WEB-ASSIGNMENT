// PRODUCTS LOGIC
// page elements: the grid that holds the product cards, and the search / category / sort controls
const productGrid = document.getElementById('product-grid');
const searchInput = document.getElementById('search-input');
const categoryFilter = document.getElementById('category-filter');
const sortFilter = document.getElementById('sort-filter');

// every product from the API, kept here so filtering doesn't need another request
let allProducts = []; 

// fetches the product list once, then shows it
async function loadProducts() {
    // this script is also loaded on pages that have no grid
    if (!productGrid) return;
    try {
        // a public route, no login needed
        const response = await fetch(`${API_BASE}/api/products`);
        if (!response.ok) throw new Error("Failed to fetch products");
        allProducts = await response.json();
        // draw the cards
        applyFilters(); 
    } catch (error) {
        productGrid.innerHTML = '<p>Error loading products. Is the backend running?</p>';
        console.error(error);
    }
}

// filters by search and category, sorts, then redraws
function applyFilters() {
    // read the current controls (with defaults if a control isn't on the page)
    const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    const category = categoryFilter ? categoryFilter.value : 'all';
    const sort = sortFilter ? sortFilter.value : 'newest';

    // keep a product if it matches the search (product name or farmer name) AND the chosen category
    let filtered = allProducts.filter(p => {
        const matchesSearch = p.item_name.toLowerCase().includes(searchTerm) || (p.farmer_username && p.farmer_username.toLowerCase().includes(searchTerm));
        const matchesCategory = category === 'all' || p.category === category;
        return matchesSearch && matchesCategory;
    });

    // sorting: cheapest first / most expensive first / newest first (a higher id means newer)
    if (sort === 'price-low') filtered.sort((a, b) => a.unit_price - b.unit_price);
    if (sort === 'price-high') filtered.sort((a, b) => b.unit_price - a.unit_price);
    if (sort === 'newest') filtered.sort((a, b) => b.id - a.id);

    // show the result
    renderProducts(filtered);
}

// re-filter as the person types or changes a dropdown
if (searchInput) searchInput.addEventListener('input', applyFilters);
if (categoryFilter) categoryFilter.addEventListener('change', applyFilters);
if (sortFilter) sortFilter.addEventListener('change', applyFilters);

// builds one card per product and puts it in the grid
function renderProducts(products) {
    // clear the old cards first
    productGrid.innerHTML = '';
    // nothing matched
    if (products.length === 0) {
        productGrid.innerHTML = '<p>No products found.</p>';
        return;
    }

    products.forEach(product => {
        // true while there is stock left
        const inStock = product.stock > 0;

        // the card is built with createElement (not innerHTML) so product names can't inject HTML
        const card = document.createElement('article');
        card.className = 'product-card';

        const imgDiv = document.createElement('div');
        imgDiv.className = 'product-img';
        // the photo as a CSS background; assetUrl() adds the API address when needed
        imgDiv.style.backgroundImage = `url("${assetUrl(product.image_url)}")`;

        // Low stock badge is intentionally NOT here (it's only on the farmer dashboard)

        // the 'N kg available' or 'Out of stock' label on the photo
        const badge = document.createElement('span');
        badge.className = 'availability-badge' + (inStock ? '' : ' out');
        badge.textContent = inStock ? `${product.stock} ${product.unit} available` : 'Out of stock';
        imgDiv.appendChild(badge);

        const infoDiv = document.createElement('div');
        infoDiv.className = 'product-info';

        // the text parts of the card: product name, farmer, price
        const title = document.createElement('h3');
        title.textContent = product.item_name;

        const farmer = document.createElement('p');
        farmer.className = 'farmer';
        farmer.textContent = `By ${product.farmer_username || 'Unknown'}`;

        const price = document.createElement('p');
        price.className = 'price';
        price.textContent = `${formatKES(product.unit_price)} / ${product.unit}`;

        // the order button (disabled when sold out)
        const btn = document.createElement('button');
        btn.className = 'btn main order-btn';
        btn.textContent = inStock ? 'Order Now' : 'Out of stock';
        btn.disabled = !inStock;

        // not logged in: go to login. A farmer: can't buy. Otherwise open the order page for this product
        btn.addEventListener('click', () => {
            const token = localStorage.getItem('shamba_token');
            if (!token) {
                window.location.href = 'login.html';
            } else if (localStorage.getItem('shamba_role') === 'farmer') {
                showToast("Farmers can't place orders. Log in with a customer account to buy.");
            } else {
                window.location.href = `order.html?product=${encodeURIComponent(product.id)}`;
            }
        });

        // put the parts together and add the card to the page
        infoDiv.append(title, farmer, price, btn);
        card.append(imgDiv, infoDiv);
        productGrid.appendChild(card);
    });
}

// start: load the products as soon as the script runs
loadProducts();