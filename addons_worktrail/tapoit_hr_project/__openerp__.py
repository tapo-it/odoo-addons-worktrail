# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2011 TaPo-IT (http://tapo-it.at) All Rights Reserved.
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
{
    "name": "Project & HR",

    "version": "1.0",
    "sequence": 15,
    "author": "TaPo-IT",
    "website": "http://tapo-it.at",

    "category": "Human Resources",

    'summary': "Project Task Work & HR Attendance",
    'license': 'AGPL-3',
    "description": """

This module extends the modules hr_attendance/ hr_timesheet and implements a booking system by project task work.
==========================================================================
In detail the module
- is taking hr_attendance entries as timestamp and reference for project task work
- provides a wizard for booking on project task work
- adds a new option in the selection of hr_attendance actions (action)
- all time and user related post attendance modifications are limited to project task work
- moving and deleting of project task work will protect sign in and sign out for post manipulation in hr_attendance
- attendances/ timestamp actions are dynamically changed by logic (created, changed, deleted, merged, splitted)

                        """,

    "depends": [
        'hr_attendance',
        'hr_timesheet',
        "project_timesheet",
    ],
    "demo": [],

    "data": [
        'security/tapoit_hr_project_ir_model_access.xml',
        'wizard/tapoit_hr_project_sign_in_out_view.xml',
        'wizard/tapoit_hr_project_move_work_view.xml',
        'view/tapoit_hr_project_view.xml',
    ],
    'test': [
    ],

    "certificate": '',
    "active": False,
    "installable": True,
    "application": True,
    "js": ["static/src/js/attendance.js"],
}
