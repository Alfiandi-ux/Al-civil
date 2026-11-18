/**
 * AL-CIVIL WMS - Core Application Scripts
 */

// Ambil token CSRF dari meta tag
function getCsrfToken() {
  const meta = document.querySelector('meta[name="csrf-token"]');
  return meta ? meta.getAttribute('content') : '';
}

// Otomatis sisipkan header X-CSRF-Token pada panggilan fetch (POST, PUT, DELETE, PATCH)
if (window.fetch) {
  const _originalFetch = window.fetch;
  window.fetch = function(resource, init) {
    init = init || {};
    const method = (init.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
      const token = getCsrfToken();
      if (token) {
        if (!init.headers) {
          init.headers = {};
        }
        if (init.headers instanceof Headers) {
          if (!init.headers.has('X-CSRF-Token')) {
            init.headers.set('X-CSRF-Token', token);
          }
        } else if (Array.isArray(init.headers)) {
          if (!init.headers.some(([k]) => k.toLowerCase() === 'x-csrf-token')) {
            init.headers.push(['X-CSRF-Token', token]);
          }
        } else if (typeof init.headers === 'object') {
          if (!init.headers['X-CSRF-Token']) {
            init.headers['X-CSRF-Token'] = token;
          }
        }
      }
    }
    return _originalFetch.call(this, resource, init);
  };
}

// Otomatis pastikan semua form submit ber-method POST membawa hidden input csrf_token
document.addEventListener('submit', function(e) {
  const form = e.target;
  if (!form || form.tagName !== 'FORM') return;
  const method = (form.getAttribute('method') || 'GET').toUpperCase();
  if (method === 'POST') {
    const token = getCsrfToken();
    if (!token) return;
    let csrfInput = form.querySelector('input[name="csrf_token"]');
    if (!csrfInput) {
      csrfInput = document.createElement('input');
      csrfInput.type = 'hidden';
      csrfInput.name = 'csrf_token';
      csrfInput.value = token;
      form.appendChild(csrfInput);
    } else if (!csrfInput.value) {
      csrfInput.value = token;
    }
  }
}, true);

// Escape teks sebelum dimasukkan ke innerHTML, supaya nama material yang
// mengandung karakter < > " ' & tidak merusak tampilan (dan aman dari XSS).
function escapeHtml(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, (ch) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  }[ch]));
}

// Toast notification helper
function showToast(message, type = 'success') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✅' : '⚠️'}</span>
    <span>${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// Modal open/close helpers
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.style.display = 'flex';
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.style.display = 'none';
  }
}

// Close modals when clicking outside
window.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.style.display = 'none';
  }
});

// Format currency IDR
function formatRupiah(num) {
  return 'Rp ' + Number(num || 0).toLocaleString('id-ID');
}
