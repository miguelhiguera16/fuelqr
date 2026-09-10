# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: MIT. See LICENSE

import json

import frappe
from frappe import _
from frappe.custom.doctype.property_setter.property_setter import delete_property_setter
from frappe.model import core_doctypes_list
from frappe.model.docfield import supports_translation
from frappe.model.document import Document
from frappe.query_builder import Field, functions
from frappe.utils import cstr, random_string

from frappe.custom.doctype.custom_field.custom_field import CustomField


class CustomCustomField(CustomField):
	def set_fieldname(self):
		restricted = (
			"name",
			"parent",
			"creation",
			"modified",
			"modified_by",
			"parentfield",
			"parenttype",
			"file_list",
			"flags",
			"docstatus",
		)
		if not self.fieldname:
			label = self.label
			if not label:
				if self.fieldtype in ["Section Break", "Column Break", "Tab Break"]:
					label = self.fieldtype + "_" + str(random_string(5))
				else:
					frappe.throw(_("Label is mandatory"))

			# remove special characters from fieldname
			self.fieldname = "".join(
				[c for c in cstr(label).replace(" ", "_") if c.isdigit() or c.isalpha() or c == "_"]
			)
			self.fieldname = f"{self.fieldname}"

		# fieldnames should be lowercase
		self.fieldname = self.fieldname.lower()

		if self.fieldname in restricted:
			self.fieldname = self.fieldname + "1"
