FROM hybrid/murano:base

RUN  rm -rf /usr/lib/python2.7/dist-packages/murano && rm -rf /usr/local/lib/python2.7/dist-packages/muranodashboard

COPY etc/ /etc/
COPY openstack_dashboard/ /usr/share/openstack-dashboard/openstack_dashboard/
COPY hybrid_ui/ /usr/local/lib/python2.7/dist-packages/hybrid_ui/
COPY murano/ /usr/lib/python2.7/dist-packages/murano/
COPY muranodashboard/ /usr/local/lib/python2.7/dist-packages/muranodashboard/

RUN  sed -i "s/%%MYSQL_PASSWORD%%/$MYSQL_PASSWORD/g" /etc/murano/murano.conf.template && \
     sed -i "s/%%MYSQL_PASSWORD%%/$MYSQL_PASSWORD/g" /etc/start.sh && chmod -v +x /etc/start.sh && \
     service mysql restart && murano-db-manage --config-file /etc/murano/murano.conf.template upgrade && \
     
     MULTI_DOMAIN="False" PAGINATE="False" && \
     TZ=`echo $TZ|sed "s/\//\\\\\\\\\\//g"` && sed "s/%%TZ%%/$TZ/g" /etc/openstack-dashboard/local_settings.py.template > /etc/openstack-dashboard/local_settings.py && \
     sed -i "s/%%PAGINATE%%/$PAGINATE/g" /etc/openstack-dashboard/local_settings.py && \
     sed -i "s/%%MULTI_DOMAIN%%/$MULTI_DOMAIN/g" /etc/openstack-dashboard/local_settings.py && \
     cp -sf /usr/local/lib/python2.7/dist-packages/hybrid_ui/enabled/_8*.py /usr/share/openstack-dashboard/openstack_dashboard/local/enabled/ && \
     msgfmt /usr/local/lib/python2.7/dist-packages/muranodashboard/locale/zh_CN/LC_MESSAGES/django.po -o /usr/local/lib/python2.7/dist-packages/muranodashboard/locale/zh_CN/LC_MESSAGES/django.mo && \
     msgfmt /usr/local/lib/python2.7/dist-packages/hybrid_ui/locale/en/LC_MESSAGES/django.po -o /usr/local/lib/python2.7/dist-packages/hybrid_ui/locale/en/LC_MESSAGES/django.mo && \
     msgfmt /usr/local/lib/python2.7/dist-packages/hybrid_ui/locale/zh_CN/LC_MESSAGES/django.po -o /usr/local/lib/python2.7/dist-packages/hybrid_ui/locale/zh_CN/LC_MESSAGES/django.mo && \
     /usr/share/openstack-dashboard/manage.py collectstatic --noinput && /usr/share/openstack-dashboard/manage.py compress -v 3 && \
     
     apt-get clean autoclean && apt-get autoremove -y && rm -rf /var/lib/apt /var/cache/ /tmp/muranodashboard-cache /tmp/murano-packages-cache && mkdir -p /var/cache/apt/archives/partial

EXPOSE 80
CMD ["/etc/start.sh"]
