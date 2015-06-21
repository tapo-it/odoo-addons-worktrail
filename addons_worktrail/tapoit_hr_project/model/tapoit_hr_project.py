# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2011-today TaPo-IT (http://tapo-it.at) All Rights Reserved.
#    Author: Wolfgang Taferner (w.taferner@tapo.at)
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

from openerp.osv import orm, fields

import logging
_logger = logging.getLogger(__name__)

# TODO: make standard action reason configurable


class tapoit_hr_project_workcontext(orm.Model):

    """ Work Context  """

    _name = "tapoit.hr.project.workcontext"
    _description = "Work Context"
    _columns = {
        'name': fields.char('Name', size=25, required=True, select=1),
        'keyword': fields.char('Keyword', size=25, required=True, select=1),
        'status': fields.boolean('Active'),
        'company': fields.many2one('res.company', 'Company', required=True, select=1),
        'sequence': fields.integer('Sort Order'),
        'action_reason': fields.many2many('hr.action.reason', 'tapoit_hr_project_workcontext_action_reason_rel', 'workcontext_id', 'action_reason_id', 'Related Action Reasons'),
    }
    _order = "sequence"

    _defaults = {
        'status': True,
        'company': 1
    }

    def retrieve_reason_from_workcontext(self, cr, uid, workcontext=None, action_type='action', pause=False, context=None):
        reason = False
        if action_type == 'action':
            pause = False
        if workcontext:
            if workcontext.action_reason:
                for wc_rel in workcontext.action_reason:
                    _logger.debug('Matching Action Reasons: %s (Pause: %s) - %s (Pause: %s)', wc_rel.action_type, wc_rel.pause, action_type, pause)
                    if wc_rel.action_type == action_type and wc_rel.pause == pause:
                        reason = wc_rel.id
                        _logger.debug('Match: %s (Pause: %s) - Reason: %s (%s)', action_type, pause, wc_rel.name, reason)
        return reason

tapoit_hr_project_workcontext()


class hr_action_reason(orm.Model):
    _name = "hr.action.reason"
    _description = "Action Reason"
    _columns = {
        'name': fields.char('Reason', size=64, required=True, help='Specifies the reason for Signing In/Signing Out.'),
        'action_type': fields.selection([('sign_in', 'Sign In'), ('action', 'Action'), ('sign_out', 'Sign out')], "Action Type"),
        'pause': fields.boolean('Break')
    }
    _defaults = {
        'action_type': 'sign_in',
    }
hr_action_reason()


class hr_timesheet_sheet(orm.Model):
    _inherit = 'hr_timesheet_sheet.sheet'
    _order = "date_from DESC"
hr_timesheet_sheet()
