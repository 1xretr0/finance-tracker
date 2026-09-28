// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let categories = []; // [{id, name, kind, budget, count}]
let ignoredTransfers = []; // [{id, account_last4, bank}]

// ---------------------------------------------------------------------------
// Categories table
// ---------------------------------------------------------------------------
async function loadCategories() {
    const tbody = document.getElementById("categories-tbody");
    tbody.innerHTML = `<tr><td colspan="5" class="no-data">Loading…</td></tr>`;
    try {
        categories = await fetchJSON("/api/categories?detailed=true");
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" class="no-data">Failed to load categories</td></tr>`;
        return;
    }
    renderCategories();
}

function kindOptions(selected) {
    return ["", "income", "expense"]
        .map((k) => {
            const label = k === "" ? "—" : k[0].toUpperCase() + k.slice(1);
            return `<option value="${k}" ${k === (selected || "") ? "selected" : ""}>${label}</option>`;
        })
        .join("");
}

function mergeTargetOptions(currentId) {
    return categories
        .filter((c) => c.id !== currentId)
        .map((c) => `<option value="${escapeHTML(c.name)}">${escapeHTML(c.name)}</option>`)
        .join("");
}

function renderCategories() {
    const tbody = document.getElementById("categories-tbody");
    if (categories.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="no-data">No categories yet</td></tr>`;
        return;
    }

    tbody.innerHTML = categories
        .map(
            (c) => `
                <tr data-id="${c.id}">
                    <td><input type="text" class="cat-name-input" value="${escapeHTML(c.name)}"></td>
                    <td><select class="cat-kind-select">${kindOptions(c.kind)}</select></td>
                    <td><input type="number" class="cat-budget-input" min="0" step="0.01" value="${c.budget != null ? c.budget : ""}" placeholder="—"></td>
                    <td class="cat-count">${c.count}</td>
                    <td class="col-actions">
                        <select class="cat-merge-select">
                            <option value="">Merge into…</option>
                            ${mergeTargetOptions(c.id)}
                        </select>
                        <button type="button" class="btn-delete-cat" title="Delete">&#128465;</button>
                    </td>
                </tr>
            `
        )
        .join("");
}

async function saveCategoryField(row, fields) {
    const id = parseInt(row.dataset.id, 10);
    try {
        const res = await apiFetch(`/api/categories/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(fields),
        });
        if (!res.ok) {
            showToast("Failed to update category", "error");
            return false;
        }
        showToast("Saved", "success");
        return true;
    } catch (err) {
        showToast("Failed to update category", "error");
        return false;
    }
}

async function deleteCategory(row) {
    const id = parseInt(row.dataset.id, 10);
    const name = categories.find((c) => c.id === id)?.name || "this category";
    if (!confirm(`Delete "${name}"? Its transactions will become uncategorized again.`)) return;

    try {
        const res = await apiFetch(`/api/categories/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Category deleted", "success");
            await loadCategories();
        } else {
            showToast("Failed to delete category", "error");
        }
    } catch (err) {
        showToast("Failed to delete category", "error");
    }
}

async function mergeCategory(row, targetName) {
    const id = parseInt(row.dataset.id, 10);
    const source = categories.find((c) => c.id === id)?.name || "this category";
    if (!confirm(`Merge "${source}" into "${targetName}"? All of its transactions will move to "${targetName}".`)) {
        return;
    }
    const ok = await saveCategoryField(row, { name: targetName });
    if (ok) await loadCategories();
}

function initCategoriesTable() {
    const tbody = document.getElementById("categories-tbody");

    tbody.addEventListener("change", async (e) => {
        const row = e.target.closest("tr");
        if (!row) return;

        if (e.target.classList.contains("cat-kind-select")) {
            await saveCategoryField(row, { kind: e.target.value || null });
            await loadCategories();
        } else if (e.target.classList.contains("cat-merge-select")) {
            const targetName = e.target.value;
            if (targetName) await mergeCategory(row, targetName);
            else e.target.value = "";
        }
    });

    tbody.addEventListener("blur", async (e) => {
        const row = e.target.closest("tr");
        if (!row) return;

        if (e.target.classList.contains("cat-name-input")) {
            const id = parseInt(row.dataset.id, 10);
            const current = categories.find((c) => c.id === id);
            const newName = e.target.value.trim().toUpperCase();
            if (!newName || newName === current.name) {
                e.target.value = current.name;
                return;
            }
            const willMerge = categories.some((c) => c.id !== id && c.name === newName);
            if (willMerge && !confirm(`"${newName}" already exists — merge into it?`)) {
                e.target.value = current.name;
                return;
            }
            await saveCategoryField(row, { name: newName });
            await loadCategories();
        } else if (e.target.classList.contains("cat-budget-input")) {
            const id = parseInt(row.dataset.id, 10);
            const current = categories.find((c) => c.id === id);
            const raw = e.target.value.trim();
            const budget = raw === "" ? null : parseFloat(raw);
            if (budget === current.budget) return;
            await saveCategoryField(row, { budget });
            await loadCategories();
        }
    }, true);

    tbody.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && (e.target.classList.contains("cat-name-input") || e.target.classList.contains("cat-budget-input"))) {
            e.preventDefault();
            e.target.blur();
        }
    });

    tbody.addEventListener("click", (e) => {
        const btn = e.target.closest(".btn-delete-cat");
        if (btn) deleteCategory(btn.closest("tr"));
    });
}

async function addCategory() {
    const nameInput = document.getElementById("new-category-name");
    const kindSelect = document.getElementById("new-category-kind");
    const name = nameInput.value.trim().toUpperCase();
    if (!name) return;

    const btn = document.getElementById("add-category-btn");
    setButtonLoading(btn, true);
    try {
        const res = await apiFetch("/api/categories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, kind: kindSelect.value || null }),
        });
        if (res.ok) {
            nameInput.value = "";
            kindSelect.value = "";
            showToast("Category added", "success");
            await loadCategories();
        } else {
            showToast("Failed to add category", "error");
        }
    } catch (err) {
        showToast("Failed to add category", "error");
    } finally {
        setButtonLoading(btn, false);
    }
}

// ---------------------------------------------------------------------------
// Savings goal (2.4)
// ---------------------------------------------------------------------------
async function loadSavingsGoal() {
    const input = document.getElementById("savings-goal-input");
    try {
        const settings = await fetchJSON("/api/settings");
        input.value = settings.savings_goal != null ? settings.savings_goal : "";
    } catch (err) {
        showToast("Failed to load savings goal", "error");
    }
}

async function saveSavingsGoal() {
    const input = document.getElementById("savings-goal-input");
    const raw = input.value.trim();
    const value = raw === "" ? null : parseFloat(raw);
    if (raw !== "" && (isNaN(value) || value < 0)) {
        showToast("Goal must be a non-negative number", "error");
        return;
    }

    const btn = document.getElementById("save-goal-btn");
    setButtonLoading(btn, true);
    try {
        const res = await apiFetch("/api/settings", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ savings_goal: value }),
        });
        if (res.ok) showToast("Savings goal saved", "success");
        else showToast("Failed to save goal", "error");
    } catch (err) {
        showToast("Failed to save goal", "error");
    } finally {
        setButtonLoading(btn, false);
    }
}

// ---------------------------------------------------------------------------
// Ignored transfer rules (5.3)
// ---------------------------------------------------------------------------
async function loadIgnoredTransfers() {
    const tbody = document.getElementById("ignored-transfers-tbody");
    tbody.innerHTML = `<tr><td colspan="3" class="no-data">Loading…</td></tr>`;
    try {
        ignoredTransfers = await fetchJSON("/api/ignored-transfers");
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" class="no-data">Failed to load rules</td></tr>`;
        return;
    }
    renderIgnoredTransfers();
}

function renderIgnoredTransfers() {
    const tbody = document.getElementById("ignored-transfers-tbody");
    if (ignoredTransfers.length === 0) {
        tbody.innerHTML = `<tr><td colspan="3" class="no-data">No rules configured</td></tr>`;
        return;
    }
    tbody.innerHTML = ignoredTransfers
        .map(
            (r) => `
                <tr data-id="${r.id}">
                    <td>${escapeHTML(r.account_last4)}</td>
                    <td>${escapeHTML(r.bank)}</td>
                    <td class="col-actions"><button type="button" class="btn-delete-cat" title="Delete">&#128465;</button></td>
                </tr>
            `
        )
        .join("");
}

async function addIgnoredTransfer() {
    const accountInput = document.getElementById("new-rule-account");
    const bankInput = document.getElementById("new-rule-bank");
    const account = accountInput.value.trim();
    const bank = bankInput.value.trim();
    if (!account || !bank) return;

    const btn = document.getElementById("add-rule-btn");
    setButtonLoading(btn, true);
    try {
        const res = await apiFetch("/api/ignored-transfers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ account_last4: account, bank }),
        });
        if (res.ok) {
            accountInput.value = "";
            bankInput.value = "";
            showToast("Rule added", "success");
            await loadIgnoredTransfers();
        } else {
            showToast("Failed to add rule", "error");
        }
    } catch (err) {
        showToast("Failed to add rule", "error");
    } finally {
        setButtonLoading(btn, false);
    }
}

async function deleteIgnoredTransfer(row) {
    const id = parseInt(row.dataset.id, 10);
    if (!confirm("Delete this rule? Matching transfers will be imported again going forward.")) return;

    try {
        const res = await apiFetch(`/api/ignored-transfers/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Rule deleted", "success");
            await loadIgnoredTransfers();
        } else {
            showToast("Failed to delete rule", "error");
        }
    } catch (err) {
        showToast("Failed to delete rule", "error");
    }
}

function initIgnoredTransfersTable() {
    document.getElementById("ignored-transfers-tbody").addEventListener("click", (e) => {
        const btn = e.target.closest(".btn-delete-cat");
        if (btn) deleteIgnoredTransfer(btn.closest("tr"));
    });
}

// ---------------------------------------------------------------------------
// Event handlers & initialization
// ---------------------------------------------------------------------------
function initEventHandlers() {
    initCategoriesTable();
    initIgnoredTransfersTable();

    document.getElementById("add-category-btn").addEventListener("click", addCategory);
    document.getElementById("new-category-name").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); addCategory(); }
    });

    document.getElementById("save-goal-btn").addEventListener("click", saveSavingsGoal);
    document.getElementById("savings-goal-input").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); saveSavingsGoal(); }
    });

    document.getElementById("add-rule-btn").addEventListener("click", addIgnoredTransfer);
    document.getElementById("new-rule-bank").addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); addIgnoredTransfer(); }
    });
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
if (requireAuth()) {
    initEventHandlers();
    loadCategories();
    loadSavingsGoal();
    loadIgnoredTransfers();
}
