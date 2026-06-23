let transactions = [];
let currentIndex = 0;
let categories = [];

async function init() {
    transactions = await fetchJSON("/api/uncategorized");
    categories = await fetchJSON("/api/categories");

    transactions.sort((a, b) => a.date.localeCompare(b.date));

    populateCategoryList();
    updateCounter();
    showCurrent();
}

function populateCategoryList() {
    const datalist = document.getElementById("category-list");
    datalist.innerHTML = categories.map((c) => `<option value="${escapeHTML(c)}">`).join("");
}

function updateCounter() {
    const remaining = transactions.length - currentIndex;
    document.getElementById("counter").textContent = `${remaining} remaining`;
}

function showCurrent() {
    const container = document.getElementById("current-transaction");
    const controls = document.getElementById("controls");
    const input = document.getElementById("category-input");

    if (currentIndex >= transactions.length) {
        container.innerHTML = `<div class="empty-state">All transactions are categorized!</div>`;
        controls.style.display = "none";
        return;
    }

    controls.style.display = "flex";
    input.value = "";

    const tx = transactions[currentIndex];
    const description = tx.merchant || tx.dest_bank || tx.sender_bank || tx.concept || "-";
    const sign = tx.type === TX_TYPE_TRANSFER ? "+" : "-";

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

async function saveCategory() {
    const input = document.getElementById("category-input");
    const categoryName = input.value.trim().toUpperCase();
    if (!categoryName) return;

    const tx = transactions[currentIndex];

    if (!categories.some((c) => c.toUpperCase() === categoryName)) {
        await fetch("/api/categories", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: categoryName }),
        });
        categories.push(categoryName);
        categories.sort();
        populateCategoryList();
    }

    await fetch("/api/transactions/categorize", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify([{ id: tx.id, category: categoryName }]),
    });

    currentIndex++;
    updateCounter();
    showCurrent();
}

function skip() {
    currentIndex++;
    updateCounter();
    showCurrent();
}

document.getElementById("save-btn").addEventListener("click", saveCategory);
document.getElementById("skip-btn").addEventListener("click", skip);

document.getElementById("category-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        e.preventDefault();
        saveCategory();
    }
});

init();
