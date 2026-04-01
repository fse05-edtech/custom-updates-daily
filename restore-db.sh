#!/bin/bash
echo "Restoring Guacamole DB..."
docker network connect platform-net guacdb 2>/dev/null || true
docker network connect platform-net guacd 2>/dev/null || true
docker exec -i guacdb psql -U guacamole_user -d guacamole_db < ~/guac-docker/initdb.sql 2>/dev/null
docker exec guacdb psql -U guacamole_user -d guacamole_db -c "CREATE USER guacamole WITH PASSWORD 'guacamole' SUPERUSER;" 2>/dev/null || true
docker exec guacdb psql -U guacamole_user -d guacamole_db -c "INSERT INTO guacamole_connection (connection_name, protocol) VALUES ('Linux SSH', 'ssh'),('Test Linux VNC', 'vnc') ON CONFLICT DO NOTHING;"
docker exec guacdb psql -U guacamole_user -d guacamole_db -c "INSERT INTO guacamole_connection_parameter VALUES (1,'hostname','172.26.197.98'),(1,'port','22'),(1,'username','user1'),(1,'password','4323'),(2,'hostname','172.26.197.98'),(2,'port','5900') ON CONFLICT DO NOTHING;"
docker exec guacdb psql -U guacamole_user -d guacamole_db -c "INSERT INTO guacamole_entity (name,type) VALUES ('ashutoshmishr007@gmail.com','USER'),('guacuser@platform.com','USER') ON CONFLICT DO NOTHING;"
docker exec guacdb psql -U guacamole_user -d guacamole_db -c "INSERT INTO guacamole_user (entity_id,password_hash,password_salt,password_date) SELECT entity_id,decode('CA458A7D494E3BE824F5E1E175A1556C0F8EEF2C2D7DF3633BEC4A29C4411960','hex'),decode('FE24ADC5E11E2B25288D1704ABE67A79E342ECC26064CE69C5B3177795A82264','hex'),now() FROM guacamole_entity WHERE name IN ('ashutoshmishr007@gmail.com','guacuser@platform.com') ON CONFLICT DO NOTHING;"
docker exec guacdb psql -U guacamole_user -d guacamole_db -c "INSERT INTO guacamole_connection_permission (entity_id,connection_id,permission) SELECT e.entity_id,c.connection_id,'READ'::guacamole_object_permission_type FROM guacamole_entity e,guacamole_connection c WHERE e.name='guacuser@platform.com' ON CONFLICT DO NOTHING;"
docker exec guacdb psql -U guacamole_user -d guacamole_db -c "INSERT INTO guacamole_connection_permission (entity_id,connection_id,permission) SELECT e.entity_id,c.connection_id,'READ'::guacamole_object_permission_type FROM guacamole_entity e,guacamole_connection c WHERE e.name='ashutoshmishr007@gmail.com' ON CONFLICT DO NOTHING;"
docker exec guacdb psql -U guacamole_user -d guacamole_db -c "INSERT INTO guacamole_system_permission (entity_id,permission) SELECT entity_id,p::guacamole_system_permission_type FROM guacamole_entity,(VALUES ('ADMINISTER'),('CREATE_CONNECTION'),('CREATE_CONNECTION_GROUP'),('CREATE_SHARING_PROFILE'),('CREATE_USER'),('CREATE_USER_GROUP')) AS t(p) WHERE name='ashutoshmishr007@gmail.com' ON CONFLICT DO NOTHING;"
docker restart guacamole
sleep 15
docker cp ~/guac-docker/guac-dashboard.html guacamole:/home/guacamole/tomcat/webapps/guacamole/dashboard.html
echo "DB Restored!"
