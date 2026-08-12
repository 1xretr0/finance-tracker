// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------
async function submitLogin(e) {
    e.preventDefault();

    const username = document.getElementById("login-username").value.trim();
    const password = document.getElementById("login-password").value;
    const submitBtn = document.querySelector(".btn-login-submit");

    setButtonLoading(submitBtn, true);

    try {
        // No token exists yet, so this hits the API directly rather than
        // going through apiFetch().
        const res = await fetch("/api/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password }),
        });

        if (res.ok) {
            const data = await res.json();
            localStorage.setItem(API_TOKEN_STORAGE_KEY, data.token);
            localStorage.setItem(API_USER_STORAGE_KEY, data.username);

            const params = new URLSearchParams(window.location.search);
            window.location.href = params.get("next") || "/";
        } else {
            showToast("Invalid credentials", "error");
        }
    } catch (err) {
        showToast("Login failed", "error");
    } finally {
        setButtonLoading(submitBtn, false);
    }
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------
document.getElementById("login-form").addEventListener("submit", submitLogin);
