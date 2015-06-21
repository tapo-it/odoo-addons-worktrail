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

from datetime import timedelta, datetime
from openerp import tools
from openerp.osv import orm, fields
from openerp.tools.translate import _
import logging
import time


_logger = logging.getLogger(__name__)


class project_work(orm.Model):
    _inherit = "project.task.work"
    _description = "Project Task Work"

    def _day_compute(self, cr, uid, ids, fieldnames, args, context=None):
        res = dict.fromkeys(ids, '')
        for obj in self.browse(cr, uid, ids, context=context):
            res[obj.id] = time.strftime('%Y-%m-%d', time.strptime(obj.date, '%Y-%m-%d %H:%M:%S'))
        return res

    def _year_compute(self, cr, uid, ids, fieldnames, args, context=None):
        res = dict.fromkeys(ids, '')
        for obj in self.browse(cr, uid, ids, context=context):
            res[obj.id] = time.strftime('%Y', time.strptime(obj.date, '%Y-%m-%d %H:%M:%S'))
        return res

    def _get_related_project_id(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        for task_work in self.browse(cr, uid, ids):
            if task_work.task_id:
                res[task_work.id] = task_work.task_id.project_id.id
        return res

    def _get_parent_ids(self, cr, uid, project_ids, object, done=None):
        if done is None:
            done = []

        if object.id not in done and object.parent_id:
            done.append(object.id)
            project_id = self.pool.get('project.project').search(cr, uid, [('analytic_account_id', '=', object.parent_id.id)])
            if project_id:
                project_ids.append(project_id[0])
            return self._get_parent_ids(cr, uid, project_ids, object.parent_id, done=done)
        else:
            return project_ids

    def _get_related_project_ids(self, cr, uid, ids, field_name, arg, context=None):
        res = {}
        for task_work in self.browse(cr, uid, ids):
            if task_work.task_id:
                res[task_work.id] = [task_work.task_id.project_id.id]

            res[task_work.id].extend(self._get_parent_ids(cr, uid, [], task_work.task_id.project_id))

        _logger.info("Project IDs: %s ", res)
        return res

    _columns = {
        'end_attendance': fields.many2one('hr.attendance', 'Related End Attendance ID', ondelete='set null'),
        'start_attendance': fields.many2one('hr.attendance', 'Related Start Attendance ID', ondelete='set null'),
        'project_id': fields.function(_get_related_project_id, store=True, method=True, type='many2one', relation="project.project", string='Projekt'),
        'project_ids': fields.function(_get_related_project_ids, store=False, method=True, type='one2many', relation="project.project", string='Übergeordnete Projekte'),
        'workcontext': fields.many2one('tapoit.hr.project.workcontext', 'Related Work Context ID', ondelete='set null'),
        'day': fields.function(_day_compute, type='char', string='Day', store=True, select=1, size=32),
        'year': fields.function(_year_compute, type='char', string='Year', store=True, select=1, size=32)
    }
    _defaults = {
        'date': fields.datetime.now
    }
    _order = "date DESC"

    def create(self, cr, uid, vals, *args, **kwargs):
        end_type = False
        if 'type' in kwargs:
            end_type = kwargs['type']
            del kwargs['type']
        if 'type' in vals:
            end_type = vals['type']
            del vals['type']
        context = None
        if 'context' in kwargs:
            context = kwargs['context']

        attendance_obj = self.pool.get('hr.attendance')
        emp_obj = self.pool.get('hr.employee')

        search_emp_id = emp_obj.search(cr, uid, [('user_id', '=', vals['user_id'])])
        for employee in search_emp_id:
            new_emp_id = employee

        if 'date' in vals:
            start_date = datetime.strptime(vals['date'], "%Y-%m-%d %H:%M:%S")
        else:
            start_date = datetime.now()

        end_date = start_date + timedelta(hours=vals['hours'])
        _logger.info("start: %s | end: %s", start_date, end_date)
        # Get rid of microseconds from vals['hours'] due to float
        end_date += timedelta(seconds=0.5)
        end_date -= timedelta(seconds=end_date.second % 1, microseconds=end_date.microsecond)

        vars = {'emp_id': new_emp_id, 'start_date': str(start_date), 'end_date': str(end_date), 'start_id': 0, 'end_id': 0, 'work_id': 0}
        _logger.debug("obstruction_check: %s", vars)
        if not self.check_obstruction(cr, uid, vars):
            return False

        excluded = []

        # get latest entry before start_date
        if 'start_attendance' not in vals:
            _logger.info('start_attendance: retrieve')
            action_type = self.get_start_action(cr, uid, vars)
            existing_start_id = attendance_obj.search(cr, uid, [('employee_id', '=', new_emp_id), ('name', '=', str(start_date))])
            if existing_start_id:
                vals['start_attendance'] = existing_start_id[0]
                existing_work_id = self.search(cr, uid, [('end_attendance', '=', vals['start_attendance'],)])
                if existing_work_id:
                    excluded.append(existing_work_id[0])
                attendance_obj.write(cr, uid, vals['start_attendance'], {'action': action_type, 'employee_id': new_emp_id, 'pause': False}, context={'exclude': excluded})
            else:
                vals['start_attendance'] = attendance_obj.create(cr, uid, {'action': action_type, 'employee_id': new_emp_id, 'name': str(start_date)})

        # TODO
        if end_type:
            action_type = end_type
        else:
            vars['start_date'] = end_date
            action_type = self.get_start_action(cr, uid, vars)
        _logger.info('create: %s', action_type)

        existing_end_id = attendance_obj.search(cr, uid, [('employee_id', '=', new_emp_id), ('name', '=', str(end_date))])
        if existing_end_id:
            vals['end_attendance'] = existing_end_id[0]
            existing_work_id = self.search(cr, uid, [('start_attendance', '=', vals['end_attendance'],)])
            if existing_work_id:
                excluded.append(existing_work_id[0])
            attendance_obj.write(cr, uid, vals['end_attendance'], {'action': action_type, 'employee_id': new_emp_id, 'pause': False}, context={'exclude': excluded})
        else:
            _logger.info('end_attendance: retrieve')
            if context and 'source' in context:
                vals['source'] = context['source']
            vals['end_attendance'] = emp_obj.attendance_action_change(cr, uid, [new_emp_id], action_type=action_type, dt=str(end_date), context=vals)

        if 'source' in vals:
            del vals['source']

        workcontext = False
        if 'workcontext' in vals:
            workcontext = vals['workcontext']

        # Update Attendance Entries (Action)
        start_update_context = {'position': 'start', 'start_handling': 'change', 'end_handling': 'change', 'workcontext': workcontext}
        end_update_context = {'position': 'end', 'start_handling': 'change', 'end_handling': 'change', 'workcontext': workcontext}
        if 'pause' in context:
            end_update_context['pause'] = context['pause']
        start_update = {'emp_id': new_emp_id, 'id': vals['start_attendance'], 'date': str(start_date)}
        self.update_attendance(cr, uid, start_update, context=start_update_context)
        end_update = {'emp_id': new_emp_id, 'id': vals['end_attendance'], 'date': str(end_date)}
        self.update_attendance(cr, uid, end_update, context=end_update_context)

        _logger.info('create: %s', vals)
        return super(project_work, self).create(cr, uid, vals, *args, **kwargs)

    def write(self, cr, uid, ids, vals, context=None):
        context = dict(context or {})

        attendance_obj = self.pool.get('hr.attendance')
        emp_obj = self.pool.get('hr.employee')

        work_ids = self.browse(cr, uid, ids, context=context)
        if isinstance(work_ids, orm.browse_record_list):
            _logger.info('More than one work is updated at once: %s', ids)

        resetter = vals

        # Check if only a link request is triggered and task work is already linked to desired task
        if 'task_id' in vals and work_ids[0].task_id.id == vals['task_id']:
            del vals['task_id']
        if len(vals) == 0:
            return super(project_work, self).write(cr, uid, ids, vals, context)

        for task_work in work_ids:
            vals = resetter
            current_user_id = False

            if task_work.id:
                task_work_browse = self.browse(cr, uid, task_work.id)

                start_id = task_work_browse.start_attendance.id
                end_id = task_work_browse.end_attendance.id
                current_user_id = task_work_browse.user_id.id

            if current_user_id:
                search_emp_id = emp_obj.search(cr, uid, [('user_id', '=', current_user_id)], context=context)

                for employee in search_emp_id:
                    emp_id = employee

            if 'date' not in resetter and 'hours' not in resetter and 'user_id' not in resetter:
                vals['date'] = task_work.date
                vals['hours'] = task_work.hours
                vals['start_attendance'] = task_work.start_attendance
                vals['end_attendance'] = task_work.end_attendance
                _logger.info('write: vals (%s)', vals)

            if 'user_id' not in resetter:
                vals['user_id'] = current_user_id
            if 'hours' not in resetter:
                vals['hours'] = task_work.hours
            if 'date' not in resetter:
                vals['date'] = task_work.date

            if not task_work.hr_analytic_timesheet_id:
                _logger.warning('No analytic timesheet id: %s', ids)

            # Updating analytic line when task/project has changed
            if task_work.hr_analytic_timesheet_id and 'task_id' in vals:
                vals_line = {}
                line_id = task_work.hr_analytic_timesheet_id.id
                task_search = self.pool.get('project.task').search(cr, uid, [('id', '=', vals['task_id'])])
                if task_search:
                    task_obj = self.pool.get('project.task').browse(cr, uid, task_search)[0]
                    vals_line['name'] = '%s: %s' % (tools.ustr(task_obj.name), tools.ustr(task_work.name) or '/')

                    project_obj = self.pool.get('project.project').browse(cr, uid, task_obj.project_id.id, context=context)
                    vals_line['account_id'] = project_obj.analytic_account_id.id
                    vals_line['to_invoice'] = project_obj.to_invoice.id
                    vals_line['sheet_id'] = task_work.hr_analytic_timesheet_id.sheet_id.id
                    _logger.info('Analytic line(%s) is updated: %s', line_id, vals_line)
                    self.pool.get('hr.analytic.timesheet').write(cr, uid, [line_id], vals_line, {})

            # Employee has been adapted
            if 'user_id' in vals and current_user_id != vals['user_id']:
                _logger.info('write: user id changed (%s => %s)', current_user_id, vals['user_id'])
                search_emp_id = emp_obj.search(cr, uid, [('user_id', '=', vals['user_id'])], context=context)
                for employee in search_emp_id:
                    new_emp_id = employee
                    _logger.info('write: employee id changed (%s => %s)', emp_id, new_emp_id)
            else:
                new_emp_id = emp_id
                _logger.info('write: employee id (%s)', new_emp_id)
            # Attendance resource for creating new attendances
            res = {'action': 'action', 'employee_id': new_emp_id}
            # Attendance resource for writing attendances
            attendance = {}
            _logger.info('write: attendance ids (%s, %s)', start_id, end_id)

            start_date = datetime.strptime(vals['date'], "%Y-%m-%d %H:%M:%S")
            end_date = start_date + timedelta(hours=vals['hours'])
            # Get rid of microseconds from vals['hours'] due to float
            end_date += timedelta(seconds=0.5)
            end_date -= timedelta(seconds=end_date.second % 1, microseconds=end_date.microsecond)

            vars = {'emp_id': new_emp_id, 'start_date': start_date, 'end_date': end_date, 'start_id': start_id, 'end_id': end_id, 'work_id': task_work.id}
            if not self.check_obstruction(cr, uid, vars, context):
                return False
            _logger.info('write: ====================== start_attendance ======================')
            existing_start_date = attendance_obj.search(cr, uid, [('employee_id', '=', new_emp_id), ('name', '=', str(start_date)), ('id', '!=', start_id)], context=context)
            vars['start_handling'] = False
            protect = False
            unlink = []
            excluded = []
            excluded.append(task_work.id)
            start_update = {}
            end_update = {}

            # Handling start timestamp / attendance
            if start_id != 0:
                start_attendance_obj = attendance_obj.browse(cr, uid, start_id)
                # Get work which also uses this timestamp
                worklink = self.search(cr, uid, [('end_attendance', '=', start_id,), ('id', '!=', task_work.id)], context=context)
                # There is a timestamp / attendance entry with the same start_date
                if existing_start_date:
                    vars['start_handling'] = 'merged'
                elif worklink:
                    vars['start_handling'] = 'splitted'
                    res['name'] = str(start_date)
                    res['action'] = self.get_start_action(cr, uid, vars)
                else:
                    vars['start_handling'] = 'change'

                    attendance['name'] = str(vals['date'])
                    attendance['employee_id'] = new_emp_id
                    attendance['action'] = self.get_start_action(cr, uid, vars)

                    if start_attendance_obj.action == 'sign_in' and (start_attendance_obj.name > str(start_date) and start_attendance_obj.name > str(end_date) or start_attendance_obj.name < str(start_date) and start_attendance_obj.name < str(end_date)):
                        vars['start_handling'] = 'preserve'

                # Check if the start date was modified
                if start_attendance_obj.name != str(start_date) or 'user_id' in vals and current_user_id != vals['user_id']:
                    if vars['start_handling'] == 'splitted':
                        vals['start_attendance'] = attendance_obj.create(cr, uid, res, context=context)
                        _logger.info('write: attendance splitted (%s)', start_attendance_obj.name)
                        start_update = {'emp_id': new_emp_id, 'id': start_id, 'date': start_attendance_obj.name}
                    elif vars['start_handling'] == 'merged':
                        vals['start_attendance'] = existing_start_date[0]

                        usage = self.search(cr, uid, [('end_attendance', '=', start_id,)], context=context)
                        if not usage and start_attendance_obj.action != 'sign_in' and start_attendance_obj.action != 'sign_out':
                            unlink.append(start_id)
                            _logger.info('write: attendance marked (%s)', start_id)
                        elif start_attendance_obj.action == 'sign_in':
                            if start_attendance_obj.name > str(start_date) and start_attendance_obj.name > str(end_date) or start_attendance_obj.name < str(start_date) and start_attendance_obj.name < str(end_date):
                                _logger.info('write: attendance preserve - sign in (%s)', start_id)
                            else:
                                unlink.append(start_id)
                                _logger.info('write: attendance marked (%s)', start_id)
                        elif start_attendance_obj.action == 'sign_out':
                            _logger.info('write: attendance preserve - sign in (%s)', start_id)
                        else:
                            _logger.info('write: attendance preserve - linked (%s)', start_id)

                        if usage:
                            excluded.append(usage[0])
                        _logger.info('write: Excluded (%s)', excluded)

                        attendance_obj.write(cr, uid, vals['start_attendance'], attendance, context={'exclude': excluded})
                        _logger.info('write: merged start date (%s)', start_date)
                        start_update = {'emp_id': new_emp_id, 'id': vals['start_attendance'], 'date': start_date}
                    else:
                        vals['start_attendance'] = start_id

                        if vars['start_handling'] == 'preserve':
                            # if no other action than preserved exists it will be sign in which is in conflict with the same sign in
                            if attendance['action'] == 'sign_in':
                                attendance['action'] = 'action'
                                _logger.info('write: correcting wrong attendance action due to being the first action at all')

                            vals['start_attendance'] = attendance_obj.create(cr, uid, attendance, context=context)
                            _logger.info('write: attendance preserve - sign in (%s)', start_id)
                            _logger.info('write: created start date (%s)', start_date)
                            start_update = {'emp_id': new_emp_id, 'id': vals['start_attendance'], 'date': start_date}
                        else:
                            attendance_obj.write(cr, uid, vals['start_attendance'], attendance, context={'exclude': excluded})
                            _logger.info('write: attendance change')
                            _logger.info('write: changed start date (%s)', start_date)
                else:
                    vals['start_attendance'] = start_id
                    _logger.info('write: unchanged (%s)', start_date)
            else:
                res['name'] = str(start_date)
                start_id = attendance_obj.search(cr, uid, [('employee_id', '=', new_emp_id), ('name', '=', str(start_date))], context=context)
                if existing_start_date:
                    vals['start_attendance'] = existing_start_date[0]
                    _logger.info('write: added start date (%s)', start_date)
                else:
                    vals['start_attendance'] = attendance_obj.create(cr, uid, res, context=context)
                    _logger.info('write: created start date (%s)', start_date)
                    start_update = {'emp_id': new_emp_id, 'id': vals['start_attendance'], 'date': start_date}

            _logger.info('write: ====================== end_attendance ======================')
            existing_end_date = attendance_obj.search(cr, uid, [('employee_id', '=', new_emp_id), ('name', '=', str(end_date)), ('id', '!=', end_id)], context=context)
            vars['end_handling'] = False
            # Handling end timestamp / attendance
            if end_id != 0:
                end_attendance_obj = attendance_obj.browse(cr, uid, end_id)
                current_end = self.browse(cr, uid, task_work.id)

                if vars['start_handling'] == 'merged' and vals['start_attendance'] == end_id:
                    protect = vals['start_attendance']
                # Get work which also uses this timestamp
                worklink = self.search(cr, uid, [('start_attendance', '=', end_id,), ('id', '!=', task_work.id)], context=context)
                if existing_end_date:
                    vars['end_handling'] = 'merged'
                elif worklink:
                    current_start_date = datetime.strptime(current_end.date, "%Y-%m-%d %H:%M:%S")
                    current_end_date = current_start_date + timedelta(hours=current_end.hours)
                    # Get rid of microseconds from vals['hours'] due to float
                    current_end_date += timedelta(seconds=0.5)
                    current_end_date -= timedelta(seconds=current_end_date.second % 1, microseconds=current_end_date.microsecond)

                    if current_end_date != end_date:
                        vars['end_handling'] = 'splitted'
                        res['name'] = str(end_date)
                        res['action'] = self.get_end_action(cr, uid, vars)
                    else:
                        vars['end_handling'] = 'change'
                        usage = self.search(cr, uid, [('start_attendance', '=', end_id,), ('id', '!=', task_work.id)], context=context)
                        if usage:
                            excluded.append(usage[0])
                else:
                    vars['end_handling'] = 'change'
                    if end_attendance_obj.action == 'sign_out':
                        if vars['start_handling'] == 'preserve':
                            vars['end_handling'] = 'preserve'
                        elif (end_attendance_obj.name < str(start_date) and end_attendance_obj.name < str(end_date) or end_attendance_obj.name > str(end_date) and end_attendance_obj.name > str(start_date)):
                            vars['end_handling'] = 'preserve'

                if vars['end_handling'] == 'change' or vars['end_handling'] == 'preserve':
                    attendance['name'] = str(end_date)
                    attendance['employee_id'] = new_emp_id
                    attendance['action'] = self.get_end_action(cr, uid, vars)

                if current_end.hours != vals['hours'] or str(current_end.date) != vals['date'] or 'user_id' in vals and current_user_id != vals['user_id']:

                    if vars['end_handling'] == 'splitted':
                        vals['end_attendance'] = attendance_obj.create(cr, uid, res, context=context)
                        _logger.info('write: attendance splitted (%s)', current_end.date)
                        _logger.info('write: created end date (%s)', end_date)
                        end_update = {'emp_id': new_emp_id, 'id': end_id, 'date': end_attendance_obj.name}
                    elif vars['end_handling'] == 'merged':
                        vals['end_attendance'] = existing_end_date[0]
                        usage = self.search(cr, uid, [('start_attendance', '=', end_id,), ('id', '!=', task_work.id)], context=context)
                        if usage:
                            excluded.append(usage[0])

                        if not usage and protect != vals['start_attendance'] and end_attendance_obj.action != 'sign_in' and end_attendance_obj.action != 'sign_out':
                            unlink.append(end_id)
                            _logger.info('write: attendance marked (%s)', end_id)
                        elif end_attendance_obj.action == 'sign_in':
                            _logger.info('write: attendance preserve - sign in (%s)', end_id)
                        elif end_attendance_obj.action == 'sign_out':
                            if end_attendance_obj.name < str(start_date) and end_attendance_obj.name < str(end_date) or end_attendance_obj.name > str(end_date) and end_attendance_obj.name > str(start_date):
                                _logger.info('write: attendance preserve - sign out (%s)', end_id)
                            else:
                                unlink.append(end_id)
                                _logger.info('write: attendance marked (%s)', end_id)  # 1
                        else:
                            _logger.info('write: attendance preserve - linked (%s)', end_id)
                        _logger.info('write: merged end date (%s)', end_date)
                        end_update = {'emp_id': new_emp_id, 'id': vals['end_attendance'], 'date': end_date}
                    else:
                        vals['end_attendance'] = end_id
                        if vars['end_handling'] == 'preserve' or protect == vals['start_attendance']:
                            vals['end_attendance'] = attendance_obj.create(cr, uid, attendance, context=context)
                            _logger.info('write: attendance preserve')
                            _logger.info('write: created end date (%s)', end_date)
                            end_update = {'emp_id': new_emp_id, 'id': vals['end_attendance'], 'date': end_date}
                        else:
                            attendance_obj.write(cr, uid, vals['end_attendance'], attendance, context={'exclude': excluded})
                            _logger.info('write: attendance change')
                            _logger.info('write: changed end date (%s)', end_date)
                else:
                    vals['end_attendance'] = end_id
                    _logger.info('write: unchanged (%s)', end_id)
            else:
                res['name'] = str(end_date)
                if existing_end_date:
                    vals['end_attendance'] = existing_end_date[0]
                    _logger.info('write: added end date (%s)', end_date)
                else:
                    vals['end_attendance'] = attendance_obj.create(cr, uid, res, context=context)
                    _logger.info('write: created end date (%s)', end_date)
                    end_update = {'emp_id': new_emp_id, 'id': vals['end_attendance'], 'date': end_date}

        _logger.info('write: ====================== post_processing ======================')
        if vals['end_attendance'] == start_id:
            if start_id in unlink:
                unlink.remove(start_id)
        for id in unlink:
            attendance_obj.unlink(cr, uid, id, context={'exclude': excluded, 'project_task_write': True})
            _logger.info('write: attendance unlinked (%s)', id)

        # Finally update attendances of merged/splitted attendances (after preserving sign_in and sign_out and updating actual attendances)
        workcontext = None
        if 'workcontext' in vals:
            workcontext = vals['workcontext']

        context['start_handling'] = vars['start_handling']
        context['end_handling'] = vars['end_handling']
        context['workcontext'] = workcontext

        if not start_update:
            start_update = {'emp_id': vars['emp_id'], 'id': vars['start_id'], 'date': vars['start_date']}
        context['position'] = 'start'
        self.update_attendance(cr, uid, start_update, context=context)

        if not end_update:
            end_update = {'emp_id': vars['emp_id'], 'id': vars['end_id'], 'date': vars['end_date']}
        context['position'] = 'end'
        self.update_attendance(cr, uid, end_update, context=context)

        _logger.info('write: %s', vals)
        return super(project_work, self).write(cr, uid, ids, vals, context)

    def unlink(self, cr, uid, ids, *args, **kwargs):
        attendance_obj = self.pool.get('hr.attendance')
        delete_all = False
        if 'context' in kwargs and 'all_attendance_delete' in kwargs['context']:
            delete_all = True
        for task_work in self.browse(cr, uid, ids):
            start_id = task_work.start_attendance.id
            end_id = task_work.end_attendance.id

            # ONLY DELETE UNIQUE ATTENDANCES (NOT SIGN IN AND OUT)
            if start_id != 0:
                start_attendance_obj = attendance_obj.browse(cr, uid, start_id)
                unique_start = self.search(cr, uid, [('end_attendance', '=', start_id), ('id', '!=', task_work.id)])
                _logger.info('start: %s', [unique_start, delete_all])
                if not unique_start and start_attendance_obj.action == 'action':
                    attendance_obj.unlink(cr, uid, start_id, context={'exclude': [task_work.id]})
                    _logger.info('unlink: start attendance (%s)', start_id)

                if unique_start and start_attendance_obj:
                    _logger.info('update attendance after delete: %s', [unique_start, start_attendance_obj.pause])
                    start_attendance_obj.action = 'sign_out'
                    start_attendance_obj.pause = self.pool.get('hr.attendance').check_pre_attendance_pause_begin(cr, uid, start_id, {})
                    self.updateAttendances(cr, uid, start_attendance_obj, context={'workcontext': self.browse(cr, uid, unique_start)[0].workcontext})

            if end_id != 0:
                end_attendance_obj = attendance_obj.browse(cr, uid, end_id)
                unique_end = self.search(cr, uid, [('start_attendance', '=', end_id), ('id', '!=', task_work.id)])
                _logger.info('end: %s', [unique_end, delete_all])
                if not unique_end and end_attendance_obj.action == 'action':
                    attendance_obj.unlink(cr, uid, end_id, context={'exclude': [task_work.id]})
                    _logger.info('unlink: end attendance (%s)', end_id)

                if unique_end and end_attendance_obj:
                    _logger.info('update attendance after delete: %s', [unique_end, end_attendance_obj.pause])
                    end_attendance_obj.action = 'sign_in'
                    end_attendance_obj.pause = False
                    self.updateAttendances(cr, uid, end_attendance_obj, context={'workcontext': self.browse(cr, uid, unique_end)[0].workcontext})

            if 'context' in kwargs and 'all_attendance_delete' in kwargs['context']:
                delete_all = kwargs['context']['all_attendance_delete']

                # DELETE ALL ATTENDANCES BASED ON TASK WORK
                if not unique_start and delete_all:
                    _logger.info('start delete all: %s', [unique_start, delete_all])
                    attendance_obj.unlink(cr, uid, start_id, context={'exclude': [task_work.id]})

        _logger.info('unlink: work (%s)', ids)
        return super(project_work, self).unlink(cr, uid, ids, *args, **kwargs)

    # RETRIEVE ATTENDANCE ANCESTOR
    def get_start_action(self, cr, uid, vars):
        attendance_obj = self.pool.get('hr.attendance')
        action = "action"
        action_check = attendance_obj.search(cr, uid, [('employee_id', '=', vars['emp_id']), ('id', '!=', vars['start_id']), ('name', '<', str(vars['start_date']))], order='name desc', limit=1)
        if action_check:
            pre = attendance_obj.browse(cr, uid, action_check[0])
            _logger.info('attendance: pre: %s - %s', pre.action, pre.name)
            if attendance_obj.browse(cr, uid, action_check[0]).action == 'sign_out':
                action = 'sign_in'
        else:
            _logger.info('attendance: pre: not found')
            action = 'sign_in'
        _logger.info('attendance: current: %s - %s', action, vars['start_date'])
        return action

    # RETRIEVE ATTENDANCE SUCCESSOR
    def get_end_action(self, cr, uid, vars):
        attendance_obj = self.pool.get('hr.attendance')
        action = "action"
        action_check = attendance_obj.search(cr, uid, [('employee_id', '=', vars['emp_id']), ('id', '!=', vars['end_id']), ('name', '>', str(vars['end_date']))], order='name asc', limit=1)
        if action_check:
            post = attendance_obj.browse(cr, uid, action_check[0])
            _logger.info('attendance: post: %s - %s', post.action, post.name)
            if attendance_obj.browse(cr, uid, action_check[0]).action == 'sign_in':
                action = 'sign_out'
        else:
            _logger.info('attendance: post: not found')
            if vars['end_id']:
                current = attendance_obj.browse(cr, uid, [vars['end_id']])[0]
                if current.action == 'sign_out':
                    action = current.action

        _logger.info('attendance: current: %s - %s', action, vars['end_date'])
        return action

    def updateAttendances(self, cr, uid, attendance_obj, context=None):
        vals = {
            'action': attendance_obj.action,
            'pause': attendance_obj.pause
        }
        if attendance_obj.action_desc:
            vals['action_desc'] = attendance_obj.action_desc.id

        if context:
            # Retrieving reason from work context
            if 'workcontext' in context and isinstance(context['workcontext'], orm.browse_record):
                reason = self.pool.get('tapoit.hr.project.workcontext').retrieve_reason_from_workcontext(cr, uid, workcontext=context['workcontext'], action_type=attendance_obj.action, pause=attendance_obj.pause)
                if reason:
                    vals['action_desc'] = reason

        if self.pool.get('hr.attendance').write(cr, uid, [attendance_obj.id], vals):
            return attendance_obj.id
        else:
            return False

    # RETRIEVE PROPER ACTION TYPE FOR ATTENDANCE
    def update_attendance(self, cr, uid, vars, context=None):
        pre = post = pause = False
        action = "action"

        context = dict(context or {})

        if 'position' in context:
            position = context['position']
        if 'workcontext' in context:
            workcontext = context['workcontext']
        if 'pause' in context:
            pause = context['pause']

        attendance_obj = self.pool.get('hr.attendance')

        action_check = attendance_obj.search(cr, uid, [('employee_id', '=', vars['emp_id']), ('name', '<', str(vars['date']))], order='name DESC', limit=1)
        if action_check:
            pre = attendance_obj.browse(cr, uid, action_check[0])
        action_check = attendance_obj.search(cr, uid, [('employee_id', '=', vars['emp_id']), ('name', '>', str(vars['date']))], order='name ASC', limit=1)
        if action_check:
            post = attendance_obj.browse(cr, uid, action_check[0])

        current = attendance_obj.browse(cr, uid, [vars['id']])[0]

        if not pre:
            action = 'sign_in'
        elif pre.action == 'sign_out':
            action = 'sign_in'
        if not post:
            if current.action == 'sign_out':
                action = current.action
            else:
                action = 'action'

        elif post.action == "sign_in":
            action = 'sign_out'

        if pre and post:
            if pre.action == 'sign_in' and post.action == 'sign_in':
                if position == 'start':
                    action = 'action'
                else:
                    action = 'sign_out'
            elif pre.action == 'sign_in' and post.action == 'action':
                action = 'action'
            elif pre.action == 'sign_in' and post.action == 'sign_out':
                action = 'action'
            elif pre.action == 'action' and post.action == 'sign_in':
                action = 'sign_out'
            elif pre.action == 'action' and post.action == 'sign_out':
                action = 'action'
            elif pre.action == 'action' and post.action == 'action':
                action = 'action'

        update_vals = {}
        if action != current.action:
            update_vals['action'] = action

        # Retrieve reason based on Work Context
        if workcontext:
            workcontext = self.pool.get('tapoit.hr.project.workcontext').browse(cr, uid, [workcontext])[0]
            if not current.pause and not pause:
                current.pause = self.pool.get('hr.attendance').check_pre_attendance_pause_begin(cr, uid, current.id, context)
                update_vals['pause'] = current.pause
            elif pause:
                current.pause = pause
                update_vals['pause'] = pause

            reason = self.pool.get('tapoit.hr.project.workcontext').retrieve_reason_from_workcontext(cr, uid, workcontext=workcontext, action_type=action, pause=current.pause)
            _logger.info('Work Context: %s | Reason: %s', workcontext, reason)
            if reason:
                update_vals['action_desc'] = reason
        if update_vals:
            attendance_obj.write(cr, uid, vars['id'], update_vals)
        return True

    # SEARCH FOR OBSTRUCTIONS
    def check_obstruction(self, cr, uid, vars, context=None):
        context = dict(context or {})

        attendance_obj = self.pool.get('hr.attendance')
        search = [('employee_id', '=', vars['emp_id']), ('name', '>', str(vars['start_date'])), ('name', '<', str(vars['end_date']))]
        unique_start = self.search(cr, uid, [('end_attendance', '=', vars['start_id']), ('id', '!=', vars['work_id'])], context=context)
        if not unique_start:
            search.append(('id', '!=', vars['start_id']))
            _logger.info('write: search append (start_id)')
        unique_end = self.search(cr, uid, [('start_attendance', '=', vars['end_id']), ('id', '!=', vars['work_id'])], context=context)
        if not unique_end:
            search.append(('id', '!=', vars['end_id']))
            _logger.info('write: search append (end_id)')
        obstruction = attendance_obj.search(cr, uid, search, context=context)

        if obstruction:
            _logger.info('obstruction: %s, %s', obstruction, vars)
            important_attendance4work = self.search(cr, uid, ['&', '|', ('id', '!=', vars['work_id']), ('start_attendance', 'in', obstruction), ('end_attendance', 'in', obstruction)])
            if not important_attendance4work:
                _logger.info('Attendance(s) will be unlinked %s', obstruction)
                attendance_obj.unlink(cr, uid, obstruction, context={'obstructions_remove': True})
            else:
                _logger.info('write: conflicting with work and attendance id (%s)', obstruction[0])
                raise orm.except_orm(_('Task Work Conflict - Attendance Timestamp'), _('This work (%s) conflicts with another work or attendance entry (%s).') % (vars['work_id'], repr(obstruction[0],)))
                return False
        else:
            cr.execute(
                """
                    SELECT
                        p.id AS obstruction_work
                    FROM hr_attendance h
                    JOIN project_task_work p ON h.id = p.start_attendance
                    WHERE
                        (SELECT name FROM hr_attendance WHERE id = p.start_attendance) <= %s
                    AND
                        (SELECT name FROM hr_attendance WHERE id = p.end_attendance) >= %s
                    AND h.employee_id = %s
                    AND p.id <> %s
                """, (vars['start_date'], vars['end_date'], vars['emp_id'], vars['work_id'])
            )
            result = cr.dictfetchall()
            if len(result) != 0:
                _logger.info('write: positioned in work (%s)', result[0]['obstruction_work'])
                raise orm.except_orm(_('Task Work Conflict - Attendance Timestamp'), _('This work (%s) conflicts with another work (%s) or attendance entry.') % (vars['work_id'], repr(result[0]['obstruction_work'],)))
                return False

        return True

project_work()
