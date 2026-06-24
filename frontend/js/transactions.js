let categories = [];

function getMonthDateRange(monthStr) {
    const [year, month] = monthStr.split("-").map(Number);
    const lastDay = new Date(year, month, 0).getDate();
    return {
        start: `${year}-${String(month).padStart(2, "0")}-01`,
        end: `${year}-${String(month).padStart(2, "0")}-${lastDay}`,
    };
}

function shiftMonth(monthStr, delta) {
    const [year, month] = monthStr.split("-").map(Number);
    const d = new Date(year, month - 1 + delta, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

async function loadTransactions(monthStr) {
    const { start, end } = getMonthDateRange(monthStr);
    const transactions = await fetchJSON(`/api/transactions?start_date=${start}&end_date=${end}`);

    const income = transactions.filter((tx) => tx.type === TX_TYPE_TRANSFER);
    const expenses = transactions.filter((tx) => tx.type === TX_TYPE_PURCHASE || tx.type === TX_TYPE_OUTGOING_TRANSFER);

    exitEditMode("income");
    exitEditMode("expense");
    renderTable("income-table", income, "income");
    renderTable("expense-table", expenses, "expense");
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
    // cells: [selector, date, amount, description, category, actions]

    cells[2].innerHTML = `<input type="number" class="inline-edit-input ${amountClass}" step="0.01" value="${amount}">`;
    cells[3].innerHTML = `<input type="text" class="inline-edit-input" value="${description}">`;
    cells[4].innerHTML = `<input type="text" class="inline-edit-input" list="category-list" value="${category}">`;
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

    const res = await fetch(`/api/transactions/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

    if (res.ok) {
        row.dataset.amount = newAmount;
        row.dataset.description = newDescription;
        row.dataset.category = newCategory.toUpperCase();
        deselectRow(row);
    }
}

async function deleteRow(row) {
    const id = row.dataset.id;
    const res = await fetch(`/api/transactions/${id}`, {
        method: "DELETE",
    });
    if (res.ok) {
        row.remove();
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

function initMonthFilter() {
    const input = document.getElementById("transactions-month");
    const prevBtn = document.getElementById("month-prev");
    const nextBtn = document.getElementById("month-next");

    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    input.value = currentMonth;
    loadTransactions(currentMonth);

    input.addEventListener("change", () => {
        if (input.value) loadTransactions(input.value);
    });

    prevBtn.addEventListener("click", () => {
        input.value = shiftMonth(input.value, -1);
        loadTransactions(input.value);
    });

    nextBtn.addEventListener("click", () => {
        input.value = shiftMonth(input.value, 1);
        loadTransactions(input.value);
    });
}

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

async function submitNewTx(e) {
    e.preventDefault();

    const type = document.getElementById("tx-form-type").value;
    const amount = parseFloat(document.getElementById("tx-form-amount").value);
    const date = document.getElementById("tx-form-date").value;
    const description = document.getElementById("tx-form-description").value.trim();
    const category = document.getElementById("tx-form-category").value.trim();
    const person = document.getElementById("tx-form-person").value.trim();
    const reference = document.getElementById("tx-form-reference").value.trim();

    if (isNaN(amount) || amount < 0) return;

    const payload = { type, amount, date };

    if (type === TX_TYPE_TRANSFER) {
        payload.sender_bank = description || null;
    } else {
        payload.merchant = description || null;
    }

    if (category) payload.category = category.toUpperCase();
    if (person) payload.person = person;
    if (reference) payload.reference = reference;

    const res = await fetch("/api/transactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

    if (res.ok) {
        closeNewTxModal();
        const monthInput = document.getElementById("transactions-month");
        loadTransactions(monthInput.value);
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

loadCategories().then(() => {
    buildCategoryDatalist();
    initMonthFilter();
    initEditMode();
    initNewTxModal();
});
