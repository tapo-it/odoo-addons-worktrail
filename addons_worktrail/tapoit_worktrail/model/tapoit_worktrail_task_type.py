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

from openerp.osv import orm, fields


class tapoit_worktrail_task_type(orm.Model):

    """ TaPo-IT Worktrail Task Types  """

    _name = "tapoit_worktrail.server.task.type"
    _description = "Worktrail Task Types"

    def _task_type_get(self, cr, uid, context=None):
        task_types = [('worktask', 'Task'), ('breaktask', 'Break'), ('timetask', 'Time')]
        return task_types

    _columns = {
        'type': fields.selection(_task_type_get, "Task Type", change_default=True),
        'task': fields.many2one('project.task', 'Task', select=True, ondelete='cascade'),
    }
tapoit_worktrail_task_type()
