// Copyright (c) 2026, Pymegrowth and contributors
// Lógica de la página de despacho FuelQR

// ── Estado ───────────────────────────────────────────────────────────────────
const state = {
    currentTicket: null,
    scanning: false,
    stream: null,
    scanInterval: null,
    validating: false,
};

// ── Formateo de fechas ────────────────────────────────────────────────────────
function formatDate(dateStr) {
    if (!dateStr) return "—";
    const d = new Date(dateStr.replace(" ", "T"));
    if (isNaN(d)) return dateStr;
    return d.toLocaleDateString("es-DO", {
        day:   "2-digit",
        month: "short",
        year:  "numeric"
    });
}

function formatDatetime(dateStr) {
    if (!dateStr) return "—";
    const d = new Date(dateStr.replace(" ", "T"));
    if (isNaN(d)) return dateStr;
    return d.toLocaleString("es-DO", {
        day:    "2-digit",
        month:  "short",
        year:   "numeric",
        hour:   "2-digit",
        minute: "2-digit"
    });
}

function formatTime(dateStr) {
    if (!dateStr) return "—";
    const d = new Date(dateStr.replace(" ", "T"));
    if (isNaN(d)) return dateStr;
    return d.toLocaleTimeString("es-DO", {
        hour:   "2-digit",
        minute: "2-digit"
    });
}

// ── Utilidades ───────────────────────────────────────────────────────────────
function showScreen(id) {
    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    document.getElementById(id).classList.add("active");
}

function showError(elementId, message) {
    const el = document.getElementById(elementId);
    el.textContent = message;
    el.classList.add("show");
}

function hideError(elementId) {
    const el = document.getElementById(elementId);
    el.textContent = "";
    el.classList.remove("show");
}

function showLoading(text = "Procesando...") {
    document.getElementById("loading-text").textContent = text;
    showScreen("screen-loading");
}

// ── API ───────────────────────────────────────────────────────────────────────
async function apiCall(method, args) {
    const response = await fetch(`/api/method/${method}`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-Frappe-CSRF-Token": frappe.csrf_token,
        },
        body: JSON.stringify(args),
    });
    const data = await response.json();
    if (data.exc) {
        const match = data.exc.match(/\w+Error: .+/);
        throw new Error(match ? match[0] : data.exc);
    }
    return data.message;
}

// ── Validación del ticket ─────────────────────────────────────────────────────
async function validateToken(token) {
    if (!token || !token.trim()) return;
    if (state.validating) return;
    state.validating = true;

    showLoading("Validando ticket...");
    hideError("scan-error");
    stopScanner();

    try {
        const result = await apiCall(
            "fuelqr.api.dispatch.validate_ticket",
            { token: token.trim() }
        );

        if (!result.success) {
            showScreen("screen-scan");
            showError("scan-error", result.error || "Ticket inválido");
            state.validating = false;
            return;
        }

        state.currentTicket = result.ticket;
        renderTicketInfo(result.ticket);
        showScreen("screen-confirm");

    } catch (err) {
        showScreen("screen-scan");
        showError("scan-error", err.message || "Error al validar el ticket. Intente de nuevo.");
        console.error(err);
    }

    state.validating = false;
}

// ── Render del ticket ─────────────────────────────────────────────────────────
function renderTicketInfo(ticket) {
    document.getElementById("t-name").textContent       = ticket.name;
    document.getElementById("t-employee").textContent   = ticket.employee_name || ticket.employee;
    document.getElementById("t-cedula").textContent     = ticket.cedula || "—";
    document.getElementById("t-vehicle").textContent    = ticket.vehicle;
    document.getElementById("t-department").textContent = ticket.department;
    document.getElementById("t-fuel").textContent       = ticket.fuel_item;
    document.getElementById("t-station").textContent    = ticket.station;

    const auth = parseFloat(ticket.qty_authorized) || 0;
    const disp = parseFloat(ticket.qty_dispatched) || 0;
    const rem  = parseFloat(ticket.qty_remaining)  || 0;
    const pct  = auth > 0 ? Math.round((disp / auth) * 100) : 0;

    document.getElementById("t-qty-auth").textContent             = `${auth} ${ticket.uom}`;
    document.getElementById("t-progress").style.width             = `${pct}%`;
    document.getElementById("t-qty-dispatched-label").textContent = `Despachado: ${disp}`;
    document.getElementById("t-qty-remaining-label").textContent  = `Restante: ${rem}`;
    document.getElementById("t-expires").textContent              = formatDatetime(ticket.expires_on);

    const badgeClass = {
        "Creado":           "badge-creado",
        "Enviado":          "badge-creado",
        "Pendiente":        "badge-pendiente",
        "Próximo a Vencer": "badge-proximo",
    }[ticket.status] || "badge-pendiente";
    document.getElementById("ticket-status-badge").innerHTML =
        `<span class="ticket-badge ${badgeClass}">${ticket.status}</span>`;

    const warnEl = document.getElementById("confirm-warning");
    if (ticket.status === "Próximo a Vencer") {
        warnEl.textContent = "⚠️ Este ticket está próximo a vencer. Despache a la brevedad.";
        warnEl.classList.add("show");
    } else {
        warnEl.classList.remove("show");
    }

    document.getElementById("d-qty").max   = rem;
    document.getElementById("d-qty").value = "";
}

// ── Scanner ───────────────────────────────────────────────────────────────────
async function startScanner() {
    try {
        state.stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: "environment",
                width:  { ideal: 1280 },
                height: { ideal: 720 }
            }
        });

        const video = document.getElementById("scanner-video");
        video.srcObject = state.stream;
        await video.play();

        state.scanning = true;
        document.getElementById("btn-start-scan").style.display = "none";
        document.getElementById("btn-stop-scan").style.display  = "block";

        if ("BarcodeDetector" in window) {
            _startBarcodeDetector(video);
        } else {
            loadScript(
                "/assets/fuelqr/js/jsQR.min.js",
                () => _startJsQr(video)
            );
        }

    } catch (err) {
        showError("scan-error",
            "No se pudo acceder a la cámara. Verifica los permisos e intenta de nuevo.");
        document.getElementById("btn-start-scan").style.display = "block";
        document.getElementById("btn-stop-scan").style.display  = "none";
        console.error(err);
    }
}

function _startBarcodeDetector(video) {
    const detector = new BarcodeDetector({ formats: ["qr_code"] });
    state.scanInterval = setInterval(async () => {
        if (!state.scanning || video.readyState !== 4) return;
        try {
            const codes = await detector.detect(video);
            if (codes.length > 0 && codes[0].rawValue) {
                await validateToken(codes[0].rawValue);
            }
        } catch (_) {}
    }, 400);
}

function _startJsQr(video) {
    const canvas = document.createElement("canvas");
    const ctx    = canvas.getContext("2d", { willReadFrequently: true });

    state.scanInterval = setInterval(() => {
        if (!state.scanning || video.readyState !== 4) return;
        if (video.videoWidth === 0 || video.videoHeight === 0) return;

        canvas.width  = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        const code = jsQR(imageData.data, imageData.width, imageData.height, {
            inversionAttempts: "dontInvert",
        });

        if (code && code.data) {
            validateToken(code.data);
        }
    }, 300);
}

function stopScanner() {
    state.scanning = false;
    if (state.scanInterval) {
        clearInterval(state.scanInterval);
        state.scanInterval = null;
    }
    if (state.stream) {
        state.stream.getTracks().forEach(t => t.stop());
        state.stream = null;
    }
    document.getElementById("btn-start-scan").style.display = "block";
    document.getElementById("btn-stop-scan").style.display  = "none";
}

function loadScript(src, callback) {
    if (document.querySelector(`script[src="${src}"]`)) {
        callback();
        return;
    }
    const s = document.createElement("script");
    s.src = src;
    s.onload = callback;
    s.onerror = () => {
        showError("scan-error", "No se pudo cargar el lector QR. Ingresa el código manualmente.");
    };
    document.head.appendChild(s);
}

// ── Submit del despacho ───────────────────────────────────────────────────────
async function submitDispatch() {
    hideError("dispatch-error");

    const qty    = parseFloat(document.getElementById("d-qty").value);
    const method = document.getElementById("d-identity-method").value;
    const ref    = document.getElementById("d-identity-ref").value.trim();
    const odo    = document.getElementById("d-odometer").value;
    const obs    = document.getElementById("d-observations").value;

    if (!qty || qty <= 0) {
        showError("dispatch-error", "Ingrese la cantidad a despachar");
        return;
    }

    const remaining = parseFloat(state.currentTicket.qty_remaining);
    if (qty > remaining * 1.02) {
        showError("dispatch-error",
            `La cantidad supera el saldo disponible (${remaining} ${state.currentTicket.uom})`);
        return;
    }

    if (method !== "Visual" && !ref) {
        showError("dispatch-error", "Ingrese la referencia de identidad");
        return;
    }

    showLoading("Registrando despacho...");

    try {
        const result = await apiCall("fuelqr.api.dispatch.create_dispatch", {
            ticket_name:     state.currentTicket.name,
            qty_dispatched:  qty,
            odometer:        odo || null,
            identity_method: method,
            identity_ref:    ref || null,
            observations:    obs || null,
        });

        if (!result.success) {
            showScreen("screen-dispatch");
            showError("dispatch-error", result.error || "Error al registrar el despacho");
            return;
        }

        document.getElementById("s-dispatch-name").textContent = result.dispatch;
        document.getElementById("s-qty").textContent =
            `${qty} ${state.currentTicket.uom}`;
        document.getElementById("s-vehicle").textContent =
            state.currentTicket.vehicle;
        document.getElementById("success-message").textContent =
            `Despacho registrado exitosamente para ${state.currentTicket.employee_name}`;

        showScreen("screen-success");
        state.currentTicket = null;

    } catch (err) {
        showScreen("screen-dispatch");
        showError("dispatch-error", err.message || "Error al registrar el despacho.");
        console.error(err);
    }
}

// ── Historial ─────────────────────────────────────────────────────────────────
async function loadMyDispatches() {
    try {
        const result = await apiCall("fuelqr.api.dispatch.get_my_dispatches", {});

        document.getElementById("h-count").textContent = result.count;
        document.getElementById("h-total").textContent =
            result.total_qty ? result.total_qty.toFixed(1) : "0";

        const listEl = document.getElementById("dispatch-list");

        if (!result.dispatches || result.dispatches.length === 0) {
            listEl.innerHTML = `<div class="empty-state">No hay despachos registrados hoy</div>`;
            return;
        }

        listEl.innerHTML = result.dispatches.map(d => `
            <div class="dispatch-item">
                <div class="dispatch-item-left">
                    <div class="dispatch-name">${d.name}</div>
                    <div class="dispatch-detail">${d.vehicle} · ${d.employee_name || d.fuel_ticket}</div>
                </div>
                <div class="dispatch-item-right">
                    <div class="dispatch-qty">${d.qty_dispatched} <small>${d.uom || ""}</small></div>
                    <div class="dispatch-time">${formatTime(d.scanned_at)}</div>
                </div>
            </div>`
        ).join("");

    } catch (err) {
        document.getElementById("dispatch-list").innerHTML =
            `<div class="empty-state">Error al cargar los despachos</div>`;
        console.error(err);
    }
}

// ── Búsqueda ──────────────────────────────────────────────────────────────────
async function searchTickets() {
    const query     = document.getElementById("search-input").value.trim();
    const resultsEl = document.getElementById("search-results");

    if (!query || query.length < 3) {
        resultsEl.innerHTML = `<div class="empty-state">Ingresa al menos 3 caracteres</div>`;
        return;
    }

    resultsEl.innerHTML = `<div class="loading"><div class="spinner"></div><span>Buscando...</span></div>`;

    try {
        const tickets = await apiCall("fuelqr.api.dispatch.search_ticket", { query });

        if (!tickets || tickets.length === 0) {
            resultsEl.innerHTML = `<div class="empty-state">No se encontraron tickets</div>`;
            return;
        }

        const statusClass = {
            "Pendiente":        "sr-status-pendiente",
            "Próximo a Vencer": "sr-status-pendiente",
            "Creado":           "sr-status-creado",
            "Enviado":          "sr-status-creado",
            "Consumido":        "sr-status-consumido",
            "Vencido":          "sr-status-vencido",
            "Anulado":          "sr-status-vencido",
        };

        resultsEl.innerHTML = tickets.map(t => `
            <div class="search-result-item" onclick="useTicketFromSearch('${t.short_code}')">
                <div class="sr-header">
                    <span class="sr-name">${t.name}</span>
                    <span class="sr-status ${statusClass[t.status] || ""}">${t.status}</span>
                </div>
                <div class="sr-detail">
                    🚗 ${t.vehicle} · 👤 ${t.employee_name || "—"}
                    · ${t.qty_remaining} / ${t.qty_authorized} ${t.uom || ""}
                    · Vence: ${formatDate(t.expires_on)}
                </div>
            </div>`
        ).join("");

    } catch (err) {
        resultsEl.innerHTML = `<div class="empty-state">Error al buscar</div>`;
        console.error(err);
    }
}

function useTicketFromSearch(shortCode) {
    document.querySelector('[data-tab="scan"]').click();
    document.getElementById("manual-code").value = shortCode;
    document.getElementById("btn-validate-manual").click();
}

// ── Event Listeners ───────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {

    // Scanner
    document.getElementById("btn-start-scan").addEventListener("click", startScanner);
    document.getElementById("btn-stop-scan").addEventListener("click", stopScanner);

    // Código manual
    document.getElementById("btn-validate-manual").addEventListener("click", () => {
        const code = document.getElementById("manual-code").value.trim();
        if (!code) { showError("scan-error", "Ingrese un código"); return; }
        validateToken(code);
    });
    document.getElementById("manual-code").addEventListener("keypress", e => {
        if (e.key === "Enter") document.getElementById("btn-validate-manual").click();
    });

    // Pantalla 2 — Confirmar
    document.getElementById("btn-proceed").addEventListener("click", () =>
        showScreen("screen-dispatch"));
    document.getElementById("btn-back-scan").addEventListener("click", () => {
        state.currentTicket = null;
        hideError("scan-error");
        showScreen("screen-scan");
    });

    // Pantalla 3 — Despacho
    document.getElementById("d-identity-method").addEventListener("change", e => {
        document.getElementById("d-identity-ref-group").style.display =
            e.target.value === "Visual" ? "none" : "block";
    });
    document.getElementById("btn-submit-dispatch").addEventListener("click", submitDispatch);
    document.getElementById("btn-back-confirm").addEventListener("click", () =>
        showScreen("screen-confirm"));

    // Pantalla 4 — Éxito
    document.getElementById("btn-new-dispatch").addEventListener("click", () => {
        hideError("scan-error");
        document.getElementById("manual-code").value = "";
        showScreen("screen-scan");
    });

    // Tabs
    document.querySelectorAll(".tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
            const tab = btn.dataset.tab;
            document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
            btn.classList.add("active");
            document.getElementById(`tab-${tab}`).classList.add("active");
            if (tab === "history") loadMyDispatches();
            if (tab !== "scan") stopScanner();
        });
    });

    // Búsqueda
    document.getElementById("btn-search").addEventListener("click", searchTickets);
    document.getElementById("search-input").addEventListener("keypress", e => {
        if (e.key === "Enter") searchTickets();
    });

});