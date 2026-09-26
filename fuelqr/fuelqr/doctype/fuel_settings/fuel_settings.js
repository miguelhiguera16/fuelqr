// Copyright (c) 2026, FuelQR and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fuel Request", {

    // Al abrir un documento nuevo
    onload(frm) {
        if (frm.is_new()) {
            frm.set_value("request_date", frappe.datetime.get_today());
            frm.set_value("status", "Draft");
            frm.set_value("request_type", "Manual");
        }
    },

    // Al seleccionar vehículo — autocompleta departamento, combustible y UOM
    vehicle(frm) {
        if (!frm.doc.vehicle) return;

        frappe.db.get_value("Vehicle", frm.doc.vehicle, 
            ["department", "fuel_item", "uom", "status", "tank_capacity"],
            (r) => {
                if (!r) return;

                frm.set_value("department", r.department);
                frm.set_value("fuel_item", r.fuel_item);
                frm.set_value("uom", r.uom);

                // Advertencia si el vehículo no está activo
                if (r.status && r.status !== "Activo"){
                    frappe.msgprint({
                        title: __("Vehículo no disponible"),
                        message: __("El vehículo {0} tiene estado: {1}", 
                            [frm.doc.vehicle, r.status]),
                        indicator: "red"
                    });
                }

                // Mostrar capacidad del tanque como referencia
                if (r.tank_capacity) {
                    frm.set_df_property(
                        "qty_authorized", 
                        "description", 
                        __("Capacidad del tanque: {0} {1}", [r.tank_capacity, frm.doc.uom || ""])
                    );
                }
            }
        );
    },

    // Al cambiar la fecha de solicitud — recalcula valid_until
    request_date(frm) {
        if (!frm.doc.request_date) return;

        frappe.db.get_single_value("Fuel Settings", "default_validity_days")
            .then(days => {
                if (days) {
                    let valid = frappe.datetime.add_days(frm.doc.request_date, days);
                    frm.set_value("valid_until", valid);
                }
            });
    },

    // Validación antes de guardar
    qty_authorized(frm) {
        if (!frm.doc.qty_authorized || !frm.doc.vehicle) return;

        frappe.db.get_value("Vehicle", frm.doc.vehicle, "tank_capacity", (r) => {
            if (r && r.tank_capacity && frm.doc.qty_authorized > r.tank_capacity) {
                frappe.msgprint({
                    title: __("Cantidad excedida"),
                    message: __("La cantidad {0} supera la capacidad del tanque ({1})", 
                        [frm.doc.qty_authorized, r.tank_capacity]),
                    indicator: "orange"
                });
            }
        });
    }

});