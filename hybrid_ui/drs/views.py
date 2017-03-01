import base64
import json

from django.core.urlresolvers import reverse
from django.core.urlresolvers import reverse_lazy
from django import http
from django.utils.translation import ugettext_lazy as _
from django.views import generic
from horizon import exceptions
from horizon.forms import views
from horizon import tables
from horizon import tabs

from muranoclient.common import exceptions as exc
from muranodashboard import api as api_utils
from muranodashboard.environments import api
import tables as env_tables
import tabs as env_tabs

from oslo_log import log as logging
LOG = logging.getLogger(__name__)

from horizon import messages
from muranodashboard.environments import consts
from muranodashboard.common import utils
from muranodashboard.dynamic_ui import helpers
from muranodashboard.dynamic_ui import services
from muranodashboard.catalog.views import LazyWizard
class Wizard(views.ModalFormMixin, LazyWizard):
    template_name = 'drs/wizard_create.html'
    do_redirect = False
    environment_id = env_tables.get_scheduler_id()

    def get_prefix(self, *args, **kwargs):
        base = super(Wizard, self).get_prefix(*args, **kwargs)
        fmt = utils.BlankFormatter()
        return fmt.format('{0}_{app_id}', base, **kwargs)

    def get_form_prefix(self, step=None, form=None):
        if step is None:
            return self.steps.step0
        else:
            index0 = self.steps.all.index(step)
            return str(index0)

    def done(self, form_list, **kwargs):
        app_name = self.storage.extra_data['app'].name

        service = form_list[0].service
        attributes = service.extract_attributes()
        attributes = helpers.insert_hidden_ids(attributes)
        storage = attributes.setdefault('?', {}).setdefault(consts.DASHBOARD_ATTRS_KEY, {})
        storage['name'] = app_name

        do_redirect = self.get_wizard_flag('do_redirect')
        wm_form_data = service.cleaned_data.get('workflowManagement')
        if wm_form_data:
            do_redirect = do_redirect or not wm_form_data.get(
                'stay_at_the_catalog', True)

        fail_url = reverse("horizon:murano:drs:index")
        try:
            env_url = reverse('horizon:murano:drs:index')
            srv = api.service_create(self.request, self.environment_id, attributes)
        except exc.HTTPForbidden:
            msg = _("Sorry, you can't add task right now. The drs is deploying.")
            exceptions.handle(self.request, msg, redirect=fail_url)
        except Exception:
            message = _('Adding task to an schedule failed.')
            LOG.exception(message)
            exceptions.handle(self.request, message, redirect=fail_url)
        else:
            message = _("The '{0}' task successfully added to schedule.").format(app_name)
            LOG.info(message)
            messages.success(self.request, message)

            if do_redirect:
                return http.HttpResponseRedirect(env_url)
            else:
                srv_id = getattr(srv, '?')['id']
                return self.create_hacked_response(
                    srv_id,
                    attributes['?'].get('name') or attributes.get('name'))

    def create_hacked_response(self, obj_id, obj_name):
        # copy-paste from horizon.forms.views.ModalFormView; should be done
        # that way until we move here from django Wizard to horizon workflow
        if views.ADD_TO_FIELD_HEADER in self.request.META:
            field_id = self.request.META[views.ADD_TO_FIELD_HEADER]
            response = http.HttpResponse(json.dumps(
                [obj_id, html.escape(obj_name)]
            ))
            response["X-Horizon-Add-To-Field"] = field_id
            return response
        else:
            return http.HttpResponse()

    def get_form_initial(self, step):
        init_dict = {'request': self.request,
                     'app_id': self.kwargs['app_id'],
                     'environment_id': self.environment_id}
        return self.initial_dict.get(step, init_dict)

    def _get_wizard_param(self, key):
        param = self.kwargs.get(key)
        return param if param is not None else self.request.POST.get(key)

    def get_wizard_flag(self, key):
        value = self._get_wizard_param(key)
        return utils.ensure_python_obj(value)

    def get_context_data(self, form, **kwargs):
        context = super(Wizard, self).get_context_data(form=form, **kwargs)
        app_id = self.kwargs.get('app_id')
        app = self.storage.extra_data.get('app')

        # Save extra data to prevent extra API calls
        mc = api_utils.muranoclient(self.request)
        if not app:
            app = mc.packages.get(app_id)
            self.storage.extra_data['app'] = app

        env_name = mc.environments.get(self.environment_id).name

        context['field_descriptions'] = services.get_app_field_descriptions(self.request, app_id, self.steps.index)
        context.update({'type': app.fully_qualified_name,
                        'service_name': app.name,
                        'app_id': app_id,
                        'environment_id': self.environment_id,
                        'environment_name': env_name,
                        'do_redirect': self.get_wizard_flag('do_redirect'),
                        'drop_wm_form': self.get_wizard_flag('drop_wm_form'),
                        'prefix': self.prefix,
                        'got_picture': app.supplier.has_key('Logo'),
                        })
        return context


class SchedulerView(tabs.TabbedTableView):
    tab_group_class = env_tabs.EnvironmentDetailsTabs
    template_name = 'drs/index.html'
    page_title = 'Schedule Tasks'
    environment_id = env_tables.get_scheduler_id()

    def get_context_data(self, **kwargs):
        context = super(SchedulerView, self).get_context_data(**kwargs)
        context['tenant_id'] = self.request.session['token'].tenant['id']
        context['environment_id'] = self.environment_id
        context["url"] = self.get_redirect_url()
        return context

    def get_tabs(self, request, *args, **kwargs):
        try:
            deployments = api.deployments_list(self.request, self.environment_id)
        except exc.HTTPException:
            msg = _('Unable to retrieve list of deployments')
            exceptions.handle(self.request, msg, redirect=self.get_redirect_url())

        logs = []
        if deployments:
            last_deployment = deployments[0]
            logs = api.deployment_reports(self.request, self.environment_id, last_deployment.id)
        return self.tab_group_class(request, logs=logs, **kwargs)

    @staticmethod
    def get_redirect_url():
        return reverse_lazy("horizon:murano:drs:index")


class DetailServiceView(tabs.TabbedTableView):
    tab_group_class = env_tabs.ServicesTabs
    template_name = 'drs/details.html'
    page_title = '{{ service_name }}'

    def get_context_data(self, **kwargs):
        context = super(DetailServiceView, self).get_context_data(**kwargs)
        service = self.get_data()
        context["service"] = service
        context["service_name"] = getattr(self.service, 'name', '-')
        context["custom_breadcrumb"] = [(_("DRS"), SchedulerView.get_redirect_url()),]
        return context

    def get_data(self):
        service_id = self.kwargs['service_id']
        self.environment_id = env_tables.get_scheduler_id()
        try:
            self.service = api.service_get(self.request, self.environment_id, service_id)
        except exc.HTTPUnauthorized:
            exceptions.handle(self.request)

        except exc.HTTPForbidden:
            redirect = reverse('horizon:murano:drs:index')
            exceptions.handle(self.request, _('Unable to retrieve details for task'), redirect=redirect)
        else:
            self._service = self.service
            return self._service

    def get_tabs(self, request, *args, **kwargs):
        service = self.get_data()
        return self.tab_group_class(request, service=service, **kwargs)


class DeploymentDetailsView(tabs.TabbedTableView):
    tab_group_class = env_tabs.DeploymentDetailsTabs
    table_class = env_tables.EnvConfigTable
    template_name = 'drs/reports.html'
    page_title = _('Schedule at {{ deployment_start_time }}')

    def get_context_data(self, **kwargs):
        context = super(DeploymentDetailsView, self).get_context_data(**kwargs)
        context["deployment_start_time"] = api.get_deployment_start(self.request, self.environment_id, self.deployment_id)
        context["custom_breadcrumb"] = [(_("DRS"), SchedulerView.get_redirect_url()),]
        return context

    def get_deployment(self):
        deployment = None
        try:
            deployment = api.get_deployment_descr(self.request,
                                                  self.environment_id,
                                                  self.deployment_id)
        except (exc.HTTPInternalServerError, exc.HTTPNotFound):
            msg = _("Deployment with id %s doesn't exist anymore")
            redirect = reverse("horizon:murano:drs:deployments")
            exceptions.handle(self.request,
                              msg % self.deployment_id,
                              redirect=redirect)
        return deployment

    def get_logs(self):
        logs = []
        try:
            logs = api.deployment_reports(self.request,
                                          self.environment_id,
                                          self.deployment_id)
        except (exc.HTTPInternalServerError, exc.HTTPNotFound):
            msg = _('Deployment with id %s doesn\'t exist anymore')
            redirect = reverse("horizon:murano:drs:deployments")
            exceptions.handle(self.request,
                              msg % self.deployment_id,
                              redirect=redirect)
        return logs

    def get_tabs(self, request, *args, **kwargs):
        self.deployment_id = self.kwargs['deployment_id']
        self.environment_id = env_tables.get_scheduler_id()
        deployment = self.get_deployment()
        logs = self.get_logs()

        return self.tab_group_class(request, deployment=deployment, logs=logs,
                                    **kwargs)


class JSONResponse(http.HttpResponse):
    def __init__(self, content=None, **kwargs):
        if content is None:
            content = {}
        kwargs.pop('content_type', None)
        super(JSONResponse, self).__init__(
            content=json.dumps(content), content_type='application/json',
            **kwargs)


class StartActionView(generic.View):
    @staticmethod
    def post(request, environment_id, action_id):
        if api.action_allowed(request, environment_id):
            task_id = api.run_action(request, environment_id, action_id)
            url = reverse('horizon:murano:drs:action_result',
                          args=(environment_id, task_id))
            return JSONResponse({'url': url})
        else:
            return JSONResponse()


class ActionResultView(generic.View):
    @staticmethod
    def is_file_returned(result):
        try:
            return result['result']['?']['type'] == 'io.murano.File'
        except (KeyError, ValueError, TypeError):
            return False

    @staticmethod
    def compose_response(result, is_file=False, is_exc=False):
        filename = 'exception.json' if is_exc else 'result.json'
        content_type = 'application/octet-stream'
        if is_file:
            filename = result.get('filename') or 'action_result_file'
            content_type = result.get('mimeType') or content_type
            content = base64.b64decode(result['base64Content'])
        else:
            content = json.dumps(result, indent=True)

        response = http.HttpResponse(content_type=content_type)
        response['Content-Disposition'] = (
            'attachment; filename=%s' % filename)
        response.write(content)
        response['Content-Length'] = str(len(response.content))
        return response

    def get(self, request, environment_id, task_id, optional):
        mc = api_utils.muranoclient(request)
        result = mc.actions.get_result(environment_id, task_id)
        if result:
            if result and optional == 'poll':
                if result['result'] is not None:
                    # Remove content from response on first successful poll
                    del result['result']
                return JSONResponse(result)
            return self.compose_response(result['result'],
                                         self.is_file_returned(result),
                                         result['isException'])
        # Polling hasn't returned content yet
        return JSONResponse()
