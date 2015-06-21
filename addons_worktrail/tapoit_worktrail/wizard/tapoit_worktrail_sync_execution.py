# -*- coding: utf-8 -*-
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
from datetime import timedelta, datetime
from openerp.osv import orm
from openerp.tools import misc
from openerp.tools.translate import _
from string import find
from urllib2 import *
import json
import logging
import pytz
import urllib


_logger = logging.getLogger(__name__)

MAPPING = {
    'draft': 'project_tt_analysis',
    'open': 'project_tt_development',
    'cancelled': 'project_tt_cancel',
    'done': 'project_tt_deployment',
    'pending': 'project_tt_testing',
}


class tapoit_worktrail_sync_execution(orm.TransientModel):

    """ TaPo-IT Worktrail Sync Execution  """

    _name = "tapoit_worktrail.sync.execution"
    _description = "Worktrail Sync Execution"

    def __init__(self, cr, uid, *args, **kwargs):
        super(tapoit_worktrail_sync_execution, self).__init__(cr, uid, *args, **kwargs)
        self.sync_conf = self.pool.get('tapoit_worktrail.server.conf')
        self.sync = self.pool.get('tapoit_worktrail.server.sync')
        self.resource = self.pool.get('tapoit_worktrail.server.resource')
        self.tasktype = self.pool.get('tapoit_worktrail.server.task.type')
        self.employee = self.pool.get('hr.employee')
        self.attendance = self.pool.get('hr.attendance')
        self.project = self.pool.get('project.project')
        self.task = self.pool.get('project.task')
        self.work = self.pool.get('project.task.work')
        self.workcontext = self.pool.get('tapoit.hr.project.workcontext')

        self.log = ''
        self.sync_id = False
        self.state = ''
        self.sync_vars = {}
        self.affected = []

    def event_log(self, loglevel, text):
        if (loglevel == 'info'):
            _logger.info(text)
        elif (loglevel == 'warning'):
            _logger.warning(text)
        elif (loglevel == 'error'):
            _logger.error(text)
        elif (loglevel == 'critical'):
            _logger.critical(text)
        elif (loglevel == 'debug'):
            _logger.debug(text)

        if not self.sync_vars or self.sync_vars and self.sync_vars['debug']:
            u = datetime.utcnow()
            u = u.replace(tzinfo=pytz.utc)
            self.log += datetime.astimezone(u, pytz.timezone("CET")).strftime('%Y-%m-%d %H:%M:%S') + u' (' + unicode(loglevel) + u'): ' + unicode(text) + '\n'

    def json_request(self, cr, uid, url, data, header=None, context=None):
        context = dict(context or {})

        if header is None:
            header = {'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8', }
            header['X-APPKEY'] = self.sync_vars['app_key']
            header['X-SECRETAPIKEY'] = self.sync_vars['secret_api_key']
            header['X-AUTHTOKEN'] = self.sync_vars['auth_token']

        response = False
        data = urllib.urlencode(data)
        req = Request(url, data, header)
        try:
            f = urlopen(req)
            response = json.loads(f.read())
            f.close()
        except HTTPError, e:
            self.sync_vars['debug'] = True
            self.state = u'error'
            self.event_log('error', 'Error Code: %s' % e.code)
            self.event_log('error', 'URL: %s' % url)
            self.event_log('error', 'Data: %s' % urlparse.parse_qs(data))
            if 'runtype' in self.sync_vars and self.sync_vars['runtype'] == 'Automatic':
                self.sync_vars['debug'] = False
        except URLError, e:
            self.sync_vars['debug'] = True
            self.state = u'error'
            self.event_log('error', 'URL Code: %s' % e.reason)
            self.event_log('error', 'Data: %s' % urlparse.parse_qs(data))
            if 'runtype' in self.sync_vars and self.sync_vars['runtype'] == 'Automatic':
                self.sync_vars['debug'] = False
        except:
            self.sync_vars['debug'] = True
            self.state = u'error'
            self.event_log('error', 'Unknown Error')
            if 'runtype' in self.sync_vars and self.sync_vars['runtype'] == 'Automatic':
                self.sync_vars['debug'] = False

        if response and 'errortype' in response:
            self.sync_vars['debug'] = True
            self.state = 'failed'
            self.event_log('error', 'Sync (%s) Error: %s' % (self.sync_id, response['errortype']))
            self.closeSync(cr, uid, context=context)

            if self.sync_vars and self.sync_vars['runtype'] != 'Automatic':
                raise orm.except_orm(_('Error !'), _('%s') % (response['errortype']))
            return False

        return response

    def get_all_json_results(self, cr, uid, url, data, params):
        list = []
        response = self.json_request(cr, uid, url, data)
        if response and 'num_pages' in response:
            count = response['num_pages']
            for y in range(0, count):
                ext_params = ''
                for item in response['list']:
                    list.append(item)
                if count > 1 and count > (y + 1):
                    ext_params = '&page=%s' % (y + 2)
                    n_url = "%s%s" % (url, ext_params)
                    response = self.json_request(cr, uid, n_url, data)

        if response:
            return list
        else:
            return False

    def sync_check(self, cr, uid, obj_local, obj_sync, obj_remote):
        if obj_sync.type == 'project':
            res_id = obj_sync.project.id
        elif obj_sync.type == 'task':
            res_id = obj_sync.task.id
        elif obj_sync.type == 'work':
            res_id = obj_sync.work.id
        elif obj_sync.type == 'employee':
            res_id = obj_sync.employee.id
        elif obj_sync.type == 'workcontext':
            res_id = obj_sync.workcontext.id

        sync_worktrail_write = self.convertDatetime2Timestamp(cr, uid, obj_sync.sync_remote_modified)
        sync_openerp_write = self.convertDatetime2Timestamp(cr, uid, obj_sync.sync_openerp_modified)
        remote_write = obj_remote['modifydate']

        # self.event_log('debug', 'Objekt: %s, Local ID: %s, Perm: %s' % (bj_sync.type, res_id, obj_local.perm_read(cr, uid, [res_id])))
        local_write = False
        if res_id:
            perm_obj = obj_local.browse(cr, uid, [res_id])
            if perm_obj:
                local_write = self.convertDatetime2Timestamp(cr, uid,
                                                             perm_obj.write_date  # or perm_obj[0].get('create_date', 'n/a')
                                                             )

        sync = {'incoming': False, 'outgoing': False}

        # self.event_log('debug', 'Objekt: %s, Local ID: %s, %s < %s, %s' % (obj_sync.type, res_id, datetime.fromtimestamp(sync_worktrail_write), datetime.fromtimestamp(remote_write), obj_remote ))
        if int(sync_worktrail_write) < int(remote_write):
            self.event_log('info', '[Time Remote] Modified: %s' % datetime.fromtimestamp(remote_write))
            self.event_log('info', '[Time Remote] Sync: %s' % datetime.fromtimestamp(sync_worktrail_write))
            sync['incoming'] = True

        if local_write and int(local_write) > int(sync_openerp_write):
            self.event_log('info', '[Time Local] Sync (%s): %s' % (res_id, datetime.fromtimestamp(sync_openerp_write)))
            self.event_log('info', '[Time Local] Modified (%s): %s' % (res_id, datetime.fromtimestamp(local_write)))
            sync['outgoing'] = True

        return sync

    def createUserLink(self, cr, uid, obj, modifydates, context=None):
        context = dict(context or {})

        new_user = self.resource.create(cr, uid, {
            'type': 'employee',
            'external_id': obj['id'],
            'sync_openerp_modified': datetime.now().strftime(misc.DEFAULT_SERVER_DATETIME_FORMAT),
            'sync_remote_modified': datetime.fromtimestamp(obj['modifydate']),
            'sync_conf': self.sync_vars['id']
        })
        self.affected.append(new_user)
        modifydates.append(obj['modifydate'])
        return modifydates

    def createUser(self, cr, uid, obj, modifydates, context=None):
        context = dict(context or {})

        # TODO: Creation of Users
        return True

    def syncUser(self, cr, uid, obj, modifydates, context=None):
        context = dict(context or {})

        # TODO: Rest API and incoming/outgoing sync
        return True

    def createProject(self, cr, uid, project, direction, modifydates):
        if direction == 'incoming':
            project_vals = {
                'name': project['name'],
                'description': project['description'],
                'planned_hours': project['time_planned'] / 3600,
                'effective_hours': project['time_effective'] / 3600,
                'total_hours': project['time_total'] / 3600
            }
            res_obj = self.getResourceFromExternalID(cr, uid, project['assigned_to'], 'employee')
            if res_obj:
                project_vals['user_id'] = res_obj.employee.user_id.id

            self.event_log('debug', 'Worktrail -> OpenERP Project Creation: %s' % project_vals)

            new_project_id = self.project.create(cr, project_vals.get('user_id', uid), project_vals)

            perm_obj = self.project.browse(cr, uid, [new_project_id])
            if perm_obj:
                sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

            res_project_vals = {
                'type': 'project',
                'external_id': project['id'],
                'project': new_project_id,
                'sync': True,
                'sync_openerp_modified': sync_openerp_modified,
                'sync_remote_modified': datetime.fromtimestamp(project['modifydate']),
                'sync_conf': self.sync_vars['id']
            }
            res_project_id = self.resource.create(cr, uid, res_project_vals)
            self.affected.append(res_project_id)
            modifydates.append(project['modifydate'])
            cr.commit()
        elif direction == 'outgoing':
            if project.state == 'close':
                mapped_state = 'done'
            else:
                mapped_state = project.state
            attr = {
                'name': project.name,
                'description': project.description or '',
                'state': mapped_state,
                'time_effective': project.effective_hours * 3600,
                'time_total': project.total_hours * 3600,
                'time_planned': project.planned_hours * 3600,
            }

            res_obj = self.getResourceFromLocalObject(cr, uid, self.getEmployee(cr, uid, project.user_id), 'employee')
            if res_obj:
                attr['assigned_to'] = res_obj.external_id

            data = {'project': json.dumps(attr)}
            self.event_log('debug', 'OpenERP -> Worktrail Project Creation: %s' % data)

            url = "%s://%s:%s/rest/projects/create/" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'])
            response = self.json_request(cr, uid, url, data)
            if response and response['status'] == 'success':
                external_project = response['id']
                self.event_log('debug', 'OpenERP -> Worktrail Project Creation: %s' % response)
            else:
                external_project = 0
            sync_remote_modified = datetime.fromtimestamp(response['project']['modifydate'])

            project_vals = {
                'type': 'project',
                'external_id': external_project,
                'project': project.id,
                'sync': True,
                'sync_openerp_modified': datetime.now().strftime(misc.DEFAULT_SERVER_DATETIME_FORMAT),
                'sync_remote_modified': sync_remote_modified,
                'sync_conf': self.sync_vars['id']
            }
            new_project = self.resource.create(cr, uid, project_vals)
            modifydates.append(response['project']['modifydate'])
            self.affected.append(new_project)
            cr.commit()
        else:
            self.event_log('info', 'No creation direction defined')
        return modifydates

    def syncProject(self, cr, uid, obj, modifydates, context=None):
        context = dict(context or {})

        sync_conflict = True

        if not obj['remote']:
            self.event_log('info', 'Remote Object is missing')
            return False
        syncflow = self.sync_check(cr, uid, obj['local'], obj['sync'], obj['remote'])
        if syncflow['incoming'] and syncflow['outgoing'] and sync_conflict:
            self.event_log('info', 'Sync Conflict: Local Project (%s) | Sync Object (%s) | Remote Project (%s)' % (obj['sync'].project.id, obj['sync'].id, obj['sync'].external_id))
        else:
            if syncflow['incoming'] and 'name' in obj['remote']:
                self.event_log('info', 'Sync Incoming')
                self.event_log('debug', 'Remote Object: %s' % obj['remote'])

                project_vals = {
                    'name': obj['remote']['name'],
                    'description': obj['remote']['description'],
                    # 'planned_hours': obj['remote']['time_planned'] / 3600,
                    # 'effective_hours': obj['remote']['time_effective'] / 3600,
                    # 'total_hours': obj['remote']['time_total'] / 3600
                }
                res_obj = self.getResourceFromExternalID(cr, uid, obj['remote']['assigned_to'], 'employee')
                if res_obj:
                    project_vals['user_id'] = res_obj.employee.user_id.id

                self.event_log('info', 'Worktrail -> OpenERP Project Update: %s' % project_vals)

                obj['local'].write(cr, uid, [obj['sync'].project.id], project_vals)

                perm_obj = obj['local'].browse(cr, uid, [obj['sync'].project.id])
                if perm_obj:
                    sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

                res_project_vals = {
                    'sync_openerp_modified': sync_openerp_modified,
                    'sync_remote_modified': datetime.fromtimestamp(obj['remote']['modifydate']),
                }
                res_project_id = self.resource.write(cr, uid, [obj['sync'].id], res_project_vals)
                self.affected.append(obj['sync'].id)
                modifydates.append(obj['remote']['modifydate'])
                cr.commit()
            elif syncflow['incoming']:
                self.event_log('info', 'Sync Incoming w/ insufficient remote data')

            if syncflow['outgoing']:
                self.event_log('info', 'Sync Outgoing')
                project = obj['sync'].project
                if project.state == 'close':
                    mapped_state = 'done'
                else:
                    mapped_state = project.state
                attr = {
                    'id': obj['sync'].external_id,
                    'name': project.name,
                    'description': project.description or '',
                    'state': mapped_state,
                    'time_effective': project.effective_hours * 3600,
                    'time_total': project.total_hours * 3600,
                    'time_planned': project.planned_hours * 3600,
                }
                res_obj = self.getResourceFromLocalObject(cr, uid, self.getEmployee(cr, uid, project.user_id), 'employee')
                if res_obj:
                    attr['assigned_to'] = res_obj.external_id

                data = {'project': json.dumps(attr)}
                self.event_log('info', 'OpenERP -> Worktrail Project Update: %s' % data)
                url = "%s://%s:%s/rest/projects/update/" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'])
                response = self.json_request(cr, uid, url, data)
                if response and response['status'] == 'success':
                    external_project = response['id']
                    sync_remote_modified = response['project']['modifydate']
                    self.event_log('info', 'OpenERP -> Worktrail Project Update: %s' % response)
                else:
                    external_project = 0

                perm_obj = obj['local'].browse(cr, uid, [obj['sync'].project.id])
                if perm_obj:
                    sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

                res_project_vals = {
                    'sync_openerp_modified': sync_openerp_modified,
                    'sync_remote_modified': datetime.fromtimestamp(sync_remote_modified),
                }
                res_project_id = self.resource.write(cr, uid, [obj['sync'].id], res_project_vals)
                self.affected.append(obj['sync'].id)
                modifydates.append(sync_remote_modified)
                cr.commit()
                # self.event_log('info', 'Projekt: %s | %s' % (project, attr) )

        return modifydates

    def createTask(self, cr, uid, task, direction, modifydates):
        if direction == 'incoming':
            res_obj = self.getResourceFromExternalID(cr, uid, task['project_id'], 'project')
            if res_obj:
                task_vals = {
                    'name': task['summary'],
                    'state': task['state'],
                    'planned_hours': task['time_planned'] / 3600,
                    'remaining_hours': task['time_remaining'] / 3600,
                    'total_hours': task['time_total'] / 3600,
                    'effective_hours': task['time_effective'] / 3600,
                    'project_id': res_obj.project.id,
                    'description': task['description'],
                    'notes': task['notes'] or '',
                }

                # Retrieve the stage from state
                if task_vals['state']:
                    stage_id = self._getRelatedStageID(cr, uid, task_vals['state'])
                    if stage_id:
                        task_vals['stage_id'] = stage_id
                    del task_vals['state']

                res_obj = self.getResourceFromExternalID(cr, uid, task['assigned_to'], 'employee')
                if res_obj:
                    task_vals['user_id'] = res_obj.employee.user_id.id

                self.event_log('info', 'Worktrail -> OpenERP Task Creation: %s' % task_vals)
                new_task_id = self.task.create(cr, task_vals.get('user_id', uid), task_vals)
                tasktype_rel_id = self.tasktype.create(cr, uid, {'type': task['task_type'], 'task': new_task_id})

                perm_obj = self.task.browse(cr, uid, [new_task_id])
                if perm_obj:
                    sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

                sync_remote_modified = datetime.fromtimestamp(task['modifydate'])

                if 'parent_id' in task and task['parent_id']:
                    res_obj = self.getResourceFromExternalID(cr, uid, task['parent_id'], 'task')
                    if res_obj:
                        # TODO: RESPECT parent_ids which are created later
                        parent_ids = [res_obj.task.id]
                        self.task.write(cr, uid, [new_task_id], {'parent_ids': [(6, 0, set(parent_ids))]})
                    else:
                        sync_remote_modified = datetime.fromtimestamp(task['modifydate'] - 60)
                res_task_vals = {
                    'type': 'task',
                    'external_id': task['id'],
                    'task': new_task_id,
                    'sync_openerp_modified': sync_openerp_modified,
                    'sync_remote_modified': sync_remote_modified,
                    'sync': True,
                    'sync_conf': self.sync_vars['id']
                }
                res_task_id = self.resource.create(cr, uid, res_task_vals)
                self.affected.append(res_task_id)
                modifydates.append(task['modifydate'])
                cr.commit()
        elif direction == 'outgoing':
            res_obj = self.getResourceFromLocalObject(cr, uid, task.project_id, 'project')
            if res_obj:
                task_state = False
                for state, external_id in MAPPING.items():
                    mod_obj = self.pool.get('ir.model.data')
                    stage_ids = mod_obj.get_object_reference(cr, uid, 'project', external_id)
                    if stage_ids and stage_ids[1] == task.stage_id.id:
                        task_state = state

                attr = {
                    'project_id': res_obj.external_id,
                    'progress': task.progress,
                    'active': task.active,
                    'notes': task.notes or '',
                    'summary': task.name,
                    'description': task.description or '',
                    'state': task_state,
                    'time_effective': task.effective_hours * 3600,
                    'time_total': task.total_hours * 3600,
                    'time_planned': task.planned_hours * 3600,
                }

                res_obj = self.getResourceFromLocalObject(cr, uid, self.getEmployee(cr, uid, task.user_id), 'employee')
                if res_obj:
                    attr['assigned_to'] = res_obj.external_id

                if task.parent_ids:
                    for parent_id in task.parent_ids:
                        res_obj = self.getResourceFromLocalObject(cr, uid, parent_id, 'task')
                        if res_obj:
                            attr['parent_id'] = res_obj.external_id
                        else:
                            test = False
                            # sync_openerp_modified = ''

                data = {'task': json.dumps(attr)}
                self.event_log('debug', 'OpenERP -> Worktrail Task Creation: %s' % data)

                url = "%s://%s:%s/rest/tasks/create/" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'])
                response = self.json_request(cr, uid, url, data)
                if response and response['status'] == 'success':
                    external_task = response['id']
                    self.event_log('debug', 'OpenERP -> Worktrail Task Creation: %s' % response)
                else:
                    external_task = 0

                res_task_vals = {
                    'type': 'task',
                    'external_id': external_task,
                    'task': task.id,
                    'sync': True,
                    'sync_openerp_modified': datetime.now().strftime(misc.DEFAULT_SERVER_DATETIME_FORMAT),
                    'sync_remote_modified': datetime.fromtimestamp(response['task']['modifydate']),
                    'sync_conf': self.sync_vars['id']
                }
                new_task = self.resource.create(cr, uid, res_task_vals)
                self.affected.append(new_task)
                modifydates.append(response['task']['modifydate'])
                cr.commit()
        else:
            self.event_log('info', 'No creation direction defined')

        return modifydates

    def syncTask(self, cr, uid, obj, modifydates, context=None):
        context = dict(context or {})

        sync_conflict = True

        # Type of Changes (Sync Mode)
        # incoming (in, both)
        # outgoing (out, both)
        # conflict (both)

        syncflow = self.sync_check(cr, uid, obj['local'], obj['sync'], obj['remote'])
        if syncflow['incoming'] and syncflow['outgoing'] and sync_conflict:
            self.event_log('info', 'Sync Conflict: Local Task (%s) | Sync Object (%s) | Remote Task (%s)' % (obj['sync'].task.id, obj['sync'].id, obj['sync'].external_id))
        else:
            # SYNC INCOMING
            if syncflow['incoming'] or (syncflow['incoming'] and syncflow['outgoing']):
                self.event_log('info', 'Sync Incoming')
                self.event_log('debug', 'Remote Object: %s' % obj['remote'])
                res_obj = self.getResourceFromExternalID(cr, uid, obj['remote']['project_id'], 'project')
                task_vals = {
                    'name': obj['remote']['summary'],
                    'state': obj['remote']['state'],
                    'planned_hours': obj['remote']['time_planned'] / 3600,
                    # 'remaining_hours': obj['remote']['time_remaining'] / 3600,
                    # 'total_hours': obj['remote']['time_total'] / 3600,
                    # 'effective_hours': obj['remote']['time_effective'] / 3600,
                    'project_id': res_obj.project.id,
                    'description': obj['remote']['description'],
                    'notes': obj['remote']['notes'],
                }
                # Retrieve the stage from state
                if task_vals['state']:
                    stage_id = self._getRelatedStageID(cr, uid, task_vals['state'])
                    if stage_id and obj['sync'].task.stage_id.id != stage_id:
                        task_vals['stage_id'] = stage_id
                    del task_vals['state']

                if res_obj.project and obj['sync'].task.project_id.id == res_obj.project.id:
                    del task_vals['project_id']

                if res_obj.project and obj['sync'].task.name == task_vals['name']:
                    del task_vals['name']

                if res_obj.project and obj['sync'].task.description == task_vals['description']:
                    del task_vals['description']

                if res_obj.project and obj['sync'].task.notes == task_vals['notes']:
                    del task_vals['notes']

                if res_obj.project and obj['sync'].task.planned_hours == task_vals['planned_hours']:
                    del task_vals['planned_hours']

                res_obj = self.getResourceFromExternalID(cr, uid, obj['remote']['assigned_to'], 'employee')
                if res_obj and obj['sync'].task.user_id.id != res_obj.employee.user_id.id:
                    task_vals['user_id'] = res_obj.employee.user_id.id

                if obj['sync'].task.id:
                    obj['local'].write(cr, task_vals.get('user_id', uid), [obj['sync'].task.id], task_vals)

                    tasktype_id = self.tasktype.search(cr, uid, [('task', '=', obj['sync'].task.id)])
                    if not tasktype_id:
                        tasktype_rel_id = self.tasktype.create(cr, uid, {'type': obj['remote']['task_type'], 'task': obj['sync'].task.id})
                    else:
                        tasktype_rel_id = self.tasktype.write(cr, task_vals.get('user_id', uid), tasktype_id, {'type': obj['remote']['task_type'], 'task': obj['sync'].task.id})

                    perm_obj = obj['local'].browse(cr, uid, [obj['sync'].task.id])
                    if perm_obj:
                        sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

                    res_task_vals = {
                        'sync_openerp_modified': sync_openerp_modified,
                        'sync_remote_modified': datetime.fromtimestamp(obj['remote']['modifydate']),
                    }
                    res_task_id = self.resource.write(cr, task_vals.get('user_id', uid), [obj['sync'].id], res_task_vals)
                    self.affected.append(obj['sync'].id)
                    modifydates.append(obj['remote']['modifydate'])
                    cr.commit()
                else:
                    self.event_log('info', "This task has been deleted before...you are probably out of sync")
            # SYNC OUTGOING
            if syncflow['outgoing']:
                self.event_log('info', 'Sync Outgoing')
                task = obj['local'].browse(cr, uid, obj['sync'].task.id, context=context)

                res_obj = self.getResourceFromLocalObject(cr, uid, task.project_id, 'project')
                if res_obj:

                    task_state = False
                    for state, external_id in MAPPING.items():
                        mod_obj = self.pool.get('ir.model.data')
                        stage_ids = mod_obj.get_object_reference(cr, uid, 'project', external_id)
                        if stage_ids:
                            stage_id = stage_ids[1]
                        if stage_id == task.stage_id.id:
                            task_state = state

                    attr = {
                        'id': obj['sync'].external_id,
                        'project_id': res_obj.external_id,
                        'progress': task.progress,
                        'active': task.active,
                        'notes': task.notes or '',
                        'summary': task.name,
                        'description': task.description or '',
                        'state': task_state,
                        'time_effective': task.effective_hours * 3600,
                        'time_total': task.total_hours * 3600,
                        'time_planned': task.planned_hours * 3600,
                    }
                    res_obj = self.getResourceFromLocalObject(cr, uid, self.getEmployee(cr, uid, task.user_id), 'employee')
                    if res_obj:
                        attr['assigned_to'] = res_obj.external_id

                    if task.parent_ids:
                        for parent_id in task.parent_ids:
                            res_obj = self.getResourceFromLocalObject(cr, uid, parent_id, 'task')
                            if res_obj:
                                attr['parent_id'] = res_obj.external_id
                    data = {'task': json.dumps(attr)}
                    self.event_log('debug', 'OpenERP -> Worktrail Task Update: %s' % data)
                    url = "%s://%s:%s/rest/tasks/update/" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'])
                    response = self.json_request(cr, uid, url, data)
                    if response and response['status'] == 'success':
                        external_task = response['id']
                        sync_remote_modified = response['task']['modifydate']
                        self.event_log('debug', 'OpenERP -> Worktrail Task Update: %s' % response)
                    else:
                        external_task = 0

                    perm_obj = obj['local'].browse(cr, uid, [obj['sync'].task.id])
                    if perm_obj:
                        sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

                    res_task_vals = {
                        'sync_openerp_modified': sync_openerp_modified,
                        'sync_remote_modified': datetime.fromtimestamp(sync_remote_modified),
                    }
                    res_task_id = self.resource.write(cr, uid, [obj['sync'].id], res_task_vals)
                    self.affected.append(obj['sync'].id)
                    modifydates.append(sync_remote_modified)
                    cr.commit()
        return modifydates

    def createTaskWork(self, cr, uid, work, direction, modifydates, context=None):
        context = dict(context or {})

        if direction == 'incoming':
            if work['status'] == 'active':
                workcontext = self.getWorkContextFromResource(cr, uid, work)
                work_entry = {'name': work['description'], 'workcontext': None}

                res_obj = self.getResourceFromExternalID(cr, uid, work['taskid'], 'task')
                if res_obj:
                    work_entry['task_id'] = res_obj.task.id
                    if work_entry['task_id']:
                        employee_obj = self.getResourceFromExternalID(cr, uid, work['employee'], 'employee')
                        if employee_obj:
                            work_entry['user_id'] = employee_obj.employee.user_id.id
                        work_entry['date'] = datetime.strftime(datetime.fromtimestamp(work['start']['time']), "%Y-%m-%d %H:%M:%S")
                        if workcontext:
                            work_entry['workcontext'] = workcontext.id

                        # Which type of task work has to be created
                        task_type = 'worktask'
                        res_id = self.tasktype.search(cr, uid, [('task', '=', work_entry['task_id'])])
                        if res_id:
                            task_type = self.tasktype.browse(cr, uid, res_id)[0].type
                        self.event_log('info', '[Task Typ] %s' % task_type)

                        if task_type != 'breaktask':
                            if task_type == 'timetask':
                                self.event_log('info', '[Syncing Time Task] Local Task (%s)' % work_entry['task_id'])
                            else:
                                self.event_log('info', '[Syncing Work Task] Local Task (%s)' % work_entry['task_id'])

                            # We need a result which is not integer
                            work_seconds = (work['end']['time'] - work['start']['time'])
                            work_entry['hours'] = work_seconds / 3600.0
                            if task_type == 'timetask' and work_seconds < 60:
                                self.event_log('warning', '[ALERT] TimeTask has less than 60 seconds (exactly %s seconds)' % (work_seconds))
                            else:
                                # APPLY WORKCONTEXT + TASK TYPE for start and end attendance
                                context['source'] = 'worktrail'
                                new_work_id = self.work.create(cr, work_entry['user_id'], work_entry, type=work['end']['type'], context=context)

                                perm_obj = self.work.browse(cr, uid, [new_work_id])
                                if perm_obj:
                                    sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

                                if new_work_id:
                                    resource_entry = {
                                        'type': 'work',
                                        'external_id': work['id'],
                                        'work': new_work_id,
                                        'sync': True,
                                        'sync_openerp_modified': sync_openerp_modified,
                                        'sync_remote_modified': datetime.fromtimestamp(work['modifydate']),
                                        'sync_conf': self.sync_vars['id']
                                    }

                                    res_work_id = self.resource.create(cr, uid, resource_entry)
                                    self.affected.append(res_work_id)
                                    modifydates.append(work['modifydate'])
                                    cr.commit()
                        else:
                            self.event_log('info', '[Syncing Break Task] Local Task (%s)' % work_entry['task_id'])
                            # CORRECT start_attendance and end_attendance timestamps - apply workcontext reasons and set pause + change action_type
                            start_attendance_time = work_entry['date']
                            end_attendance_time = datetime.strftime(datetime.fromtimestamp(work['end']['time']), "%Y-%m-%d %H:%M:%S")

                            context['workcontext'] = workcontext
                            # START
                            start_id = self.attendance.search(cr, uid, [('name', '=', start_attendance_time)])
                            if start_id:
                                attendance_obj = self.attendance.browse(cr, uid, start_id)[0]
                                attendance_obj.pause = True
                                attendance_obj.action = 'sign_out'
                                start_id_success = self.updateAttendances(cr, uid, attendance_obj, context=context)
                                self.event_log('info', '[Break Task Timestamp] Start Attendance ID: %s' % start_id_success)
                                self.event_log('info', '[Break Task Timestamp] Action: %s' % (self.attendance.browse(cr, uid, start_id_success).action))
                            # END
                            end_id = self.attendance.search(cr, uid, [('name', '=', end_attendance_time)])
                            if end_id:
                                attendance_obj = self.attendance.browse(cr, uid, end_id)[0]
                                attendance_obj.pause = True
                                attendance_obj.action = 'sign_in'
                                end_id_success = self.updateAttendances(cr, uid, attendance_obj, context=context)
                                self.event_log('info', '[Break Task Timestamp] End Attendance ID: %s' % end_id_success)
                                self.event_log('info', '[Break Task Timestamp] Action: %s' % (self.attendance.browse(cr, uid, end_id_success).action))

                            cr.commit()
                    else:
                        self.event_log('info', 'Task of this work is not in sync')
            else:
                # Task work has been created and deleted before getting synced
                self.event_log('debug', 'Work will not be synced: %s' % work['status'])
        elif direction == 'outgoing':
            res_obj = self.getResourceFromLocalObject(cr, uid, work.task_id, 'task')
            if res_obj:
                attr = {
                    'taskid': res_obj.external_id,
                    'description': work.name,
                    'start': {
                        'time': self.convertDatetime2Timestamp(cr, uid, work.date),
                        'type': 'sign_in',
                        'reason': ''
                    },
                    'end': {
                        'time': self.convertDatetime2Timestamp(cr, uid, work.date) + work.hours * 3600,
                        'type': 'sign_out',
                        'reason': ''
                    }
                }

                employee_id = self.employee.search(cr, uid, [('user_id', '=', work.user_id.id)])
                if employee_id:
                    res_obj = self.getResourceFromLocalObject(cr, uid, self.employee.browse(cr, uid, employee_id)[0], 'employee')
                    attr['employee'] = res_obj.external_id

                workcontext = self.getResourceFromLocalObject(cr, uid, work.workcontext, 'workcontext')
                if workcontext:
                    attr['workcontext'] = workcontext.external_id
                else:
                    attr['workcontext'] = 0

                if work.start_attendance:
                    attr['start']['type'] = work.start_attendance.action
                    attr['end']['type'] = work.end_attendance.action
                    if work.start_attendance.action_desc:
                        attr['start']['reason'] = work.start_attendance.action_desc.name
                    if work.end_attendance.action_desc:
                        attr['end']['reason'] = work.end_attendance.action_desc.name
                else:
                    # Try to retrieve the start_attendance and link it (hr_project)
                    endtime = self.convertDatetime2Timestamp(cr, uid, work.date) + work.hours * 3600
                    if employee_id:
                        start_attendance = self.attendance.search(cr, uid, [('employee_id', '=', employee_id), ('name', '=', work.date)])
                        end_attendance = self.attendance.search(cr, uid, [('employee_id', '=', employee_id), ('name', '=', datetime.fromtimestamp(endtime).strftime(misc.DEFAULT_SERVER_DATETIME_FORMAT))])
                        self.event_log('info', "Start ID: %s End ID: %s" % (start_attendance, end_attendance))
                        if start_attendance:
                            cr.execute("""UPDATE project_task_work SET start_attendance = %s WHERE id = %s""", (start_attendance[0], work.id))
                            attr['start']['reason'] = self.attendance.browse(cr, uid, start_attendance)[0].action_desc.name
                        if end_attendance:
                            cr.execute("""UPDATE project_task_work SET end_attendance = %s WHERE id = %s""", (end_attendance[0], work.id))
                            attr['end']['reason'] = self.attendance.browse(cr, uid, end_attendance)[0].action_desc.name

                data = {'workentry': json.dumps(attr)}
                self.event_log('debug', 'OpenERP -> Worktrail Task Work Creation: %s' % data)

                url = "%s://%s:%s/rest/workentries/create/" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'])
                response = self.json_request(cr, uid, url, data)
                if response and response['status'] == 'success':
                    external_work = response['id']
                    self.event_log('debug', 'OpenERP -> Worktrail Task Work Creation: %s' % response)

                    res_work_vals = {
                        'type': 'work',
                        'external_id': external_work,
                        'work': work.id,
                        'sync': True,
                        'sync_openerp_modified': datetime.now().strftime(misc.DEFAULT_SERVER_DATETIME_FORMAT),
                        'sync_remote_modified': datetime.fromtimestamp(response['workentry']['modifydate']),
                        'sync_conf': self.sync_vars['id']
                    }
                    new_workentry = self.resource.create(cr, uid, res_work_vals)
                    self.affected.append(new_workentry)
                    modifydates.append(response['workentry']['modifydate'])
                    cr.commit()
                else:
                    self.event_log('error', 'OpenERP -> Worktrail Task Work Creation: %s' % data)
        else:
            self.event_log('info', 'No creation direction defined')

        return modifydates

    def syncTaskWork(self, cr, uid, obj, modifydates, work_ids, context=None):
        context = dict(context or {})

        sync_conflict = False

        syncflow = self.sync_check(cr, uid, obj['local'], obj['sync'], obj['remote'])
        if syncflow['incoming'] and syncflow['outgoing'] and sync_conflict:
            self.event_log('info', 'Sync Conflict: Local Work (%s) | Sync Object (%s) | Remote Work (%s)' % (obj['sync'].work.id, obj['sync'].id, obj['sync'].external_id))
        else:
            if syncflow['incoming'] or (syncflow['incoming'] and syncflow['outgoing']):
                self.event_log('info', 'Sync Incoming')
                self.event_log('debug', 'Remote Object: %s' % obj['remote'])

                if obj['remote']['status'] == 'active' and obj['sync'].work.id:
                    workcontext = self.getWorkContextFromResource(cr, uid, obj['remote'])
                    work_vals = {'name': obj['remote']['description']}
                    res_obj = self.getResourceFromExternalID(cr, uid, obj['remote']['taskid'], 'task')
                    if res_obj:
                        work_vals['task_id'] = res_obj.task.id
                        if work_vals['task_id']:
                            task_type = 'Kein Tasktyp'
                            res_id = self.tasktype.search(cr, uid, [('task', '=', work_vals['task_id'])])
                            if res_id:
                                task_type = self.tasktype.browse(cr, uid, res_id)[0].type
                            self.event_log('info', '[Task Type] %s' % task_type)

                            employee_obj = self.getResourceFromExternalID(cr, uid, obj['remote']['employee'], 'employee')
                            if employee_obj:
                                work_vals['user_id'] = employee_obj.employee.user_id.id

                            work_vals['date'] = datetime.strftime(datetime.fromtimestamp(obj['remote']['start']['time']), "%Y-%m-%d %H:%M:%S")
                            if workcontext:
                                work_vals['workcontext'] = workcontext.id

                            # Get corresponeded start and end attendances
                            start_attendance_time = work_vals['date']
                            end_attendance_time = datetime.strftime(datetime.fromtimestamp(obj['remote']['end']['time']), "%Y-%m-%d %H:%M:%S")
                            start_id = self.attendance.search(cr, uid, [('name', '=', start_attendance_time)])
                            end_attendance_obj = False

                            if start_id:
                                start_attendance_obj = self.attendance.browse(cr, uid, start_id)[0]
                                if not start_attendance_obj.pause or obj['remote']['start']['type'] == "action":
                                    start_attendance_obj.action = obj['remote']['start']['type']
                                    start_attendance_obj.pause = False
                                else:
                                    start_attendance_obj.action = 'sign_in'
                                    start_attendance_obj.pause = True

                            end_id = self.attendance.search(cr, uid, [('name', '=', end_attendance_time)])
                            if end_id:
                                end_attendance_obj = self.attendance.browse(cr, uid, end_id)[0]
                                end_attendance_obj.action = obj['remote']['end']['type']
                                end_attendance_obj.pause = False
                            # If Sign out was starting a pause Sign in must be pause as well
                            if obj['remote']['end']['type'] == 'sign_out' and start_id and end_attendance_obj:
                                end_attendance_obj.pause = start_attendance_obj.pause

                            # Only if the work is not a breaktask it will be booked
                            if task_type != 'breaktask':
                                if employee_obj:
                                    work_vals['user_id'] = employee_obj.employee.user_id.id
                                    # We need a result which is not integer
                                    work_vals['hours'] = (obj['remote']['end']['time'] - obj['remote']['start']['time']) / 3600.0

                                    self.event_log('info', 'Start: %s, End: %s, Diff: %s' % (start_attendance_time, end_attendance_time, work_vals['hours']))

                                    # self.task.write (cr, uid, [work_vals['task_id']], {'work_ids': [1, obj['sync'].work.id, work_vals]})

                                    # APPLY WORKCONTEXT + TASK TYPE for start and end attendance
                                    obj['local'].write(cr, uid, [obj['sync'].work.id], work_vals)

                                    perm_obj = obj['local'].browse(cr, uid, [obj['sync'].work.id])
                                    if perm_obj:
                                        sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

                                    res_vals = {
                                        'sync_openerp_modified': sync_openerp_modified,
                                        'sync_remote_modified': datetime.fromtimestamp(obj['remote']['modifydate']),
                                    }
                                    res_work_id = self.resource.write(cr, uid, [obj['sync'].id], res_vals)
                                    self.affected.append(obj['sync'].id)
                                    cr.commit()
                                    modifydates.append(obj['remote']['modifydate'])
                                else:
                                    self.event_log('info', 'No local object found')
                            else:
                                self.event_log('info', 'Break Task: %s' % work_vals['task_id'])
                                # We need to remove the resource and the task!!!
                                if start_id:
                                    start_attendance_obj.pause = True
                                    start_attendance_obj.action = 'sign_out'
                                if end_id:
                                    end_attendance_obj.pause = True
                                    end_attendance_obj.action = 'sign_in'

                            context['workcontext'] = workcontext
                            if start_id:
                                start_id_success = self.updateAttendances(cr, uid, start_attendance_obj, context=context)
                                self.event_log('info', '[Break Task Timestamp] Start Attendance ID: %s' % start_id_success)
                                self.event_log('info', '[Break Task Timestamp] Action: %s' % (self.attendance.browse(cr, uid, start_id_success).action))
                            if end_id:
                                end_id_success = self.updateAttendances(cr, uid, end_attendance_obj, context=context)
                                self.event_log('info', '[Break Task Timestamp] End Attendance ID: %s' % end_id_success)
                                self.event_log('info', '[Break Task Timestamp] Action: %s' % (self.attendance.browse(cr, uid, end_id_success).action))

                            cr.commit()
                    else:
                        # DELETE LOCAL WORK AND RESOURCE
                        self.event_log('info', 'Remote task of this work is not in sync, so we delete the local task work')
                        if obj['sync'].work.id:
                            context['all_attendance_delete'] = True
                            obj['local'].unlink(cr, uid, [obj['sync'].work.id], context=context)
                            work_ids = filter(lambda a: a != obj['sync'].work.id, work_ids)
                            self.resource.unlink(cr, uid, [obj['sync'].id])
                            cr.commit()
                        else:
                            self.event_log('info', 'SHOULD NEVER APPEAR: Local object has already been deleted')
                else:
                    self.event_log('info', 'Remote Task Work: %s, Sync Resource: %s,  Local Task Work: %s' % (obj['remote']['status'], obj['sync'].id, obj['sync'].work.id))
                    if obj['sync'].work.id:
                        context['all_attendance_delete'] = True
                        obj['local'].unlink(cr, uid, [obj['sync'].work.id], context=context)
                        work_ids = filter(lambda a: a != obj['sync'].work.id, work_ids)
                        self.resource.unlink(cr, uid, [obj['sync'].id])
                        cr.commit()
                    else:
                        self.event_log('info', 'Local Object has already been deleted')

            if syncflow['outgoing']:
                self.event_log('info', 'Sync Outgoing')
                # TODO: REST API and do only sync of description
                work = obj['local'].browse(cr, uid, obj['sync'].work.id, context=context)
                res_obj = self.getResourceFromLocalObject(cr, uid, work.task_id, 'task')
                if res_obj:
                    attr = {
                        'id': obj['sync'].external_id,
                        'taskid': res_obj.external_id,
                        'description': work.name,
                    }

                    employee_id = self.employee.search(cr, uid, [('user_id', '=', work.user_id.id)])
                    if employee_id:
                        res_obj = self.getResourceFromLocalObject(cr, uid, self.employee.browse(cr, uid, employee_id)[0], 'employee')
                        attr['employee'] = res_obj.external_id

                    workcontext_id = self.getResourceFromLocalObject(cr, uid, work.workcontext, 'workcontext')
                    if workcontext_id:
                        attr['workcontext'] = workcontext_id.external_id

                    data = {'workentry': json.dumps(attr)}
                    self.event_log('debug', 'OpenERP -> Worktrail Task Work Update: %s' % data)

                    url = "%s://%s:%s/rest/workentries/update/" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'])
                    response = self.json_request(cr, uid, url, data)
                    if response and response['status'] == 'success':
                        external_work = response['id']
                        sync_remote_modified = response['workentry']['modifydate']
                        self.event_log('debug', 'OpenERP -> Worktrail Task Work Update: %s' % response)
                    else:
                        external_work = 0
                        self.event_log('info', 'Worktrail Task Work Update failed')

                    if external_work:
                        perm_obj = obj['local'].browse(cr, uid, [obj['sync'].work.id])
                        if perm_obj:
                            sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

                        res_work_vals = {
                            'sync_openerp_modified': sync_openerp_modified,
                            'sync_remote_modified': datetime.fromtimestamp(sync_remote_modified),
                        }
                        res_work_id = self.resource.write(cr, uid, [obj['sync'].id], res_work_vals)
                        self.affected.append(obj['sync'].id)
                        modifydates.append(sync_remote_modified)
                        cr.commit()

        return modifydates, work_ids

    def _get_last_sync(self, cr, uid, type):
        max_id = self.resource.search(cr, uid, [('type', '=', type)], order='sync_remote_modified DESC')
        if max_id:
            last_sync = self.resource.browse(cr, uid, max_id)[0].sync_remote_modified
        else:
            last_sync = '1970-01-01 00:00:00'

#         if 'work' == type:
# last_sync = '2014-01-15 09:55:43' #'15.01.2014 09:55:43'

        self.event_log('info', 'Last Sync (%s): %s' % (type, last_sync))
        return last_sync

    def _getRelatedStageID(self, cr, uid, state):
        stage_id = False
        mod_obj = self.pool.get('ir.model.data')
        stage_ids = mod_obj.get_object_reference(cr, uid, 'project', MAPPING[state])
        if stage_ids:
            stage_id = stage_ids[1]

        return stage_id

    def convertDatetime2Timestamp(self, cr, uid, obj):
        if obj:
            format = '%Y-%m-%d %H:%M:%S'
            if find(obj, '.') >= 0:
                format = '%Y-%m-%d %H:%M:%S.%f'
            obj = datetime.strptime(obj, format)
            return time.mktime(obj.timetuple())
        else:
            return False

    def getEmployee(self, cr, uid, user):
        employee = False
        search = self.employee.search(cr, uid, [('user_id', '=', user.id)])
        if search:
            employee = self.employee.browse(cr, uid, search)[0]

        return employee

    def getResourceFromExternalID(self, cr, uid, external_id, local_type):
        res_obj = False
        res_id = self.resource.search(cr, uid, [('external_id', '=', external_id), ('type', '=', local_type)])
        if res_id:
            res_obj = self.resource.browse(cr, uid, res_id)[0]
        return res_obj

    def getResourceFromLocalObject(self, cr, uid, local_obj, local_type):
        res_obj = False
        if local_obj:
            res_id = self.resource.search(cr, uid, [(local_type, '=', local_obj.id), ('type', '=', local_type)])
            if res_id:
                res_obj = self.resource.browse(cr, uid, res_id)[0]
        return res_obj

    def getWorkContextFromResource(self, cr, uid, obj):
        res_obj = self.getResourceFromExternalID(cr, uid, obj['workcontext'], 'workcontext')
        if res_obj:
            workcontext = res_obj.workcontext
            self.event_log('info', '[Work Context] %s (%s)' % (workcontext.name, obj['workcontext']))
            return workcontext
        return False

    def updateWorkContext(self, cr, uid, work):
        # Context nehmen und die entsprechenden Reasons für die einzelnen Aktionen (Sign In, Sign Out bzw. Action) holen und den Attendances zuordnen
        return True

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

    def sync_start(self, cr, uid, ids=None, context=None):
        data = ''
        search = self.sync_conf.search(cr, uid, [('type', '=', 'workentries')])
        syncs = self.sync_conf.browse(cr, uid, search, context=context)
        for sync in syncs:
            self.state = u'running'
            self.start = datetime.now()
            protocol = 'http'
            if sync.secure:
                protocol = 'https'
            self.sync_vars = {
                'host': sync.host,
                'port': sync.port,
                'protocol': protocol,
                'id': sync.id,
                'mode': sync.mode,
                'debug': sync.debug,
                'dbname': sync.dbname,
                'auth_token': sync.auth_token,
                'secret_api_key': sync.secret_api_key,
                'app_key': sync.app_key
            }
            wrong_db = cr.dbname != self.sync_vars['dbname']

            if ids is None:
                self.sync_vars['runtype'] = 'Automatic'
                self.sync_vars['debug'] = True
            else:
                self.sync_vars['runtype'] = 'Manual'

            if wrong_db:
                self.sync_vars['debug'] = True

            self.event_log('info', '%s WorkTrail Sync started' % self.sync_vars['runtype'])
            self.event_log('info', 'Sync Mode: %s' % (self.sync_vars['mode']))

            if not self.sync_vars['debug']:
                self.log = 'Debug Log not enabled\n'

            if sync.access_granted == 'active':

                params = ''
                modifydates = []
                task_ids = []
                work_ids = []
                self.sync_id = self.sync.create(cr, uid, {'sync_conf': sync.id, 'state': self.state}, context=context)

                if wrong_db:
                    self.event_log('info', '%s WorkTrail Sync aborted: Wrong Database (%s)' % (self.sync_vars['runtype'], cr.dbname))
                    self.state = u'failed'
                    timedelta = datetime.now() - self.start
                    duration = float(timedelta.seconds + timedelta.microseconds / 1E6)
                    self.sync.write(cr, uid, self.sync_id, {'log': self.log, 'state': self.state, 'duration': duration, 'resources': [(6, 0, self.affected)]}, context=context)

                    self.log = ''
                    self.state = ''
                    self.sync_vars = []
                    self.affected = []
                    self.sync_id = False
                    return False

                # USERS INCOMING
                params = '?after=%s' % self.convertDatetime2Timestamp(cr, uid, self._get_last_sync(cr, uid, 'employee'))
                url = "%s://%s:%s/rest/employees/%s" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'], params)
                self.event_log('info', 'Loading Worktrail Users - URL: %s' % url)
                list = self.get_all_json_results(cr, uid, url, data, params)
                if list:
                    for user in list:
                        self.event_log('debug', 'Loading Worktrail User (%s)' % (user['id']))
                        res_obj = self.getResourceFromExternalID(cr, uid, user['id'], 'employee')
                        # CREATE USER LINK
                        if not res_obj:
                            modifydates = self.createUserLink(cr, uid, user, modifydates, context=None)
                        else:
                            # self.event_log('debug', 'Username: %s, Worktrail ID: %s, Modified: %s' % (user['username'], user['id'], user['modifydate'] ))
                            obj = {'sync': res_obj, 'local': self.employee, 'remote': user}
                            syncflow = self.sync_check(cr, uid, obj['local'], obj['sync'], obj['remote'])

                            if syncflow['incoming'] and syncflow['outgoing']:
                                self.event_log('info', 'Sync Conflict: Local Employee (%s) | Sync Object (%s) | Remote Employee (%s)' % (obj['sync'].employee.id, obj['sync'].id, obj['sync'].external_id))
                            else:
                                if syncflow['incoming']:
                                    self.event_log('info', 'Sync Incoming')
                                if syncflow['outgoing']:
                                    self.event_log('info', 'Sync Outgoing')
                elif not isinstance(list, list):
                    self.log = ''
                    self.state = ''
                    self.sync_vars = []
                    self.affected = []
                    self.sync_id = False
                    return False

                # WORKCONTEXT INCOMING
                params = '?after=%s' % self.convertDatetime2Timestamp(cr, uid, self._get_last_sync(cr, uid, 'workcontext'))
                url = "%s://%s:%s/rest/workcontext/%s" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'], params)
                self.event_log('info', 'Loading Worktrail Work Context - URL: %s' % url)
                list = self.get_all_json_results(cr, uid, url, data, params)
                if list:
                    for workcontext in list:
                        res_obj = self.getResourceFromExternalID(cr, uid, workcontext['id'], 'workcontext')
                        if not res_obj:
                            external_work = workcontext['id']
                            workcontext_vals = {
                                'name': workcontext['label'],
                                'keyword': workcontext['key'],
                                'sequence': workcontext['sortorder'],
                            }
                            # SEARCH for workcontext via keyword
                            search_id = self.workcontext.search(cr, uid, [('keyword', '=', workcontext_vals['keyword'])])

                            if search_id:
                                self.event_log('info', 'Similar workcontext has already been created in OpenERP (Sync Connection will be created)')
                                workcontext_id = search_id[0]
                            else:
                                workcontext_id = self.workcontext.create(cr, uid, workcontext_vals)

                            perm_obj = self.workcontext.browse(cr, uid, [workcontext_id])
                            if perm_obj:
                                sync_openerp_modified = perm_obj.write_date or perm_obj.create_date

                            res_workcontext_vals = {
                                'type': 'workcontext',
                                'external_id': external_work,
                                'workcontext': workcontext_id,
                                'sync': True,
                                'sync_openerp_modified': sync_openerp_modified,
                                'sync_remote_modified': datetime.fromtimestamp(workcontext['modifydate']),
                                'sync_conf': self.sync_vars['id']
                            }
                            new_workcontext = self.resource.create(cr, uid, res_workcontext_vals)
                            self.affected.append(new_workcontext)
                            modifydates.append(workcontext['modifydate'])

                    # RETRIEVE SYNC USER SPECIFIC PROJECTS, TASKS, WORKS
                    search = self.resource.search(cr, uid, [('type', '=', 'employee'), ('sync', '=', True)])
                    if search:
                        employee_ids = []
                        user_ids = []
                        external_user_ids = []
                        for sync_user in self.resource.browse(cr, uid, search, context=context):
                            self.event_log('info', 'Getting OpenERP Infos for Synced Users (%s)' % sync_user.employee.user_id.id)
                            self.event_log('debug', 'Username: %s' % sync_user.employee.user_id.name)
                            self.event_log('debug', 'Employee Name: %s' % sync_user.employee.name)
                            employee_ids.append(sync_user.employee.id)
                            user_ids.append(sync_user.employee.user_id.id)
                            external_user_ids.append(sync_user.external_id)

                        project_ids = self.project.search(cr, uid, ['|', ('user_id', 'in', user_ids), ('members', 'in', employee_ids)])
                        if project_ids:
                            task_ids = self.task.search(cr, uid, ['|', ('user_id', 'in', user_ids), ('project_id', 'in', project_ids)])
                        if task_ids:
                            work_ids = self.work.search(cr, uid, [('task_id', 'in', task_ids), ('user_id', 'in', user_ids)])

                        self.event_log('info', "Lokale Projekte: %s, Lokale Tasks: %s, Lokale Arbeiten: %s" % (len(project_ids), len(task_ids), len(work_ids)))

                        # Questions: Create Project and Tasks automatically or should we first need the user to activate Sync? Option in Sync Server Configuration...

                        # PROJECTS INCOMING
                        params = '?after=%s' % self.convertDatetime2Timestamp(cr, uid, self._get_last_sync(cr, uid, 'project'))
                        url = "%s://%s:%s/rest/projects/%s" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'], params)
                        self.event_log('info', 'Loading Worktrail Projects - URL: %s' % url)
                        list = self.get_all_json_results(cr, uid, url, data, params)
                        for project in list:
                            self.event_log('debug', 'Getting Worktrail Projects (%s)' % project['id'])
                            local_object = self.getResourceFromExternalID(cr, uid, project['id'], 'project')
                            # CREATE LOCAL PROJECT
                            if not local_object:
                                modifydates = self.createProject(cr, uid, project, 'incoming', modifydates)
                            # SYNC PROJECT
                            else:
                                obj = {'sync': local_object, 'local': self.project, 'remote': project}
                                modifydates = self.syncProject(cr, uid, obj, modifydates, context=context)

                        # TASKS INCOMING
                        params = '?after=%s' % self.convertDatetime2Timestamp(cr, uid, self._get_last_sync(cr, uid, 'task'))
                        url = "%s://%s:%s/rest/tasks/%s" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'], params)
                        self.event_log('info', 'Loading Worktrail Tasks - URL: %s' % url)
                        list = self.get_all_json_results(cr, uid, url, data, params)
                        for task in list:
                            self.event_log('debug', 'Getting Worktrail Tasks (%s)' % task['id'])
                            local_object = self.getResourceFromExternalID(cr, uid, task['id'], 'task')
                            # CREATE LOCAL TASK
                            if not local_object:
                                modifydates = self.createTask(cr, uid, task, 'incoming', modifydates)
                            # SYNC TASK
                            else:
                                obj = {'sync': local_object, 'local': self.task, 'remote': task}
                                modifydates = self.syncTask(cr, uid, obj, modifydates, context=context)

                        # TASK WORKS INCOMING
                        params = '?after=%s' % self.convertDatetime2Timestamp(cr, uid, self._get_last_sync(cr, uid, 'work'))
                        url = "%s://%s:%s/rest/workentries/%s" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'], params)
                        self.event_log('info', 'Loading Worktrail Task Works - URL: %s' % url)
                        list = self.get_all_json_results(cr, uid, url, data, params)
                        if list:
                            # I need the incoming works ordered by datetime otherwise we have big troubles
                            for work in list:
                                self.event_log('debug', 'Getting Worktrail Task Works (%s)' % work['id'])
                                # Only get workentries for users in sync
                                if work['employee'] in external_user_ids:
                                    local_object = self.getResourceFromExternalID(cr, uid, work['id'], 'work')
                                    # CREATE LOCAL TASK WORK
                                    if not local_object:
                                        modifydates = self.createTaskWork(cr, uid, work, 'incoming', modifydates)
                                    # SYNC TASK WORK
                                    else:
                                        obj = {'sync': local_object, 'local': self.work, 'remote': work}
                                        modifydates, work_ids = self.syncTaskWork(cr, uid, obj, modifydates, work_ids, context=context)

                        # Questions: Create Project and Tasks automatically or should we first need the user to activate Sync? Option in Sync Server Configuration...

                        # PROJECTS OUTGOING
                        self.event_log('info', 'Pushing OpenERP Projects (%s)' % len(project_ids))
                        for project_id in project_ids:
                            search = self.resource.search(cr, uid, [('project', '=', project_id), ('type', '=', 'project')])
                            # CREATE REMOTE PROJECT
                            if not search:
                                project = self.project.browse(cr, uid, project_id, context=context)
                                modifydates = self.createProject(cr, uid, project, 'outgoing', modifydates)
                            # SYNC PROJECT
                            else:
                                project_sync = self.resource.browse(cr, uid, search)[0]
                                obj = {'sync': project_sync, 'local': self.project, 'remote': {'modifydate': self.convertDatetime2Timestamp(cr, uid, project_sync.sync_remote_modified)}}
                                newmodifydates = self.syncProject(cr, uid, obj, modifydates)
                                if newmodifydates:
                                    modifydates = newmodifydates

                        # TASKS OUTGOING
                        self.event_log('info', 'Pushing OpenERP Tasks (%s)' % len(task_ids))
                        for task_id in task_ids:
                            search = self.resource.search(cr, uid, [('task', '=', task_id), ('type', '=', 'task')])
                            # CREATE REMOTE TASK
                            if not search:
                                task = self.task.browse(cr, uid, task_id, context=context)
                                modifydates = self.createTask(cr, uid, task, 'outgoing', modifydates)
                            # SYNC TASK
                            else:
                                task_sync = self.resource.browse(cr, uid, search)[0]
                                obj = {'sync': task_sync, 'local': self.task, 'remote': {'modifydate': self.convertDatetime2Timestamp(cr, uid, task_sync.sync_remote_modified)}}
                                newmodifydates = self.syncTask(cr, uid, obj, modifydates, context=context)
                                if newmodifydates:
                                    modifydates = newmodifydates
                        # TASK WORKS OUTGOING
                        self.event_log('info', 'Pushing OpenERP Task Works (%s)' % len(work_ids))
                        for work_id in work_ids:

                            search = self.resource.search(cr, uid, [('work', '=', work_id), ('type', '=', 'work')])
                            # CREATE REMOTE TASK WORK
                            if not search:
                                self.event_log('debug', "Work ID %s" % work_id)
                                work = self.work.browse(cr, uid, work_id, context=context)
                                modifydates = self.createTaskWork(cr, uid, work, 'outgoing', modifydates)
                            # SYNC TASK WORK
                            else:

                                work_sync = self.resource.browse(cr, uid, search)[0]
                                obj = {'sync': work_sync, 'local': self.work, 'remote': {'modifydate': self.convertDatetime2Timestamp(cr, uid, work_sync.sync_remote_modified)}}
                                newmodifydates, work_ids = self.syncTaskWork(cr, uid, obj, modifydates, work_ids, context=context)
                                if newmodifydates:
                                    modifydates = newmodifydates

                        deleted_ids = self.resource.search(cr, uid, [('type', '=', 'work'), ('work', '=', False)])
                        # OBJECTS DELETED OUTGOING
                        if deleted_ids:
                            self.event_log('info', 'Pushing deleted local objects: %s' % deleted_ids)
                            for deleted_work in deleted_ids:
                                obj = {}
                                obj['sync'] = self.resource.browse(cr, uid, [deleted_work])[0]
                                if obj['sync']:
                                    attr = {
                                        'id': obj['sync'].external_id,
                                        'status': 'deleted',
                                    }

                                    data = {'workentry': json.dumps(attr)}
                                    self.event_log('debug', 'OpenERP -> Worktrail Task Work Deletion: %s' % data)

                                    url = "%s://%s:%s/rest/workentries/update/" % (self.sync_vars['protocol'], self.sync_vars['host'], self.sync_vars['port'])
                                    response = self.json_request(cr, uid, url, data)
                                    if response and response['status'] == 'success':
                                        external_work = response['id']
                                        self.event_log('debug', 'OpenERP -> Worktrail Task Work Update: %s' % response)

                                        self.resource.unlink(cr, uid, [obj['sync'].id])
                                        cr.commit()
                                    else:
                                        self.event_log('debug', 'Deletion has failed')

                    if modifydates:
                        last_modified = datetime.fromtimestamp(max(modifydates))

                if self.state != 'error':
                    self.state = u'done'

                self.closeSync(cr, uid, context=context)

            else:
                self.sync_vars['debug'] = True
                self.state = 'failed'
                self.event_log('error', 'Sync (%s) is not active!' % self.sync_vars['id'])
                self.closeSync(cr, uid, context=context)
                if self.sync_vars and self.sync_vars['runtype'] != 'Automatic':
                    raise orm.except_orm(_('Error !'), _('Sync(%s) is not active!') % self.sync_id)
        mod_obj = self.pool.get('ir.model.data')
        return True

    def closeSync(self, cr, uid, context=None):
        context = dict(context or {})

        timedelta = datetime.now() - self.start
        duration = float(timedelta.seconds + timedelta.microseconds / 1E6)
        # self.event_log('info', 'Seconds: %s | Microseconds: %s' % (timedelta.seconds, timedelta.microseconds) )

        self.event_log('info', '%s Worktrail Sync completed (%s seconds)' % (self.sync_vars['runtype'], duration))

        self.sync.write(cr, uid, self.sync_id, {'log': self.log, 'state': self.state, 'duration': duration, 'resources': [(6, 0, self.affected)]}, context=context)
        self.log = ''
        self.state = ''
        self.sync_vars = []
        self.affected = []
        self.sync_id = False

        return True

tapoit_worktrail_sync_execution()


class hr_timesheet_line(orm.Model):
    _inherit = "hr.analytic.timesheet"

    def write(self, cr, uid, ids, values, context=None):
        context = context or {}
        ids = self._remove_wrong_state_ids(cr, uid, ids)
        return super(hr_timesheet_line, self).write(cr, uid, ids, values, context=context)

    def unlink(self, cr, uid, ids, values, context=None):
        context = context or {}
        return super(hr_timesheet_line, self).unlink(cr, uid, ids, values, context=context)

    def _remove_wrong_state_ids(self, cr, uid, ids, *args, **kwargs):
        for att in self.browse(cr, uid, ids):
            if att.sheet_id and att.sheet_id.state not in ('draft', 'new'):
                ids = filter(lambda a: a != att.id, ids)
        return ids

hr_timesheet_line()


class account_analytic_line(orm.Model):
    _inherit = 'account.analytic.line'

    def _check_inv(self, cr, uid, ids, vals):
        # Override to be able to sync w/o being disturbed by inherited class showstopper
        return True

        # Inherited showstopper (task.write is iterating over all work_ids and actually updating them)
        select = ids
        if isinstance(select, (int, long)):
            select = [ids]
        if ('invoice_id' not in vals) or vals['invoice_id'] is False:
            for line in self.browse(cr, uid, select):
                if line.invoice_id:
                    raise orm.except_orm(_('Error !'),
                                         _('You can not modify an invoiced analytic line!'))
        return True

account_analytic_line()
