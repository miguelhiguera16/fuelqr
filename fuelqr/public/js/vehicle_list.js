frappe.listview_settings["Vehicle"] = {
    get_indicator: function (doc) {
        const colors = {
            "Activo": "green",
            "Inactivo": "red",
            "En Mantenimiento": "orange",
        };
        return [
            doc.status || "",
            colors[doc.status] || "grey",
            "status,=," + doc.status
        ];
    }
};