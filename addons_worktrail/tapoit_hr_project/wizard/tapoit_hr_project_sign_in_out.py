# -*- encoding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (c) 2011 TaPo-IT (http://tapo-it.at) All Rights Reserved.
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
from openerp.tools.translate import _
import logging
import time


_logger = logging.getLogger(__name__)


class hr_so_project(orm.TransientModel):
    _name = 'hr.sign.out.task.work'
    _description = 'Sign Out By Task Work'
    _columns = {
        'task_id': fields.many2one('project.task', 'Task', required=True),
        'action_desc': fields.many2one('hr.action.reason', 'Action description'),
        'info': fields.char('Work Description', size=256, required=True),
        'date_start': fields.datetime('Starting Date', readonly=True),
        'date': fields.datetime('Closing Date', help="Keep empty for current time"),
        'name': fields.char('Employees name', size=32, required=True, readonly=True),
        'state': fields.related('emp_id', 'state', string='Current state', type='char', required=True, readonly=True),
        'pause': fields.boolean('Break'),
        'server_date': fields.datetime('Current Date', required=True, help="Local time on the server side", readonly=True),
        'emp_id': fields.many2one('hr.employee', 'Employee ID'),
        'start_attendance': fields.integer('Related Start Attendance ID'),
        'end_attendance': fields.integer('Related End Attendance ID'),
        'workcontext': fields.many2one('tapoit.hr.project.workcontext', 'Work Context'),
    }

    def _get_empid(self, cr, uid, context=None):
        emp_obj = self.pool.get('hr.employee')
        emp_ids = emp_obj.search(cr, uid, [('user_id', '=', uid)], context=context)
        if emp_ids:
            for employee in emp_obj.browse(cr, uid, emp_ids, context=context):
                return {'name': employee.name, 'state': employee.state, 'emp_id': emp_ids[0], 'server_date': time.strftime('%Y-%m-%d %H:%M:%S')}

    def _get_empid2(self, cr, uid, context=None):
        res = self._get_empid(cr, uid, context=context)
        cr.execute('SELECT name,action FROM hr_attendance WHERE employee_id=%s ORDER BY name DESC LIMIT 1', (res['emp_id'],))

        res['server_date'] = time.strftime('%Y-%m-%d %H:%M:%S')
        date_start = cr.fetchone()

        if date_start:
            res['date_start'] = date_start[0]
        return res

    def default_get(self, cr, uid, fields_list, context=None):
        res = super(hr_so_project, self).default_get(cr, uid, fields_list, context=context)
        res.update(self._get_empid2(cr, uid, context=context))
        return res

    def _write(self, cr, uid, data, emp_id, context=None):
        context = dict(context or {})

        hour = (time.mktime(time.strptime(data['date'] or time.strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S')) -
                time.mktime(time.strptime(data['date_start'], '%Y-%m-%d %H:%M:%S'))) / 3600.0

        task_obj = self.pool.get('project.task.work')
        res = {
            'hours': hour,
            'date': str(data['date_start']),
            'user_id': uid,
            'name': data['info'],
            'task_id': data['task_id'].id,
            'start_attendance': data.start_attendance,
            'end_attendance': data.end_attendance,
            'workcontext': data.workcontext.id
        }
        return task_obj.create(cr, uid, res, type=context['type'], context=context)

    def sign_out_break(self, cr, uid, ids, context=None):
        context = dict(context or {})

        context['pause'] = True
        return self.sign_out_result_end(cr, uid, ids, context)

    def sign_out_result_end(self, cr, uid, ids, context=None):
        context = dict(context or {})

        emp_obj = self.pool.get('hr.employee')
        for data in self.browse(cr, uid, ids, context=context):
            emp_id = data.emp_id.id
            cr.execute('SELECT id FROM hr_attendance WHERE employee_id=%s ORDER BY name DESC LIMIT 1', (emp_id,))
            data.start_attendance = (cr.fetchone() or (False,))[0]
            if 'pause' in context:
                data.pause = True
            context['data'] = data
            # _logger.info('Context: %s', context)
            data.end_attendance = emp_obj.attendance_action_change(cr, uid, [emp_id], action_type='sign_out', dt=data.date, context=context)
            context['type'] = 'sign_out'
            self._write(cr, uid, data, emp_id, context=context)
        return {'type': 'ir.actions.act_window_close'}

    def sign_out_result(self, cr, uid, ids, context=None):
        emp_obj = self.pool.get('hr.employee')
        for data in self.browse(cr, uid, ids, context=context):
            emp_id = data.emp_id.id
            cr.execute('SELECT id FROM hr_attendance WHERE employee_id=%s ORDER BY name DESC LIMIT 1', (emp_id,))
            data.start_attendance = (cr.fetchone() or (False,))[0]
            data.end_attendance = emp_obj.attendance_action_change(cr, uid, [emp_id], action_type='action', dt=data.date, context=data)
            context['type'] = 'action'
            self._write(cr, uid, data, emp_id, context=context)
        return {'type': 'ir.actions.act_window_close'}

hr_so_project()


class hr_si_project(orm.TransientModel):

    _name = 'hr.sign.in.task.work'
    _description = 'Sign In By Task Work'
    _columns = {
        'name': fields.char('Employees name', size=32, readonly=True),
        'state': fields.related('emp_id', 'state', string='Current state', type='char', required=True, readonly=True),
        'date': fields.datetime('Starting Date', help="Keep empty for current time"),
        'server_date': fields.datetime('Current Date', readonly=True, help="Local time on the server side"),
        'pause': fields.boolean('Break'),
        'action_desc': fields.many2one('hr.action.reason', 'Action description'),
        'workcontext': fields.many2one('tapoit.hr.project.workcontext', 'Work Context'),
        'emp_id': fields.many2one('hr.employee', 'Employee ID')
    }

    def get_emp_id(self, cr, uid, context=None):
        emp_obj = self.pool.get('hr.employee')
        emp_id = emp_obj.search(cr, uid, [('user_id', '=', uid)], context=context)

        if not emp_id:
            raise orm.except_orm(_('UserError'), _('No employee defined for your user !'))
        if len(emp_id) > 1:
            raise orm.except_orm(_('UserError'), _('More than one employee defined for this user! Please correct this issue'))
        return emp_id

    def _get_pause_state(self, cr, uid, context={}):
        emp_id = self.get_emp_id(cr, uid)
        pause = False
        res = cr.execute('SELECT pause FROM hr_attendance WHERE employee_id=%s AND action IN (\'sign_in\',\'sign_out\') ORDER BY name DESC LIMIT 1', emp_id)
        result = cr.fetchone()
        if result is not None:
            pause = result[0]
        return pause

    _defaults = {
        'emp_id': get_emp_id,
        'pause': _get_pause_state,
    }

    def check_state(self, cr, uid, field_list, context=None):
        context = dict(context or {})

        # _logger.info("Fields: %s | Context: %s", field_list, context)
        res = self.default_get(cr, uid, field_list, context)
        emp_id = res['emp_id']
        in_out = (res['state'] == 'absent') and 'out' or 'in'

        # get the latest action (sign_in or out) for this employee
        cr.execute('SELECT action FROM hr_attendance WHERE employee_id=%s AND action IN (\'sign_in\',\'sign_out\') ORDER BY name DESC LIMIT 1', (emp_id,))
        res = (cr.fetchone() or ('sign_out',))[0]
        in_out = (res == 'sign_out') and 'in' or 'out'

        obj_model = self.pool.get('ir.model.data')
        model_data_ids = obj_model.search(cr, uid, [('model', '=', 'ir.ui.view'), ('name', '=', 'view_hr_project_sign_%s' % in_out)], context=context)
        resource_id = obj_model.read(cr, uid, model_data_ids, fields=['res_id'], context=context)[0]['res_id']

        action = {
            'name': 'Sign in / Sign out',
            'view_type': 'form',
            'view_mode': 'form',
            'views': [(resource_id, 'form')],
            'res_model': 'hr.sign.%s.task.work' % in_out,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'domain': '[]',
            'context': dict(context, active_ids=field_list)
        }
        # _logger.info("Action: %s", action)
        return action

    def sign_in_break(self, cr, uid, ids, context=None):
        context = dict(context or {})

        context['pause'] = True
        return self.sign_in_result(cr, uid, ids, context)

    def sign_in_result(self, cr, uid, ids, context=None):
        context = dict(context or {})

        emp_obj = self.pool.get('hr.employee')
        for data in self.browse(cr, uid, ids, context=context):
            emp_id = data.emp_id.id
            if 'pause' in context:
                data.pause = True
            context['data'] = data
            # _logger.info('Context: %s', context)
            emp_obj.attendance_action_change(cr, uid, [emp_id], action_type='sign_in', dt=data.date or False, context=context)
        return {'type': 'ir.actions.act_window_close'}

    def default_get(self, cr, uid, fields_list, context=None):
        res = super(hr_si_project, self).default_get(cr, uid, fields_list, context=context)
        emp_obj = self.pool.get('hr.employee')
        emp_id = emp_obj.search(cr, uid, [('user_id', '=', uid)], context=context)
        if emp_id:
            for employee in emp_obj.browse(cr, uid, emp_id, context=context):
                res.update({'name': employee.name, 'state': employee.state, 'emp_id': emp_id[0], 'server_date': time.strftime('%Y-%m-%d %H:%M:%S')})
        return res

hr_si_project()
