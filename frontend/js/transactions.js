function getQuarterDateRange(quarter) {
    const year = new Date().getFullYear();
    const startMonth = (quarter - 1) * 3 + 1;
    const endMonth = startMonth + 2;
    const lastDay = new Date(year, endMonth, 0).getDate();
    return {
        start: `${year}-${String(startMonth).padStart(2, "0")}-01`,
        end: `${year}-${String(endMonth).padStart(2, "0")}-${lastDay}`,
    };
}

async function loadTransactions(quarter) {
    const { start, end } = getQuarterDateRange(quarter);
    const transactions = await fetchJSON(`/api/transactions?start_date=${start}&end_date=${end}`);

    const income = transactions.filter((tx) => tx.type === TX_TYPE_TRANSFER);
    const expenses = transactions.filter((tx) => tx.type === TX_TYPE_PURCHASE || tx.type === TX_TYPE_OUTGOING_TRANSFER);

    renderTable("income-table", income, "income");
    renderTable("expense-table", expenses, "expense");
}

function renderTable(tableId, rows, type) {
    const tbody = document.querySelector(`#${tableId} tbody`);

    if (rows.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="no-data">No transactions</td></tr>`;
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
                <tr>
                    <td>${escapeHTML(date)}</td>
                    <td class="${amountClass}">${amount}</td>
                    <td>${escapeHTML(description)}</td>
                    <td>${category}</td>
                </tr>
            `;
        })
        .join("");
}

function initQuarterFilter() {
    const buttons = document.querySelectorAll(".quarter-btn");
    const currentQuarter = getCurrentQuarter();

    buttons.forEach((btn) => {
        const q = parseInt(btn.dataset.quarter);
        btn.classList.toggle("active", q === currentQuarter);

        btn.addEventListener("click", () => {
            buttons.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            loadTransactions(q);
        });
    });

    loadTransactions(currentQuarter);
}

initQuarterFilter();
