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

from openerp.tools.translate import _
import logging

_logger = logging.getLogger(__name__)


class hr_attendance(orm.Model):
    _inherit = 'hr.attendance'
    _columns = {
        'pause': fields.boolean('Break')
    }
    _defaults = {
        'name': fields.datetime.now
    }
    _order = "name DESC"

    # not required to inherit create
    def create(self, cr, uid, vals, context=None):
        context = dict(context or {})

        # Automation: Logic change of pre and post processor? follow up write in project.task.work inherited create, write
        # TODO

        if 'sheet_id' in context:
            ts = self.pool.get('hr_timesheet_sheet.sheet').browse(cr, uid, context['sheet_id'], context=context)
            if ts.state not in ('draft', 'new'):
                raise orm.except_orm(_('Error !'), _('You cannot modify an entry in a confirmed timesheet !'))

        res = super(hr_attendance, self).create(cr, uid, vals, context=context)
        if 'sheet_id' in context:
            if context['sheet_id'] != self.browse(cr, uid, res, context=context).sheet_id.id:
                raise orm.except_orm(_('UserError'), _('You cannot enter an attendance '
                                                       'date outside the current timesheet dates!'))
        return res

    def write(self, cr, uid, ids, vals, context=None):
        context = dict(context or {})

        context['handling'] = 'modify'
        context['hint'] = '\n\nPlease modify the duration, time and employee/user directly with the task work!'

        if 'name' in vals or 'employee_id' in vals:
            self.check_linked_work(cr, uid, ids, context=context)
        else:
            _logger.info('write: timestamp or employee_id were not changed (%s) | vals: %s', ids, vals)
        # Automation: Change of pre and post processor? follow up write in project.task.work inherited create, write
        # TODO
        workcontext = False
        pause = self.check_pre_attendance_pause_begin(cr, uid, ids, context)
        # Get related workcontext (always start_attendance)

        if not isinstance(ids, (list)):
            ids = [ids]
        related_task_work = self.pool.get('project.task.work').search(cr, uid, [('start_attendance', 'in', ids)])
        if not related_task_work:
            related_task_work = self.pool.get('project.task.work').search(cr, uid, [('end_attendance', 'in', ids)])

        if related_task_work:
            task_work = self.pool.get('project.task.work').browse(cr, uid, related_task_work)[0]
            workcontext = task_work.workcontext
        return super(hr_attendance, self).write(cr, uid, ids, vals, context=context)

    def unlink(self, cr, uid, ids, context=None):
        context = dict(context or {})

        excluded = []
        if 'exclude' in context:
            for id in context['exclude']:
                excluded.append(id)
            context['exclude'] = excluded

        context['handling'] = 'delete'
        context['hint'] = '\n\nPlease delete the task work first!'
        self.check_linked_work(cr, uid, ids, context=context)
        if not isinstance(ids, list):
            ids = [ids]
        own_list = self.browse(cr, uid, ids)
        if own_list:
            for own in own_list:
                # Delete or modify atttendances (sign_in and sign_out only) next to deleted attendance to preserve the logic itself and support the user
                if 'project_task_write' not in context and 'obstructions_remove' not in context:

                    _logger.info('Object: %s', own.id)
                    if own.action == 'sign_in':
                        action_check = self.search(cr, uid, [('employee_id', '=', own.employee_id.id), ('name', '>', own.name)], order='name asc', limit=1)
                        if action_check:
                            post = self.browse(cr, uid, action_check[0])
                            if post.action == 'action':
                                # add pre_deleted to context for indicating that the predecesor will be deleted
                                self.write(cr, uid, post.id, {'action': own.action}, context={'pre_deleted': True})
                            elif post.action == 'sign_out':
                                if 'trigger' not in context:
                                    context['trigger'] = own.id
                                if context['trigger'] != post.id:
                                    _logger.info('POST DELETE: %s', own.id)
                                    self.unlink(cr, uid, post.id, context=context)
                                    del context['trigger']
                                    ids = filter(lambda a: a != post.id, ids)

                    elif own.action == 'sign_out':
                        action_check = self.search(cr, uid, [('employee_id', '=', own.employee_id.id), ('name', '<', own.name)], order='name desc', limit=1)
                        if action_check:
                            pre = self.browse(cr, uid, action_check[0])
                            if pre.action == 'action':
                                self.write(cr, uid, pre.id, {'action': own.action})
                            elif pre.action == 'sign_in':
                                if 'trigger' not in context:
                                    context['trigger'] = own.id
                                if context['trigger'] != pre.id:
                                    _logger.info('PRE DELETE: %s', own.id)
                                    self.unlink(cr, uid, pre.id, context=context)
                                    del context['trigger']
                                    ids = filter(lambda a: a != pre.id, ids)
                            else:
                                _logger.info('Object: %s', own)
        return super(hr_attendance, self).unlink(cr, uid, ids, context=context)

    def _check(self, cr, uid, ids):

        if isinstance(ids, int):
            own = self.browse(cr, uid, [ids])
        else:
            own = self.browse(cr, uid, ids)
        if not isinstance(own, list):
            own = [own]

        for att in own:
            if att.sheet_id and att.sheet_id.state not in ('draft', 'new'):
                raise orm.except_orm(_('Error !'), _('You cannot modify an entry in a confirmed timesheet !'))
        return True

    def check_linked_work(self, cr, uid, ids, context=None):
        search_base = []
        context = dict(context or {})

        if 'exclude' in context:
            for id in context['exclude']:
                search_base.append(('id', '!=', id))

        workobj = self.pool.get('project.task.work')
        emp_obj = self.pool.get('hr.employee')

        if isinstance(ids, int):
            ids = [ids]
        attendance_browse = self.browse(cr, uid, ids)

        for attendance in attendance_browse:
            search_list = search_base
            search_list.append('|')
            search_list.append(('start_attendance', '=', attendance.id))
            search_list.append(('end_attendance', '=', attendance.id))
            search = workobj.search(cr, uid, search_list)
            if search:
                if len(search) > 1:
                    text = ''
                    x = 1
                    for id in search:
                        text = text + str(id)
                        if (x < len(search)):
                            text = text + ', '
                        x = x + 1
                else:
                    text = str(search[0])
                _logger.info('write: You can not %s the attendance %s because it is linked to this/these task work entry/entries (%s)!%s', context['handling'], attendance.id, text, context['hint'])
                raise orm.except_orm(_('Dependency Error!'), _('You can not %s the attendance %s because it is linked to this/these task work entry/entries (%s)!%s') % (context['handling'], attendance.id, text, context['hint'],))

        return True

    def check_pre_attendance_pause_begin(self, cr, uid, ids, context=None):
        if not isinstance(ids, list):
            ids = [ids]

        if len(ids) == 1:
            current = self.browse(cr, uid, ids)
            if isinstance(current, orm.browse_record_list):
                current = current[0]
            if 'pre_deleted' in context:
                offset = 1
            else:
                offset = 0

            action_check = self.search(cr, uid, [('employee_id', '=', current.employee_id.id), ('name', '<', str(current.name))], order='name DESC', limit=1, offset=offset)

            if action_check:
                if isinstance(action_check, list):
                    action_check = action_check[0]
                pre = self.browse(cr, uid, action_check)
                # if sign in check reason of the ancestor (pause adaption)
                if pre and pre.action == 'sign_out' and pre.action_desc.pause:
                    _logger.debug('Pre Reason: %s | Current Pause: %s', pre.action_desc.pause, current.action_desc.pause)
                    return True
        return False

    # Neutralize constraint b/c it is not working properly with actions
    def _altern_si_so(self, cr, uid, ids, context=None):
        return True

    _constraints = [(_altern_si_so, 'Error: Sign in (resp. Sign out) must follow Sign out (resp. Sign in)', ['action'])]

hr_attendance()
