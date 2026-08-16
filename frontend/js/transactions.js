// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let categories = [];
let currentMonth = null;
let incomeRows = [];
let incomeSort = { field: null, dir: "asc" };
let expenseRows = [];
let expenseFilter = { field: null, query: "" };

// ---------------------------------------------------------------------------
// Data loading & rendering
// ---------------------------------------------------------------------------
async function loadTransactions(monthStr) {
    const { start, end } = getMonthDateRange(monthStr);

    let transactions;
    try {
        transactions = await fetchJSON(`/api/transactions?start_date=${start}&end_date=${end}`);
    } catch (err) {
        showToast("Failed to load transactions", "error");
        return;
    }

    const income = transactions.filter((tx) => tx.type === TX_TYPE_TRANSFER);
    const expenses = transactions.filter((tx) => tx.type === TX_TYPE_PURCHASE || tx.type === TX_TYPE_OUTGOING_TRANSFER);

    incomeRows = income;
    expenseRows = expenses;

    exitEditMode("income");
    exitEditMode("expense");
    renderTable("income-table", sortIncomeRows(incomeRows), "income");
    renderTable("expense-table", filterExpenseRows(expenseRows), "expense");
}

function renderTable(tableId, rows, type) {
    const tbody = document.querySelector(`#${tableId} tbody`);
    const section = document.getElementById(`${type}-section`);
    const inEditMode = section.classList.contains("edit-mode");

    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="no-data">No transactions</td></tr>`;
        return;
    }

    tbody.innerHTML = rows
        .map((tx) => {
            const date = tx.date.replace("T", " ").slice(0, 16);
            const amount = formatAmount(tx.amount);
            const amountClass = type === "income" ? "amount-income" : "amount-expense";
            const description = type === "income"
                ? (tx.sender_bank || tx.concept || "-")
                : (tx.merchant || tx.dest_bank || "-");
            const category = tx.category
                ? `<span class="category-tag">${escapeHTML(tx.category)}</span>`
                : "";

            return `
                <tr data-id="${tx.id}" data-amount="${tx.amount}" data-description="${escapeHTML(description)}" data-category="${escapeHTML(tx.category || "")}">
                    <td class="cell-selector">${inEditMode ? '<span class="row-selector"></span>' : ""}</td>
                    <td>${escapeHTML(date)}</td>
                    <td class="${amountClass}">${amount}</td>
                    <td class="cell-description">${escapeHTML(description)}</td>
                    <td class="cell-category">${category}</td>
                    <td class="cell-actions"></td>
                </tr>
            `;
        })
        .join("");
}

// ---------------------------------------------------------------------------
// Income sorting
// ---------------------------------------------------------------------------
function incomeSortValue(tx, field) {
    switch (field) {
        case "date":
            return tx.date || "";
        case "amount":
            return parseFloat(tx.amount) || 0;
        case "source":
            return (tx.sender_bank || tx.concept || "").toLowerCase();
        case "category":
            return (tx.category || "").toLowerCase();
        default:
            return "";
    }
}

function sortIncomeRows(rows) {
    if (!incomeSort.field) return rows;

    const sorted = [...rows].sort((a, b) => {
        const av = incomeSortValue(a, incomeSort.field);
        const bv = incomeSortValue(b, incomeSort.field);
        if (av < bv) return -1;
        if (av > bv) return 1;
        return 0;
    });

    if (incomeSort.dir === "desc") sorted.reverse();
    return sorted;
}

// Keep the cached income rows in sync with an inline edit so a later re-sort
// reflects the change instead of reverting to the loaded data.
function syncIncomeCache(id, { amount, description, category }) {
    const tx = incomeRows.find((t) => String(t.id) === String(id));
    if (!tx) return;
    tx.amount = amount;
    tx.sender_bank = description;
    tx.concept = null;
    tx.category = category;
}

function updateSortMenu() {
    const menu = document.getElementById("income-sort-menu");
    menu.querySelectorAll(".sort-option").forEach((opt) => {
        opt.classList.toggle("active", opt.dataset.field === incomeSort.field);
        opt.dataset.dir = opt.dataset.field === incomeSort.field ? incomeSort.dir : "";
    });
}

function closeSortMenu() {
    const btn = document.getElementById("income-sort-btn");
    const menu = document.getElementById("income-sort-menu");
    menu.hidden = true;
    btn.setAttribute("aria-expanded", "false");
}

function initSort() {
    const btn = document.getElementById("income-sort-btn");
    const menu = document.getElementById("income-sort-menu");

    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeFilterMenu();
        const willOpen = menu.hidden;
        menu.hidden = !willOpen;
        btn.setAttribute("aria-expanded", String(willOpen));
        if (willOpen) updateSortMenu();
    });

    menu.addEventListener("click", (e) => {
        const opt = e.target.closest(".sort-option");
        if (!opt) return;
        const field = opt.dataset.field;
        if (incomeSort.field === field) {
            incomeSort.dir = incomeSort.dir === "asc" ? "desc" : "asc";
        } else {
            incomeSort.field = field;
            incomeSort.dir = "asc";
        }
        btn.classList.add("active");
        updateSortMenu();
        renderTable("income-table", sortIncomeRows(incomeRows), "income");
    });

    document.addEventListener("click", () => {
        if (!menu.hidden) closeSortMenu();
    });
}

// ---------------------------------------------------------------------------
// Expense filtering
// ---------------------------------------------------------------------------
function expenseFilterValue(tx, field) {
    switch (field) {
        case "date":
            return (tx.date || "").replace("T", " ").slice(0, 16).toLowerCase();
        case "amount":
            return String(tx.amount ?? "").toLowerCase();
        case "description":
            return (tx.merchant || tx.dest_bank || "").toLowerCase();
        case "category":
            return (tx.category || "").toLowerCase();
        default:
            return "";
    }
}

function filterExpenseRows(rows) {
    const query = expenseFilter.query.trim().toLowerCase();
    if (!expenseFilter.field || !query) return rows;
    return rows.filter((tx) => expenseFilterValue(tx, expenseFilter.field).includes(query));
}

// Keep the cached expense rows in sync with an inline edit so a later re-filter
// reflects the change instead of reverting to the loaded data.
function syncExpenseCache(id, { amount, description, category }) {
    const tx = expenseRows.find((t) => String(t.id) === String(id));
    if (!tx) return;
    tx.amount = amount;
    tx.merchant = description;
    tx.dest_bank = null;
    tx.category = category;
}

function updateFilterMenu() {
    const menu = document.getElementById("expense-filter-menu");
    menu.querySelectorAll(".filter-option").forEach((opt) => {
        opt.classList.toggle("active", opt.dataset.field === expenseFilter.field);
    });
}

function closeFilterMenu() {
    const btn = document.getElementById("expense-filter-btn");
    const menu = document.getElementById("expense-filter-menu");
    menu.hidden = true;
    btn.setAttribute("aria-expanded", "false");
}

function applyExpenseFilter() {
    btnFilterActiveState();
    renderTable("expense-table", filterExpenseRows(expenseRows), "expense");
}

function btnFilterActiveState() {
    const btn = document.getElementById("expense-filter-btn");
    const active = Boolean(expenseFilter.field && expenseFilter.query.trim());
    btn.classList.toggle("active", active);
}

function clearExpenseFilter() {
    const input = document.getElementById("expense-filter-input");
    expenseFilter = { field: null, query: "" };
    input.value = "";
    input.disabled = true;
    input.placeholder = "Select a column first";
    updateFilterMenu();
    applyExpenseFilter();
}

function initFilter() {
    const btn = document.getElementById("expense-filter-btn");
    const menu = document.getElementById("expense-filter-menu");
    const input = document.getElementById("expense-filter-input");
    const clearBtn = document.getElementById("expense-filter-clear");

    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        closeSortMenu();
        const willOpen = menu.hidden;
        menu.hidden = !willOpen;
        btn.setAttribute("aria-expanded", String(willOpen));
        if (willOpen) {
            updateFilterMenu();
            if (expenseFilter.field) input.focus();
        }
    });

    menu.addEventListener("click", (e) => {
        e.stopPropagation();
        const opt = e.target.closest(".filter-option");
        if (!opt) return;
        expenseFilter.field = opt.dataset.field;
        input.disabled = false;
        input.placeholder = `Filter by ${opt.textContent.toLowerCase()}…`;
        updateFilterMenu();
        input.focus();
        applyExpenseFilter();
    });

    input.addEventListener("input", () => {
        expenseFilter.query = input.value;
        applyExpenseFilter();
    });

    clearBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        clearExpenseFilter();
    });

    document.addEventListener("click", () => {
        if (!menu.hidden) closeFilterMenu();
    });
}

// ---------------------------------------------------------------------------
// Inline row editing
// ---------------------------------------------------------------------------
function enterEditMode(tableType) {
    const section = document.getElementById(`${tableType}-section`);
    section.classList.add("edit-mode");

    const btn = section.querySelector(".btn-edit-table");
    btn.textContent = "Done";
    btn.classList.add("active");

    const rows = section.querySelectorAll("tbody tr[data-id]");
    rows.forEach((row) => {
        row.querySelector(".cell-selector").innerHTML = '<span class="row-selector"></span>';
    });
}

function exitEditMode(tableType) {
    const section = document.getElementById(`${tableType}-section`);
    if (!section.classList.contains("edit-mode")) return;

    section.classList.remove("edit-mode");

    const btn = section.querySelector(".btn-edit-table");
    btn.textContent = "Edit";
    btn.classList.remove("active");

    const selected = section.querySelector("tr.row-selected");
    if (selected) deselectRow(selected);

    const rows = section.querySelectorAll("tbody tr[data-id]");
    rows.forEach((row) => {
        row.querySelector(".cell-selector").innerHTML = "";
        row.querySelector(".cell-actions").innerHTML = "";
    });
}

function selectRow(row) {
    const section = row.closest(".table-section");
    const prev = section.querySelector("tr.row-selected");
    if (prev && prev !== row) deselectRow(prev);

    row.classList.add("row-selected");

    const amount = row.dataset.amount;
    const description = row.dataset.description;
    const category = row.dataset.category;
    const type = section.id === "income-section" ? "income" : "expense";
    const amountClass = type === "income" ? "amount-income" : "amount-expense";

    const cells = row.querySelectorAll("td");

    cells[2].innerHTML = `<input type="number" class="inline-edit-input ${amountClass}" step="0.01" value="${escapeHTML(amount)}">`;
    cells[3].innerHTML = `<input type="text" class="inline-edit-input" value="${escapeHTML(description)}">`;
    cells[4].innerHTML = `<input type="text" class="inline-edit-input" list="category-list" value="${escapeHTML(category)}">`;
    cells[5].innerHTML = `
        <button class="btn-save-row" title="Save">&#10003;</button>
        <button class="btn-delete-row" title="Delete">&#128465;</button>
    `;

    const firstInput = cells[2].querySelector("input");
    firstInput.focus();
    firstInput.select();
}

function deselectRow(row) {
    row.classList.remove("row-selected");
    const amount = row.dataset.amount;
    const description = row.dataset.description;
    const category = row.dataset.category;
    const section = row.closest(".table-section");
    const type = section.id === "income-section" ? "income" : "expense";
    const amountClass = type === "income" ? "amount-income" : "amount-expense";

    const cells = row.querySelectorAll("td");
    cells[2].className = amountClass;
    cells[2].textContent = formatAmount(parseFloat(amount));
    cells[3].className = "cell-description";
    cells[3].textContent = description;
    cells[4].className = "cell-category";
    cells[4].innerHTML = category
        ? `<span class="category-tag">${escapeHTML(category)}</span>`
        : "";
    cells[5].innerHTML = "";
}

async function saveRow(row) {
    const monthInput = document.getElementById("transactions-month");
    if (monthInput.value !== currentMonth) {
        showToast("Month changed — edit cancelled", "error");
        deselectRow(row);
        return;
    }

    const id = row.dataset.id;
    const cells = row.querySelectorAll("td");
    const newAmount = parseFloat(cells[2].querySelector("input").value);
    const newDescription = cells[3].querySelector("input").value.trim();
    const newCategory = cells[4].querySelector("input").value.trim();

    if (isNaN(newAmount) || newAmount < 0) return;

    const payload = {};
    if (newAmount !== parseFloat(row.dataset.amount)) payload.amount = newAmount;
    if (newDescription !== row.dataset.description) payload.merchant = newDescription;
    if (newCategory !== row.dataset.category) payload.category = newCategory || null;

    if (Object.keys(payload).length === 0) {
        deselectRow(row);
        return;
    }

    try {
        const res = await apiFetch(`/api/transactions/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (res.ok) {
            row.dataset.amount = newAmount;
            row.dataset.description = newDescription;
            row.dataset.category = newCategory.toUpperCase();
            syncIncomeCache(id, {
                amount: newAmount,
                description: newDescription,
                category: newCategory.toUpperCase() || null,
            });
            syncExpenseCache(id, {
                amount: newAmount,
                description: newDescription,
                category: newCategory.toUpperCase() || null,
            });
            deselectRow(row);
            showToast("Saved", "success");
        } else {
            showToast("Save failed", "error");
        }
    } catch (err) {
        showToast("Save failed", "error");
    }
}

async function deleteRow(row) {
    const id = row.dataset.id;
    try {
        const res = await apiFetch(`/api/transactions/${id}`, {
            method: "DELETE",
        });
        if (res.ok) {
            incomeRows = incomeRows.filter((tx) => String(tx.id) !== String(id));
            expenseRows = expenseRows.filter((tx) => String(tx.id) !== String(id));
            row.remove();
            showToast("Deleted", "success");
        } else {
            showToast("Delete failed", "error");
        }
    } catch (err) {
        showToast("Delete failed", "error");
    }
}

function initEditMode() {
    document.addEventListener("click", (e) => {
        const editBtn = e.target.closest(".btn-edit-table");
        if (editBtn) {
            const tableType = editBtn.dataset.table;
            const section = document.getElementById(`${tableType}-section`);
            if (section.classList.contains("edit-mode")) {
                exitEditMode(tableType);
            } else {
                enterEditMode(tableType);
            }
            return;
        }

        const selector = e.target.closest(".row-selector");
        if (selector) {
            const row = selector.closest("tr");
            selectRow(row);
            return;
        }

        const saveBtn = e.target.closest(".btn-save-row");
        if (saveBtn) {
            const row = saveBtn.closest("tr");
            saveRow(row);
            return;
        }

        const deleteBtn = e.target.closest(".btn-delete-row");
        if (deleteBtn) {
            const row = deleteBtn.closest("tr");
            deleteRow(row);
            return;
        }
    });

    document.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            const row = e.target.closest("tr.row-selected");
            if (row) {
                e.preventDefault();
                saveRow(row);
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Categories
// ---------------------------------------------------------------------------
async function loadCategories() {
    categories = await fetchJSON("/api/categories");
}

function buildCategoryDatalist() {
    if (document.getElementById("category-list")) return;
    const dl = document.createElement("datalist");
    dl.id = "category-list";
    categories.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c;
        dl.appendChild(opt);
    });
    document.body.appendChild(dl);
}

// ---------------------------------------------------------------------------
// Banks
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Month filter
// ---------------------------------------------------------------------------
function initMonthFilter() {
    const input = document.getElementById("transactions-month");
    const prevBtn = document.getElementById("month-prev");
    const nextBtn = document.getElementById("month-next");

    currentMonth = getCurrentMonthStr();
    input.value = currentMonth;
    loadTransactions(currentMonth);

    input.addEventListener("change", () => {
        if (input.value) {
            currentMonth = input.value;
            loadTransactions(input.value);
        }
    });

    prevBtn.addEventListener("click", () => {
        input.value = shiftMonth(input.value, -1);
        currentMonth = input.value;
        loadTransactions(input.value);
    });

    nextBtn.addEventListener("click", () => {
        input.value = shiftMonth(input.value, 1);
        currentMonth = input.value;
        loadTransactions(input.value);
    });
}

// ---------------------------------------------------------------------------
// New transaction modal
// ---------------------------------------------------------------------------
function openNewTxModal(txType) {
    const modal = document.getElementById("new-tx-modal");
    const form = document.getElementById("new-tx-form");
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

    modal.hidden = false;
    document.getElementById("tx-form-amount").focus();
}

function closeNewTxModal() {
    document.getElementById("new-tx-modal").hidden = true;
}

// Manual transactions have no bank-issued reference, but `reference`
// participates in the dedup unique index, so give each one a unique value.
function generateReference() {
    return `MAN-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
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

    const payload = {
		type,
		amount,
		date,
		person: getLoggedUser(),
		reference: generateReference(),
		bank
	};

    if (type === TX_TYPE_TRANSFER) {
        payload.sender_bank = description || null;
		payload.concept = TX_TYPE_TRANSFER;
    } else {
        payload.merchant = description || null;
		payload.concept = description || null;
    }

    if (category) payload.category = category.toUpperCase();

    const submitBtn = document.querySelector(".btn-modal-submit");
    setButtonLoading(submitBtn, true);

    try {
        if (payload.category && !categories.some((c) => c.toUpperCase() === payload.category)) {
            await apiFetch("/api/categories", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: payload.category }),
            });
            categories.push(payload.category);
        }

        const res = await apiFetch("/api/transactions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (res.ok) {
            closeNewTxModal();
            showToast("Transaction created", "success");
            const monthInput = document.getElementById("transactions-month");
            loadTransactions(monthInput.value);
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

function initNewTxModal() {
    document.addEventListener("click", (e) => {
        const btn = e.target.closest(".btn-new-tx");
        if (btn) {
            openNewTxModal(btn.dataset.type);
            return;
        }
    });

    document.getElementById("modal-close").addEventListener("click", closeNewTxModal);
    document.getElementById("modal-cancel").addEventListener("click", closeNewTxModal);
    document.getElementById("new-tx-modal").addEventListener("click", (e) => {
        if (e.target === e.currentTarget) closeNewTxModal();
    });
    document.getElementById("new-tx-form").addEventListener("submit", submitNewTx);
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
if (requireAuth()) {
    loadCategories().then(() => {
        buildCategoryDatalist();
        buildBankDatalist();
        initMonthFilter();
        initEditMode();
        initNewTxModal();
        initSort();
        initFilter();
    });
}
