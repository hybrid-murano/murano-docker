from openstack_auth import user as auth_user
from django.contrib.auth import models
from django.contrib import auth
from django import shortcuts

from django.contrib.auth.decorators import login_required  # noqa
from keystoneclient.v3 import client as v3_client
from keystoneclient.auth.identity import v3 as v3_auth
from openstack_dashboard.api import base
from openstack_dashboard.api import keystone

def sso(request):
    token = request.REQUEST.get('token')
    project_id = request.REQUEST.get('vdcId')
    if token is None or project_id is None:
        return None
    token = token.replace(' ', '+')
    try:
        request.user = auth.authenticate(request=request, auth_url=auth_url, token=token, project_id=project_id)
        auth_user.set_session_from_user(request, request.user)
        auth.login(request, request.user)
        if request.session.test_cookie_worked():
            request.session.delete_test_cookie()
        return request.user
    except Exception:
        return None

def get_user(request):
    try:
        user_id = request.session[auth.SESSION_KEY]
        backend_path = request.session[auth.BACKEND_SESSION_KEY]
        backend = auth.load_backend(backend_path)
        backend.request = request
        user = backend.get_user(user_id) or models.AnonymousUser()
    except KeyError:
        user = sso(request) or models.AnonymousUser()
    return user

@login_required
def sso_jump(request, service):
    endpoint = base.url_for(request, service, region='global')
    ks = keystone.keystoneclient(request, admin=True)
    auth_url = ks.get_endpoint(None).replace('v2.0', 'v3')
    auth_methods = [v3_auth.TokenMethod(token=request.user.token.id)]
    plugin = v3_auth.Auth(auth_url, auth_methods, project_id=request.user.tenant_id, include_catalog=False)
    token = plugin.get_auth_ref(ks.session).auth_token
    redirect_url = ('%s?vdcId=%s&token=%s'%(endpoint, request.user.tenant_id, token))
    return shortcuts.redirect(redirect_url)

from openstack_auth import urls
from django.conf.urls import url
def patch():
    auth.get_user = get_user
    urls.urlpatterns.append(url(r"^sso_jump/(?P<service>[^/]+)/$", sso_jump, name='sso_jump'))
