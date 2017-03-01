import json

from django.core.urlresolvers import reverse
from django import http as django_http
from django import shortcuts
from django.template import defaultfilters
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ungettext_lazy
from django.utils.translation import ugettext

from horizon import exceptions
from horizon import forms
from horizon import messages
from horizon import tables
from horizon.utils import filters
from muranoclient.common import exceptions as exc
from oslo_log import log as logging

from muranodashboard import api as api_utils
from muranodashboard.api import packages as pkg_api
from muranodashboard.catalog import views as catalog_views
from muranodashboard.environments import api
from muranodashboard.environments import consts
from muranodashboard.packages import consts as pkg_consts


LOG = logging.getLogger(__name__)

def get_scheduler_id():
    return '40b590492fca4ccfbb39a55c2d9b3269'


#def _get_environment_status_and_version(request, table):
#    environment_id = get_scheduler_id()
#    env = api.environment_get(request, environment_id)
#    status = getattr(env, 'status', None)
#    version = getattr(env, 'version', None)
#    return status, version


class DeleteService(tables.DeleteAction):

    @staticmethod
    def action_present(count):
        return ungettext_lazy(
            u"Delete Task",
            u"Delete Tasks",
            count
        )

    @staticmethod
    def action_past(count):
        return ungettext_lazy(
            u"Start Deleting Task",
            u"Start Deleting Tasks",
            count
        )

    def action(self, request, service_id):
        try:
            environment_id = get_scheduler_id()
            for service in self.table.data:
                if service['?']['id'] == service_id:
                    api.service_delete(request, environment_id, service_id)
        except Exception:
            msg = _('Sorry, you can\'t delete service right now')
            redirect = reverse("horizon:murano:drs:index")
            exceptions.handle(request, msg, redirect=redirect)


class RefreshThisEnvironment(tables.Action):
    name = 'refresh_env'
    verbose_name = _('Refresh Task Status')
    requires_input = False
    classes = ('btn-launch',)
    icon = 'refresh'

    def single(self, data_table, request, service_id):
#            api.environment_deploy(request, get_scheduler_id())
        return shortcuts.redirect(reverse('horizon:murano:drs:index'))


class UpdateEnvironmentRow(tables.Row):
    ajax = True

    def get_data(self, request, environment_id):
        try:
            return api.environment_get(request, environment_id)
        except exc.HTTPNotFound:
            # returning 404 to the ajax call removes the
            # row from the table on the ui
            raise django_http.Http404
        except Exception:
            # let our unified handler take care of errors here
            with api_utils.handled_exceptions(request):
                raise


class UpdateServiceRow(tables.Row):
    ajax = True

    def get_data(self, request, service_id):
        environment_id = get_scheduler_id()
        return api.service_get(request, environment_id, service_id)


class UpdateName(tables.UpdateAction):
    def update_cell(self, request, datum, obj_id, cell_name, new_cell_value):
        try:
            if not new_cell_value or new_cell_value.isspace():
                message = _("The environment name field cannot be empty.")
                messages.warning(request, message)
                raise ValueError(message)
            mc = api_utils.muranoclient(request)
            mc.environments.update(datum.id, name=new_cell_value)
        except exc.HTTPConflict:
            message = _("This name is already taken.")
            messages.warning(request, message)
            LOG.warning(_("Couldn't update environment. Reason: ") + message)

            # FIXME(kzaitsev): There is a bug in horizon and inline error
            # icons are missing. This means, that if we return 400 here, by
            # raising django.core.exceptions.ValidationError(message) the UI
            # will break a little. Until the bug is fixed this will raise 500
            # bug link: https://bugs.launchpad.net/horizon/+bug/1359399
            # Alternatively this could somehow raise 409, which would result
            # in the same behaviour.
            raise ValueError(message)
        except Exception:
            exceptions.handle(request, ignore=True)
            return False
        return True


def get_service_type(datum):
    return datum['?'].get(consts.DASHBOARD_ATTRS_KEY, {}).get('name')


class ServicesTable(tables.DataTable):
    d_date = tables.Column('date', verbose_name=_("Date"))
    d_time = tables.Column('time', verbose_name=_("Time"))
    d_mode = tables.Column('mode', verbose_name=_("Repeat"))
    name = tables.Column('name', verbose_name=_('Name'), link="horizon:murano:drs:service_details")
    _type = tables.Column(get_service_type, verbose_name=_('Type'))

    status = tables.Column(lambda datum: datum['?'].get('status'),
                           verbose_name=_('Status'),
                           status=True,
                           status_choices=consts.STATUS_CHOICES,
                           display_choices=consts.STATUS_DISPLAY_CHOICES)
    operation = tables.Column('operation',
                              verbose_name=_('Last operation'),
                              filters=(defaultfilters.urlize, ))
    operation_updated = tables.Column('operation_updated',
                                      verbose_name=_('Time updated'),
                                      filters=(filters.parse_isotime,))

    def get_object_id(self, datum):
        return datum['?']['id']

    def get_apps_list(self):
        packages = []
        with api_utils.handled_exceptions(self.request):
            packages, self._more = pkg_api.package_list(
                self.request,
                filters={'type': 'Schedule', 'catalog': True})
        items = []
        for package in packages:
            item = package.to_dict()
            item['name'] = ugettext(item['name'])
            items.append(item)
        return json.dumps(items)

    def actions_allowed(self):
        #status, version = _get_environment_status_and_version(
        #    self.request, self)
        status = getattr(self._meta.env, 'status', None)
        return status not in consts.NO_ACTION_ALLOWED_STATUSES

    def get_categories_list(self):
        return catalog_views.get_categories_list(self.request)

    def get_row_actions(self, datum):
        actions = super(ServicesTable, self).get_row_actions(datum)
        environment_id = get_scheduler_id()
        app_actions = []
        for action_datum in api.extract_actions_list(datum):
            _classes = ('murano_action',)

            class CustomAction(tables.LinkAction):
                name = action_datum['name']
                verbose_name = action_datum['name']
                url = reverse('horizon:murano:drs:start_action', args=(action_datum['id'],))
                classes = _classes
                table = self

                def allowed(self, request, datum):
                    #status, version = _get_environment_status_and_version(
                    #    request, self.table)
                    status = datum['?'].get('status', consts.STATUS_ID_NEW)
                    if status in consts.NO_ACTION_ALLOWED_STATUSES:
                        return False
                    return True

            bound_action = CustomAction()
            if not bound_action.allowed(self.request, datum):
                continue
            bound_action.datum = datum
            if issubclass(bound_action.__class__, tables.LinkAction):
                bound_action.bound_url = bound_action.get_link_url(datum)
            app_actions.append(bound_action)
        if app_actions:
            # Show native actions first (such as "Delete Task") and
            # then add sorted application actions
            actions.extend(sorted(app_actions, key=lambda x: x.name))
        return actions

    def get_repo_url(self):
        return pkg_consts.MURANO_REPO_URL

    def get_pkg_def_url(self):
        return reverse('horizon:murano:packages:index')

    class Meta(object):
        name = 'services'
        verbose_name = _('Task List')
        no_data_message = _('No components')
        status_columns = ['status']
        row_class = UpdateServiceRow
        table_actions = (RefreshThisEnvironment,)
        row_actions = (DeleteService,)
        multi_select = False


class ShowDeploymentDetails(tables.LinkAction):
    name = 'show_deployment_details'
    verbose_name = _('Show Details')

    def get_link_url(self, deployment):
        return reverse('horizon:murano:drs:deployment_details', args=(deployment.id,))

    def allowed(self, request, environment):
        return True


class DeploymentsTable(tables.DataTable):
    started = tables.Column('started',
                            verbose_name=_('Time Started'),
                            filters=(filters.parse_isotime,))
    finished = tables.Column('finished',
                             verbose_name=_('Time Finished'),
                             filters=(filters.parse_isotime,))

    status = tables.Column(
        'state',
        verbose_name=_('Status'),
        status=True,
        display_choices=consts.DEPLOYMENT_STATUS_DISPLAY_CHOICES)

    class Meta(object):
        name = 'deployments'
        verbose_name = _('Deployments')
        row_actions = (ShowDeploymentDetails,)


class EnvConfigTable(tables.DataTable):
    name = tables.Column('name',
                         verbose_name=_('Name'))
    _type = tables.Column(
        lambda datum: get_service_type(datum) or 'Unknown',
        verbose_name=_('Type'))

    def get_object_id(self, datum):
        return datum['?']['id']

    class Meta(object):
        name = 'environment_configuration'
        verbose_name = _('Deployed Tasks')
