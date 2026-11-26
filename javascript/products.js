// PRODUCTS LOGIC
const productGrid = document.getElementById('product-grid');
const searchInput = document.getElementById('search-input');
const categoryFilter = document.getElementById('category-filter');
const sortFilter = document.getElementById('sort-filter');

let allProducts = []; 

async function loadProducts() {
    if (!productGrid) return;
    try {
        const response = await fetch(`${API_BASE}/api/products`);
        if (!response.ok) throw new Error("Failed to fetch products");
        allProducts = await response.json();
        applyFilters(); 
    } catch (error) {
        productGrid.innerHTML = '<p>Error loading products. Is the backend running?</p>';
        console.error(error);
    }
}

function applyFilters() {
    const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    const category = categoryFilter ? categoryFilter.value : 'all';
    const sort = sortFilter ? sortFilter.value : 'newest';

    let filtered = allProducts.filter(p => {
        const matchesSearch = p.item_name.toLowerCase().includes(searchTerm) || (p.farmer_username && p.farmer_username.toLowerCase().includes(searchTerm));
        const matchesCategory = category === 'all' || p.category === category;
        return matchesSearch && matchesCategory;
    });

    if (sort === 'price-low') filtered.sort((a, b) => a.unit_price - b.unit_price);
    if (sort === 'price-high') filtered.sort((a, b) => b.unit_price - a.unit_price);
    if (sort === 'newest') filtered.sort((a, b) => b.id - a.id);

    renderProducts(filtered);
}

if (searchInput) searchInput.addEventListener('input', applyFilters);
if (categoryFilter) categoryFilter.addEventListener('change', applyFilters);
if (sortFilter) sortFilter.addEventListener('change', applyFilters);

function renderProducts(products) {
    productGrid.innerHTML = '';
    if (products.length === 0) {
        productGrid.innerHTML = '<p>No products found.</p>';
        return;
    }

    products.forEach(product => {
        const inStock = product.stock > 0;

        const card = document.createElement('article');
        card.className = 'product-card';

        const imgDiv = document.createElement('div');
        imgDiv.className = 'product-img';
        imgDiv.style.backgroundImage = `url("${assetUrl(product.image_url)}")`;

        // Low stock badge is intentionally NOT here (it's only on the farmer dashboard)

        const badge = document.createElement('span');
        badge.className = 'availability-badge' + (inStock ? '' : ' out');
        badge.textContent = inStock ? `${product.stock} ${product.unit} available` : 'Out of stock';
        imgDiv.appendChild(badge);

        const infoDiv = document.createElement('div');
        infoDiv.className = 'product-info';

        const title = document.createElement('h3');
        title.textContent = product.item_name;

        const farmer = document.createElement('p');
        farmer.className = 'farmer';
        farmer.textContent = `By ${product.farmer_username || 'Unknown'}`;

        const price = document.createElement('p');
        price.className = 'price';
        price.textContent = `${formatKES(product.unit_price)} / ${product.unit}`;

        const btn = document.createElement('button');
        btn.className = 'btn main order-btn';
        btn.textContent = inStock ? 'Order Now' : 'Out of stock';
        btn.disabled = !inStock;

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

        infoDiv.append(title, farmer, price, btn);
        card.append(imgDiv, infoDiv);
        productGrid.appendChild(card);
    });
}

loadProducts();