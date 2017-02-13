if [ -z "${KEYSTONE}" ] ; then
    export OS_AUTH_URL="http://127.0.0.1:5000/v3"
else
    export OS_AUTH_URL=${KEYSTONE}/v3
fi
export OS_IDENTITY_API_VERSION=3
export OS_USER_DOMAIN_NAME=Default
export OS_PROJECT_NAME=service
export OS_USERNAME=heat
if [ -z "${PASSWORD}" ] ; then
    export OS_PASSWORD=${MYSQL_PASSWORD}
else
    export OS_PASSWORD=${PASSWORD}
fi
alias openstack='openstack --insecure'
