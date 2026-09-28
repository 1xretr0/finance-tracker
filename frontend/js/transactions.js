// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let currentMonth = null;
let incomeRows = [];
let expenseRows = [];
let visibleIncomeRows = [];
let visibleExpenseRows = [];
let incomeState = { sort: "date", dir: "desc", q: "" };
let expenseState = { sort: "date", dir: "desc", q: "" };
let bankFilter = "";
let personFilter = "";
let categoryFilter = null;

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
function rowDescription(tx, type) {
    return type === "income" ? (tx.sender_bank || tx.concept || "") : (tx.merchant || tx.dest_bank || "");
}

// A muted sub-line under the description showing where the money moved
// (4.4), e.g. "SANTANDER ••1234".
function bankSubline(tx) {
    const last4 = tx.card_last4 || tx.account_last4 || tx.dest_account_last4 || "";
    return last4 ? `${tx.bank} ••${last4}` : (tx.bank || "");
}

function sortValue(tx, field, type) {
    switch (field) {
        case "date":
            return tx.date || "";
        case "amount":
            return parseFloat(tx.amount) || 0;
        case "source":
        case "description":
            return rowDescription(tx, type).toLowerCase();
        case "category":
            return (tx.category || "").toLowerCase();
        default:
            return "";
    }
}

function sortRows(rows, field, dir, type) {
    const sorted = [...rows].sort((a, b) => {
        const av = sortValue(a, field, type);
        const bv = sortValue(b, field, type);
        if (av < bv) return -1;
        if (av > bv) return 1;
        return 0;
    });
    if (dir === "desc") sorted.reverse();
    return sorted;
}

function matchesSharedFilters(tx) {
    if (bankFilter && tx.bank !== bankFilter) return false;
    if (personFilter && tx.person !== personFilter) return false;
    if (categoryFilter && (tx.category || "").toUpperCase() !== categoryFilter) return false;
    return true;
}

// Matches every visible column: date, amount, description (+ its bank/card
// sub-line) and category (4.1).
function rowMatchesSearch(tx, type, query) {
    if (!query) return true;
    const q = query.trim().toLowerCase();
    if (!q) return true;
    const haystack = [
        (tx.date || "").replace("T", " ").slice(0, 16),
        String(tx.amount ?? ""),
        rowDescription(tx, type),
        bankSubline(tx),
        tx.category || "",
    ]
        .join(" ")
        .toLowerCase();
    return haystack.includes(q);
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------
async function loadTransactions(month) {
    currentMonth = month;
    document.getElementById("transactions-month").value = month;
    document.querySelector("#income-table tbody").innerHTML = `<tr><td colspan="4" class="no-data">Loading…</td></tr>`;
    document.querySelector("#expense-table tbody").innerHTML = `<tr><td colspan="4" class="no-data">Loading…</td></tr>`;

    const { start, end } = getMonthDateRange(month);
    let all;
    try {
        all = await fetchJSON(`/api/transactions?start_date=${start}&end_date=${end}`);
    } catch (err) {
        showToast("Failed to load transactions", "error");
        return;
    }

    incomeRows = all.filter((tx) => tx.type === TX_TYPE_TRANSFER);
    expenseRows = all.filter((tx) => tx.type === TX_TYPE_PURCHASE || tx.type === TX_TYPE_OUTGOING_TRANSFER);

    updatePersonFilterOptions();
    updateMonthNet();
    applyAllFilters();
    updateURLState();
}

function updatePersonFilterOptions() {
    const select = document.getElementById("person-filter");
    const persons = [...new Set([...incomeRows, ...expenseRows].map((tx) => tx.person).filter(Boolean))];

    if (persons.length <= 1) {
        select.hidden = true;
        select.innerHTML = "";
        personFilter = "";
        return;
    }

    select.hidden = false;
    select.innerHTML =
        `<option value="">All people</option>` +
        persons.map((p) => `<option value="${escapeHTML(p)}" ${p === personFilter ? "selected" : ""}>${escapeHTML(p)}</option>`).join("");
    if (!persons.includes(personFilter)) personFilter = "";
}

function updateMonthNet() {
    const income = incomeRows.reduce((s, tx) => s + tx.amount, 0);
    const expenses = expenseRows.reduce((s, tx) => s + tx.amount, 0);
    const net = income - expenses;
    const el = document.getElementById("month-net");
    el.textContent = `Net: ${formatAmount(net)}`;
    el.className = `month-net ${net >= 0 ? "income" : "expense"}`;
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
function renderRow(tx, type) {
    const date = (tx.date || "").replace("T", " ").slice(0, 16);
    const amountClass = type === "income" ? "amount-income" : "amount-expense";
    const description = rowDescription(tx, type) || "-";
    const sub = bankSubline(tx);
    const category = tx.category ? `<span class="category-tag">${escapeHTML(tx.category)}</span>` : "";
    const notesMarker = tx.notes ? `<span class="notes-marker" title="${escapeHTML(tx.notes)}">&#128221;</span>` : "";

    return `
        <tr data-id="${tx.id}" tabindex="0">
            <td>${escapeHTML(date)}</td>
            <td class="${amountClass}">${formatAmount(tx.amount)}</td>
            <td class="cell-description">
                <div class="description-main">${escapeHTML(description)} ${notesMarker}</div>
                <div class="description-sub">${escapeHTML(sub)}</div>
            </td>
            <td class="cell-category">${category}</td>
        </tr>
    `;
}

function renderTable(type, rows) {
    const tbody = document.querySelector(`#${type}-table tbody`);
    tbody.innerHTML = rows.length === 0
        ? `<tr><td colspan="4" class="no-data">No transactions</td></tr>`
        : rows.map((tx) => renderRow(tx, type)).join("");

    document.getElementById(`${type}-count`).textContent = `${rows.length} row${rows.length === 1 ? "" : "s"}`;
    document.getElementById(`${type}-sum`).textContent = formatAmount(rows.reduce((s, tx) => s + tx.amount, 0));
}

function updateSortHeaders() {
    document.querySelectorAll("#income-table th.sortable").forEach((th) => {
        th.setAttribute("aria-sort", th.dataset.field === incomeState.sort ? (incomeState.dir === "asc" ? "ascending" : "descending") : "none");
    });
    document.querySelectorAll("#expense-table th.sortable").forEach((th) => {
        th.setAttribute("aria-sort", th.dataset.field === expenseState.sort ? (expenseState.dir === "asc" ? "ascending" : "descending") : "none");
    });
}

function renderCategoryChip() {
    const container = document.getElementById("active-filters");
    if (!categoryFilter) {
        container.innerHTML = "";
        return;
    }
    container.innerHTML = `
        <span class="filter-chip">
            ${escapeHTML(categoryFilter)}
            <button type="button" class="filter-chip-remove" id="remove-category-filter" aria-label="Remove category filter">&times;</button>
        </span>
    `;
}

function applyAllFilters() {
    visibleIncomeRows = sortRows(
        incomeRows.filter((tx) => matchesSharedFilters(tx) && rowMatchesSearch(tx, "income", incomeState.q)),
        incomeState.sort,
        incomeState.dir,
        "income"
    );
    visibleExpenseRows = sortRows(
        expenseRows.filter((tx) => matchesSharedFilters(tx) && rowMatchesSearch(tx, "expense", expenseState.q)),
        expenseState.sort,
        expenseState.dir,
        "expense"
    );

    renderTable("income", visibleIncomeRows);
    renderTable("expense", visibleExpenseRows);
    updateSortHeaders();
    renderCategoryChip();
}

// ---------------------------------------------------------------------------
// URL state (4.8)
// ---------------------------------------------------------------------------
function updateURLState() {
    const url = new URL(window.location);
    url.searchParams.set("month", currentMonth);

    const setOrDelete = (key, value) => {
        if (value) url.searchParams.set(key, value);
        else url.searchParams.delete(key);
    };
    setOrDelete("bank", bankFilter);
    setOrDelete("person", personFilter);
    setOrDelete("category", categoryFilter);
    setOrDelete("q", incomeState.q);
    setOrDelete("eq", expenseState.q);

    history.replaceState({}, "", url);
}

function initFromURL() {
    const params = new URLSearchParams(window.location.search);
    currentMonth = params.get("month") || getCurrentMonthStr();
    bankFilter = params.get("bank") || "";
    personFilter = params.get("person") || "";
    categoryFilter = params.get("category") ? params.get("category").toUpperCase() : null;
    incomeState.q = params.get("q") || "";
    expenseState.q = params.get("eq") || "";

    document.getElementById("bank-filter").value = bankFilter;
    document.getElementById("income-search").value = incomeState.q;
    document.getElementById("expense-search").value = expenseState.q;
}

// ---------------------------------------------------------------------------
// Filter & sort controls
// ---------------------------------------------------------------------------
function initBankFilter() {
    const select = document.getElementById("bank-filter");
    select.innerHTML = `<option value="">All banks</option>` +
        BANKS_LIST.map((b) => `<option value="${escapeHTML(b)}">${escapeHTML(b)}</option>`).join("");
    select.value = bankFilter;

    select.addEventListener("change", () => {
        bankFilter = select.value;
        applyAllFilters();
        updateURLState();
    });
}

function initPersonFilter() {
    document.getElementById("person-filter").addEventListener("change", (e) => {
        personFilter = e.target.value;
        applyAllFilters();
        updateURLState();
    });
}

function initSearch() {
    document.getElementById("income-search").addEventListener("input", (e) => {
        incomeState.q = e.target.value;
        applyAllFilters();
        updateURLState();
    });
    document.getElementById("expense-search").addEventListener("input", (e) => {
        expenseState.q = e.target.value;
        applyAllFilters();
        updateURLState();
    });
}

function initSortHeaders() {
    const wire = (tableId, state) => {
        document.querySelectorAll(`#${tableId} th.sortable`).forEach((th) => {
            th.addEventListener("click", () => {
                const field = th.dataset.field;
                if (state.sort === field) state.dir = state.dir === "asc" ? "desc" : "asc";
                else {
                    state.sort = field;
                    state.dir = "asc";
                }
                applyAllFilters();
            });
        });
    };
    wire("income-table", incomeState);
    wire("expense-table", expenseState);
}

function initCategoryChip() {
    document.getElementById("active-filters").addEventListener("click", (e) => {
        if (!e.target.closest(".filter-chip-remove")) return;
        categoryFilter = null;
        applyAllFilters();
        updateURLState();
    });
}

// ---------------------------------------------------------------------------
// Row click/keyboard -> edit modal (4.6, 4.7)
// ---------------------------------------------------------------------------
function openRowEditor(row) {
    const id = row.dataset.id;
    const tx = [...incomeRows, ...expenseRows].find((t) => String(t.id) === String(id));
    if (tx) openEditTxModal(tx);
}

function initRowInteractions() {
    const rowSelector = "#income-table tbody tr[data-id], #expense-table tbody tr[data-id]";

    document.addEventListener("click", (e) => {
        const row = e.target.closest(rowSelector);
        if (row) openRowEditor(row);
    });

    document.addEventListener("keydown", (e) => {
        if (e.key !== "Enter") return;
        const row = e.target.closest(rowSelector);
        if (row) {
            e.preventDefault();
            openRowEditor(row);
        }
    });
}

// ---------------------------------------------------------------------------
// Month filter
// ---------------------------------------------------------------------------
function initMonthFilter() {
    const input = document.getElementById("transactions-month");

    input.addEventListener("change", () => {
        if (input.value) loadTransactions(input.value);
    });
    document.getElementById("month-prev").addEventListener("click", () => loadTransactions(shiftMonth(currentMonth, -1)));
    document.getElementById("month-next").addEventListener("click", () => loadTransactions(shiftMonth(currentMonth, 1)));
}

// ---------------------------------------------------------------------------
// CSV export (4.9)
// ---------------------------------------------------------------------------
// Quotes every field and prefixes anything starting with = + - @ with a
// leading apostrophe, guarding against formula injection when opened in a
// spreadsheet app.
function csvField(value) {
    let str = String(value ?? "");
    if (/^[=+\-@]/.test(str)) str = `'${str}`;
    return `"${str.replace(/"/g, '""')}"`;
}

function exportCSV() {
    const header = ["Type", "Date", "Amount", "Description", "Category", "Bank"];
    const lines = [header.map(csvField).join(",")];

    visibleIncomeRows.forEach((tx) => {
        lines.push([tx.type, tx.date, tx.amount, rowDescription(tx, "income"), tx.category || "", tx.bank].map(csvField).join(","));
    });
    visibleExpenseRows.forEach((tx) => {
        lines.push([tx.type, tx.date, tx.amount, rowDescription(tx, "expense"), tx.category || "", tx.bank].map(csvField).join(","));
    });

    const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `transactions-${currentMonth}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

// The shared modal (common.js) calls this after any create, edit or delete
// so the currently visible month refreshes with the change.
window.onTransactionChanged = () => loadTransactions(currentMonth);

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
if (requireAuth()) {
    initFromURL();
    initBankFilter();
    initPersonFilter();
    initSearch();
    initSortHeaders();
    initCategoryChip();
    initRowInteractions();
    initMonthFilter();
    document.getElementById("export-csv-btn").addEventListener("click", exportCSV);
    loadTransactions(currentMonth);
}
