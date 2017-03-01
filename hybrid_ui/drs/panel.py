from django.utils.translation import ugettext_lazy as _
import horizon

class DRS(horizon.Panel):
    name = _("DRS")
    slug = 'drs'
