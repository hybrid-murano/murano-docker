#!/bin/sh

if [ -z "${HOST}" ] ; then
    HOST=`ip address show up|grep -v 'inet6'|grep 'inet'|grep -v 'docker'|tail -n1|awk '{print $2}'|cut -f1  -d'/'`
fi
if [ -z "${MQ_HOST}" ]; then
    MQ_HOST=${HOST}
fi
if [ -z "${KEYSTONE}" ] ; then
    KEYSTONE="http://127.0.0.1:5000"
    SERVICE_ON=1
fi
if [ -z "${REGION}" ] ; then
    REGION="cloud.hybrid"
fi
if [ -z "${TZ}" ] ; then
    TZ="Asia/Chongqing"
fi
echo ${TZ} > /etc/timezone && dpkg-reconfigure -f noninteractive tzdata
if [ -z "${PASSWORD}" ] ; then
    PASSWORD=${MYSQL_PASSWORD}
fi
if [ -z "${MULTI_DOMAIN}" ]; then
    MULTI_DOMAIN="True"
fi
if [ -z "${PAGINATE}" ]; then
    PAGINATE="False"
fi
if [ -z "${MQ_USER}" ]; then
    MQ_USER="murano"
fi
if [ -z "${MQ_PASS}" ]; then
    MQ_PASS=${PASSWORD}
fi
if [ -z "${MQ_SSL}" ]; then
    MQ_SSL="false"
fi

TZ_sed=`echo $TZ|sed "s/\//\\\\\\\\\\//g"`
KEYSTONE_sed=`echo $KEYSTONE|sed "s/\//\\\\\\\\\\//g"`

sed "s/%%KEYSTONE%%/$KEYSTONE_sed/g" /etc/murano/murano.conf.template | tee /etc/murano/murano.conf
sed -i "s/%%PASSWORD%%/$PASSWORD/g" /etc/murano/murano.conf
sed -i "s/%%REGION%%/$REGION/g" /etc/murano/murano.conf
sed -i "s/%%MQ_HOST%%/$MQ_HOST/g" /etc/murano/murano.conf
sed -i "s/%%MQ_USER%%/$MQ_USER/g" /etc/murano/murano.conf
sed -i "s/%%MQ_PASS%%/$MQ_PASS/g" /etc/murano/murano.conf
sed -i "s/%%MQ_SSL%%/$MQ_SSL/g" /etc/murano/murano.conf

sed "s/%%TZ%%/$TZ_sed/g" /etc/openstack-dashboard/local_settings.py.template | tee /etc/openstack-dashboard/local_settings.py
sed -i "s/%%KEYSTONE%%/$KEYSTONE_sed/g" /etc/openstack-dashboard/local_settings.py
sed -i "s/%%REGION%%/$REGION/g" /etc/openstack-dashboard/local_settings.py
sed -i "s/%%PAGINATE%%/$PAGINATE/g" /etc/openstack-dashboard/local_settings.py
sed -i "s/%%MULTI_DOMAIN%%/$MULTI_DOMAIN/g" /etc/openstack-dashboard/local_settings.py

service_init() {
    ADMIN_TOKEN=dcf9aaec0ac46e841459
    export OS_TOKEN=$ADMIN_TOKEN OS_URL=http://127.0.0.1:35357/v3 OS_IDENTITY_API_VERSION=3
    
    sed "s/%%MYSQL_PASSWORD%%/$MYSQL_PASSWORD/g" /etc/ironic/ironic.conf.template | tee /etc/ironic/ironic.conf
    sed -i "s/%%KEYSTONE%%/$KEYSTONE_sed/g" /etc/ironic/ironic.conf
    sed -i "s/%%HOST%%/$HOST/g" /etc/ironic/ironic.conf
    sed -i "s/%%PASSWORD%%/$PASSWORD/g" /etc/ironic/ironic.conf
    sed -i "s/%%MQ_PASS%%/$MQ_PASS/g" /etc/ironic/ironic.conf
    sed -i "s/%%REGION%%/$REGION/g" /etc/ironic/ironic.conf

    sed -i "s/%%MYSQL_PASSWORD%%/$MYSQL_PASSWORD/g" /etc/glance/glance-api.conf
    sed -i "s/%%MYSQL_PASSWORD%%/$MYSQL_PASSWORD/g" /etc/glance/glance-registry.conf
    #sed -i "s/%%MYSQL_PASSWORD%%/$MYSQL_PASSWORD/g" /etc/nova/nova.conf.template
    sed -i "s/%%MYSQL_PASSWORD%%/$MYSQL_PASSWORD/g" /etc/keystone/keystone.conf
    ##sed -i "s/%%MYSQL_PASSWORD%%/$MYSQL_PASSWORD/g" /etc/murano/murano.conf.template
    ##mysql -u root -p$MYSQL_PASSWORD -e "CREATE DATABASE murano;" && murano-db-manage --config-file /etc/murano/murano.conf.template upgrade
    mysql -u root -p$MYSQL_PASSWORD -e "CREATE DATABASE keystone;" && su -s /bin/sh -c "keystone-manage db_sync" keystone
    mysql -u root -p$MYSQL_PASSWORD -e "CREATE DATABASE glance;" && su -s /bin/sh -c "glance-manage db_sync" glance
    mysql -u root -p$MYSQL_PASSWORD -e "CREATE DATABASE ironic CHARACTER SET utf8;" && ironic-dbsync --config-file /etc/ironic/ironic.conf.template create_schema
    #mysql -u root -p$MYSQL_PASSWORD -e "CREATE DATABASE nova_api;" && mysql -u root -p$MYSQL_PASSWORD -e "CREATE DATABASE nova;"
    
    sed -i "s/%%ADMIN_TOKEN%%/$ADMIN_TOKEN/g" /etc/keystone/keystone.conf
    keystone-manage fernet_setup --keystone-user keystone --keystone-group keystone
    service keystone restart && rm -f /var/lib/keystone/keystone.db
    
    RETRY=15; while [[ $RETRY -gt 0 ]]; do nc -z -w 3 127.0.0.1 5000; if [ $? = 0 ]; then break; fi; sleep 2; RETRY=`expr $RETRY - 1`; done
    openstack endpoint create --region $REGION identity public http://$HOST:5000/v3
    openstack endpoint create --region $REGION identity internal http://$HOST:5000/v3
    openstack endpoint create --region $REGION identity admin http://$HOST:35357/v3
    openstack endpoint create --region $REGION image public http://$HOST:9292
    openstack endpoint create --region $REGION image internal http://$HOST:9292
    openstack endpoint create --region $REGION image admin http://$HOST:9292
    openstack endpoint create --region $REGION baremetal public http://$HOST:6385
    openstack endpoint create --region $REGION baremetal internal http://$HOST:6385
    openstack endpoint create --region $REGION baremetal admin http://$HOST:6385
    
    openstack service create --name keystone --description "OpenStack Identity" identity
    openstack domain create --description "Default Domain" default
    openstack project create --domain Default --description "Admin Project" admin
    openstack user create --domain Default --password $MYSQL_PASSWORD cloud_admin
    openstack role create admin
    openstack role add --project admin --user cloud_admin admin
    openstack project create --domain Default --description "Service Project" service
    openstack user create --domain Default --password $MYSQL_PASSWORD heat
    openstack role add --project service --user heat admin
    
    openstack service create --name glance --description "OpenStack Image" image
    openstack user create --domain Default --password $MYSQL_PASSWORD glance
    openstack role add --project service --user glance admin
    openstack service create --name ironic --description "Ironic baremetal provisioning service" baremetal
    openstack user create --domain Default --password $MYSQL_PASSWORD ironic
    openstack role add --project service --user ironic admin
    openstack role create baremetal_admin && openstack role create baremetal_observer
    #openstack service create --name nova --description "OpenStack Compute" compute
    #openstack user create --domain Default --password $MYSQL_PASSWORD nova
    #openstack role add --project service --user nova admin
    #openstack endpoint create --region $REGION compute public http://$HOST:8774/v2.1/%\(tenant_id\)s
    #openstack endpoint create --region $REGION compute internal http://$HOST:8774/v2.1/%\(tenant_id\)s
    #openstack endpoint create --region $REGION compute admin http://$HOST:8774/v2.1/%\(tenant_id\)s
    touch /etc/ready
}

service_start() {
    service rabbitmq-server restart; service mysql restart
    rabbitmqctl delete_user murano; rabbitmqctl add_user murano ${PASSWORD}; rabbitmqctl set_permissions murano ".*" ".*" ".*"
    if [ ! -e /etc/ready ] ; then
        mysql -u root -p$MYSQL_PASSWORD -e "CREATE DATABASE murano;" && murano-db-manage --config-file /etc/murano/murano.conf.template upgrade
        
        cp -sf /usr/local/lib/python2.7/dist-packages/hybrid_ui/enabled/_89_scheduler_panel.py /usr/share/openstack-dashboard/openstack_dashboard/local/enabled/
        msgfmt /usr/local/lib/python2.7/dist-packages/muranodashboard/locale/zh_CN/LC_MESSAGES/django.po -o /usr/local/lib/python2.7/dist-packages/muranodashboard/locale/zh_CN/LC_MESSAGES/django.mo
        msgfmt /usr/local/lib/python2.7/dist-packages/hybrid_ui/locale/en/LC_MESSAGES/django.po -o /usr/local/lib/python2.7/dist-packages/hybrid_ui/locale/en/LC_MESSAGES/django.mo
        msgfmt /usr/local/lib/python2.7/dist-packages/hybrid_ui/locale/zh_CN/LC_MESSAGES/django.po -o /usr/local/lib/python2.7/dist-packages/hybrid_ui/locale/zh_CN/LC_MESSAGES/django.mo
        /usr/share/openstack-dashboard/manage.py collectstatic --noinput && /usr/share/openstack-dashboard/manage.py compress -v 3
    fi
    if [ -n "${SERVICE_ON}" ]; then
        service keystone start
        service glance-registry start && service glance-api start
        service dnsmasq restart
        service open-iscsi start && service ironic-api start && service ironic-conductor start
        if [ ! -e /etc/ready ] ; then
            service_init
        fi
    fi
    service murano-api start && service murano-engine start
    service memcached restart; service apache2 restart
}

service_stop() {
    service apache2 stop; service memcached stop
    service murano-api stop; service murano-engine stop
    service ironic-api stop; service ironic-conductor stop; service open-iscsi stop
    service dnsmasq stop
    service glance-registry stop; service glance-api stop
    service keystone stop
    service rabbitmq-server stop; service mysql stop
}

sleep infinity &
pid="$!"
trap 'service_stop; kill $pid; exit' TERM

service_start

wait
