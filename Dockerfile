FROM guacamole/guacamole:1.5.4
USER root
COPY extensions/guacamole-logout-ext-1.5.4.jar /opt/guacamole/logout/guacamole-logout-ext-1.5.4.jar
COPY extensions/guacamole-backchannel-logout-1.5.4.jar /opt/guacamole/logout/guacamole-backchannel-logout-1.5.4.jar
COPY extensions/chipcraft-branding.jar /opt/guacamole/branding/chipcraft-branding.jar
RUN mkdir -p /opt/guacamole/branding && \
    chmod 644 /opt/guacamole/logout/guacamole-logout-ext-1.5.4.jar && \
    chmod 644 /opt/guacamole/logout/guacamole-backchannel-logout-1.5.4.jar && \
    chmod 644 /opt/guacamole/branding/chipcraft-branding.jar && \
    chmod +w /opt/guacamole/bin/start.sh && \
    sed -i 's|ln -sf /opt/guacamole/guacamole.war|ln -sf /opt/guacamole/logout/guacamole-logout-ext-1.5.4.jar "$GUACAMOLE_EXT/guacamole-logout-ext-1.5.4.jar" \&\& ln -sf /opt/guacamole/logout/guacamole-backchannel-logout-1.5.4.jar "$GUACAMOLE_EXT/guacamole-backchannel-logout-1.5.4.jar" \&\& ln -sf /opt/guacamole/branding/chipcraft-branding.jar "$GUACAMOLE_EXT/chipcraft-branding.jar" \&\& ln -sf /opt/guacamole/guacamole.war|' /opt/guacamole/bin/start.sh && \
    sed -i 's|exec "$CATALINA_HOME/bin/catalina.sh" run|cp /opt/guacamole/dashboard.html /home/guacamole/tomcat/webapps/guacamole/dashboard.html \&\& exec "$CATALINA_HOME/bin/catalina.sh" run|' /opt/guacamole/bin/start.sh
COPY guac-dashboard.html /opt/guacamole/dashboard.html
COPY logout-redirect.js /opt/guacamole/logout-redirect.js
USER guacamole
