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


class tapoit_worktrail_resource(orm.Model):

    """ TaPo-IT Worktrail Sync Mapping  """

    _name = "tapoit_worktrail.server.resource"
    _description = "Worktrail Resource Mapping"

    def _resource_type_get(self, cr, uid, context=None):
        resource_types = [('employee', 'Worktrail User'), ('project', 'Worktrail Project'), ('task', 'Worktrail Task'), ('work', 'Worktrail Task Work'), ('workcontext', 'Worktrail Work Context')]
        return resource_types

    def fields_get(self, cr, uid, fields=None, context=None):
        res = super(tapoit_worktrail_resource, self).fields_get(cr, uid, fields, context)
        resource = None
        if 'resource' in context:
            resource = context['resource']
        types = self._resource_type_get

        return res

    def onchange_resource_type(self, cr, uid, ids, resource=False, context=None):
        result = {}
        if resource:
            for type in ['employee', 'project', 'task', 'work', 'workcontext']:
                if resource not in type:
                    result[type] = ''
        else:
            for type in ['employee', 'project', 'task', 'work', 'workcontext']:
                result[type] = ''
        return {'value': result}

    _columns = {
        'sync_conf': fields.many2one('tapoit_worktrail.server.conf', 'Sync Server', required=True, select=True, ondelete='set null'),
        'external_id': fields.integer('Worktrail ID', required=True),
        'type': fields.selection(_resource_type_get, "Resource Type", change_default=True),
        'employee': fields.many2one('hr.employee', 'Employee', select=True, ondelete='set null'),
        'project': fields.many2one('project.project', 'Project', select=True, ondelete='set null'),
        'task': fields.many2one('project.task', 'Task', select=True, ondelete='set null'),
        'work': fields.many2one('project.task.work', 'Task Work', select=True, ondelete='set null'),
        'workcontext': fields.many2one('tapoit.hr.project.workcontext', 'Work Context', select=True, ondelete='set null'),
        'sync': fields.boolean('Sync'),
        'sync_remote_modified': fields.datetime('Worktrail Modified', readonly=True),
        'sync_openerp_modified': fields.datetime('OpenERP Modified', readonly=True),
    }
    _sql_constraints = [('employee_unique', 'unique(employee)', 'Employee/User must be unique!')]
    _order = "sync_openerp_modified DESC"
tapoit_worktrail_resource()
