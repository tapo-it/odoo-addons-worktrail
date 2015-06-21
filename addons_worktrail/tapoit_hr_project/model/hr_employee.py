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

from datetime import datetime
from openerp.osv import orm
from openerp.tools.translate import _
import logging


_logger = logging.getLogger(__name__)


class hr_employee(orm.Model):
    _inherit = "hr.employee"
    _description = "Employee"

    def attendance_action_change(self, cr, uid, ids, action_type='action', context=None, dt=False, *args):
        obj_attendance = self.pool.get('hr.attendance')
        id = False
        reason = False
        pause = False
        warning_sign = 'sign'

        # Special case when button calls this method: type=context
        if isinstance(action_type, dict):
            action_type = action_type.get('action_type', 'action')

        if action_type == 'sign_in':
            warning_sign = "Sign In"
        elif action_type == 'sign_out':
            warning_sign = "Sign Out"

        source = ''
        if context is not None:
            # TODO: Refactor whole module to fit better and improve
            if 'web_wizard' in context:
                return self.attendance_action_change_web(cr, uid, ids, context=context)

            # Retrieving reason from work context
            if 'data' in context and isinstance(context['data'], orm.browse_record):
                if 'pause' in context['data']:
                    pause = context['data'].pause
                reason = self.pool.get('tapoit.hr.project.workcontext').retrieve_reason_from_workcontext(cr, uid, workcontext=context['data'].workcontext, action_type=action_type, pause=pause)
                if not reason:
                    reason = context['data'].action_desc
            else:
                if 'pause' in context:
                    pause = context['pause']
            _logger.info('Context: %s | Reason: %s', context, reason)
            if not isinstance(reason, int):
                if 'action_desc' in context['data']:
                    reason = context['data']['action_desc']
            source = 'wizard'
            if 'source' in context:
                source = context['source']
            context = None
        if isinstance(reason, orm.browse_record):
            reason = reason.id
        if not isinstance(reason, int):
            reason = {}

        _logger.info('create attendance vals: %s', [reason, pause, action_type, dt])

        for emp in self.read(cr, uid, ids, ['id'], context=context):
            if source == 'wizard':
                if not self._action_check(cr, uid, emp['id'], dt, context) and action_type != 'action':
                    raise orm.except_orm(_('Warning'), _('You tried to %s with a date anterior to another event !\nTry to contact the administrator to correct attendances.') % (warning_sign,))
            res = {'action': action_type, 'employee_id': emp['id'], 'action_desc': reason, 'pause': pause}
            if dt:
                res['name'] = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")

        res['name'] = str(res['name'])

        # CREATE
        id = obj_attendance.create(cr, uid, res, context=context)

        return id

    def attendance_action_change_web(self, cr, uid, ids, context=None):
        context = dict(context or {})

        action_date = context.get('action_date', False)
        action = context.get('action', False)
        hr_attendance = self.pool.get('hr.attendance')
        warning_sign = {'sign_in': _('Sign In'), 'sign_out': _('Sign Out')}
        for employee in self.browse(cr, uid, ids, context=context):
            if not action:
                if employee.state == 'present':
                    action = 'sign_out'
                if employee.state == 'absent':
                    action = 'sign_in'

            if not self._action_check(cr, uid, employee.id, action_date, context):
                raise orm.except_orm(_('Warning'), _('You tried to %s with a date anterior to another event !\nTry to contact the HR Manager to correct attendances.') % (warning_sign[action],))

            vals = {'action': action, 'employee_id': employee.id}
            if action_date:
                vals['name'] = str(action_date)
            hr_attendance.create(cr, uid, vals, context=context)
        return True

hr_employee()
