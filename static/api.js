function guardarSesion(token, rol) {
  localStorage.setItem("token", token);
  localStorage.setItem("rol", rol);
}

function cerrarSesion() {
  localStorage.clear();
  location.href = "/static/login.html";
}

async function api(path, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };
  const token = localStorage.getItem("token");
  if (token) headers["Authorization"] = "Bearer " + token;

  const r = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : null });
  let data = null;
  try { data = await r.json(); } catch (e) {}

  if (!r.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map(e => e.msg).join(", ");
    const err = new Error(msg || "Error " + r.status);
    err.status = r.status;
    throw err;
  }
  return data;
}

function mostrar(el, texto, tipo) {
  el.textContent = texto;
  el.className = "msg " + tipo;
}

// ---------- MS Eventos e Inventario (puerto 8002) ----------
const EVENTOS_URL = location.protocol + "//" + location.hostname + ":8002";

function apiEv(path, method = "GET", body = null) {
  return api(EVENTOS_URL + path, method, body);
}

function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "href") e.href = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  e.append(...kids);
  return e;
}

function fmtFecha(s) {
  return new Date(s).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
}

function fmtPrecio(n) {
  return "$" + Number(n || 0).toLocaleString("es-CO");
}
