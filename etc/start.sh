#!/bin/sh

if [ -z "${KEYSTONE}" ] ; then
    KEYSTONE="http://127.0.0.1:5000"
else
    rm -f /etc/apache2/sites-enabled/wsgi-keystone.conf
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
if [ -z "${MQ_HOST}" ]; then
    MQ_HOST="202.96.135.237"
fi
if [ -z "${MQ_USER}" ]; then
    MQ_USER="guest"
fi
if [ -z "${MQ_PASS}" ]; then
    MQ_PASS="openstack"
fi
if [ -z "${MQ_SSL}" ]; then
    MQ_SSL="false"
fi

TZ=`echo $TZ|sed "s/\//\\\\\\\\\\//g"`
KEYSTONE=`echo $KEYSTONE|sed "s/\//\\\\\\\\\\//g"`

sed "s/%%KEYSTONE%%/$KEYSTONE/g" /etc/murano/murano.conf.template | tee /etc/murano/murano.conf
sed -i "s/%%PASSWORD%%/$PASSWORD/g" /etc/murano/murano.conf
sed -i "s/%%REGION%%/$REGION/g" /etc/murano/murano.conf
sed -i "s/%%MQ_HOST%%/$MQ_HOST/g" /etc/murano/murano.conf
sed -i "s/%%MQ_USER%%/$MQ_USER/g" /etc/murano/murano.conf
sed -i "s/%%MQ_PASS%%/$MQ_PASS/g" /etc/murano/murano.conf
sed -i "s/%%MQ_SSL%%/$MQ_SSL/g" /etc/murano/murano.conf

sed "s/%%TZ%%/$TZ/g" /etc/openstack-dashboard/local_settings.py.template | tee /etc/openstack-dashboard/local_settings.py
sed -i "s/%%KEYSTONE%%/$KEYSTONE/g" /etc/openstack-dashboard/local_settings.py
sed -i "s/%%REGION%%/$REGION/g" /etc/openstack-dashboard/local_settings.py
sed -i "s/%%PAGINATE%%/$PAGINATE/g" /etc/openstack-dashboard/local_settings.py
sed -i "s/%%MULTI_DOMAIN%%/$MULTI_DOMAIN/g" /etc/openstack-dashboard/local_settings.py

service_start() {
    service rabbitmq-server restart && rabbitmqctl change_password guest %%MYSQL_PASSWORD%%
    service memcached restart; service mysql restart
    service murano-api restart; service murano-engine restart
    service apache2 restart
}

service_stop() {
    service apache2 stop
    service murano-api stop; service murano-engine stop
    service rabbitmq-server stop; service mysql stop; service memcached stop
}

sleep infinity &
pid="$!"
trap 'service_stop; kill $pid; exit' TERM

service_start

wait
