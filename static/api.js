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

// ---------- Menú del panel: se inyecta solo en panel.html ----------
document.addEventListener("DOMContentLoaded", () => {
  const saludo = document.getElementById("saludo");
  if (!saludo || document.getElementById("menu") || document.getElementById("menu-rol")) return;
  const rol = localStorage.getItem("rol");
  const estilo = "background:#7c3aed;color:#fff;text-decoration:none;padding:10px 16px;border-radius:8px;font-weight:600;font-size:14px";
  const menu = h("div", { id: "menu-rol", style: "display:flex;flex-wrap:wrap;gap:10px;margin:16px 0" },
    h("a", { href: "/static/eventos.html", style: estilo }, "🎟️ Ver eventos"));
  if (rol === "ADMIN" || rol === "ORGANIZADOR")
    menu.append(h("a", { href: "/static/crear-evento.html", style: estilo }, "➕ Crear evento"));
  if (rol === "ADMIN")
    menu.append(h("a", { href: "/static/usuarios.html", style: estilo }, "👥 Gestionar usuarios"));
  saludo.after(menu);
});

// ---------- Imágenes, órdenes y pagos (MS Órdenes, puerto 8003) ----------
const ORDENES_URL = location.protocol + "//" + location.hostname + ":8003";

function apiOrd(path, method = "GET", body = null) {
  return api(ORDENES_URL + path, method, body);
}

function imgEvento(url, alto = 140) {
  const base = `width:100%;height:${alto}px;border-radius:8px;margin-bottom:8px;`;
  if (url) return h("img", { src: EVENTOS_URL + url, alt: "Imagen del evento", style: base + "object-fit:cover;display:block" });
  return h("div", { style: base + "background:linear-gradient(135deg,#4c1d95,#7c3aed);display:flex;align-items:center;justify-content:center;font-size:32px" }, "🎟️");
}

async function subirImagen(idEvento, archivo) {
  if (archivo.size > 3 * 1024 * 1024) throw new Error("La imagen supera 3 MB");
  const fd = new FormData();
  fd.append("archivo", archivo);
  const r = await fetch(EVENTOS_URL + "/eventos/" + idEvento + "/imagen", {
    method: "POST", headers: { Authorization: "Bearer " + localStorage.getItem("token") }, body: fd,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Error " + r.status);
  return data;
}

document.addEventListener("DOMContentLoaded", () => {
  const menu = document.getElementById("menu") || document.getElementById("menu-rol");
  if (!menu || menu.dataset.extra) return;
  menu.dataset.extra = "1";
  const rol = localStorage.getItem("rol");
  const estilo = "background:#7c3aed;color:#fff;text-decoration:none;padding:10px 16px;border-radius:8px;font-weight:600;font-size:14px";
  if (rol === "CLIENTE" || rol === "ADMIN")
    menu.append(h("a", { href: "/static/mis-boletas.html", style: estilo }, "🎫 Mis boletas"));
  if (rol === "VALIDADOR" || rol === "ADMIN")
    menu.append(h("a", { href: "/static/validar.html", style: estilo }, "✅ Validar ingreso"));
});
