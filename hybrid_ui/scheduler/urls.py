from django.conf import urls

import views

from muranodashboard.dynamic_ui import services
wizard_view = views.Wizard.as_view(services.get_app_forms, condition_dict=services.condition_getter)

urlpatterns = [
    urls.url(r'^$', views.SchedulerView.as_view(), name='index'),
    urls.url(r'^(?P<service_id>[^/]+)?$', views.DetailServiceView.as_view(), name='service_details'),
    urls.url(r'^deployments/(?P<deployment_id>[^/]+)$', views.DeploymentDetailsView.as_view(), name='deployment_details'),
    urls.url(r'^add/(?P<app_id>[^/]+)/(?P<do_redirect>[^/]+)/(?P<drop_wm_form>[^/]+)$', wizard_view, name='add'),
    urls.url(r'^start_action/(?P<action_id>[^/]+)/$', views.StartActionView.as_view(), name='start_action'),
    urls.url(r'^actions/(?P<task_id>[^/]+)(?:/(?P<optional>[^/]+))?/$', views.ActionResultView.as_view(), name='action_result'),
]
