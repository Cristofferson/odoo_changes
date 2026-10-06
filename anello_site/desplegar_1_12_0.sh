#!/bin/bash
# xb_joyeria_peso_precio 1.12.0: la ficha no cuenta la zirconia central como acento
set -e
sudo rm -rf /tmp/dev-addons
B=/opt/odoo/predeploy_backups/xb_joyeria_peso_precio-$(date +%Y%m%d-%H%M%S)
sudo mkdir -p $B && sudo cp -r /odoo/custom-addons/xb_joyeria_peso_precio $B/
sudo rsync -a --delete --exclude __pycache__ ~/anello-bluenile/xb_joyeria_peso_precio/ /odoo/custom-addons/xb_joyeria_peso_precio/
sudo chown -R odoo:odoo /odoo/custom-addons/xb_joyeria_peso_precio
cd /tmp
sudo -u odoo timeout 900 /odoo/odoo-server/env/bin/python3 /odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf \
  -d novadiam-anello-diamane-xubax --no-http --log-level=warn -u xb_joyeria_peso_precio --stop-after-init 2>&1 | tail -3
sudo -u postgres psql -At -d novadiam-anello-diamane-xubax -c "select 'version: '||latest_version from ir_module_module where name='xb_joyeria_peso_precio'"
sudo systemctl restart odoo-server && echo "LISTO: reiniciado"
