# Copyright (c) 2026, FuelQR and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class FuelSettings(Document):
    pass


def get_settings():
    """
    Retorna la instancia de Fuel Settings.
    Usar desde cualquier otro doctype:
        from fuelqr.fuelqr.doctype.fuel_settings.fuel_settings import get_settings
        settings = get_settings()
    """
    return frappe.get_single("Fuel Settings")
