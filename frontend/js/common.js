// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const TX_TYPE_PURCHASE = "purchase";
const TX_TYPE_TRANSFER = "transfer";
const TX_TYPE_OUTGOING_TRANSFER = "outgoing_transfer";

const QUARTER_MONTHS = {
    1: [0, 1, 2],
    2: [3, 4, 5],
    3: [6, 7, 8],
    4: [9, 10, 11],
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const CHART_COLORS = [
    "#4ade80", "#60a5fa", "#f472b6", "#facc15", "#a78bfa",
    "#fb923c", "#34d399", "#f87171", "#38bdf8", "#c084fc",
];

const EXPENSE_COLORS = [
    "#f87171", "#fb923c", "#f472b6", "#ef4444", "#fca5a5",
    "#e11d48", "#fb7185", "#dc2626", "#f43f5e", "#b91c1c",
];

const API_TOKEN_STORAGE_KEY = "financeTrackerApiToken";
const API_USER_STORAGE_KEY = "financeTrackerUsername";

const BANKS_LIST = ["SANTANDER", "SANTANDER LIKEU", "SANTANDER GOLD", "MERCADO PAGO", "BBVA", "BBVA AZUL"]

// ---------------------------------------------------------------------------
// Utility functions
// ---------------------------------------------------------------------------
function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

// ---------------------------------------------------------------------------
// API auth helper
// ---------------------------------------------------------------------------
// The hosted server requires a shared-secret bearer token on every /api/*
// request. The token is obtained via the /login page (POST /api/login),
// kept in localStorage, and attached to every API call via apiFetch(); on a
// 401 it's cleared and the user is sent back to /login.

function getApiToken() {
    return localStorage.getItem(API_TOKEN_STORAGE_KEY) || "";
}

function getLoggedUser() {
    return localStorage.getItem(API_USER_STORAGE_KEY) || "";
}

// Every page must be logged in before it renders/loads data. Call this as
// the very first step of a page's bootstrap, before any data fetch, and
// skip the rest of the bootstrap if it returns false.
function requireAuth() {
    if (!getApiToken()) {
        const next = encodeURIComponent(window.location.pathname);
        window.location.href = `/login?next=${next}`;
        return false;
    }
    return true;
}

function logout() {
    localStorage.removeItem(API_TOKEN_STORAGE_KEY);
    localStorage.removeItem(API_USER_STORAGE_KEY);
    window.location.href = "/login";
}

// The "Log out" control lives in the shared header markup on every page;
// wire it here once instead of duplicating the listener per page script.
document.addEventListener("click", (e) => {
    if (e.target.closest(".btn-logout")) logout();
});

document.addEventListener("DOMContentLoaded", () => {
    const usernameEl = document.getElementById("logged-user");
    if (usernameEl) usernameEl.textContent = getLoggedUser();
});

async function apiFetch(url, options = {}) {
    const headers = { ...(options.headers || {}), Authorization: `Bearer ${getApiToken()}` };
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
        localStorage.removeItem(API_TOKEN_STORAGE_KEY);
        localStorage.removeItem(API_USER_STORAGE_KEY);
        window.location.href = "/login";
    }
    return res;
}

async function fetchJSON(url) {
    const res = await apiFetch(url);
    if (!res.ok) {
        throw new Error(`Request failed: ${res.status} ${res.statusText}`);
    }
    return res.json();
}

// ---------------------------------------------------------------------------
// Date & formatting helpers
// ---------------------------------------------------------------------------
function getCurrentQuarter() {
    return Math.floor(new Date().getMonth() / 3) + 1;
}

function formatAmount(amount) {
    return `$${amount.toLocaleString("en", { minimumFractionDigits: 2 })}`;
}

function getCurrentMonthStr() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function shiftMonth(monthStr, delta) {
    const [year, month] = monthStr.split("-").map(Number);
    const d = new Date(year, month - 1 + delta, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function getMonthDateRange(monthStr) {
    const [year, month] = monthStr.split("-").map(Number);
    const lastDay = new Date(year, month, 0).getDate();
    return {
        start: `${year}-${String(month).padStart(2, "0")}-01`,
        end: `${year}-${String(month).padStart(2, "0")}-${lastDay}`,
    };
}

// ---------------------------------------------------------------------------
// UI helpers
// ---------------------------------------------------------------------------
function showToast(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add("toast-visible"));

    setTimeout(() => {
        toast.classList.remove("toast-visible");
        toast.addEventListener("transitionend", () => toast.remove());
    }, 3000);
}

function setButtonLoading(btn, loading) {
    if (loading) {
        btn.disabled = true;
        btn.dataset.originalText = btn.textContent;
        btn.textContent = "...";
    } else {
        btn.disabled = false;
        btn.textContent = btn.dataset.originalText || btn.textContent;
        delete btn.dataset.originalText;
    }
}

// ---------------------------------------------------------------------------
// New transaction modal (shared across every page — a persistent "+ New"
// nav button and a Ctrl/Cmd+K shortcut both open this). The markup is
// injected once here rather than duplicated in each HTML file; the
// transactions page's per-table "+ New" buttons (`.btn-new-tx[data-type]`)
// reuse the same modal and skip straight to the form.
// ---------------------------------------------------------------------------
const NEW_TX_MODAL_HTML = `
    <div class="modal-overlay" id="new-tx-modal" hidden>
        <div class="modal">
            <div class="modal-header">
                <h3 id="modal-title">New Transaction</h3>
                <button class="modal-close" id="modal-close">&times;</button>
            </div>
            <div class="tx-type-picker" id="tx-type-picker">
                <button type="button" class="tx-type-btn income" id="tx-type-income">Income</button>
                <button type="button" class="tx-type-btn expense" id="tx-type-expense">Expense</button>
            </div>
            <form id="new-tx-form" hidden>
                <input type="hidden" id="tx-form-type">
                <div class="form-row">
                    <label for="tx-form-amount">Amount</label>
                    <input type="number" id="tx-form-amount" step="0.01" min="0" required>
                </div>
                <div class="form-row">
                    <label for="tx-form-date">Date</label>
                    <input type="datetime-local" id="tx-form-date" required>
                </div>
                <div class="form-row">
                    <label for="tx-form-description" id="tx-form-description-label">Description</label>
                    <input type="text" id="tx-form-description" required>
                </div>
                <div class="form-row">
                    <label for="tx-form-category">Category</label>
                    <input type="text" id="tx-form-category" list="category-list">
                </div>
                <div class="form-row">
                    <label for="tx-form-bank">Bank</label>
                    <input type="text" id="tx-form-bank" list="bank-list" required>
                </div>
                <div class="form-actions">
                    <button type="button" class="btn-modal-cancel" id="modal-cancel">Cancel</button>
                    <button type="submit" class="btn-modal-submit">Save</button>
                </div>
            </form>
        </div>
    </div>
`;

// Categories are fetched once per page load purely to populate the datalist
// and to validate what the user types — this form does not create new
// categories (that stays a /categorize-only action), so there's no need to
// keep a mutable global cache of them.
async function loadCategories() {
    return fetchJSON("/api/categories");
}

function buildCategoryDatalist(cats) {
    if (document.getElementById("category-list")) return;
    const dl = document.createElement("datalist");
    dl.id = "category-list";
    cats.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c;
        dl.appendChild(opt);
    });
    document.body.appendChild(dl);
}

function buildBankDatalist() {
    if (document.getElementById("bank-list")) return;

    const dl = document.createElement("datalist");
    dl.id = "bank-list";

    BANKS_LIST.forEach((b) => {
        const opt = document.createElement("option");
        opt.value = b;
        dl.appendChild(opt);
    });
    document.body.appendChild(dl);
}

// Manual transactions have no bank-issued reference, but `reference`
// participates in the dedup unique index, so give each one a unique value.
function generateReference() {
    return `MAN-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
}

function openTxTypePicker() {
    const modal = document.getElementById("new-tx-modal");
    if (!modal) return;
    document.getElementById("new-tx-form").reset();
    document.getElementById("modal-title").textContent = "New Transaction";
    document.getElementById("tx-type-picker").hidden = false;
    document.getElementById("new-tx-form").hidden = true;
    modal.hidden = false;
}

function openNewTxModal(txType) {
    const modal = document.getElementById("new-tx-modal");
    const form = document.getElementById("new-tx-form");
    const picker = document.getElementById("tx-type-picker");
    const title = document.getElementById("modal-title");
    const descLabel = document.getElementById("tx-form-description-label");
    const typeInput = document.getElementById("tx-form-type");

    form.reset();

    if (txType === "income") {
        title.textContent = "New Income";
        descLabel.textContent = "Source";
        typeInput.value = TX_TYPE_TRANSFER;
    } else {
        title.textContent = "New Expense";
        descLabel.textContent = "Merchant";
        typeInput.value = TX_TYPE_PURCHASE;
    }

    const now = new Date();
    const localISO = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}T${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    document.getElementById("tx-form-date").value = localISO;

    picker.hidden = true;
    form.hidden = false;
    modal.hidden = false;
    document.getElementById("tx-form-amount").focus();
}

function closeNewTxModal() {
    document.getElementById("new-tx-modal").hidden = true;
}

async function submitNewTx(e) {
    e.preventDefault();

    const type = document.getElementById("tx-form-type").value;
    const amount = parseFloat(document.getElementById("tx-form-amount").value);
    const date = document.getElementById("tx-form-date").value;
    const description = document.getElementById("tx-form-description").value.trim();
    const category = document.getElementById("tx-form-category").value.trim();
    const bank = document.getElementById("tx-form-bank").value.trim();

    if (isNaN(amount) || amount < 0) return;

    // This form only accepts existing categories — new ones are created via
    // /categorize. Reject anything that doesn't match (case-insensitive).
    let categoryValue = null;
    if (category) {
        const upper = category.toUpperCase();
        const known = (window.__newTxCategories || []).some((c) => c.toUpperCase() === upper);
        if (!known) {
            showToast("Unknown category", "error");
            return;
        }
        categoryValue = upper;
    }

    const payload = {
        type,
        amount,
        date,
        person: getLoggedUser(),
        reference: generateReference(),
        bank,
    };

    if (type === TX_TYPE_TRANSFER) {
        payload.sender_bank = description || null;
        payload.concept = TX_TYPE_TRANSFER;
    } else {
        payload.merchant = description || null;
        payload.concept = description || null;
    }

    if (categoryValue) payload.category = categoryValue;

    const submitBtn = document.querySelector(".btn-modal-submit");
    setButtonLoading(submitBtn, true);

    try {
        const res = await apiFetch("/api/transactions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (res.ok) {
            closeNewTxModal();
            showToast("Transaction created", "success");
            // Pages that display transactions (e.g. /transactions) define this
            // hook to refresh themselves; other pages simply do nothing.
            window.onTransactionCreated?.();
        } else if (res.status === 409) {
            showToast("Duplicate transaction", "error");
        } else {
            showToast("Failed to create transaction", "error");
        }
    } catch (err) {
        showToast("Failed to create transaction", "error");
    } finally {
        setButtonLoading(submitBtn, false);
    }
}

// Injects the nav button + modal markup once the header exists, then wires
// its listeners. Guarded on `header nav` so it's a no-op on pages without
// the shared header (e.g. login).
function initNewTxUI() {
    const nav = document.querySelector("header nav");
    if (!nav) return;

    const navBtn = document.createElement("button");
    navBtn.type = "button";
    navBtn.className = "btn-nav-new";
    navBtn.textContent = "+ New";
    const logoutBtn = nav.querySelector(".btn-logout");
    if (logoutBtn) nav.insertBefore(navBtn, logoutBtn);
    else nav.appendChild(navBtn);

    if (!document.getElementById("new-tx-modal")) {
        document.body.insertAdjacentHTML("beforeend", NEW_TX_MODAL_HTML);
    }

    // Wiring must happen after injection — these elements don't exist before this point.
    document.getElementById("modal-close").addEventListener("click", closeNewTxModal);
    document.getElementById("modal-cancel").addEventListener("click", closeNewTxModal);
    document.getElementById("new-tx-modal").addEventListener("click", (e) => {
        if (e.target === e.currentTarget) closeNewTxModal();
    });
    document.getElementById("new-tx-form").addEventListener("submit", submitNewTx);
    document.getElementById("tx-type-income").addEventListener("click", () => openNewTxModal("income"));
    document.getElementById("tx-type-expense").addEventListener("click", () => openNewTxModal("expense"));

    loadCategories().then((cats) => {
        window.__newTxCategories = cats;
        buildCategoryDatalist(cats);
        buildBankDatalist();
    });
}

// Delegated so it covers both the injected nav button and any pre-existing
// per-table buttons (e.g. transactions.html's `.btn-new-tx[data-type]`,
// which open the form directly at that type, skipping the picker).
document.addEventListener("click", (e) => {
    if (e.target.closest(".btn-nav-new")) {
        openTxTypePicker();
        return;
    }
    const btn = e.target.closest(".btn-new-tx");
    if (btn) openNewTxModal(btn.dataset.type);
});

// Ctrl/Cmd+K opens the picker from anywhere, except while typing in a field
// or when the modal is already open.
document.addEventListener("keydown", (e) => {
    if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "k") return;
    if (!document.querySelector("header nav")) return;

    const modal = document.getElementById("new-tx-modal");
    if (modal && !modal.hidden) return;

    const target = e.target;
    const isTyping = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" ||
        target.tagName === "SELECT" || target.isContentEditable);
    if (isTyping) return;

    e.preventDefault();
    openTxTypePicker();
});

document.addEventListener("DOMContentLoaded", initNewTxUI);
