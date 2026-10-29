/* Shared helpers used by the dashboard and student pages. */

/** Escape text before putting it in HTML (prevents cross-site scripting). */
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/** Call the JSON API. Throws an Error (with .status and .fields) when the request fails. */
async function api(url, options = {}) {
  const init = { method: options.method || "GET", credentials: "same-origin", headers: {} };
  if (options.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  let res;
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new Error("Cannot reach the server. Check your connection and try again.");
  }
  if (res.status === 401) { window.location.href = "/login"; throw new Error("Please log in."); }
  let data = null;
  try { data = await res.json(); } catch (e) { /* non-JSON response */ }
  if (!res.ok) {
    const err = new Error((data && data.error) || "Something went wrong. Please try again.");
    err.status = res.status;
    err.fields = (data && data.fields) || {};
    throw err;
  }
  return data;
}

/** Show a short message in the corner of the screen. */
function toast(message, kind = "success") {
  const el = document.getElementById("appToast");
  if (!el) return;
  el.className = `toast align-items-center border-0 text-bg-${kind === "error" ? "danger" : "success"}`;
  document.getElementById("appToastBody").textContent = message;
  bootstrap.Toast.getOrCreateInstance(el, { delay: 3000 }).show();
}

function riskBadge(level) {
  const cls = "risk-" + String(level).replace(/\s+/g, "-");
  return `<span class="risk-badge ${cls}">${esc(level)}</span>`;
}

/** Mark fields invalid using the { fieldName: message } object returned by the API. */
function showFieldErrors(form, fields, idPrefix) {
  clearFieldErrors(form);
  Object.entries(fields || {}).forEach(([name, message]) => {
    const input = form.querySelector(`#${idPrefix}${name}`);
    if (!input) return;
    input.classList.add("is-invalid");
    const fb = input.parentElement.querySelector(".invalid-feedback");
    if (fb) fb.textContent = message;
  });
}

function clearFieldErrors(form) {
  form.querySelectorAll(".is-invalid").forEach(el => el.classList.remove("is-invalid"));
}

function debounce(fn, ms = 250) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
