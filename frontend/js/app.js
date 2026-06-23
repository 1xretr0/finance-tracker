let savingsChart = null;
let incomeChart = null;
let expenseChart = null;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const CHART_COLORS = [
    "#4ade80", "#60a5fa", "#f472b6", "#facc15", "#a78bfa",
    "#fb923c", "#34d399", "#f87171", "#38bdf8", "#c084fc",
];

const EXPENSE_COLORS = [
    "#f87171", "#fb923c", "#f472b6", "#ef4444", "#fca5a5",
    "#e11d48", "#fb7185", "#dc2626", "#f43f5e", "#b91c1c",
];

async function loadSavingsChart() {
    const year = new Date().getFullYear();
    document.getElementById("savings-year").textContent = year;

    const data = await fetchJSON(`/api/savings?year=${year}`);

    const savingsByMonth = {};
    data.forEach((row) => {
        savingsByMonth[row.month] = row.savings;
    });

    const values = MONTHS.map((_, i) => {
        const key = `${year}-${String(i + 1).padStart(2, "0")}`;
        return savingsByMonth[key] ?? null;
    });

    const ctx = document.getElementById("savings-chart").getContext("2d");
    if (savingsChart) savingsChart.destroy();

    savingsChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: MONTHS,
            datasets: [
                {
                    label: "Savings (MXN)",
                    data: values,
                    borderColor: "#4ade80",
                    backgroundColor: "rgba(74, 222, 128, 0.1)",
                    fill: true,
                    tension: 0.3,
                    pointBackgroundColor: "#4ade80",
                    pointRadius: 5,
                    spanGaps: false,
                },
            ],
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${formatAmount(ctx.parsed.y)} MXN`,
                    },
                },
            },
            scales: {
                x: {
                    ticks: { color: "#888" },
                    grid: { color: "#2a2a2a" },
                },
                y: {
                    ticks: {
                        color: "#888",
                        callback: (v) => `$${v.toLocaleString()}`,
                    },
                    grid: { color: "#2a2a2a" },
                },
            },
        },
    });
}

async function loadBreakdownCharts(month) {
    const data = await fetchJSON(`/api/breakdown?month=${month}`);

    const incomeCtx = document.getElementById("income-chart").getContext("2d");
    if (incomeChart) incomeChart.destroy();

    const incomeTotal = data.income.reduce((sum, r) => sum + r.total, 0);
    document.getElementById("income-total").textContent = formatAmount(incomeTotal);
    document.getElementById("income-total").className = "breakdown-total income";

    incomeChart = new Chart(incomeCtx, {
        type: "doughnut",
        data: {
            labels: data.income.map((r) => r.category),
            datasets: [{
                data: data.income.map((r) => r.total),
                backgroundColor: CHART_COLORS,
                borderColor: "#1e1e1e",
                borderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            cutout: "65%",
            plugins: {
                legend: {
                    position: "bottom",
                    labels: { color: "#888", boxWidth: 12, padding: 12 },
                },
            },
        },
    });

    const expenseCtx = document.getElementById("expense-chart").getContext("2d");
    if (expenseChart) expenseChart.destroy();

    const expenseTotal = data.expenses.reduce((sum, r) => sum + r.total, 0);
    document.getElementById("expense-total").textContent = formatAmount(expenseTotal);
    document.getElementById("expense-total").className = "breakdown-total expense";

    expenseChart = new Chart(expenseCtx, {
        type: "doughnut",
        data: {
            labels: data.expenses.map((r) => r.category),
            datasets: [{
                data: data.expenses.map((r) => r.total),
                backgroundColor: EXPENSE_COLORS,
                borderColor: "#1e1e1e",
                borderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            cutout: "65%",
            plugins: {
                legend: {
                    position: "bottom",
                    labels: { color: "#888", boxWidth: 12, padding: 12 },
                },
            },
        },
    });
}

function shiftMonth(monthStr, delta) {
    const [year, month] = monthStr.split("-").map(Number);
    const d = new Date(year, month - 1 + delta, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function initBreakdownFilter() {
    const input = document.getElementById("breakdown-month");
    const prevBtn = document.getElementById("month-prev");
    const nextBtn = document.getElementById("month-next");
    const now = new Date();
    const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    input.value = currentMonth;
    loadBreakdownCharts(currentMonth);

    input.addEventListener("change", () => {
        if (input.value) loadBreakdownCharts(input.value);
    });

    prevBtn.addEventListener("click", () => {
        input.value = shiftMonth(input.value, -1);
        loadBreakdownCharts(input.value);
    });

    nextBtn.addEventListener("click", () => {
        input.value = shiftMonth(input.value, 1);
        loadBreakdownCharts(input.value);
    });
}

let savingsData = [];

async function loadSavingsOverview(quarter) {
    const year = new Date().getFullYear();

    if (savingsData.length === 0) {
        savingsData = await fetchJSON(`/api/savings?year=${year}`);
    }

    const monthIndices = QUARTER_MONTHS[quarter];
    const container = document.getElementById("overview-grid");

    container.innerHTML = monthIndices
        .map((i) => {
            const key = `${year}-${String(i + 1).padStart(2, "0")}`;
            const row = savingsData.find((r) => r.month === key);
            const income = row ? row.income : 0;
            const expenses = row ? row.purchases + row.outgoing : 0;
            const balance = income - expenses;
            const balanceClass = balance < 0 ? "negative" : "";

            return `
                <div class="month-card">
                    <div class="month-name">${escapeHTML(MONTHS[i])} ${year}</div>
                    <div class="month-row income">
                        <span class="label">Income</span>
                        <span class="value">${formatAmount(income)}</span>
                    </div>
                    <div class="month-row expenses">
                        <span class="label">Expenses</span>
                        <span class="value">${formatAmount(expenses)}</span>
                    </div>
                    <hr class="divider">
                    <div class="month-row balance">
                        <span class="label">Balance</span>
                        <span class="value ${balanceClass}">${formatAmount(balance)}</span>
                    </div>
                </div>
            `;
        })
        .join("");
}

function initQuarterFilter() {
    const buttons = document.querySelectorAll(".overview-section .quarter-btn");
    const currentQuarter = getCurrentQuarter();

    buttons.forEach((btn) => {
        const q = parseInt(btn.dataset.quarter);
        btn.classList.toggle("active", q === currentQuarter);

        btn.addEventListener("click", () => {
            buttons.forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            loadSavingsOverview(q);
        });
    });

    loadSavingsOverview(currentQuarter);
}

loadSavingsChart().then(() => {
    initBreakdownFilter();
    initQuarterFilter();
});
