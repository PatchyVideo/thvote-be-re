#!/bin/sh

set -eu

MYSQL_HOST="${APOLLO_MYSQL_HOST:-apollo-mysql}"
MYSQL_PORT="${APOLLO_MYSQL_PORT:-3306}"
MYSQL_USER="${APOLLO_MYSQL_ROOT_USER:-root}"
MYSQL_PASSWORD="${APOLLO_MYSQL_ROOT_PASSWORD:-}"
PORTAL_ENVS="${APOLLO_PORTAL_ENVS:-dev}"
PORTAL_META_SERVERS="${APOLLO_PORTAL_META_SERVERS:-{\"dev\":\"http://apollo-configservice:8080\"}}"

mysql_exec() {
  mysql -h"${MYSQL_HOST}" -P"${MYSQL_PORT}" -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" "$@"
}

until mysqladmin ping -h"${MYSQL_HOST}" -P"${MYSQL_PORT}" -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" --silent; do
  echo "Waiting for Apollo MySQL to become ready..."
  sleep 2
done

config_db_ready="$(mysql_exec -Nse "SELECT 1 FROM information_schema.tables WHERE table_schema = 'ApolloConfigDB' AND table_name = 'App' LIMIT 1;" || true)"
if [ "${config_db_ready}" != "1" ]; then
  echo "Initializing ApolloConfigDB from official SQL..."
  mysql_exec < /apollo/sql/official/apolloconfigdb.sql
fi

portal_db_ready="$(mysql_exec -Nse "SELECT 1 FROM information_schema.tables WHERE table_schema = 'ApolloPortalDB' AND table_name = 'ServerConfig' LIMIT 1;" || true)"
if [ "${portal_db_ready}" != "1" ]; then
  echo "Initializing ApolloPortalDB from official SQL..."
  mysql_exec < /apollo/sql/official/apolloportaldb.sql
fi

echo "Applying THVote Apollo portal configuration..."
mysql_exec <<SQL
USE ApolloPortalDB;
INSERT INTO ServerConfig (\`Key\`, \`Value\`, \`Comment\`)
VALUES
  ('apollo.portal.envs', '${PORTAL_ENVS}', 'list of supported environments'),
  ('apollo.portal.meta.servers', '${PORTAL_META_SERVERS}', 'environment meta server mapping')
ON DUPLICATE KEY UPDATE
  \`Value\` = VALUES(\`Value\`),
  \`Comment\` = VALUES(\`Comment\`);
SQL

echo "Apollo bootstrap completed."
