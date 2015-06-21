# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2012 TaPo-IT (http://tapo-it.at) All Rights Reserved.
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
    'name': 'WorkTrail Sync',

    'version': '1.0',
    "sequence": 15,
    'author': 'TaPo-IT',
    'website': 'http://tapo-it.at',
    'complexity': 'expert',
    'license': 'AGPL-3',
    'category': 'Human Resources',
    'summary': "WorkTrail Sync",

    'description': """Odoo - WorkTrail Sync Module (https://worktrail.net)""",

    'depends': [
        'base',
        'tapoit_hr_project'
    ],

    'demo': [
    ],

    'data': [
        'view/tapoit_worktrail_view.xml',
        'wizard/tapoit_worktrail_sync_execution_view.xml',
        'security/tapoit_worktrail_ir_model_access.xml'

    ],

    'test': [],
    'installable': True,
    'application': True,
    'active': False,
    'certificate': '',
    'post_load': '',
    'js': [],
    'css': [],
    'images': [],
    'qweb': [],
}
