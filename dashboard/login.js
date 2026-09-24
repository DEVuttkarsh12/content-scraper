const form = document.getElementById("loginForm");
const submit = document.getElementById("submit");
const error = document.getElementById("loginError");
const password = document.getElementById("password");
document.getElementById("showPassword").addEventListener("click", (event) => {
  const visible = password.type === "text";
  password.type = visible ? "password" : "text";
  event.currentTarget.textContent = visible ? "Show" : "Hide";
  event.currentTarget.setAttribute("aria-label", visible ? "Show password" : "Hide password");
});
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.hidden = true;
  submit.disabled = true;
  try {
    const response = await fetch("/api/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: document.getElementById("username").value, password: password.value }),
    });
    if (response.ok) { window.location.replace("/"); return; }
    const result = await response.json();
    error.textContent = result.error === "too many attempts; try again in 10 minutes"
      ? "Too many attempts. Try again in 10 minutes." : "Account or password is incorrect.";
    error.hidden = false;
    password.value = "";
    password.focus();
  } catch {
    error.textContent = "The dashboard is unavailable. Try again shortly.";
    error.hidden = false;
  } finally { submit.disabled = false; }
});
