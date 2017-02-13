from django.utils.translation import ugettext_lazy as _
import horizon

class Clouds(horizon.Panel):
    name = _("Clouds")
    slug = 'clouds'
    permissions = ('openstack.roles.admin',)
