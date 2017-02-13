from webob import exc

from oslo_log import log as logging
LOG = logging.getLogger(__name__)

from murano.db import session as db_session
from murano.db import models
from murano.services import states

from murano.common import auth_utils
from murano.common.i18n import _
from murano.common.i18n import _LI, _LW
from murano.common import utils as common_utils
from murano.common import uuidutils

import scheduler
import cloud
specs = set([scheduler.get_scheduler_id(), cloud.get_cloud_id()])

def my_post_data(environment_id, session_id, data, path, request):
    if path:
        path = '/services/' + path
    else:
        path = '/services'

    unit = db_session.get_session()
    model = unit.query(models.Session).get(session_id)
    if model is None:
        msg = _('Session is not found')
        LOG.error(msg)
        raise exc.HTTPNotFound(explanation=msg)

    if path == '/services':
        env_description = model.description['Objects']
        if 'services' not in env_description:
            env_description['services'] = []
        if isinstance(data, list):
            common_utils.TraverseHelper.extend(path, data, env_description)
        else:
            common_utils.TraverseHelper.insert(path, data, env_description)

        session = models.Session()
        session.environment_id = model.environment_id
        session.user_id = model.user_id
        session.state = states.EnvironmentStatus.PENDING
        session.version = 2
        session.description = model.description
        session.description['Objects'] = env_description
        session.id = uuidutils.generate_uuid()
        session.description['SystemData']= {}
        session.description['SystemData']['SessionId'] = session.id
        session.description['SystemData']['TrustId'] = auth_utils.create_trust(request.context.auth_token, request.context.tenant)
        session.description['SystemData']['UserId'] = request.context.user
        session.description['SystemData']['Tenant'] = request.context.tenant
        session.description['SystemData']['Token'] = request.context.auth_token     # TODO: alloc long-term token
        with unit.begin():
            unit.add(session)

        session.save(unit)

    return data

def my_check_env(request, environment_id):
    unit = db_session.get_session()
    environment = unit.query(models.Environment).get(environment_id)
    if environment is None:
        msg = _('Environment with id {env_id} not found').format(env_id=environment_id)
        LOG.error(msg)
        raise exc.HTTPNotFound(explanation=msg)

    if environment_id not in specs:
        if hasattr(request, 'context'):
            if environment.tenant_id != request.context.tenant:
                msg = _('User is not authorized to access these tenant resources')
                LOG.error(msg)
                raise exc.HTTPForbidden(explanation=msg)
    return environment

from murano import utils
import functools
def my_verify_env(func):
    @functools.wraps(func)
    def __inner(self, request, environment_id, *args, **kwargs):
        try:
            my_check_env(request, environment_id)
        except exc.HTTPNotFound:
            if environment_id in specs:
                body = {'id':environment_id, 'name':'t_{0}'.format(environment_id)}
                environment = envs.EnvironmentServices.create(body.copy(), request.context)
            else:
                raise
        return func(self, request, environment_id, *args, **kwargs)
    return __inner

from murano.api.v1 import request_statistics
import time
from murano.common.i18n import _LE
from murano.db.services import core_services
def my_session_create(environment_id, request):
    unit = db_session.get_session()
    session = unit.query(models.Session).filter_by(environment_id=environment_id, user_id=request.context.user, version=1).first()
    if session is None:
        environment = unit.query(models.Environment).get(environment_id)
        session = models.Session()
        session.environment_id = environment_id
        session.user_id = request.context.user
        session.state = states.EnvironmentStatus.PENDING
        session.version = 1
        session.description = environment.description
        #session.description['SystemData']= {}
        #session.description['SystemData']['TrustId'] = auth_utils.create_trust(request.context.auth_token, request.context.tenant)
        #session.description['SystemData']['UserId'] = request.context.user
        #session.description['SystemData']['Tenant'] = request.context.tenant
        #session.description['SystemData']['Token'] = request.context.auth_token     # TODO: alloc long-term token
        with unit.begin():
            unit.add(session)
    return session

old_delete_data = core_services.CoreServices.delete_data
def my_delete_data(environment_id, session_id, path):
    if environment_id not in specs:
        return old_delete_data(environment_id, session_id, path)
    
    parts = path.split("/services/")
    if len(parts) > 1:
        session_id = parts[1]
        unit = db_session.get_session()
        session = unit.query(models.Session).get(session_id)
        if session:
            with unit.begin():
                unit.delete(session)

def my_stats_count(api, method):
    def wrapper(func):
        def wrap(*args, **kwargs):
            try:
                ts = time.time()
                result = None
                if (api == 'Environments' and method == 'Show'):
                    environment_id = kwargs.get('environment_id')
                    if environment_id in specs:
                        request = args[1]
                        unit = db_session.get_session()
                        environment = unit.query(models.Environment).get(environment_id)
                        result = environment.to_dict()
                        result['status'] = states.EnvironmentStatus.READY
                        result['acquired_by'] = None
                        schedules = unit.query(models.Session).filter_by(environment_id=environment_id, user_id=request.context.user)
                        result['services'] = []
                        for session in schedules:
                            if session is not None and session.description['Objects'].has_key('services'):
                                services = session.description['Objects']['services']
                                for service in services:
                                    service['?']['status'] = session.state
                                    service['?']['id'] = session.id
                                result['services'].extend(services)
                elif (api == 'Sessions' and method == 'Create'):
                    environment_id = kwargs.get('environment_id')
                    if environment_id in specs:
                        result = my_session_create(environment_id, args[1]).to_dict()
                elif (api == 'Services' and method == 'Create'):
                    environment_id = kwargs.get('environment_id')
                    if environment_id in specs:
                        request = args[1]
                        result = my_post_data(environment_id, request.context.session, kwargs.get('body'), kwargs.get('path'), request)
                if result is None:
                    result = func(*args, **kwargs)
                te = time.time()
                tenant = args[1].context.tenant
                request_statistics.update_count(api, method, te - ts, tenant)
                return result
            except Exception:
                te = time.time()
                tenant = args[1].context.tenant
                LOG.exception(_LE('API {api} method {method} raised an exception').format(api=api, method=method))
                request_statistics.update_error_count(api, method, te - te, tenant)
                raise
        return wrap
    return wrapper


from murano.db.services import environments as envs
old_get_environments_by = envs.EnvironmentServices.get_environments_by
def my_get_environments_by(filters):
    envs = old_get_environments_by(filters)
    for env in envs:
        if env.id in specs:
            envs.remove(env)
    return envs

from murano.common import server
from oslo_utils import timeutils
old_process_result = server.ResultEndpoint.process_result
def my_process_result(context, result, environment_id):
    if environment_id != scheduler.get_scheduler_id():
        return old_process_result(context, result, environment_id)

    model = result['model']
    action_result = result.get('action', {})
    unit = db_session.get_session()

    # close deployment
    deployment = server.get_last_deployment(unit, environment_id)
    deployment.finished = timeutils.utcnow()
    deployment.result = action_result

    num_errors = unit.query(models.Status).filter_by(level='error', task_id=deployment.id).count()
    num_warnings = unit.query(models.Status).filter_by(level='warning', task_id=deployment.id).count()
    if num_errors:
        final_status_text = "finished with errors"
    elif num_warnings:
        final_status_text = "finished with warnings"
    else:
        final_status_text = "finished"

    status = models.Status()
    status.task_id = deployment.id
    status.text = final_status_text
    status.level = 'info'
    deployment.statuses.append(status)
    deployment.save(unit)

    # close session
    session_id = model['SystemData']['SessionId']
    conf_session = unit.query(models.Session).get(session_id)
    if num_errors > 0 or result['action'].get('isException'):
        conf_session.state = states.EnvironmentStatus.DEPLOY_FAILURE
    else:
        conf_session.state = states.EnvironmentStatus.READY
    conf_session.description = model
    if conf_session.description['Objects'] is not None:
        conf_session.description['Objects']['services'] = conf_session.description['Objects'].pop('applications', [])
    conf_session.version += 1
    conf_session.save(unit)

    # output application tracking information
    services = []
    objects = model['Objects']
    if objects:
        services = objects.get('services')
    if num_errors + num_warnings > 0:
        LOG.warning(_LW('Schedule Status: Failed Apps: {services}').format(services=services))
    else:
        LOG.info(_LI('Schedule Status: Successful Apps: {services}').format(services=services))


def patch():
    envs.EnvironmentServices.get_environments_by = staticmethod(my_get_environments_by)
    utils.verify_env = my_verify_env
    utils.check_env = my_check_env
    request_statistics.stats_count = my_stats_count
    server.ResultEndpoint.process_result = staticmethod(my_process_result)
    #core_services.CoreServices.post_data = staticmethod(my_post_data)
    core_services.CoreServices.delete_data = staticmethod(my_delete_data)

