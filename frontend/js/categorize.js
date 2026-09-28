// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let transactions = [];
let currentIndex = 0;
let categoriesDetailed = []; // [{id, name, kind, budget, count}]

// ---------------------------------------------------------------------------
// Data loading & rendering
// ---------------------------------------------------------------------------
async function init() {
    try {
        [transactions, categoriesDetailed] = await Promise.all([
            fetchJSON("/api/uncategorized"),
            fetchJSON("/api/categories?detailed=true"),
        ]);
    } catch (err) {
        document.getElementById("current-transaction").innerHTML =
            `<div class="empty-state" style="color: var(--color-expense)">Failed to load data. Please refresh.</div>`;
        showToast("Failed to load transactions", "error");
        return;
    }

    transactions.sort((a, b) => a.date.localeCompare(b.date));

    populateCategoryList();
    updateCounter();
    showCurrent();
}

// The field used to recognize "the same transaction description" across
// rows — mirrors backend/db/storage.py's _description_key.
function descriptionKey(tx) {
    return tx.merchant || tx.dest_bank || tx.sender_bank || tx.concept || null;
}

// Income categories are suggested for transfers, expense categories for
// purchases/outgoing transfers — mirrors the kind a category created here
// would be tagged with.
function desiredKind(tx) {
    return tx.type === TX_TYPE_TRANSFER ? "income" : "expense";
}

function categoryNames() {
    return categoriesDetailed.map((c) => c.name);
}

function populateCategoryList() {
    const datalist = document.getElementById("category-list");
    datalist.innerHTML = categoryNames().map((c) => `<option value="${escapeHTML(c)}">`).join("");
}

function topChipsFor(tx) {
    const kind = desiredKind(tx);
    return categoriesDetailed
        .filter((c) => c.kind === kind || c.kind == null)
        .sort((a, b) => b.count - a.count)
        .slice(0, 8);
}

function renderChips(tx) {
    const container = document.getElementById("category-chips");
    const chips = topChipsFor(tx);
    container.innerHTML = chips
        .map(
            (c, i) => `<button type="button" class="category-chip" data-category="${escapeHTML(c.name)}">
                <span class="chip-key">${i + 1}</span>${escapeHTML(c.name)}
            </button>`
        )
        .join("");
}

function renderApplyAll(tx) {
    const row = document.getElementById("apply-all-row");
    const checkbox = document.getElementById("apply-all-checkbox");
    const key = descriptionKey(tx);
    const matches = key ? transactions.filter((t, i) => i !== currentIndex && descriptionKey(t) === key) : [];

    checkbox.checked = false;
    if (matches.length === 0) {
        row.hidden = true;
        return;
    }
    row.hidden = false;
    document.getElementById("apply-all-text").textContent =
        `Apply to all ${matches.length} remaining from "${key}"`;
}

function showCurrent() {
    const container = document.getElementById("current-transaction");
    const controls = document.getElementById("controls");
    const input = document.getElementById("category-input");
    const hint = document.getElementById("suggested-hint");

    if (currentIndex >= transactions.length) {
        container.innerHTML = `<div class="empty-state">All transactions are categorized!</div>`;
        controls.style.display = "none";
        return;
    }

    controls.style.display = "flex";

    const tx = transactions[currentIndex];
    const description = descriptionKey(tx) || "-";
    const sign = tx.type === TX_TYPE_TRANSFER ? "+" : "-";

    input.value = tx.suggested_category || "";
    if (tx.suggested_category) {
        hint.hidden = false;
        hint.textContent = `Suggested: ${tx.suggested_category} (press Enter to accept)`;
    } else {
        hint.hidden = true;
        hint.textContent = "";
    }

    renderChips(tx);
    renderApplyAll(tx);

    container.innerHTML = `
        <div class="tx-row">
            <span class="label">Date</span>
            <span class="value">${escapeHTML(tx.date.replace("T", " ").slice(0, 16))}</span>
        </div>
        <div class="tx-row">
            <span class="label">Type</span>
            <span class="value">${escapeHTML(tx.type)}</span>
        </div>
        <div class="tx-row">
            <span class="label">Amount</span>
            <span class="value amount-${escapeHTML(tx.type)}">${sign}${formatAmount(tx.amount)} ${escapeHTML(tx.currency)}</span>
        </div>
        <hr class="tx-divider">
        <div class="tx-row">
            <span class="label">Description</span>
            <span class="value">${escapeHTML(description)}</span>
        </div>
        ${tx.card_last4 ? `<div class="tx-row"><span class="label">Card</span><span class="value">****${escapeHTML(tx.card_last4)}</span></div>` : ""}
        ${tx.sender_bank ? `<div class="tx-row"><span class="label">From</span><span class="value">${escapeHTML(tx.sender_bank)}</span></div>` : ""}
        ${tx.dest_bank ? `<div class="tx-row"><span class="label">To</span><span class="value">${escapeHTML(tx.dest_bank)}</span></div>` : ""}
    `;

    input.focus();
}

// ---------------------------------------------------------------------------
// Category management
// ---------------------------------------------------------------------------
async function ensureCategory(categoryName, kind) {
    if (categoryNames().some((c) => c.toUpperCase() === categoryName)) return true;

    const createRes = await apiFetch("/api/categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: categoryName, kind }),
    });
    if (!createRes.ok) return false;

    categoriesDetailed.push({ id: null, name: categoryName, kind, budget: null, count: 0 });
    categoriesDetailed.sort((a, b) => a.name.localeCompare(b.name));
    populateCategoryList();
    return true;
}

async function saveCategory(explicitCategory) {
    const input = document.getElementById("category-input");
    const categoryName = (explicitCategory || input.value.trim()).toUpperCase();
    if (!categoryName) return;

    const tx = transactions[currentIndex];
    const applyToAll = document.getElementById("apply-all-checkbox").checked;
    const saveBtn = document.getElementById("save-btn");
    setButtonLoading(saveBtn, true);

    try {
        const created = await ensureCategory(categoryName, desiredKind(tx));
        if (!created) {
            showToast("Failed to create category", "error");
            return;
        }

        const key = descriptionKey(tx);
        const matches = applyToAll && key
            ? transactions.filter((t, i) => i !== currentIndex && descriptionKey(t) === key)
            : [];
        const updates = [tx, ...matches].map((t) => ({ id: t.id, category: categoryName }));

        const res = await apiFetch("/api/transactions/categorize", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(updates),
        });

        if (res.ok) {
            const removedIds = new Set(updates.map((u) => u.id));
            const before = transactions;
            let pointer = currentIndex + 1;
            while (pointer < before.length && removedIds.has(before[pointer].id)) pointer++;
            const nextId = pointer < before.length ? before[pointer].id : null;

            transactions = before.filter((t) => !removedIds.has(t.id));
            currentIndex = nextId != null ? transactions.findIndex((t) => t.id === nextId) : transactions.length;

            updateCounter();
            showCurrent();
        } else {
            showToast("Failed to save category", "error");
        }
    } catch (err) {
        showToast("Failed to save category", "error");
    } finally {
        setButtonLoading(saveBtn, false);
    }
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
function skip() {
    currentIndex++;
    updateCounter();
    showCurrent();
}

function updateCounter() {
    const remaining = transactions.length - currentIndex;
    document.getElementById("counter").textContent = `${remaining} remaining`;
}

// ---------------------------------------------------------------------------
// Event handlers & initialization
// ---------------------------------------------------------------------------
function initEventHandlers() {
    document.getElementById("save-btn").addEventListener("click", () => saveCategory());
    document.getElementById("skip-btn").addEventListener("click", skip);

    document.getElementById("category-input").addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            e.preventDefault();
            saveCategory();
        }
    });

    document.getElementById("category-chips").addEventListener("click", (e) => {
        const chip = e.target.closest(".category-chip");
        if (chip) saveCategory(chip.dataset.category);
    });

    // Number keys 1-8 pick a chip, but only while the input is empty (a
    // pre-filled suggestion or manual text takes priority over shortcuts).
    document.addEventListener("keydown", (e) => {
        if (!/^[1-8]$/.test(e.key)) return;
        const input = document.getElementById("category-input");
        if (document.getElementById("controls").style.display === "none") return;
        if (input.value.trim() !== "") return;

        const chips = document.querySelectorAll(".category-chip");
        const chip = chips[parseInt(e.key, 10) - 1];
        if (!chip) return;
        e.preventDefault();
        saveCategory(chip.dataset.category);
    });
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
if (requireAuth()) {
    initEventHandlers();
    init();
}
