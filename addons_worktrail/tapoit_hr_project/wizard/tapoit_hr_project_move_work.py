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

from openerp import netsvc

from openerp.osv import orm, fields
import logging

_logger = logging.getLogger(__name__)


class hr_project_move_work(orm.TransientModel):
    _name = 'hr.move.task.work'
    _description = 'Move project task work'
    _columns = {
        'work_ids': fields.many2many('project.task.work', 'hr_task_work_rel', 'rel_id', 'work_id', 'Works', required=True),
        'target_task_id': fields.many2one('project.task', 'Target Task', required=True),
    }

    def move_selection(self, cr, uid, id, *args, **kwargs):
        logger = netsvc.Logger()

        move_obj = self.browse(cr, uid, id)[0]
        target_id = move_obj.target_task_id.id

        vals = {}
        updated = []
        update_remaining = {}
        add_time = 0

        for work in move_obj.work_ids:
            obj_work = self.pool.get('project.task.work').browse(cr, uid, work.id)
            update_task = [1, work.id, {'name': unicode(obj_work.name), 'task_id': target_id}]

            if obj_work.task_id.id in update_remaining:
                update_remaining[obj_work.task_id.id] += obj_work.hours
            else:
                update_remaining[obj_work.task_id.id] = obj_work.hours

            add_time += obj_work.hours

            updated.append(update_task)
            self.pool.get('project.task.work').write(cr, uid, [work.id], {'task_id': target_id})

        obj_task = self.pool.get('project.task')

        for task in update_remaining:
            source_task = obj_task.browse(cr, uid, [task])[0]
            if source_task.state == 'draft':
                remaining_hours = 0
            else:
                if source_task.remaining_hours != 0 and source_task.planned_hours - source_task.effective_hours > 0:
                    remaining_hours = source_task.remaining_hours + update_remaining[task]
                else:
                    remaining_hours = source_task.planned_hours - source_task.effective_hours
            if remaining_hours < 0:
                remaining_hours = 0

            obj_task.write(cr, uid, [task], {'remaining_hours': remaining_hours})
            _logger.info('move_selection: time task (%s) remaining', task)

        target_task = obj_task.browse(cr, uid, target_id)
        if target_task.remaining_hours - add_time > 0:
            if target_task.remaining_hours > 0:
                vals['remaining_hours'] = target_task.remaining_hours - add_time
            elif target_task.planned_hours - target_task.effective_hours > 0:
                vals['remaining_hours'] = target_task.planned_hours - target_task.effective_hours
            else:
                vals['remaining_hours'] = 0
        else:
            vals['remaining_hours'] = 0

        vals['project_id'] = target_task.project_id.id
        vals['work_ids'] = updated

        _logger.info('move_selection: vals (%s) remaining', vals)
        self.pool.get('project.task').write(cr, uid, [target_id], vals)
        _logger.info('move_selection: update task (%s) for project_timesheet', target_id)

        return {'type': 'ir.actions.act_window_close'}

hr_project_move_work()
