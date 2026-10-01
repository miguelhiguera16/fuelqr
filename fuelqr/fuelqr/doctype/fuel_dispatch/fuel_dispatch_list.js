frappe.listview_settings["Fuel Dispatch"] = {
    get_indicator: function (doc) {
        const colors = {
            "Confirmado": "green",
            "Anulado": "red"
        };
        return [
            doc.status || "Borrador",
            colors[doc.status] || "grey",
            "status,=," + doc.status
        ];
    }
};