frappe.listview_settings["Fuel Ticket"] = {
    get_indicator: function (doc) {
        const colors = {
            "Creado":           "blue",
            "Enviado":          "blue",
            "Pendiente":        "yellow",
            "Próximo a Vencer": "orange",
            "Vencido":          "red",
            "Consumido":        "green",
            "Anulado":          "grey"
        };
        return [
            doc.status,
            colors[doc.status] || "grey",
            "status,=," + doc.status
        ];
    }
};