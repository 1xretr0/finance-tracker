// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
let cashflowChart = null;
let savingsChart = null;
let incomeChart = null;
let expenseChart = null;
let selectedMonth = getCurrentMonthStr();
let savingsGoal = null; // number or null, from /api/settings

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------
function monthLabel(monthStr) {
    const [y, m] = monthStr.split("-").map(Number);
    return `${MONTHS[m - 1]} ${y}`;
}

function pctDelta(cur, prev) {
    if (!prev) return null;
    return ((cur - prev) / Math.abs(prev)) * 100;
}

function formatPct(p) {
    return `${p >= 0 ? "+" : ""}${p.toFixed(1)}%`;
}

// `invert` flips which sign counts as "good" — used for expenses, where a
// smaller number is the improvement.
function deltaClass(p, invert = false) {
    if (p == null) return "";
    const good = invert ? p <= 0 : p >= 0;
    return good ? "positive" : "negative";
}

// ---------------------------------------------------------------------------
// KPI row (1.3, 2.3, 2.4)
// ---------------------------------------------------------------------------
async function loadKPIs(month) {
    const container = document.getElementById("kpi-row");
    container.innerHTML = `<div class="section-loading">Loading…</div>`;

    const months = [shiftMonth(month, -3), shiftMonth(month, -2), shiftMonth(month, -1), month];
    const start = getMonthDateRange(months[0]).start;
    const end = getMonthDateRange(month).end;

    let rows;
    try {
        rows = await fetchJSON(`/api/monthly?start_date=${start}&end_date=${end}`);
    } catch (err) {
        container.innerHTML = `<div class="section-loading">Failed to load KPIs</div>`;
        return;
    }

    const byMonth = {};
    months.forEach((m) => (byMonth[m] = { income: 0, expenses: 0 }));
    rows.forEach((r) => {
        if (!(r.month in byMonth)) return;
        if (r.type === TX_TYPE_TRANSFER) byMonth[r.month].income += r.total;
        else byMonth[r.month].expenses += r.total;
    });
    months.forEach((m) => (byMonth[m].net = byMonth[m].income - byMonth[m].expenses));

    const cur = byMonth[month];
    const prev = byMonth[months[2]];
    const threeMoAvgNet = (byMonth[months[0]].net + byMonth[months[1]].net + byMonth[months[2]].net) / 3;

    const incomeDelta = pctDelta(cur.income, prev.income);
    const expenseDelta = pctDelta(cur.expenses, prev.expenses);
    const netDeltaLastMonth = pctDelta(cur.net, prev.net);
    const netDeltaAvg = pctDelta(cur.net, threeMoAvgNet);
    const savingsRate = cur.income > 0 ? (cur.net / cur.income) * 100 : 0;

    let projectedHTML = "";
    if (month === getCurrentMonthStr()) {
        const now = new Date();
        const daysElapsed = now.getDate();
        const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
        const projected = daysElapsed > 0 ? (cur.expenses / daysElapsed) * daysInMonth : cur.expenses;
        projectedHTML = `<div class="kpi-sub">Projected: ${formatAmount(projected)}</div>`;
    }

    let goalHTML = "";
    if (savingsGoal != null && savingsGoal > 0) {
        const goalPct = (cur.net / savingsGoal) * 100;
        goalHTML = `<div class="kpi-sub">${goalPct.toFixed(0)}% of ${formatAmount(savingsGoal)} goal</div>`;
    }

    container.innerHTML = `
        <div class="kpi-tile">
            <div class="kpi-label">Income</div>
            <div class="kpi-value income">${formatAmount(cur.income)}</div>
            ${incomeDelta != null ? `<div class="kpi-sub ${deltaClass(incomeDelta)}">${formatPct(incomeDelta)} vs last month</div>` : ""}
        </div>
        <div class="kpi-tile">
            <div class="kpi-label">Expenses</div>
            <div class="kpi-value expense">${formatAmount(cur.expenses)}</div>
            ${expenseDelta != null ? `<div class="kpi-sub ${deltaClass(expenseDelta, true)}">${formatPct(expenseDelta)} vs last month</div>` : ""}
            ${projectedHTML}
        </div>
        <div class="kpi-tile">
            <div class="kpi-label">Net</div>
            <div class="kpi-value ${cur.net >= 0 ? "income" : "expense"}">${formatAmount(cur.net)}</div>
            ${netDeltaLastMonth != null ? `<div class="kpi-sub ${deltaClass(netDeltaLastMonth)}">${formatPct(netDeltaLastMonth)} vs last month</div>` : ""}
            ${netDeltaAvg != null ? `<div class="kpi-sub ${deltaClass(netDeltaAvg)}">${formatPct(netDeltaAvg)} vs 3-mo avg</div>` : ""}
            ${goalHTML}
        </div>
        <div class="kpi-tile">
            <div class="kpi-label">Savings Rate</div>
            <div class="kpi-value ${savingsRate >= 0 ? "income" : "expense"}">${savingsRate.toFixed(1)}%</div>
        </div>
    `;
}

// ---------------------------------------------------------------------------
// Cash-flow chart: grouped income/expense bars + net line + goal line (1.1, 1.2)
// ---------------------------------------------------------------------------
async function loadCashflowChart(month) {
    const year = parseInt(month.split("-")[0], 10);

    let monthly, yearSavings;
    try {
        [monthly, yearSavings] = await Promise.all([
            fetchJSON(`/api/monthly?start_date=${year}-01-01&end_date=${year}-12-31`),
            fetchJSON(`/api/savings?year=${year}`),
        ]);
    } catch (err) {
        showToast("Failed to load cash flow data", "error");
        return;
    }

    const incomeByMonth = {};
    const expenseByMonth = {};
    monthly.forEach((r) => {
        const bucket = r.type === TX_TYPE_TRANSFER ? incomeByMonth : expenseByMonth;
        bucket[r.month] = (bucket[r.month] || 0) + r.total;
    });

    const netByMonth = {};
    yearSavings.forEach((r) => (netByMonth[r.month] = r.savings));

    const monthKeys = MONTHS.map((_, i) => `${year}-${String(i + 1).padStart(2, "0")}`);
    const incomeData = monthKeys.map((k) => incomeByMonth[k] ?? 0);
    const expenseData = monthKeys.map((k) => expenseByMonth[k] ?? 0);
    const netData = monthKeys.map((k) => (k in netByMonth ? netByMonth[k] : null));

    const datasets = [
        { type: "bar", label: "Income", data: incomeData, backgroundColor: "rgba(74, 222, 128, 0.7)" },
        { type: "bar", label: "Expenses", data: expenseData, backgroundColor: "rgba(248, 113, 113, 0.7)" },
        {
            type: "line",
            label: "Net",
            data: netData,
            borderColor: "#facc15",
            backgroundColor: "transparent",
            tension: 0.3,
            spanGaps: false,
        },
    ];

    if (savingsGoal != null && savingsGoal > 0) {
        datasets.push({
            type: "line",
            label: "Goal",
            data: monthKeys.map(() => savingsGoal),
            borderColor: "#9a9a9a",
            borderDash: [6, 4],
            pointRadius: 0,
            fill: false,
        });
    }

    const ctx = document.getElementById("cashflow-chart").getContext("2d");
    if (cashflowChart) cashflowChart.destroy();

    cashflowChart = new Chart(ctx, {
        type: "bar",
        data: { labels: MONTHS, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            onClick: (evt, elements) => {
                if (!elements.length) return;
                setSelectedMonth(monthKeys[elements[0].index]);
            },
            plugins: {
                legend: { labels: { color: "#9a9a9a" } },
                tooltip: {
                    callbacks: {
                        label: (ctx) => `${ctx.dataset.label}: ${formatAmount(ctx.parsed.y)} MXN`,
                    },
                },
            },
            scales: {
                x: { ticks: { color: "#9a9a9a" }, grid: { color: "#2a2a2a" } },
                y: {
                    ticks: { color: "#9a9a9a", callback: (v) => `$${v.toLocaleString()}` },
                    grid: { color: "#2a2a2a" },
                },
            },
        },
    });
}

// ---------------------------------------------------------------------------
// Net balance (cumulative) chart — formerly "Monthly Savings" (1.2)
// ---------------------------------------------------------------------------
async function loadSavingsChart(year) {
    let data;
    try {
        data = await fetchJSON(`/api/savings?year=${year}`);
    } catch (err) {
        showToast("Failed to load savings data", "error");
        return;
    }

    const savingsByMonth = {};
    data.forEach((row) => {
        savingsByMonth[row.month] = row.total_savings;
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
                    label: "Net balance (MXN)",
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
            maintainAspectRatio: false,
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

// ---------------------------------------------------------------------------
// Breakdown charts (income/expense doughnuts) — with drill-down (1.5, 6.4)
// ---------------------------------------------------------------------------
// Chart.js centers the doughnut arc on chart.chartArea, which shrinks to make
// room for the bottom legend — that center drifts from the wrapper's CSS
// center as the legend's relative share of the box grows on narrow screens.
// Re-anchor the overlay to the real chartArea center on every layout/resize.
function centerTotalOnChartArea(totalElementId) {
    return {
        id: `center-total-${totalElementId}`,
        afterLayout(chart) {
            const totalEl = document.getElementById(totalElementId);
            if (!totalEl) return;
            const { left, right, top, bottom } = chart.chartArea;
            totalEl.style.left = `${(left + right) / 2}px`;
            totalEl.style.top = `${(top + bottom) / 2}px`;
        },
    };
}

function goToTransactions(month, params) {
    const url = new URL("/transactions", window.location.origin);
    url.searchParams.set("month", month);
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    window.location.href = url.toString();
}

async function loadBreakdownCharts(month) {
    let data;
    try {
        data = await fetchJSON(`/api/breakdown?month=${month}`);
    } catch (err) {
        showToast("Failed to load breakdown data", "error");
        return;
    }

    const emptyEl = document.getElementById("breakdown-empty");
    const chartsEl = document.getElementById("breakdown-charts");

    if (data.income.length === 0 && data.expenses.length === 0) {
        if (incomeChart) { incomeChart.destroy(); incomeChart = null; }
        if (expenseChart) { expenseChart.destroy(); expenseChart = null; }
        chartsEl.hidden = true;
        emptyEl.hidden = false;
        emptyEl.innerHTML = `
            <p>No transactions in ${escapeHTML(monthLabel(month))}.</p>
            <button type="button" class="btn-empty-add" id="breakdown-add-btn">Add one</button>
        `;
        document.getElementById("breakdown-add-btn").addEventListener("click", () => openTxTypePicker());
        return;
    }

    emptyEl.hidden = true;
    chartsEl.hidden = false;

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
        plugins: [centerTotalOnChartArea("income-total")],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "65%",
            onClick: (evt, elements) => {
                if (!elements.length) return;
                goToTransactions(month, { category: data.income[elements[0].index].category });
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => ` ${ctx.label}: ${formatAmount(ctx.parsed)} MXN`,
                    },
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
        plugins: [centerTotalOnChartArea("expense-total")],
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "65%",
            onClick: (evt, elements) => {
                if (!elements.length) return;
                goToTransactions(month, { category: data.expenses[elements[0].index].category });
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: (ctx) => ` ${ctx.label}: ${formatAmount(ctx.parsed)} MXN`,
                    },
                },
            },
        },
    });
}

// ---------------------------------------------------------------------------
// Budgets (2.1)
// ---------------------------------------------------------------------------
async function loadBudgets(month) {
    const container = document.getElementById("budgets-list");
    container.innerHTML = `<div class="section-loading">Loading…</div>`;

    let cats, breakdown;
    try {
        [cats, breakdown] = await Promise.all([
            fetchJSON("/api/categories?detailed=true"),
            fetchJSON(`/api/breakdown?month=${month}`),
        ]);
    } catch (err) {
        container.innerHTML = `<div class="section-loading">Failed to load budgets</div>`;
        return;
    }

    const budgeted = cats.filter((c) => c.budget != null && c.budget > 0);
    if (budgeted.length === 0) {
        container.innerHTML = `<div class="section-empty">No budgets set yet. <a href="/settings">Set one up</a>.</div>`;
        return;
    }

    const spentByCategory = {};
    breakdown.expenses.forEach((r) => (spentByCategory[r.category] = r.total));

    container.innerHTML = budgeted
        .map((c) => {
            const spent = spentByCategory[c.name] || 0;
            const pct = (spent / c.budget) * 100;
            const barClass = pct > 100 ? "over" : pct >= 80 ? "warn" : "";
            const href = `/transactions?month=${month}&category=${encodeURIComponent(c.name)}`;
            return `
                <a class="budget-row" href="${href}">
                    <div class="budget-row-header">
                        <span class="budget-name">${escapeHTML(c.name)}</span>
                        <span class="budget-amounts">${formatAmount(spent)} / ${formatAmount(c.budget)}</span>
                    </div>
                    <div class="budget-bar-track">
                        <div class="budget-bar-fill ${barClass}" style="width:${Math.min(pct, 100)}%"></div>
                    </div>
                </a>
            `;
        })
        .join("");
}

// ---------------------------------------------------------------------------
// Top merchants & recurring expenses (1.1, 2.2)
// ---------------------------------------------------------------------------
async function loadMerchants(month) {
    const container = document.getElementById("merchants-list");
    container.innerHTML = `<div class="section-loading">Loading…</div>`;

    const { start, end } = getMonthDateRange(month);
    let data;
    try {
        data = await fetchJSON(`/api/merchants?start_date=${start}&end_date=${end}`);
    } catch (err) {
        container.innerHTML = `<div class="section-loading">Failed to load merchants</div>`;
        return;
    }

    if (data.length === 0) {
        container.innerHTML = `
            <div class="section-empty">
                No expenses in ${escapeHTML(monthLabel(month))} —
                <button type="button" class="btn-empty-add" id="merchants-add-btn">add one</button>
            </div>
        `;
        document.getElementById("merchants-add-btn").addEventListener("click", () => openTxTypePicker());
        return;
    }

    container.innerHTML = data
        .slice(0, 10)
        .map(
            (m) => `
                <a class="list-row" href="/transactions?month=${month}&q=${encodeURIComponent(m.merchant)}">
                    <span class="list-row-name">${escapeHTML(m.merchant)}</span>
                    <span class="list-row-value expense">${formatAmount(m.total)}</span>
                </a>
            `
        )
        .join("");
}

async function loadRecurring(month) {
    const container = document.getElementById("recurring-list");
    const totalEl = document.getElementById("recurring-total");
    container.innerHTML = `<div class="section-loading">Loading…</div>`;
    totalEl.textContent = "";

    let data;
    try {
        data = await fetchJSON(`/api/recurring?month=${month}`);
    } catch (err) {
        container.innerHTML = `<div class="section-loading">Failed to load recurring expenses</div>`;
        return;
    }

    if (data.length === 0) {
        container.innerHTML = `<div class="section-empty">No recurring expenses detected yet.</div>`;
        return;
    }

    const committed = data.reduce((sum, r) => sum + r.typical_amount, 0);
    totalEl.textContent = `${formatAmount(committed)} / month committed`;

    container.innerHTML = data
        .map(
            (r) => `
                <a class="list-row" href="/transactions?month=${month}&q=${encodeURIComponent(r.merchant)}">
                    <span class="list-row-name">${escapeHTML(r.merchant)}</span>
                    <span class="list-row-value expense">${formatAmount(r.typical_amount)}</span>
                </a>
            `
        )
        .join("");
}

// ---------------------------------------------------------------------------
// Quarter + YTD summary (1.7)
// ---------------------------------------------------------------------------
function monthShortLabel(monthStr) {
    const [, m] = monthStr.split("-").map(Number);
    return MONTHS[m - 1];
}

async function loadSummary(month) {
    const [year, mo] = month.split("-").map(Number);
    const quarter = Math.floor((mo - 1) / 3) + 1;
    const quarterMonths = QUARTER_MONTHS[quarter].map((i) => `${year}-${String(i + 1).padStart(2, "0")}`);
    const ytdMonths = Array.from({ length: mo }, (_, i) => `${year}-${String(i + 1).padStart(2, "0")}`);

    let savings, yearBreakdown;
    try {
        [savings, yearBreakdown] = await Promise.all([
            fetchJSON(`/api/savings?year=${year}`),
            fetchJSON(`/api/breakdown?year=${year}`),
        ]);
    } catch (err) {
        showToast("Failed to load summary", "error");
        return;
    }

    const byMonth = {};
    savings.forEach((r) => (byMonth[r.month] = r));

    function summarize(months) {
        const rows = months.map((m) => byMonth[m]).filter(Boolean);
        const totalIncome = rows.reduce((s, r) => s + r.income, 0);
        const totalSaved = rows.reduce((s, r) => s + r.savings, 0);
        const rate = totalIncome > 0 ? (totalSaved / totalIncome) * 100 : 0;
        return { rows, totalSaved, rate };
    }

    const q = summarize(quarterMonths);
    const ytd = summarize(ytdMonths);

    document.getElementById("quarter-summary").innerHTML = `
        <h3>Q${quarter} ${year}</h3>
        <div class="summary-row"><span>Total saved</span><span class="${q.totalSaved >= 0 ? "income" : "expense"}">${formatAmount(q.totalSaved)}</span></div>
        <div class="summary-row"><span>Savings rate</span><span>${q.rate.toFixed(1)}%</span></div>
    `;

    let bestWorstHTML = "";
    if (ytd.rows.length > 0) {
        const best = ytd.rows.reduce((a, b) => (b.savings > a.savings ? b : a));
        const worst = ytd.rows.reduce((a, b) => (b.savings < a.savings ? b : a));
        bestWorstHTML = `
            <div class="summary-row"><span>Best month</span><span class="income">${escapeHTML(monthShortLabel(best.month))} (${formatAmount(best.savings)})</span></div>
            <div class="summary-row"><span>Worst month</span><span class="expense">${escapeHTML(monthShortLabel(worst.month))} (${formatAmount(worst.savings)})</span></div>
        `;
    }

    const biggestCategory = yearBreakdown.expenses[0]?.category;

    document.getElementById("ytd-summary").innerHTML = `
        <h3>Year to date</h3>
        <div class="summary-row"><span>Total saved</span><span class="${ytd.totalSaved >= 0 ? "income" : "expense"}">${formatAmount(ytd.totalSaved)}</span></div>
        <div class="summary-row"><span>Savings rate</span><span>${ytd.rate.toFixed(1)}%</span></div>
        ${bestWorstHTML}
        ${biggestCategory ? `<div class="summary-row"><span>Biggest category</span><span>${escapeHTML(biggestCategory)}</span></div>` : ""}
    `;
}

// ---------------------------------------------------------------------------
// Global month selector (1.6) & bootstrap
// ---------------------------------------------------------------------------
function loadAll(month) {
    document.getElementById("selected-month-label").textContent = monthLabel(month);
    loadKPIs(month);
    loadCashflowChart(month);
    loadSavingsChart(parseInt(month.split("-")[0], 10));
    loadBreakdownCharts(month);
    loadBudgets(month);
    loadMerchants(month);
    loadRecurring(month);
    loadSummary(month);
}

function setSelectedMonth(month) {
    selectedMonth = month;
    document.getElementById("ov-month").value = month;
    const url = new URL(window.location);
    url.searchParams.set("month", month);
    history.replaceState({}, "", url);
    loadAll(month);
}

function initMonthNav() {
    document.getElementById("ov-month-prev").addEventListener("click", () => setSelectedMonth(shiftMonth(selectedMonth, -1)));
    document.getElementById("ov-month-next").addEventListener("click", () => setSelectedMonth(shiftMonth(selectedMonth, 1)));
    document.getElementById("ov-month").addEventListener("change", (e) => {
        if (e.target.value) setSelectedMonth(e.target.value);
    });
}

async function loadSettings() {
    try {
        const settings = await fetchJSON("/api/settings");
        savingsGoal = settings.savings_goal != null ? parseFloat(settings.savings_goal) : null;
    } catch (err) {
        savingsGoal = null;
    }
}

async function initOverview() {
    const params = new URLSearchParams(window.location.search);
    selectedMonth = params.get("month") || getCurrentMonthStr();
    document.getElementById("ov-month").value = selectedMonth;
    await loadSettings();
    loadAll(selectedMonth);
}

// New transactions created elsewhere (e.g. via the shared modal) should
// refresh whatever's currently on screen. onTransactionChanged is the
// generalized hook the modal will call once it also supports editing
// (Phase 4); onTransactionCreated covers today's create-only modal.
window.onTransactionCreated = () => loadAll(selectedMonth);
window.onTransactionChanged = window.onTransactionCreated;

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
if (requireAuth()) {
    initMonthNav();
    initOverview();
}
