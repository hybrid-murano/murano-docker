from django.utils.translation import ugettext_lazy as _
import horizon

class Scheduler(horizon.Panel):
    name = _("Schedules")
    slug = 'scheduler'
