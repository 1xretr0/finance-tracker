const TX_TYPE_PURCHASE = "purchase";
const TX_TYPE_TRANSFER = "transfer";
const TX_TYPE_OUTGOING_TRANSFER = "outgoing_transfer";

const QUARTER_MONTHS = {
    1: [0, 1, 2],
    2: [3, 4, 5],
    3: [6, 7, 8],
    4: [9, 10, 11],
};

function escapeHTML(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) {
        throw new Error(`Request failed: ${res.status} ${res.statusText}`);
    }
    return res.json();
}

function getCurrentQuarter() {
    return Math.floor(new Date().getMonth() / 3) + 1;
}

function formatAmount(amount) {
    return `$${amount.toLocaleString("en", { minimumFractionDigits: 2 })}`;
}
