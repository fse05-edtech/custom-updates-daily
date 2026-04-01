#!/bin/bash
docker exec guacdb psql -U guacamole_user -d guacamole_db -c "\COPY (SELECT e.name, c.connection_name FROM guacamole_connection_permission cp JOIN guacamole_entity e ON cp.entity_id=e.entity_id JOIN guacamole_connection c ON cp.connection_id=c.connection_id) TO '/tmp/assignments.csv' CSV HEADER"
echo "Backup done!"
