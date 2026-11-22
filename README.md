# Shamba Fresh: payments, profile and security update

Copy `backend/*` over your backend folder and `frontend/*` over your frontend folder
(keep your own `assets/images/`). Rename `.gitignore` if your editor hid the dot.
Your existing `shamba.db` is upgraded automatically on first start. Nothing is lost.

## 1. Backend setup
```
pip install -r requirements.txt
copy .env.example .env        (Windows)   |   cp .env.example .env   (Mac/Linux)
python -c "import secrets; print(secrets.token_urlsafe(48))"      <- paste into SECRET_KEY
uvicorn main:app --port 8001 --reload
```
Frontend: `python -m http.server 8000` inside the frontend folder, then open http://localhost:8000

## 2. Connect Pesapal (use SANDBOX first)
Your old `.env` had `PESAPAL_ENVIRONMENT=live`. Every test would have charged real money.
1. Put your **sandbox** consumer key and secret in `.env` and set `PESAPAL_ENVIRONMENT=sandbox`.
2. Start your Cloudflare tunnel to port 8001 and set `PESAPAL_PUBLIC_BASE_URL` to its https address.
3. Run `python register_ipn.py`, copy the `PESAPAL_IPN_ID=...` line into `.env`, restart uvicorn.
   Quick tunnels get a new address every time they restart, so repeat step 3 when that happens.
4. Buy something as a customer. Pesapal's sandbox page gives you test payment details.

## 3. Going live checklist
- `PESAPAL_ENVIRONMENT=live`, live keys, a NEW `register_ipn.py` run against your real domain (live and sandbox IPN ids differ).
- `FRONTEND_URL` = your website address, `CORS_ORIGINS` includes it, `config.js` `API_BASE` = your live API address.
- Set `SECRET_KEY` as a hosting environment variable. Never commit `.env`.
- Use PostgreSQL (`DATABASE_URL`) and Cloudinary (`CLOUDINARY_URL`) on hosts that wipe their disk.
- Point an uptime monitor at `/health`.

## 4. How a payment works now
1. Customer picks a quantity. The **server** works out the total from the stored price. The browser never sends an amount.
2. The customer is sent to Pesapal's page to pay (M-Pesa, card...).
3. Pesapal calls `/api/pesapal/ipn` AND sends the customer to `payment-return.html`. Neither is believed:
   the server asks Pesapal directly, then checks the reference, currency and that the amount is at least the order total.
4. Only then the order becomes **paid** and stock goes down. A missed notification is repaired by the return page,
   the **Check payment** button, and an automatic re-check when the customer opens their dashboard.
5. Farmers see an order only once it is paid, and can only mark it **delivered**.

## 5. Things to know
- **Payouts to farmers are manual.** Pesapal pays into YOUR merchant account. The farmer dashboard shows what each
  farmer has earned and where to pay them. Ask Pesapal whether they support split settlement if you want to automate it.
- Prices and stock are now real numbers (`unit_price`, `unit`, `stock`). Old text prices were converted
  (`90(per kg)` became KES 90 per kg). Check any product the migration could not read (it shows price 0 and can't be bought).
- Farmers cannot place orders; farmers and customers each use their own dashboard.
- Not included: login rate limiting, password reset, email notifications, refunds from inside the site.

## 6. Tests
`python tests/test_services.py` runs the payment and validation rules (17 tests, no extra packages).

## 7. Reading the code
Every backend file, every script and every page has comments above (or beside) the lines they describe,
written as short notes: what a block does, and why when it isn't obvious.
Good places to start: `backend/main.py` (every route, in order), `backend/services.py` (the payment and
validation rules) and `frontend/javascript/order.js` (the checkout flow).
The original stylesheet keeps its own section headings; only the payment/checkout rules I added at the
bottom of `style.css` have per-rule comments.
