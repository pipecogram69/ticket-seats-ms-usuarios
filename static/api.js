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

// ---------- Panel: próximos eventos (reemplaza el mensaje de rol) ----------
document.addEventListener("DOMContentLoaded", async () => {
  const mensajeRol = document.getElementById("contenido-rol");
  if (!mensajeRol || document.getElementById("proximos")) return;
  mensajeRol.style.display = "none";

  const lista = h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px" });
  const caja = h("div", { id: "proximos", class: "section" },
    h("h2", { style: "font-size:18px;color:#1e1b4b;margin-bottom:10px" }, "📅 Próximos eventos"),
    lista);
  mensajeRol.after(caja);

  try {
    const proximos = (await apiEv("/eventos"))
      .filter(e => new Date(e.fecha_inicio) > new Date())
      .slice(0, 6);

    if (!proximos.length) {
      lista.replaceWith(h("p", { class: "sub" }, "Todavía no hay eventos próximos."));
      return;
    }

    for (const e of proximos) {
      lista.append(h("a", {
          href: "/static/evento.html?id=" + e.id_evento,
          style: "display:block;text-decoration:none;color:inherit;border:1px solid #e5e7eb;border-radius:10px;padding:10px"
        },
        imgEvento(e.imagen_url, 90),
        h("div", { style: "font-weight:700;font-size:14px;color:#1e1b4b" }, e.nombre),
        h("div", { style: "font-size:12px;color:#6b7280;margin-top:2px" }, fmtFecha(e.fecha_inicio)),
        h("div", { style: "font-size:12px;color:#6b7280" }, (e.ciudad || "") + (e.venue ? " · " + e.venue : "")),
        h("div", { style: "font-size:12px;color:#5b21b6;font-weight:600;margin-top:4px" }, "Desde " + fmtPrecio(e.precio_desde))));
    }
    caja.append(h("p", { style: "margin-top:12px;font-size:14px" },
      h("a", { href: "/static/eventos.html" }, "Ver todos los eventos →")));
  } catch (err) {
    lista.replaceWith(h("p", { class: "sub" }, "No se pudieron cargar los eventos."));
  }
});
