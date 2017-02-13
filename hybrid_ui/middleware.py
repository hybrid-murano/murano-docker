from muranodashboard.dynamic_ui.forms import TYPES
import dynamic_ui
def patch():
    TYPES.update({
        'table': dynamic_ui.TableField,
        'secret': dynamic_ui.SecretField,
        'volume': dynamic_ui.VolumeChoiceField,
        'instance': dynamic_ui.InstanceChoiceField,
        'volume_type': dynamic_ui.VolumeTypeField,
        'images': dynamic_ui.ImageChoiceField,
        'flavor_id': dynamic_ui.FlavorChoiceField,
        'networks': dynamic_ui.NetworkChoiceField,
        'date': dynamic_ui.DateField,
        'time': dynamic_ui.TimeField,
        'password': dynamic_ui.PasswordField,
        'podazone': dynamic_ui.PodAZoneChoiceField,
        'azones': dynamic_ui.AZonesChoiceField,
        'aws_region': dynamic_ui.AWSRegionChoiceField,
    })
