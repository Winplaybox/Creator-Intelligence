#!/usr/bin/env bash
# Adds nginx vhosts + Let's Encrypt for creator / creator-api. Reverts the vhost if nginx -t fails.
set -euo pipefail
S=/etc/nginx/sites-available/creator-intelligence
cat > $S <<'NG'
server {
    listen 80;
    server_name creator-api.winplaybox.in;
    client_max_body_size 50M;
    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
server {
    listen 80;
    server_name creator.winplaybox.in;
    location / {
        proxy_pass http://127.0.0.1:3100;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NG
ln -sf $S /etc/nginx/sites-enabled/creator-intelligence
if ! nginx -t 2>&1; then rm -f /etc/nginx/sites-enabled/creator-intelligence; echo "nginx -t failed, reverted"; exit 1; fi
systemctl reload nginx
command -v certbot >/dev/null || DEBIAN_FRONTEND=noninteractive apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
certbot --nginx -d creator.winplaybox.in -d creator-api.winplaybox.in --non-interactive --agree-tos -m sagarsuthar530@gmail.com --redirect
nginx -t && systemctl reload nginx
curl -s -m 10 -o /dev/null -w "https creator-api: %{http_code}\n" https://creator-api.winplaybox.in/health
curl -s -m 10 -o /dev/null -w "https creator: %{http_code}\n" https://creator.winplaybox.in/login
curl -s -m 10 -o /dev/null -w "api.winplaybox.in still: %{http_code}\n" https://api.winplaybox.in/api/auth/config
