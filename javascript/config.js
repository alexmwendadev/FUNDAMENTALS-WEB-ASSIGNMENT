// Shared settings and helpers. Loaded FIRST on every page.
// When I deploy, API_BASE changes to the live API address (e.g. https://api.yourdomain.com).
// the one place that says where the backend lives; every other script uses this
const API_BASE = 'https://shamba-fresh-api.onrender.com';

// Images are either "/uploads/..." (served by the API) or a full https:// link (Cloudinary).
// returns the full address of an image so the browser can load it
function assetUrl(path) {
  // no image stored: nothing to show
  if (!path) return '';
  // a full link (Cloudinary) is used as it is; a path like /uploads/x.png gets the API address put in front
  return /^https?:\/\//i.test(path) ? path : API_BASE + path;
}

// formats a number as money, e.g. 1200.5 becomes KES 1,200.50 (whole numbers show no decimals)
function formatKES(amount) {
  // make sure it's a real number
  const value = Number(amount);
  // missing or not a number: show a dash
  if (amount === null || amount === undefined || !isFinite(value)) return '—';
  // thousands separators; two decimals only when there are cents
  return 'KES ' + value.toLocaleString('en-KE', {
    minimumFractionDigits: value % 1 ? 2 : 0,
    maximumFractionDigits: 2,
  });
}

// Turns the API's error reply into one readable sentence.
// picks the message to show from an API error reply
function errorMessage(data, fallback) {
  // normal errors carry a plain sentence
  if (data && typeof data.detail === 'string') return data.detail;
  // validation errors arrive as a list: use the first one
  if (data && Array.isArray(data.detail) && data.detail.length) {
    // the first problem in the list
    const first = data.detail[0];
    // which field it was about (the last part of its path)
    const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : '';
    // 'field: message', or just the message
    return field ? `${field}: ${first.msg}` : first.msg;
  }
  // nothing usable in the reply: use the default text
  return fallback;
}

// forgets everything stored about the logged in user
function clearSession() {
  // token, role, username and picture are all removed
  ['shamba_token', 'shamba_role', 'shamba_username', 'shamba_avatar']
    .forEach(key => localStorage.removeItem(key));
}

// 254712345678 -> 0712345678 (how people expect to read their own number)
// the number as people write it
function localPhone(stored) {
  // turn 2547... back into 07..., leave anything else alone
  return stored && stored.startsWith('254') ? '0' + stored.slice(3) : (stored || '');
}

// the words shown to people for each order status (the status names themselves come from the backend)
const ORDER_STATUS_LABELS = {
  pending: 'Awaiting payment',
  paid: 'Paid',
  delivered: 'Delivered',
  refunded: 'Refunded',
};

// builds the coloured status badge used in the order tables
function statusPill(status) {
  // true when I have a label for this status
  const known = Object.prototype.hasOwnProperty.call(ORDER_STATUS_LABELS, status);
  // a small <span> that CSS turns into a badge
  const span = document.createElement('span');
  // the class decides the colour, e.g. status-paid is green
  span.className = 'status-pill status-' + (known ? status : 'pending');
  // unknown statuses fall back to the pending colour but keep their own text
  span.textContent = known ? ORDER_STATUS_LABELS[status] : String(status);
  // hand the badge back to be placed in a table cell
  return span;
}
