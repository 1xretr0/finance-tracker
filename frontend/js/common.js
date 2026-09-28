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

// Renders negatives as "-$1,234.00" (not "$-1,234.00") and always caps at 2
// decimal places (6.5).
function formatAmount(amount) {
    const sign = amount < 0 ? "-" : "";
    const abs = Math.abs(amount);
    return `${sign}$${abs.toLocaleString("en", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
// New/edit transaction modal (shared across every page — a persistent
// "+ New" nav button and a Ctrl/Cmd+K shortcut both open this in create
// mode; the transactions page opens it in edit mode by clicking a row). The
// markup is injected once here rather than duplicated in each HTML file;
// the transactions page's per-table "+ New" buttons (`.btn-new-tx[data-type]`)
// reuse the same modal and skip straight to the form.
// ---------------------------------------------------------------------------
const NEW_TX_MODAL_HTML = `
    <div class="modal-overlay" id="new-tx-modal" hidden>
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <div class="modal-header">
                <h3 id="modal-title">New Transaction</h3>
                <button class="modal-close" id="modal-close">&times;</button>
            </div>
            <div class="tx-type-picker" id="tx-type-picker">
                <button type="button" class="tx-type-btn income" id="tx-type-income">Income</button>
                <button type="button" class="tx-type-btn expense" id="tx-type-expense">Expense</button>
            </div>
            <form id="new-tx-form" hidden>
                <input type="hidden" id="tx-form-id">
                <input type="hidden" id="tx-form-type">
                <div class="form-row" id="tx-form-type-toggle-row" hidden>
                    <label>Type</label>
                    <div class="tx-type-toggle">
                        <button type="button" class="tx-type-toggle-btn income" data-type="income">Income</button>
                        <button type="button" class="tx-type-toggle-btn expense" data-type="expense">Expense</button>
                    </div>
                </div>
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
                <div class="form-row">
                    <label for="tx-form-notes">Notes</label>
                    <input type="text" id="tx-form-notes">
                </div>
                <div class="form-actions">
                    <button type="button" class="btn-modal-delete" id="modal-delete" hidden>Delete</button>
                    <button type="button" class="btn-modal-cancel" id="modal-cancel">Cancel</button>
                    <button type="submit" class="btn-modal-submit">Save</button>
                </div>
            </form>
        </div>
    </div>
`;

// Set while the modal is open in edit mode — the original transaction, used
// to diff which fields actually changed before sending PUT /api/transactions.
let editingTxOriginal = null;

// The element that had focus right before the modal opened (6.3) — focus
// returns here on close so keyboard/screen-reader users land back where
// they started instead of at the top of the page.
let modalOpener = null;

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

// Clears any leftover edit-mode state so create-mode entry points (the
// picker, or opening straight into a typed form) never inherit a stale
// editing target, delete button, or type toggle from a previous edit.
function resetModalToCreateMode() {
    editingTxOriginal = null;
    document.getElementById("tx-form-id").value = "";
    document.getElementById("tx-form-type-toggle-row").hidden = true;
    document.getElementById("modal-delete").hidden = true;
}

function openTxTypePicker() {
    const modal = document.getElementById("new-tx-modal");
    if (!modal) return;
    if (modal.hidden) modalOpener = document.activeElement;
    document.getElementById("new-tx-form").reset();
    resetModalToCreateMode();
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

    if (modal.hidden) modalOpener = document.activeElement;
    form.reset();
    resetModalToCreateMode();

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

// Toggles the income/expense buttons inside the edit form (not the
// create-mode picker) and relabels the description field to match.
function setTypeToggleActive(kind) {
    document.querySelectorAll(".tx-type-toggle-btn").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.type === kind);
    });
    document.getElementById("tx-form-description-label").textContent = kind === "income" ? "Source" : "Merchant";
}

// Opens the shared modal pre-filled with an existing transaction's fields
// (4.6). `tx` is the full row already held by the caller (e.g. the
// transactions page's cached income/expense arrays) — no fetch needed.
function openEditTxModal(tx) {
    const modal = document.getElementById("new-tx-modal");
    const form = document.getElementById("new-tx-form");
    const picker = document.getElementById("tx-type-picker");

    modalOpener = document.activeElement;
    form.reset();
    editingTxOriginal = tx;
    document.getElementById("tx-form-id").value = tx.id;
    document.getElementById("tx-form-type").value = tx.type;
    document.getElementById("tx-form-type-toggle-row").hidden = false;
    document.getElementById("modal-delete").hidden = false;
    document.getElementById("modal-title").textContent = "Edit Transaction";

    const kind = tx.type === TX_TYPE_TRANSFER ? "income" : "expense";
    setTypeToggleActive(kind);

    document.getElementById("tx-form-amount").value = tx.amount;
    document.getElementById("tx-form-date").value = (tx.date || "").slice(0, 16);
    document.getElementById("tx-form-description").value =
        kind === "income" ? (tx.sender_bank || tx.concept || "") : (tx.merchant || tx.dest_bank || "");
    document.getElementById("tx-form-category").value = tx.category || "";
    document.getElementById("tx-form-bank").value = tx.bank || "";
    document.getElementById("tx-form-notes").value = tx.notes || "";

    picker.hidden = true;
    form.hidden = false;
    modal.hidden = false;
    document.getElementById("tx-form-amount").focus();
}

function closeNewTxModal() {
    document.getElementById("new-tx-modal").hidden = true;
    resetModalToCreateMode();
    if (modalOpener && typeof modalOpener.focus === "function") modalOpener.focus();
    modalOpener = null;
}

function readCategoryValue() {
    const category = document.getElementById("tx-form-category").value.trim();
    if (!category) return { ok: true, value: null };

    // This form only accepts existing categories — new ones are created via
    // /categorize. Reject anything that doesn't match (case-insensitive).
    const upper = category.toUpperCase();
    const known = (window.__newTxCategories || []).some((c) => c.toUpperCase() === upper);
    if (!known) {
        showToast("Unknown category", "error");
        return { ok: false };
    }
    return { ok: true, value: upper };
}

async function submitCreateTx() {
    const type = document.getElementById("tx-form-type").value;
    const amount = parseFloat(document.getElementById("tx-form-amount").value);
    const date = document.getElementById("tx-form-date").value;
    const description = document.getElementById("tx-form-description").value.trim();
    const bank = document.getElementById("tx-form-bank").value.trim();
    const notes = document.getElementById("tx-form-notes").value.trim();

    if (isNaN(amount) || amount < 0) return;

    const category = readCategoryValue();
    if (!category.ok) return;

    const payload = {
        type,
        amount,
        date,
        person: getLoggedUser(),
        reference: generateReference(),
        bank,
        notes: notes || null,
    };

    if (type === TX_TYPE_TRANSFER) {
        payload.sender_bank = description || null;
        payload.concept = TX_TYPE_TRANSFER;
    } else {
        payload.merchant = description || null;
        payload.concept = description || null;
    }

    if (category.value) payload.category = category.value;

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
            window.onTransactionChanged?.();
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

// Sends only the fields that actually changed (4.6, 4.7). The description
// is written to sender_bank for income and merchant for expenses — the
// field the transactions page actually reads back on reload — which is
// what fixes the "income edit reverts on reload" bug (4.7).
async function submitEditTx(id) {
    const original = editingTxOriginal;
    if (!original) return;

    const originalKind = original.type === TX_TYPE_TRANSFER ? "income" : "expense";
    const activeToggle = document.querySelector(".tx-type-toggle-btn.active");
    const newKind = activeToggle ? activeToggle.dataset.type : originalKind;
    const kindChanged = newKind !== originalKind;

    const amount = parseFloat(document.getElementById("tx-form-amount").value);
    const date = document.getElementById("tx-form-date").value;
    const description = document.getElementById("tx-form-description").value.trim();
    const bank = document.getElementById("tx-form-bank").value.trim();
    const notes = document.getElementById("tx-form-notes").value.trim();

    if (isNaN(amount) || amount < 0) return;

    const category = readCategoryValue();
    if (!category.ok) return;

    const payload = {};

    if (Math.abs(amount - original.amount) > 0.0001) payload.amount = amount;
    if (date && date !== (original.date || "").slice(0, 16)) payload.date = date;
    if (bank && bank !== original.bank) payload.bank = bank;

    const notesValue = notes || null;
    if (notesValue !== (original.notes || null)) payload.notes = notesValue;

    const originalCategory = original.category || null;
    if (category.value !== originalCategory) payload.category = category.value;

    const descriptionField = newKind === "income" ? "sender_bank" : "merchant";
    if (kindChanged) {
        payload.type = newKind === "income" ? TX_TYPE_TRANSFER : TX_TYPE_PURCHASE;
        payload[descriptionField] = description || null;
    } else {
        const originalDescription = originalKind === "income"
            ? (original.sender_bank || original.concept || "")
            : (original.merchant || original.dest_bank || "");
        if (description !== originalDescription) payload[descriptionField] = description || null;
    }

    if (Object.keys(payload).length === 0) {
        closeNewTxModal();
        return;
    }

    const submitBtn = document.querySelector(".btn-modal-submit");
    setButtonLoading(submitBtn, true);

    try {
        const res = await apiFetch(`/api/transactions/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (res.ok) {
            closeNewTxModal();
            showToast("Transaction updated", "success");
            window.onTransactionChanged?.();
        } else if (res.status === 409) {
            showToast("Duplicate transaction", "error");
        } else {
            showToast("Failed to update transaction", "error");
        }
    } catch (err) {
        showToast("Failed to update transaction", "error");
    } finally {
        setButtonLoading(submitBtn, false);
    }
}

// Delete stays instant (no confirmation) — matches the rest of the app.
async function deleteEditingTx() {
    if (!editingTxOriginal) return;
    const id = editingTxOriginal.id;

    try {
        const res = await apiFetch(`/api/transactions/${id}`, { method: "DELETE" });
        if (res.ok) {
            closeNewTxModal();
            showToast("Transaction deleted", "success");
            window.onTransactionChanged?.();
        } else {
            showToast("Failed to delete transaction", "error");
        }
    } catch (err) {
        showToast("Failed to delete transaction", "error");
    }
}

async function submitNewTx(e) {
    e.preventDefault();
    const id = document.getElementById("tx-form-id").value;
    if (id) await submitEditTx(parseInt(id, 10));
    else await submitCreateTx();
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

    // Floating "+" button — only visible on narrow (<600px) screens, where
    // the nav's "+ New" button wraps out of easy reach (6.1).
    if (!document.getElementById("fab-new-tx")) {
        const fab = document.createElement("button");
        fab.type = "button";
        fab.id = "fab-new-tx";
        fab.className = "fab-new-tx";
        fab.setAttribute("aria-label", "New transaction");
        fab.textContent = "+";
        fab.addEventListener("click", () => openTxTypePicker());
        document.body.appendChild(fab);
    }

    // Wiring must happen after injection — these elements don't exist before this point.
    document.getElementById("modal-close").addEventListener("click", closeNewTxModal);
    document.getElementById("modal-cancel").addEventListener("click", closeNewTxModal);
    document.getElementById("modal-delete").addEventListener("click", deleteEditingTx);
    document.getElementById("new-tx-modal").addEventListener("click", (e) => {
        if (e.target === e.currentTarget) closeNewTxModal();
    });
    document.getElementById("new-tx-form").addEventListener("submit", submitNewTx);
    document.getElementById("tx-type-income").addEventListener("click", () => openNewTxModal("income"));
    document.getElementById("tx-type-expense").addEventListener("click", () => openNewTxModal("expense"));
    document.querySelectorAll(".tx-type-toggle-btn").forEach((btn) => {
        btn.addEventListener("click", () => setTypeToggleActive(btn.dataset.type));
    });

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

// Esc closes the modal, and Tab/Shift+Tab stay trapped inside it while
// open (6.3) — otherwise keyboard focus could silently escape to page
// content hidden behind the overlay.
document.addEventListener("keydown", (e) => {
    const modal = document.getElementById("new-tx-modal");
    if (!modal || modal.hidden) return;

    if (e.key === "Escape") {
        closeNewTxModal();
        return;
    }

    if (e.key !== "Tab") return;
    const focusable = Array.from(
        modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    ).filter((el) => !el.disabled && el.offsetParent !== null);
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
    }
});

document.addEventListener("DOMContentLoaded", initNewTxUI);

// ---------------------------------------------------------------------------
// Shared header chrome: data-freshness indicator (1.8) and an uncategorized
// count badge on the Categorize nav link (3.7). Both come from one
// /api/status call so pages that don't need auth (e.g. /login, which has
// no header) simply skip this via the `nav` guard.
// ---------------------------------------------------------------------------
function renderSyncStatus(el, lastSynced) {
    if (!lastSynced) {
        el.textContent = "Never synced";
        el.title = "";
        el.classList.remove("stale");
        return;
    }

    const synced = new Date(lastSynced);
    const diffMs = Date.now() - synced.getTime();
    const diffHours = diffMs / 3600000;
    const diffDays = diffHours / 24;

    let label;
    if (diffHours < 1) label = "Synced just now";
    else if (diffHours < 24) label = `Synced ${Math.floor(diffHours)}h ago`;
    else label = `Synced ${Math.floor(diffDays)}d ago`;

    el.textContent = label;
    el.title = synced.toLocaleString();
    el.classList.toggle("stale", diffDays > 3);
}

async function initHeaderChrome() {
    const nav = document.querySelector("header nav");
    if (!nav) return;

    const statusEl = document.createElement("span");
    statusEl.className = "sync-status";
    statusEl.id = "sync-status";
    const userEl = document.getElementById("logged-user");
    if (userEl) nav.insertBefore(statusEl, userEl);
    else nav.appendChild(statusEl);

    let status;
    try {
        status = await fetchJSON("/api/status");
    } catch (err) {
        return;
    }

    renderSyncStatus(statusEl, status.last_synced);

    if (status.uncategorized > 0) {
        const link = nav.querySelector('a[href="/categorize"]');
        if (link) {
            const badge = document.createElement("span");
            badge.className = "nav-badge";
            badge.textContent = status.uncategorized;
            link.appendChild(badge);
        }
    }
}

document.addEventListener("DOMContentLoaded", initHeaderChrome);
