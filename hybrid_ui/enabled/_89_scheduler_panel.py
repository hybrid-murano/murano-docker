# The name of the panel to be added to HORIZON_CONFIG. Required.
PANEL = 'scheduler'
# The name of the dashboard the PANEL associated with. Required.
PANEL_DASHBOARD = 'murano'
# The name of the panel group the PANEL is associated with.
PANEL_GROUP = 'deployment_group'
# Python panel class of the PANEL to be added.
ADD_PANEL = 'hybrid_ui.scheduler.panel.Scheduler'

ADD_INSTALLED_APPS = [
    'hybrid_ui',
]
