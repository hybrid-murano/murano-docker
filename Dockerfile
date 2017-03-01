# docker run -d --net=host -v /proc/1/ns:/ns-net hybrid/murano:mitaka

FROM hybrid/openstack:base

RUN  rm -rf /usr/lib/python2.7/dist-packages/murano && rm -rf /usr/local/lib/python2.7/dist-packages/muranodashboard

COPY etc/ /etc/
COPY openstack_dashboard/ /usr/share/openstack-dashboard/openstack_dashboard/
COPY hybrid_ui/ /usr/local/lib/python2.7/dist-packages/hybrid_ui/
COPY murano/ /usr/lib/python2.7/dist-packages/murano/
COPY muranodashboard/ /usr/local/lib/python2.7/dist-packages/muranodashboard/

RUN  chmod -v +x /etc/start.sh /etc/init.d/murano* /usr/local/bin/murano* && \
     apt-get clean autoclean && apt-get autoremove -y && rm -rf /var/lib/apt /var/cache/ /tmp/muranodashboard-cache /tmp/murano-packages-cache && mkdir -p /var/cache/apt/archives/partial

EXPOSE 80
CMD ["/etc/start.sh"]
