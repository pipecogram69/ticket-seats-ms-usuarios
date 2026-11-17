// ===================== Sesión y peticiones =====================
function guardarSesion(token, rol, nombre) {
  localStorage.setItem("token", token);
  localStorage.setItem("rol", rol);
  if (nombre) localStorage.setItem("nombre", nombre); else localStorage.removeItem("nombre");
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

// ===================== Otros microservicios =====================
const EVENTOS_URL = window.TS_CONFIG?.eventos || "";
const ORDENES_URL = window.TS_CONFIG?.ordenes || "";
const apiEv = (path, method = "GET", body = null) => api(EVENTOS_URL + path, method, body);
const apiOrd = (path, method = "GET", body = null) => api(ORDENES_URL + path, method, body);

// ===================== Utilidades de interfaz =====================
function h(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "href") e.href = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const k of kids) if (k !== null && k !== undefined && k !== false) e.append(k);
  return e;
}

function fmtFecha(s) {
  return new Date(s).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
}

function fmtPrecio(n) {
  return "$" + Number(n || 0).toLocaleString("es-CO");
}

function imgEvento(url, alto = 150) {
  const estilo = `height:${alto}px`;
  if (url) return h("img", { class: "ev-img", src: EVENTOS_URL + url, alt: "Imagen del evento", style: estilo });
  return h("div", { class: "ev-img ph", style: estilo }, "🎟️");
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

function tarjetaEvento(e) {
  return h("a", { class: "ev", href: "/static/evento.html?id=" + e.id_evento },
    imgEvento(e.imagen_url, 150),
    h("div", { class: "ev-body" },
      h("div", { class: "tags" },
        h("span", { class: "tag" }, e.ciudad || "—"),
        h("span", { class: "tag alt" }, "Shard " + e.id_shard)),
      h("h3", {}, e.nombre),
      h("p", { class: "meta" }, "📍 " + (e.venue || "")),
      h("p", { class: "meta" }, "🗓️ " + fmtFecha(e.fecha_inicio)),
      h("div", { class: "ev-foot" },
        h("span", { class: "precio" }, "Desde " + fmtPrecio(e.precio_desde)),
        h("span", { class: "disp" }, e.disponibles + " disp."))));
}

// ===================== Menú lateral (páginas con body.app) =====================
const NAV = [
  ["/static/panel.html", "🏠", "Inicio", null],
  ["/static/eventos.html", "🎟️", "Eventos", null],
  ["/static/crear-evento.html", "➕", "Crear evento", ["ADMIN", "ORGANIZADOR"]],
  ["/static/mis-boletas.html", "🎫", "Mis boletas", ["CLIENTE", "ADMIN"]],
  ["/static/validar.html", "✅", "Validar ingreso", ["VALIDADOR", "ADMIN"]],
  ["/static/usuarios.html", "👥", "Usuarios", ["ADMIN"]],
];

document.addEventListener("DOMContentLoaded", () => {
  if (!document.body.classList.contains("app")) return;
  if (!localStorage.getItem("token")) { location.href = "/static/login.html"; return; }
  const main = document.querySelector("main.main");
  if (!main) return;

  const rol = localStorage.getItem("rol") || "";
  const ruta = location.pathname;
  const nombre = localStorage.getItem("nombre") || "Mi cuenta";
  const avatar = h("div", { class: "avatar" }, nombre.charAt(0).toUpperCase());
  const quien = h("b", {}, nombre);

  const enlaces = NAV.filter(n => !n[3] || n[3].includes(rol)).map(([href, ico, txt]) =>
    h("a", { href, class: ruta === href ? "act" : "" }, h("span", { class: "ico" }, ico), txt));

  const side = h("aside", { class: "side" },
    h("a", { class: "brand", href: "/static/panel.html" },
      h("span", { class: "logo" }, "🎟️"), h("span", {}, "Ticket ", h("em", {}, "Seats"))),
    h("nav", { class: "side-nav" }, ...enlaces),
    h("div", { class: "side-user" },
      h("div", { class: "fila-u" }, avatar, h("div", { class: "who" }, quien, h("small", {}, rol))),
      h("button", { class: "salir", onclick: cerrarSesion }, "Cerrar sesión")));

  document.body.prepend(h("div", { class: "shell" }, side, main));

  if (!localStorage.getItem("nombre")) {
    api("/auth/me").then(u => {
      const n = u.nombre + " " + u.apellido;
      localStorage.setItem("nombre", n);
      quien.textContent = n;
      avatar.textContent = n.charAt(0).toUpperCase();
    }).catch(() => {});
  }
});

// ---------- Entradas de menú: Mis eventos y Mis reservas ----------
if (typeof NAV !== "undefined" && !NAV.some(n => n[0].includes("mis-eventos"))) {
  NAV.splice(3, 0,
    ["/static/mis-eventos.html", "📊", "Mis eventos", ["ADMIN", "ORGANIZADOR"]],
    ["/static/mis-reservas.html", "📌", "Mis reservas", ["CLIENTE", "ADMIN"]]);
}
