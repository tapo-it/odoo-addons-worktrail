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

from openerp import netsvc, pooler
from openerp.osv import orm, osv, fields
from openerp.tools.translate import _
import json
import logging
import time


_logger = logging.getLogger(__name__)


class tapoit_worktrail_config(orm.Model):

    """ TaPo-IT Worktrail Config  """

    _name = "tapoit_worktrail.server.conf"
    _description = "Worktrail Server Configuration"

    def create(self, cr, uid, vals, context=None):
        context = dict(context or {})

        response = self.get_request_key(cr, uid, vals)

        if 'authtoken' in response:
            vals['request_key'] = response['requestkey']
            vals['auth_token'] = response['authtoken']
            vals['access_granted'] = 'pending'
            vals['redirect_url'] = response['redirecturl'].replace('tapolan', 'net')

        new_id = super(tapoit_worktrail_config, self).create(cr, uid, vals, context=context)
        return new_id

    def write(self, cr, uid, ids, vals, context=None):
        context = dict(context or {})

        _logger.info("DEBUG: %s", vals)

        for config in self.browse(cr, uid, ids):
            sync_type = vals.get('type', '')
            if config.type:
                sync_type = config.type

            values = {
                'host': vals.get('host', config.host),
                'secure': vals.get('secure', config.secure),
                'port': vals.get('port', config.port),
                'type': sync_type,
                'app_key': vals.get('app_key', config.app_key),
                'secret_api_key': vals.get('secret_api_key', config.secret_api_key),
            }

            if not vals.get('auth_token', config.auth_token):
                response = self.get_request_key(cr, uid, values)
                if 'authtoken' in response:
                    vals['request_key'] = response['requestkey']
                    vals['auth_token'] = response['authtoken']
                    vals['redirect_url'] = response['redirecturl'].replace('tapolan', 'net')

            values['request_key'] = vals.get('request_key', config.request_key)
            if values['request_key']:
                response = self.test_auth_token(cr, uid, values)
                if 'status' in response:
                    vals['access_granted'] = response['status']

                # header['X-AUTHTOKEN']
                # url = "%s://%s:%s/rest/token/auth/?requestkey=%s" % (config.protocol, config.host, config.port, response['requestkey'])
                # response = self.pool.get('tapoit_worktrail.sync.execution').json_request(cr, uid, url, data, header=header)

        return super(tapoit_worktrail_config, self).write(cr, uid, ids, vals, context=context)

    def get_request_key(self, cr, uid, vals):
        protocol = 'http'
        if 'secure' in vals:
            protocol = 'https'

        header = {
            'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
            'X-APPKEY': vals['app_key'],
            'X-SECRETAPIKEY': vals['secret_api_key'],
        }

        if 'type' in vals:
            if vals['type'] == 'workentries':
                data = {
                    'accesstype': 'company',
                    'scopes': 'read-tasks,write-tasks,read-employees,read-workentries,write-workentries',
                }
            elif vals['type'] == 'hubstream-personal':
                data = {
                    'accesstype': 'employee',
                    'scopes': 'sync-hub-data,read-employees',
                }
            else:
                raise orm.except_orm(_('Error !'), _('Type(%s) not possible!') % vals['type'])

        url = "%s://%s:%s/rest/token/request/" % (protocol, vals['host'], vals['port'])
        return self.pool.get('tapoit_worktrail.sync.execution').json_request(cr, uid, url, data, header=header)

    def test_auth_token(self, cr, uid, vals):
        protocol = 'http'
        if 'secure' in vals:
            protocol = 'https'

        header = {
            'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
            'X-APPKEY': vals['app_key'],
            'X-SECRETAPIKEY': vals['secret_api_key'],
        }
        data = {
            'requestkey': vals['request_key'],
        }
        url = "%s://%s:%s/rest/token/confirm/" % (protocol, vals['host'], vals['port'])
        return self.pool.get('tapoit_worktrail.sync.execution').json_request(cr, uid, url, data, header=header)

    def sync_messages_hubstream(self, cr, uid, ids, context=None):

        for config in self.browse(cr, uid, ids):
            protocol = 'http'
            if config.secure:
                protocol = 'https'

            header = {
                'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8',
                'X-APPKEY': config.app_key,
                'X-SECRETAPIKEY': config.secret_api_key,
                'X-AUTHTOKEN': config.auth_token,
            }

            url = "%s://%s:%s/rest/hub/entries/clean/" % (protocol, config.host, config.port)
            self.pool.get('tapoit_worktrail.sync.execution').json_request(cr, uid, url, {}, header=header)

            create = []
            user = self.pool.get('res.users').browse(cr, uid, uid)
            notifications = self.pool.get('mail.message')
            message_ids = notifications.search(cr, uid, [('author_id', '=', user.partner_id.id)])
            for message in notifications.browse(cr, uid, message_ids):
                create.append(
                    {
                        'time': self.pool.get('tapoit_worktrail.sync.execution').convertDatetime2Timestamp(cr, uid, message.date),
                        # 'endtime': OPTIONAL,
                        'srctype': 'other',
                        'summary': message.body
                        # 'link': OPTIONAL,
                    }
                )
            # _logger.info("Hubentries: %s", create)
            hubentries = {
                'create': create
            }
            data = {'data': json.dumps(hubentries)}
            url = "%s://%s:%s/rest/hub/entries/create/" % (protocol, config.host, config.port)
            return self.pool.get('tapoit_worktrail.sync.execution').json_request(cr, uid, url, data, header=header)

    def get_status(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {})

    def reset_app(self, cr, uid, ids, context=None):
        return self.write(cr, uid, ids, {'auth_token': False, 'request_key': False})

    STATE_ACCESS = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('rejected', 'Rejected'),
    ]

    _columns = {
        'active': fields.boolean('Active'),
        'dbname': fields.char('Local Database Name', size=80, required=True, help="This will constraint the sync to a certain database which does protect data integrity"),
        'name': fields.char('Name', size=50, select=1),
        'host': fields.char('Remote Host', size=200, required=True, select=1),
        'port': fields.char('Remote Port', size=5, required=True, select=1),
        'type': fields.selection(
            (
                ('workentries', 'Project/Task/Work Sync'),
                ('hubstream', 'Company Hub Stream'),
                ('hubstream-personal', 'Personal Hub Stream'),
            ),
            'Purpose', required=True
        ),
        'mode': fields.selection((('both', 'Two-Way Mode'), ('out', 'Outgoing Mode'), ('in', 'Incoming Mode')), 'Sync Mode'),
        'debug': fields.boolean('Debug Log'),
        'secure': fields.boolean('SSL/TLS'),

        # DEPRECATED
        'api_key': fields.char('API Key', size=200),

        'app_key': fields.char('Application Key', size=25, required=True),
        'secret_api_key': fields.char('Secret API Key', size=60, required=True),

        'request_key': fields.char('Request Key', size=25),
        'redirect_url': fields.char('Grant/Revoke access for OpenERP', size=200),
        'auth_token': fields.char('Auth Token', size=60),

        'access_granted': fields.selection(STATE_ACCESS, 'State'),
    }
    _order = "id"

    _defaults = {
        'port': lambda * a: 443,
        'secure': lambda * a: True,
        'active': lambda * a: True,
    }
tapoit_worktrail_config()


class tapoit_worktrail_sync(orm.Model):

    """ TaPo-IT Worktrail Sync History  """

    _name = "tapoit_worktrail.server.sync"
    _description = "Worktrail Server Sync"

    STATE_SYNC_HISTORY = [
        ('running', 'Running'),
        ('done', 'Done'),
        ('error', 'Error'),
        ('failed', 'Failed')
    ]

    _columns = {
        'sync_conf': fields.many2one('tapoit_worktrail.server.conf', 'Sync Server', required=True, select=True, ondelete='set null'),
        'sync_time': fields.datetime('Sync Time', readonly=True),
        'resources': fields.many2many('tapoit_worktrail.server.resource', 'tapoit_worktrail_resources_affected_rel', 'sync_id', 'resource_id', 'Resources affected', readonly=True),
        'duration': fields.float('Duration'),
        'state': fields.selection(STATE_SYNC_HISTORY, 'State'),
        'log': fields.text('Log')
    }

    _defaults = {
        'sync_time': lambda *a: time.strftime('%Y-%m-%d %H:%M:%S')
    }

    _order = "sync_time DESC"

tapoit_worktrail_sync()


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
