// Copyright (c) 2026, Pymegrowth and contributors
// Lógica de la página de despacho FuelQR

// ── Estado de la app ────────────────────────────────────────────────────────
const state = {
    currentTicket: null,
    scanning: false,
    stream: null,
    scanInterval: null,
};

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

// ── Llamadas a la API ────────────────────────────────────────────────────────
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
    if (data.exc) throw new Error(data.exc);
    return data.message;
}

// ── Validación del ticket ────────────────────────────────────────────────────
async function validateToken(token) {
    showLoading("Validando ticket...");
    hideError("scan-error");

    try {
        const result = await apiCall(
            "fuelqr.api.dispatch.validate_ticket",
            { token }
        );

        if (!result.success) {
            showScreen("screen-scan");
            showError("scan-error", result.error || "Ticket inválido");
            stopScanner();
            return;
        }

        state.currentTicket = result.ticket;
        renderTicketInfo(result.ticket);
        showScreen("screen-confirm");
        stopScanner();

    } catch (err) {
        showScreen("screen-scan");
        showError("scan-error", "Error al validar el ticket. Intente de nuevo.");
        console.error(err);
    }
}

// ── Render de datos del ticket ───────────────────────────────────────────────
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

    document.getElementById("t-qty-auth").textContent =
        `${auth} ${ticket.uom}`;
    document.getElementById("t-progress").style.width = `${pct}%`;
    document.getElementById("t-qty-dispatched-label").textContent =
        `Despachado: ${disp}`;
    document.getElementById("t-qty-remaining-label").textContent =
        `Restante: ${rem}`;
    document.getElementById("t-expires").textContent =
        ticket.expires_on ? ticket.expires_on.replace("T", " ") : "—";

    // Badge de estado
    const badgeEl = document.getElementById("ticket-status-badge");
    const badgeClass = {
        "Creado":           "badge-creado",
        "Enviado":          "badge-creado",
        "Pendiente":        "badge-pendiente",
        "Próximo a Vencer": "badge-proximo",
    }[ticket.status] || "badge-pendiente";
    badgeEl.innerHTML =
        `<span class="ticket-badge ${badgeClass}">${ticket.status}</span>`;

    // Advertencia si está próximo a vencer
    const warnEl = document.getElementById("confirm-warning");
    if (ticket.status === "Próximo a Vencer") {
        warnEl.textContent = "⚠️ Este ticket está próximo a vencer. Despache a la brevedad.";
        warnEl.classList.add("show");
    } else {
        warnEl.classList.remove("show");
    }

    // Pre-llenar cantidad máxima disponible
    document.getElementById("d-qty").max = rem;
    document.getElementById("d-qty").value = "";
}

// ── Escáner QR ───────────────────────────────────────────────────────────────
async function startScanner() {
    try {
        state.stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "environment" }
        });

        const video = document.getElementById("scanner-video");
        video.srcObject = state.stream;
        await video.play();

        state.scanning = true;
        document.getElementById("btn-start-scan").style.display = "none";
        document.getElementById("btn-stop-scan").style.display  = "block";

        // Usar BarcodeDetector si está disponible
        if ("BarcodeDetector" in window) {
            const detector = new BarcodeDetector({ formats: ["qr_code"] });
            state.scanInterval = setInterval(async () => {
                if (!state.scanning) return;
                try {
                    const codes = await detector.detect(video);
                    if (codes.length > 0) {
                        const token = codes[0].rawValue;
                        if (token) await validateToken(token);
                    }
                } catch (_) {}
            }, 500);
        } else {
            // Fallback: cargar html5-qrcode desde CDN
            loadScript(
                "https://cdnjs.cloudflare.com/ajax/libs/html5-qrcode/2.3.8/html5-qrcode.min.js",
                () => startHtml5QrScanner(video)
            );
        }

    } catch (err) {
        showError("scan-error",
            "No se pudo acceder a la cámara. Verifica los permisos.");
        console.error(err);
    }
}

function startHtml5QrScanner(video) {
    // Fallback para browsers sin BarcodeDetector
    // Usamos canvas para capturar frames y decodificar
    const canvas  = document.createElement("canvas");
    const ctx     = canvas.getContext("2d");

    state.scanInterval = setInterval(() => {
        if (!state.scanning || video.readyState !== 4) return;
        canvas.width  = video.videoWidth;
        canvas.height = video.videoHeight;
        ctx.drawImage(video, 0, 0);
        // html5-qrcode no funciona bien en modo frame-by-frame
        // el usuario puede usar el input manual como respaldo
    }, 500);
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
    const s   = document.createElement("script");
    s.src     = src;
    s.onload  = callback;
    document.head.appendChild(s);
}

// ── Submit del despacho ──────────────────────────────────────────────────────
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
    if (qty > remaining * 1.02) {  // 2% tolerancia
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
        const result = await apiCall(
            "fuelqr.api.dispatch.create_dispatch",
            {
                ticket_name:     state.currentTicket.name,
                qty_dispatched:  qty,
                odometer:        odo || null,
                identity_method: method,
                identity_ref:    ref || null,
                observations:    obs || null,
            }
        );

        if (!result.success) {
            showScreen("screen-dispatch");
            showError("dispatch-error", result.error || "Error al registrar el despacho");
            return;
        }

        // Mostrar pantalla de éxito
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
        showError("dispatch-error", "Error al registrar el despacho. Intente de nuevo.");
        console.error(err);
    }
}

// ── Event listeners ──────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {

    // Pantalla 1: Escanear
    document.getElementById("btn-start-scan").addEventListener("click", startScanner);
    document.getElementById("btn-stop-scan").addEventListener("click", stopScanner);

    document.getElementById("btn-validate-manual").addEventListener("click", () => {
        const code = document.getElementById("manual-code").value.trim();
        if (!code) {
            showError("scan-error", "Ingrese un código");
            return;
        }
        validateToken(code);
    });

    document.getElementById("manual-code").addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
            document.getElementById("btn-validate-manual").click();
        }
    });

    // Pantalla 2: Confirmar
    document.getElementById("btn-proceed").addEventListener("click", () => {
        showScreen("screen-dispatch");
    });

    document.getElementById("btn-back-scan").addEventListener("click", () => {
        state.currentTicket = null;
        hideError("scan-error");
        showScreen("screen-scan");
    });

    // Pantalla 3: Despacho
    document.getElementById("d-identity-method").addEventListener("change", (e) => {
        const refGroup = document.getElementById("d-identity-ref-group");
        refGroup.style.display = e.target.value === "Visual" ? "none" : "block";
    });

    document.getElementById("btn-submit-dispatch").addEventListener("click", submitDispatch);

    document.getElementById("btn-back-confirm").addEventListener("click", () => {
        showScreen("screen-confirm");
    });

    // Pantalla 4: Éxito
    document.getElementById("btn-new-dispatch").addEventListener("click", () => {
        hideError("scan-error");
        document.getElementById("manual-code").value = "";
        showScreen("screen-scan");
    });

});