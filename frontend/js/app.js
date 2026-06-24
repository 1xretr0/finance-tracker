let savingsChart = null;
let incomeChart = null;
let expenseChart = null;

const CHART_COLORS = [
    "#4ade80", "#60a5fa", "#f472b6", "#facc15", "#a78bfa",
    "#fb923c", "#34d399", "#f87171", "#38bdf8", "#c084fc",
];

const EXPENSE_COLORS = [
    "#f87171", "#fb923c", "#f472b6", "#ef4444", "#fca5a5",
    "#e11d48", "#fb7185", "#dc2626", "#f43f5e", "#b91c1c",
];

let savingsYear = new Date().getFullYear();

async function loadSavingsChart() {
    document.getElementById("savings-year").textContent = savingsYear;

    let data;
    try {
        data = await fetchJSON(`/api/savings?year=${savingsYear}`);
    } catch (err) {
        showToast("Failed to load savings data", "error");
        return;
    }

    const savingsByMonth = {};
    data.forEach((row) => {
        savingsByMonth[row.month] = row.savings;
    });

    const values = MONTHS.map((_, i) => {
        const key = `${savingsYear}-${String(i + 1).padStart(2, "0")}`;
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
                    ticks: { color: "#9a9a9a" },
                    grid: { color: "#2a2a2a" },
                },
                y: {
                    ticks: {
                        color: "#9a9a9a",
                        callback: (v) => `$${v.toLocaleString()}`,
                    },
                    grid: { color: "#2a2a2a" },
                },
            },
        },
    });
}

async function loadBreakdownCharts(month) {
    let data;
    try {
        data = await fetchJSON(`/api/breakdown?month=${month}`);
    } catch (err) {
        showToast("Failed to load breakdown data", "error");
        return;
    }

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
                    labels: { color: "#9a9a9a", boxWidth: 12, padding: 12 },
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
                    labels: { color: "#9a9a9a", boxWidth: 12, padding: 12 },
                },
            },
        },
    });
}

function initBreakdownMonth() {
    const input = document.getElementById("breakdown-month");
    input.value = getCurrentMonthStr();
    loadBreakdownCharts(input.value);
}

let savingsData = [];

async function loadSavingsOverview(quarter) {
    const year = savingsYear;

    if (savingsData.length === 0) {
        try {
            savingsData = await fetchJSON(`/api/savings?year=${year}`);
        } catch (err) {
            showToast("Failed to load overview data", "error");
            return;
        }
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
    });

    loadSavingsOverview(currentQuarter);
}

function getActiveQuarter() {
    const active = document.querySelector(".quarter-btn.active");
    return active ? parseInt(active.dataset.quarter) : getCurrentQuarter();
}

function initDelegation() {
    document.addEventListener("click", (e) => {
        const yearPrev = e.target.closest("#year-prev");
        if (yearPrev) {
            savingsYear--;
            savingsData = [];
            loadSavingsChart();
            loadSavingsOverview(getActiveQuarter());
            return;
        }

        const yearNext = e.target.closest("#year-next");
        if (yearNext) {
            savingsYear++;
            savingsData = [];
            loadSavingsChart();
            loadSavingsOverview(getActiveQuarter());
            return;
        }

        const quarterBtn = e.target.closest(".quarter-btn");
        if (quarterBtn) {
            document.querySelectorAll(".quarter-btn").forEach((b) => b.classList.remove("active"));
            quarterBtn.classList.add("active");
            loadSavingsOverview(parseInt(quarterBtn.dataset.quarter));
            return;
        }

        const monthPrev = e.target.closest("#month-prev");
        if (monthPrev) {
            const input = document.getElementById("breakdown-month");
            input.value = shiftMonth(input.value, -1);
            loadBreakdownCharts(input.value);
            return;
        }

        const monthNext = e.target.closest("#month-next");
        if (monthNext) {
            const input = document.getElementById("breakdown-month");
            input.value = shiftMonth(input.value, 1);
            loadBreakdownCharts(input.value);
            return;
        }
    });

    document.getElementById("breakdown-month").addEventListener("change", (e) => {
        if (e.target.value) loadBreakdownCharts(e.target.value);
    });
}

loadSavingsChart().then(() => {
    initBreakdownMonth();
    initQuarterFilter();
    initDelegation();
});
