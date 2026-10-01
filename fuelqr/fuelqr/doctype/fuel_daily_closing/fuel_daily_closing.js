// Copyright (c) 2026, FuelQR and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fuel Daily Closing", {

	onload(frm) {
		if (frm.is_new()) {
			frm.set_value("date", frappe.datetime.get_today());
			frm.set_value("closed_by", frappe.session.user);
			// frm.set_value("status", "Borrador");
		}
		frm.set_query("station", () => ({
			filters: { is_group: 0, disabled: 0 }
		}));
	},

	refresh(frm) {
		// const colors = { "Borrador": "grey", "Cerrado": "blue", "Aprobado": "green" };
		// frm.page.set_indicator(frm.doc.status, colors[frm.doc.status] || "grey");

		// Botón Aprobar — solo cuando ya está Cerrado y submitido
		if (frm.doc.docstatus === 1 && frm.doc.status === "Cerrado") {
			frm.add_custom_button(__("Aprobar"), () => {
				frappe.confirm(
					__("¿Aprobar este cierre diario? Esta acción no se puede revertir."),
					() => {
						frappe.call({
							method: "frappe.client.set_value",
							args: {
								doctype: "Fuel Daily Closing",
								name: frm.doc.name,
								fieldname: { status: "Aprobado", approved_by: frappe.session.user }
							},
							callback() {
								frm.reload_doc();
								frappe.show_alert({ message: __("Cierre aprobado"), indicator: "green" });
							}
						});
					}
				);
			}, __("Acciones"));
		}

		// Botón Cargar Datos — solo en Borrador (docstatus 0)
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Cargar Datos del Día"), () => {
				if (!frm.doc.date || !frm.doc.station) {
					frappe.msgprint({
						title: __("Campos requeridos"),
						message: __("Seleccione la fecha y la estación primero."),
						indicator: "orange"
					});
					return;
				}

				// Si es nuevo, primero guarda para obtener el name, luego recarga
				if (frm.is_new()) {
					frm.save().then(() => {
						frappe.show_alert({ message: __("Guardado. Cargando datos..."), indicator: "blue" });
						frm.reload_doc();
					}).catch(err => {
						frappe.msgprint({
							title: __("Error al guardar"),
							message: err.message || __("No se pudo guardar el documento."),
							indicator: "red"
						});
					});
				} else {
					frm.save().then(() => frm.reload_doc());
				}
			}, __("Acciones"));
		}
	},

	// Al cambiar fecha o estación en un documento YA guardado
	date(frm) {
		if (frm.doc.date && frm.doc.station && !frm.is_new() && frm.doc.docstatus === 0) {
			frm.save().then(() => frm.reload_doc());
		}
	},

	station(frm) {
		if (frm.doc.date && frm.doc.station && !frm.is_new() && frm.doc.docstatus === 0) {
			frm.save().then(() => frm.reload_doc());
		}
	},

	fuel_item(frm) {
		if (frm.doc.date && frm.doc.station && !frm.is_new() && frm.doc.docstatus === 0) {
			frm.save().then(() => frm.reload_doc());
		}
	}
});