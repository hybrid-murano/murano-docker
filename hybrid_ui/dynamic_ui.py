import ast
import copy
import json
import netaddr
import re

from django.core.exceptions import ValidationError
from django.template import defaultfilters
from django.core.urlresolvers import reverse
from django.core import validators as django_validator
from django import forms
from django.http import Http404
from django.template import defaultfilters
from django.utils.encoding import force_text
from django.utils import html
from django.utils.translation import ugettext_lazy as _
from horizon import exceptions
from horizon import forms as hz_forms
from horizon import messages
from openstack_dashboard.api import glance
from openstack_dashboard.api import nova
from openstack_dashboard.api import cinder
from openstack_dashboard.api import neutron
from oslo_log import log as logging
import six
from yaql import legacy

from muranoclient.common import exceptions as muranoclient_exc
from muranodashboard.api import packages as pkg_api
from muranodashboard.common import net
from muranodashboard.environments import api as env_api

from oslo_log import versionutils


LOG = logging.getLogger(__name__)

from muranodashboard.dynamic_ui import fields
fields.FIELD_ARGS_TO_ESCAPE = ['help_text', 'description', 'label']

from muranodashboard.dynamic_ui.fields import *

def get_available_networks(request, include_subnets=True,
                           filter=None, murano_networks=None, exclude_ext_net=True):
    if murano_networks:
        env_names = [e.name for e in env_api.environments_list(request)]

        def get_net_env(name):
            for env_name in env_names:
                if name.startswith(env_name + '-network'):
                    return env_name

    network_choices = []
    tenant_id = request.user.tenant_id
    try:
        networks = neutron.network_list_for_tenant(request,
                                                   tenant_id=tenant_id)
    except exceptions.ServiceCatalogException:
        LOG.warning("Neutron not found. Assuming Nova Network usage")
        return None

    # Remove external networks
    if exclude_ext_net:
        networks = [network for network in networks
                    if network.router__external is False]
    if filter:
        networks = [network for network in networks
                    if re.match(filter, network.name) is not None]

    for net in networks:
        env = None
        netname = None

        if murano_networks and len(net.subnets) == 1:
            env = get_net_env(net.name)
        if env:
            if murano_networks == 'exclude':
                continue
            else:
                netname = _("Network of '%s'") % env

        if include_subnets:
            for subnet in net.subnets:
                if not netname:
                    full_name = (
                        "%(net)s: %(cidr)s %(subnet)s" %
                        dict(net=net.name_or_id,
                             cidr=subnet.cidr,
                             subnet=subnet.name_or_id))

                network_choices.append(
                    ((net.id, subnet.id), netname or full_name))

        else:
            netname = netname or net.name_or_id
            network_choices.append(((net.id, None), netname))
    return network_choices


from django.template import loader
import floppyforms
from horizon import tables
class Column(tables.Column):
    template_name = 'common/form-fields/data-grid/input.html'

    def __init__(self, transform, table_name=None, **kwargs):
        if hasattr(self, 'template_name'):
            def _transform(datum):
                context = {'data': getattr(datum, self.name, None),
                           'row_index': str(datum.id),
                           'table_name': table_name,
                           'column_name': self.name}
                return loader.render_to_string(self.template_name, context)
            _transform.__name__ = transform
            transform = _transform
        super(Column, self).__init__(transform, **kwargs)


class CheckColumn(Column):
    template_name = 'common/form-fields/data-grid/checkbox.html'


class RadioColumn(Column):
    template_name = 'common/form-fields/data-grid/radio.html'


# FixME: we need to have separated object until find out way to use the same
# code for MS SQL Cluster datagrid
class Object(object):
    def __init__(self, id, **kwargs):
        self.id = id
        for key, value in kwargs.iteritems():
            setattr(self, key, value)

    def as_dict(self):
        item = {}
        for key, value in self.__dict__.iteritems():
            if key != 'id':
                item[key] = value
        return item


def DataTableFactory(name, columns):
    class Object(object):
        row_name_re = re.compile(r'.*\{0}.*')

        def __init__(self, id, **kwargs):
            self.id = id
            for key, value in kwargs.iteritems():
                if isinstance(value, basestring) and \
                        re.match(self.row_name_re, value):
                    setattr(self, key, value.format(id))
                else:
                    setattr(self, key, value)

    class DataTableBase(tables.DataTable):
        def __init__(self, request, data, **kwargs):
            if len(data) and isinstance(data[0], dict):
                objects = [Object(i, **item)
                           for (i, item) in enumerate(data, 1)]
            else:
                objects = data
            super(DataTableBase, self).__init__(request, objects, **kwargs)

    class Meta:
        template = 'common/form-fields/data-grid/data_table.html'
        name = ''
        footer = False

    attrs = dict((col_id, cls(col_id, verbose_name=col_name, table_name=name))
                 for (col_id, cls, col_name) in columns)
    attrs['Meta'] = Meta
    return tables.base.DataTableMetaclass('DataTable', (DataTableBase,), attrs)


class TableWidget(floppyforms.widgets.Input):
    template_name = 'common/form-fields/data-grid/table_field.html'
    delimiter_re = re.compile('([\w-]*)@@([0-9]*)@@([\w-]*)')
    types = {'label': Column,
             'radio': RadioColumn,
             'checkbox': CheckColumn}

    def __init__(self, columns_spec=None, table_class=None, js_buttons=True,
                 min_value=None, max_value=None, max_sync=None,
                 *args, **kwargs):
        assert columns_spec is not None or table_class is not None
        self.columns = []
        if columns_spec:
            for spec in columns_spec:
                name = spec['column_name']
                self.columns.append((name,
                                     self.types[spec['column_type']],
                                     spec.get('title', None) or name.title()))
        self.table_class = table_class
        self.js_buttons = js_buttons
        self.min_value = min_value
        self.max_value = max_value
        self.max_sync = max_sync
        # FixME: we need to use this hack because TableField passes all kwargs
        # to TableWidget
        for kwarg in ('widget', 'description', 'description_title'):
            kwargs.pop(kwarg, None)
        super(TableWidget, self).__init__(*args, **kwargs)

    def get_context(self, name, value, attrs=None):
        ctx = super(TableWidget, self).get_context_data()
        if value:
            if self.table_class:
                cls = self.table_class
            else:
                cls = DataTableFactory(name, self.columns)
            ctx.update({
                'data_table': cls(self.request, value),
                'js_buttons': self.js_buttons,
                'min_value': self.min_value,
                'max_value': self.max_value,
                'max_sync': self.max_sync
            })
        return ctx

    def value_from_datadict(self, data, files, name):
        def extract_value(row_key, col_id, col_cls):
            if col_cls == CheckColumn:
                val = data.get("{0}@@{1}@@{2}".format(name, row_key, col_id),
                               False)
                return val and val == 'on'
            elif col_cls == RadioColumn:
                row_id = data.get("{0}@@@@{1}".format(name, col_id), False)
                return row_id == row_key
            else:
                return data.get("{0}@@{1}@@{2}".format(
                    name, row_key, col_id), None)

        def extract_keys():
            keys = set()
            regexp = re.compile('^{name}@@([^@]*)@@.*$'.format(name=name))
            for key in data.iterkeys():
                match = re.match(regexp, key)
                if match and match.group(1):
                    keys.add(match.group(1))
            return keys

        items = []
        if self.table_class:
            columns = [(_name, column.__class__, unicode(column.verbose_name))
                       for (_name, column)
                       in self.table_class.base_columns.items()]
        else:
            columns = self.columns

        for row_key in extract_keys():
            item = {}
            for column_id, column_instance, column_name in columns:
                value = extract_value(row_key, column_id, column_instance)
                item[column_id] = value
            items.append(Object(row_key, **item))

        return items

    class Media:
        css = {'all': ('muranodashboard/css/tablefield.css',)}


class TableField(CustomPropertiesField):
    def __init__(self, columns=None, label=None, table_class=None,
                 initial=None,
                 **kwargs):
        widget = TableWidget(columns, table_class, **kwargs)
        super(TableField, self).__init__(
            label=label, widget=widget, initial=initial)

    @with_request
    def update(self, request, **kwargs):
        self.widget.request = request

    def clean(self, objects):
        return [obj.as_dict() for obj in objects]


class VolumeChoiceField(DynamicChoiceField):
    def __init__(self, filter={}, *args, **kwargs):
        self.filter = filter
        super(VolumeChoiceField, self).__init__(*args, **kwargs)

    @with_request
    def update(self, request, **kwargs):
        no_root = self.filter.pop('no_root', False)
        vols = cinder.cinderclient(request).volumes.list(search_opts=self.filter)
        if no_root:
            f_vols = []
            for vol in vols:
                if vol.bootable != 'true':
                    f_vols.append(vol)
                else:
                    for attach in vol.attachments:
                        if attach['device'] not in ['/dev/vda', '/dev/sda']:
                            f_vols.append(vol)
            vols = f_vols
        self.choices = [(vol.id, '{0}({1})'.format(vol.id, vol.name.encode('utf-8'))) for vol in vols]
        if vols:
            self.choices.insert(0, ('', _('Select Volume')))
        else:
            self.choices.insert(0, ('', _('No volume available')))


class InstanceChoiceField(ChoiceField):
    def __init__(self, *args, **kwargs):
        self.filter = {}
        if 'filter' in kwargs:
            self.filter = kwargs.pop('filter')
        super(InstanceChoiceField, self).__init__(*args, **kwargs)

    @with_request
    def update(self, request, **kwargs):
        instances, has_more = nova.server_list(request, search_opts=self.filter)
        #if(self.filter['power_state']):
        #    instances = [instance for instance in instances if getattr(instance, "OS-EXT-STS:power_state", 0) in self.filter['power_state']]
        insts = [(inst.id, '{0}({1})'.format(inst.name, inst.id)) for inst in instances]
        if insts:
            insts.insert(0, ("", _("Select Instance")))
        else:
            insts.insert(0, ("", _("No instance available")))
        self.choices = insts


class VolumeTypeField(ChoiceField):
    def __init__(self, *args, **kwargs):
        self.filter = {}
        if 'filter' in kwargs:
            self.filter = kwargs.pop('filter')
        super(VolumeTypeField, self).__init__(*args, **kwargs)

    @with_request
    def update(self, request, **kwargs):
        try:
            volume_types = cinder.volume_type_list(request)
        except Exception:
            volume_types = []
            exceptions.handle(request, _("Unable to retrieve volume types."))
        az = self.filter.pop('availability_zone', None)
        if az:
            volume_types = [volume_type for volume_type in volume_types if volume_type.extra_specs['availability-zone']==az]
        choices = [(volume_type.name, volume_type.name) for volume_type in volume_types]
        if choices:
            choices.insert(0, ('', _('Select Volume Type')))
        else:
            choices.insert(0, ("", _("No volume types available")))
        self.choices = choices


from openstack_dashboard.dashboards.project.images import utils as image_utils
class ImageChoiceField(ChoiceField):
    @with_request
    def update(self, request, **kwargs):
        try:
            images = image_utils.get_available_images(request, request.user.tenant_id, None)
        except Exception:
            images = []
            exceptions.handle(request, _("Unable to retrieve volume types."))
        choices = [(image.id, image.name) for image in images]
        if not choices:
            choices.insert(0, ("", _("No images available")))
        self.choices = choices


class FlavorChoiceField(ChoiceField):
    def __init__(self, *args, **kwargs):
        if 'requirements' in kwargs:
            self.requirements = kwargs.pop('requirements')
        super(FlavorChoiceField, self).__init__(*args, **kwargs)

    @with_request
    def update(self, request, **kwargs):
        self.choices = []
        flavors = nova.novaclient(request).flavors.list()

        # If no requirements are present, return all the flavors.
        if not hasattr(self, 'requirements'):
            self.choices = [(flavor.id, flavor.name) for flavor in flavors]
        else:
            for flavor in flavors:
                # If a flavor doesn't meet a minimum requirement,
                # do not add it to the options list and skip to the
                # next flavor.
                if flavor.vcpus < self.requirements.get('min_vcpus', 0):
                    continue
                if flavor.disk < self.requirements.get('min_disk', 0):
                    continue
                if flavor.ram < self.requirements.get('min_memory_mb', 0):
                    continue
                if 'max_vcpus' in self.requirements:
                    if flavor.vcpus > self.requirements['max_vcpus']:
                        continue
                if 'max_disk' in self.requirements:
                    if flavor.disk > self.requirements['max_disk']:
                        continue
                if 'max_memory_mb' in self.requirements:
                    if flavor.ram > self.requirements['max_memory_mb']:
                        continue
                self.choices.append((flavor.id, flavor.name))
        # Search through selected flavors
        if not self.initial:
            for flavor_id, flavor_name in self.choices:
                if 'small' in flavor_name:
                    self.initial = flavor_id
                    break


class NetworkChoiceField(ChoiceField):
    def __init__(self,
                 include_subnets=True,
                 filter=None,
                 murano_networks=None,
                 allow_auto=False,
                 exclude_ext_net=True,
                 *args,
                 **kwargs):
        self.filter = filter
        if murano_networks:
            if murano_networks.lower() not in ["exclude", "translate"]:
                raise ValueError(_("Invalid value of 'murano_nets' option"))
        self.murano_networks = murano_networks
        self.include_subnets = include_subnets
        self.allow_auto = allow_auto
        self.exclude_ext_net = exclude_ext_net
        super(NetworkChoiceField, self).__init__(*args,
                                                 **kwargs)

    @with_request
    def update(self, request, **kwargs):
        """Populates available networks in the control

        This method is called automatically when the form which contains it is
        rendered
        """
        network_choices = get_available_networks(request,
                                                     self.include_subnets,
                                                     self.filter,
                                                     self.murano_networks, self.exclude_ext_net)
        if self.allow_auto:
            network_choices.insert(0, ((None, None), _('Auto')))
        self.choices = network_choices or []

    def to_python(self, value):
        """Converts string representation of widget to tuple value

        Is called implicitly during form cleanup phase
        """
        if value:
            return ast.literal_eval(value)
        else:  # may happen if no networks are available and "Auto" is disabled
            return None, None


import datetime
class DateField(forms.CharField, CustomPropertiesField):
    default_error_messages = {
        'invalid': _('Enter a valid date.'),
    }
    def clean(self, value):
        try:
            return datetime.datetime.strptime(value, '%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError as e:
            raise ValidationError(self.default_error_messages['invalid'], code='invalid')


class TimeField(forms.TimeField, CustomPropertiesField):
    default_error_messages = {
        'invalid': _('Enter a valid time.')
    }
    def clean(self, value):
        l = len(value.split(":"))
        if l == 1:
            s_datetime = '{0}:0:0'.format(value)
        elif l == 2:
            s_datetime = '{0}:0'.format(value)
        else:
            s_datetime = value
        try:
            return datetime.datetime.strptime(s_datetime, '%H:%M:%S').strftime('%H:%M:%S')
        except ValueError as e:
            raise ValidationError(self.default_error_messages['invalid'], code='invalid')


class PasswordField(fields.PasswordField):
    def clean(self, value):
        if self.original:
            form_data = self.form.fields
            for k,v in form_data.iteritems():
                if v == self:
                    name = k
                    break
            form = self.form
            if value != form.data[form.add_prefix(self.get_clone_name(name))]:
                raise ValidationError(_(u"{0}{1} don't match").format(self.label, defaultfilters.pluralize(2)))
        return super(PasswordField, self).clean(value)


class SecretField(forms.CharField, CustomPropertiesField):
    def __init__(self, label, *args, **kwargs):
        kwargs.update({
            'label': label,
            'widget': forms.PasswordInput,
        })
        super(SecretField, self).__init__(*args, **kwargs)


class AZonesChoiceField(forms.MultipleChoiceField, CustomPropertiesField):
    widget = forms.CheckboxSelectMultiple

    @with_request
    def update(self, request, **kwargs):
        try:
            availability_zones = nova.novaclient(
                request).availability_zones.list(detailed=False)
        except Exception:
            availability_zones = []
            exceptions.handle(request,
                              _("Unable to retrieve  availability zones."))

        az_choices = [(az.zoneName, az.zoneName)
                      for az in availability_zones if az.zoneState['available']]
        if not az_choices:
            az_choices.insert(0, ("", _("No availability zones available")))

        self.choices = az_choices


class DCWidget(forms.Select):
    def render_option(self, selected_choices, option_value, option_label):
        option_value = force_text(option_value)
        other_html = (u' selected="selected"'
                      if option_value in selected_choices else '')
        
        vals = option_value.split("--")
        style = 'dclist_default'
        cloud = ""
        if len(vals) > 1:
            #if vals[1] == 'fusionsphere':
            #    vals[1] = 'openstack'
            style = 'dclist_' + vals[1]
            cloud = '(' + _(vals[1]).encode('ascii','ignore') + ')'
        else:
            if len(vals[0]) < 1:
                vals[0] = option_label

        return u'<option class="%s" value="%s"%s>%s</option>' % (style,
            html.escape(option_value), other_html,
            html.conditional_escape(vals[0]+cloud))


class PodAZoneChoiceField(ChoiceField):
    widget=DCWidget(attrs={'onchange':'update_az_fields();'})
    @with_request
    def update(self, request, **kwargs):
        try:
            availability_zones = nova.novaclient(request).availability_zones.list(detailed=False)
        except Exception:
            availability_zones = []
            exceptions.handle(request, _("Unable to retrieve  availability zones."))
        az_choices = [(az.zoneName, az.zoneName) for az in availability_zones if az.zoneState['available']]
        if not az_choices:
            az_choices.insert(0, ("", _("No availability zones available")))
        self.choices = az_choices


class AWSRegionChoiceField(ChoiceField):
    REGION_MAP = [
                    ('tokyo', 'Tokyo'),
                    ('singapore', 'Singapore'),
                    ('sydney', 'Sydney'),
                    ('ireland', 'Ireland'),
                    ('frankfurt', 'Frankfurt'),
                    ('sao-paulo', 'Sao Paulo'),
                    ('virginia', 'N. Virginia'),
                    ('california', 'N. California'),
                    ('oregon', 'Oregon')
                ]
    @with_request
    def update(self, request, **kwargs):
        self.choices = [('', _('Select AWS Region'))]
        for region in AWSRegionChoiceField.REGION_MAP:
            self.choices.append(region)


