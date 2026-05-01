# Ubuntu VPS Deployment Guide for Univerra

This guide deploys Univerra on an Ubuntu VPS with:

- A subdomain such as `app.example.com`
- Nginx as the public web server
- HTTPS with Certbot/Let's Encrypt
- Flask backend running privately on `127.0.0.1:5001`
- Built Vue/Vite frontend served as static files
- Cloudflare in front of the VPS with Full strict SSL
- Basic server and application hardening

Replace every example value before running commands:

```bash
APP_DOMAIN=app.example.com
APP_EMAIL=you@example.com
APP_DIR=/opt/univerra/app
```

## 1. Cloudflare DNS for the Subdomain

In Cloudflare, open your domain and go to DNS.

Create this record:

```text
Type: A
Name: app
IPv4 address: YOUR_VPS_PUBLIC_IPV4
Proxy status: DNS only for initial certificate setup
TTL: Auto
```

If your VPS has IPv6, also add:

```text
Type: AAAA
Name: app
IPv6 address: YOUR_VPS_PUBLIC_IPV6
Proxy status: DNS only for initial certificate setup
TTL: Auto
```

Wait until DNS resolves:

```bash
dig +short app.example.com
```

After HTTPS works, change the record to Proxied in Cloudflare.

Important:

- Do not create other public DNS-only records pointing to the same VPS IP unless needed.
- Do not expose `api.example.com` separately for this app. Use same-origin `/api` through Nginx.
- If your root domain is somewhere else, only the subdomain needs to point at this VPS.

## 2. Initial Ubuntu VPS Hardening

SSH into the VPS as root or your provider-created sudo user:

```bash
ssh root@YOUR_VPS_PUBLIC_IP
```

Update the system. If you are logged in directly as `root`, the `sudo` prefix is optional.

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y curl git ufw fail2ban nginx ca-certificates gnupg lsb-release
```

Create a normal admin user if you only have root:

```bash
adduser deploy
usermod -aG sudo deploy
```

Copy your SSH public key to that user:

```bash
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

Open a second terminal and confirm the new login works before disabling root/password login:

```bash
ssh deploy@YOUR_VPS_PUBLIC_IP
```

Then harden SSH:

```bash
sudo nano /etc/ssh/sshd_config
```

Recommended settings:

```text
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

Restart SSH:

```bash
sudo systemctl restart ssh
```

Enable UFW. Do this only after allowing SSH:

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Enable automatic security updates:

```bash
sudo apt install -y unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

## 3. Install Node.js and uv

The frontend uses Vite 7, so use a modern Node.js version. Node.js 22 LTS is a good default.

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node -v
npm -v
```

Install `uv` for the Python backend under the app user later. First create the app user:

```bash
sudo adduser --system --group --home /opt/univerra --shell /bin/bash univerra
sudo mkdir -p /opt/univerra
sudo chown -R univerra:univerra /opt/univerra
```

Switch to the app user:

```bash
sudo -iu univerra
```

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv --version
```

## 4. Upload or Clone the Project

Option A: clone from Git:

```bash
cd /opt/univerra
git clone YOUR_REPO_URL app
cd app
```

Option B: upload from your local machine:

Run this from your local project directory, not inside the VPS:

```bash
rsync -az --delete \
  --exclude '.git' \
  --exclude 'node_modules' \
  --exclude 'frontend/node_modules' \
  --exclude 'frontend/dist' \
  --exclude 'backend/.venv' \
  --exclude 'venv' \
  ./ deploy@YOUR_VPS_PUBLIC_IP:/tmp/univerra-upload/
```

Then on the VPS:

```bash
sudo mkdir -p /opt/univerra/app
sudo rsync -a --delete /tmp/univerra-upload/ /opt/univerra/app/
sudo chown -R univerra:univerra /opt/univerra/app
sudo -iu univerra
cd /opt/univerra/app
```

## 5. Configure Production Environment

Create the environment file. If you already uploaded a real `.env`, do not overwrite it.

```bash
test -f .env || cp .env.example .env
nano .env
```

Set at least these values:

```env
LLM_API_KEY=changeme
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-5.4

FLASK_DEBUG=False
FLASK_HOST=127.0.0.1
FLASK_PORT=5001

AUTH_SECRET_KEY=changeme
AUTH_TOKEN_MAX_AGE_SECONDS=604800

MONGODB_URI=your_mongodb_uri
MONGODB_DB_NAME=univerra
MONGODB_TIMEOUT_MS=5000
```

Generate a strong auth secret:

```bash
openssl rand -hex 32
```

Protect the file:

```bash
chmod 600 .env
```

Security notes:

- Never commit `.env`.
- Keep `FLASK_DEBUG=False` on the VPS.
- Keep `FLASK_HOST=127.0.0.1` so the backend is not exposed directly.
- If using MongoDB Atlas, allowlist only the VPS IP.
- If using local MongoDB, bind MongoDB to `127.0.0.1` and do not open port `27017`.

## 6. Install Dependencies and Build

Still as the `univerra` user:

```bash
cd /opt/univerra/app
npm ci
npm ci --prefix frontend
cd backend
uv sync --frozen
uv pip install gunicorn
cd ..
VITE_API_BASE_URL=/api npm run build
```

The `VITE_API_BASE_URL=/api` part is important. It makes the browser call:

```text
https://app.example.com/api/...
```

instead of trying to call:

```text
http://localhost:5001
```

Copy the built frontend to Nginx's web root:

```bash
exit
sudo mkdir -p /var/www/univerra
sudo rsync -a --delete /opt/univerra/app/frontend/dist/ /var/www/univerra/
sudo chown -R www-data:www-data /var/www/univerra
```

## 7. Run Backend with systemd

Create the service:

```bash
sudo nano /etc/systemd/system/univerra-backend.service
```

Paste:

```ini
[Unit]
Description=Univerra Flask API
After=network.target

[Service]
Type=simple
User=univerra
Group=univerra
WorkingDirectory=/opt/univerra/app/backend
EnvironmentFile=/opt/univerra/app/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/univerra/app/backend/.venv/bin/gunicorn 'app:create_app()' --bind 127.0.0.1:5001 --workers 2 --threads 4 --timeout 300 --access-logfile - --error-logfile -
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now univerra-backend
sudo systemctl status univerra-backend
```

Check the backend locally:

```bash
curl http://127.0.0.1:5001/health
```

Check that port `5001` is private:

```bash
sudo ss -tulpn | grep 5001
```

You should see `127.0.0.1:5001`, not `0.0.0.0:5001`.

## 8. Configure Nginx

Create rate-limit zones:

```bash
sudo nano /etc/nginx/conf.d/univerra-rate-limit.conf
```

Paste:

```nginx
limit_req_zone $binary_remote_addr zone=univerra_api:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=univerra_auth:10m rate=5r/m;
```

Create a proxy snippet:

```bash
sudo nano /etc/nginx/snippets/univerra-proxy.conf
```

Paste:

```nginx
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Connection "";
proxy_read_timeout 300s;
proxy_send_timeout 300s;
proxy_buffering off;
```

Create the site:

```bash
sudo nano /etc/nginx/sites-available/univerra
```

Paste and replace `app.example.com`:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name app.example.com;

    root /var/www/univerra;
    index index.html;

    client_max_body_size 50m;

    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;

    location = /api/auth/login {
        limit_req zone=univerra_auth burst=5 nodelay;
        include snippets/univerra-proxy.conf;
        proxy_pass http://127.0.0.1:5001;
    }

    location = /api/auth/signup {
        limit_req zone=univerra_auth burst=5 nodelay;
        include snippets/univerra-proxy.conf;
        proxy_pass http://127.0.0.1:5001;
    }

    location /api/ {
        limit_req zone=univerra_api burst=30 nodelay;
        include snippets/univerra-proxy.conf;
        proxy_pass http://127.0.0.1:5001;
    }

    location = /health {
        include snippets/univerra-proxy.conf;
        proxy_pass http://127.0.0.1:5001;
    }

    location /assets/ {
        try_files $uri =404;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/univerra /etc/nginx/sites-enabled/univerra
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
```

Test HTTP:

```bash
curl -I http://app.example.com
curl http://app.example.com/health
```

## 9. Enable HTTPS with Certbot

Install Certbot using snap:

```bash
sudo apt install -y snapd
sudo snap install --classic certbot
sudo ln -sf /snap/bin/certbot /usr/local/bin/certbot
```

Issue the certificate:

```bash
sudo certbot --nginx \
  -d app.example.com \
  --redirect \
  --email you@example.com \
  --agree-tos \
  --no-eff-email
```

Test renewal:

```bash
sudo certbot renew --dry-run
```

Test HTTPS:

```bash
curl -I https://app.example.com
curl https://app.example.com/health
```

When HTTPS works, add HSTS carefully. In the HTTPS server block created by Certbot, add:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

Only use `includeSubDomains` if every subdomain that users visit already supports HTTPS. If unsure, use this safer first step:

```nginx
add_header Strict-Transport-Security "max-age=86400" always;
```

Then reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 10. Turn On Cloudflare Proxy and Full Strict

After Certbot works:

1. Go to Cloudflare DNS.
2. Change the `app` record from DNS only to Proxied.
3. Go to SSL/TLS -> Overview.
4. Set encryption mode to Full strict.

Recommended Cloudflare settings:

```text
SSL/TLS -> Overview: Full strict
SSL/TLS -> Edge Certificates: Always Use HTTPS = On
SSL/TLS -> Edge Certificates: Automatic HTTPS Rewrites = On
SSL/TLS -> Edge Certificates: Minimum TLS Version = TLS 1.2 or higher
SSL/TLS -> Edge Certificates: TLS 1.3 = On
Security -> Bots: Bot Fight Mode = On if available
Security -> WAF: Managed rules = On if available
```

Do not use Flexible SSL. Flexible encrypts browser-to-Cloudflare traffic but not Cloudflare-to-origin traffic and often causes redirect loops.

## 11. Restore Real Visitor IPs in Nginx

Once Cloudflare is proxied, Nginx will otherwise see Cloudflare IPs instead of real visitor IPs.

Create a Cloudflare real-IP config:

```bash
{
  curl -s https://www.cloudflare.com/ips-v4 | sed 's#^#set_real_ip_from #; s#$#;#'
  curl -s https://www.cloudflare.com/ips-v6 | sed 's#^#set_real_ip_from #; s#$#;#'
  echo 'real_ip_header CF-Connecting-IP;'
  echo 'real_ip_recursive on;'
} | sudo tee /etc/nginx/conf.d/cloudflare-real-ip.conf
```

Reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Update this config periodically because Cloudflare IP ranges can change.

## 12. Protect the Origin from Direct Access

Cloudflare protects traffic only if visitors actually pass through Cloudflare. If someone knows your VPS IP, they may try to bypass Cloudflare.

The easiest origin lock is Nginx allowlisting. Enable this only after:

- The Cloudflare DNS record is Proxied.
- `https://app.example.com` works through Cloudflare.
- `sudo certbot renew --dry-run` passes.

Create an allowlist snippet:

```bash
{
  curl -s https://www.cloudflare.com/ips-v4 | sed 's#^#allow #; s#$#;#'
  curl -s https://www.cloudflare.com/ips-v6 | sed 's#^#allow #; s#$#;#'
  echo 'deny all;'
} | sudo tee /etc/nginx/snippets/cloudflare-only.conf
```

Then add this line near the top of the HTTP and HTTPS `server` blocks for this site:

```nginx
include snippets/cloudflare-only.conf;
```

Reload:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Test:

```bash
curl -I https://app.example.com
curl -I --resolve app.example.com:443:YOUR_VPS_PUBLIC_IP https://app.example.com
```

The Cloudflare request should work. The direct-to-origin request should return `403` or fail.

Stronger option: use your VPS provider firewall or UFW to allow ports `80` and `443` only from Cloudflare IP ranges. If you use this, remember that Docker published ports can bypass UFW unless you configure Docker firewall rules correctly. The direct systemd deployment in this guide avoids that issue.

## 13. Optional: Cloudflare Authenticated Origin Pulls

Authenticated Origin Pulls adds mTLS between Cloudflare and Nginx. It helps ensure HTTPS requests to your origin are really coming from Cloudflare.

Install the Cloudflare origin-pull CA:

```bash
sudo mkdir -p /etc/nginx/certs
sudo curl -fsSL \
  https://developers.cloudflare.com/ssl/static/authenticated_origin_pull_ca.pem \
  -o /etc/nginx/certs/cloudflare-origin-pull-ca.pem
sudo chmod 644 /etc/nginx/certs/cloudflare-origin-pull-ca.pem
```

In the HTTPS `server` block, add:

```nginx
ssl_client_certificate /etc/nginx/certs/cloudflare-origin-pull-ca.pem;
ssl_verify_client on;
```

Reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Then enable it in Cloudflare:

```text
SSL/TLS -> Origin Server -> Authenticated Origin Pulls -> On
```

If the site breaks, disable the Cloudflare toggle first, remove or comment the two Nginx lines, and reload Nginx.

## 14. Cloudflare WAF and Rate Rules

Good starter rules:

```text
Rule: Bypass cache for API
Expression: starts_with(http.request.uri.path, "/api/")
Action: Bypass cache

Rule: Protect login
Expression: http.request.uri.path in {"/api/auth/login" "/api/auth/signup"}
Action: Managed Challenge or Rate Limit

Rule: Block obviously bad countries or ASNs
Expression: only if you know you never serve those locations
Action: Block or Managed Challenge

Rule: Challenge high-risk traffic
Expression: cf.threat_score gt 20
Action: Managed Challenge
```

Keep these practical:

- Do not block countries unless you are sure.
- Do not cache `/api/*`.
- During an attack, enable Under Attack Mode temporarily.
- Use Cloudflare notifications for spikes in 5xx errors.

## 15. Application Security Checklist

No VPS can be made fully hack-proof, but this setup reduces the common risks.

Must do:

- Use SSH keys only.
- Disable root SSH login.
- Keep Ubuntu packages updated.
- Keep `FLASK_DEBUG=False`.
- Keep `.env` private with `chmod 600`.
- Bind backend to `127.0.0.1`.
- Expose only Nginx ports `80` and `443`.
- Use Cloudflare Full strict.
- Use strong unique API keys and rotate them if leaked.
- Use a strong `AUTH_SECRET_KEY`.
- Back up `.env`, MongoDB, and `backend/uploads`.
- Review logs after deployment.

Recommended:

- Restrict backend CORS to your production domain in code or config if you add that option.
- Add Cloudflare Access in front of the app if it is private.
- Use a separate VPS for email, or no email on this VPS, to avoid leaking origin IP.
- Use provider snapshots before major updates.
- Set budget alerts for LLM API usage.

## 16. Logs and Troubleshooting

Backend logs:

```bash
sudo journalctl -u univerra-backend -f
```

Nginx logs:

```bash
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

App file logs:

```bash
sudo ls -la /opt/univerra/app/backend/logs
sudo tail -f /opt/univerra/app/backend/logs/*.log
```

Check services:

```bash
sudo systemctl status univerra-backend
sudo systemctl status nginx
sudo nginx -t
```

Common problems:

```text
502 Bad Gateway
Backend is not running or not listening on 127.0.0.1:5001.
Check: sudo journalctl -u univerra-backend -f

Frontend loads but API fails
Frontend was probably built without VITE_API_BASE_URL=/api.
Rebuild: VITE_API_BASE_URL=/api npm run build

Cloudflare 526
Cloudflare Full strict cannot validate your origin cert.
Check: sudo certbot certificates

Cloudflare too many redirects
Usually caused by Flexible SSL or conflicting redirects.
Use Full strict.

Uploads fail
Check Nginx client_max_body_size and backend MAX_CONTENT_LENGTH.

Login/signup rate limited too aggressively
Adjust /etc/nginx/conf.d/univerra-rate-limit.conf.
```

## 17. Update Deployment

For Git-based deployments:

```bash
sudo -iu univerra
cd /opt/univerra/app
git pull
export PATH="$HOME/.local/bin:$PATH"
npm ci
npm ci --prefix frontend
cd backend
uv sync --frozen
uv pip install gunicorn
cd ..
VITE_API_BASE_URL=/api npm run build
exit

sudo rsync -a --delete /opt/univerra/app/frontend/dist/ /var/www/univerra/
sudo chown -R www-data:www-data /var/www/univerra
sudo systemctl restart univerra-backend
sudo nginx -t
sudo systemctl reload nginx
```

For rsync deployments, upload new files first, then run the same install/build/restart steps.

## 18. Optional Docker Path

The repository includes Docker files, but the current image runs the app in development mode. For a quick private demo, you can use it behind Nginx, but for production the systemd/static frontend path above is cleaner.

If you still use Docker, do not publish app ports on all interfaces. Bind them to localhost:

```yaml
services:
  univerra:
    build: .
    image: univerra-simulation:latest
    container_name: univerra
    env_file:
      - .env
    ports:
      - "127.0.0.1:3000:3000"
      - "127.0.0.1:5001:5001"
    restart: unless-stopped
    volumes:
      - ./backend/uploads:/app/backend/uploads
```

Then configure Nginx:

```nginx
location /api/ {
    include snippets/univerra-proxy.conf;
    proxy_pass http://127.0.0.1:5001;
}

location / {
    include snippets/univerra-proxy.conf;
    proxy_pass http://127.0.0.1:3000;
}
```

Again: for serious production, prefer the static frontend plus systemd backend deployment above.

## 19. Reference Links

- Certbot Nginx instructions: https://certbot.eff.org/instructions?ws=nginx&os=snap
- Nginx reverse proxy docs: https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/
- Cloudflare Full strict SSL: https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/
- Cloudflare protect your origin server: https://developers.cloudflare.com/fundamentals/security/protect-your-origin-server/
- Cloudflare IP addresses and origin allowlisting: https://developers.cloudflare.com/fundamentals/concepts/cloudflare-ip-addresses/
- Cloudflare restore original visitor IPs: https://developers.cloudflare.com/support/troubleshooting/restoring-visitor-ips/restoring-original-visitor-ips/
- Cloudflare Authenticated Origin Pulls: https://developers.cloudflare.com/ssl/origin-configuration/authenticated-origin-pull/set-up/global/
- Docker Engine on Ubuntu: https://docs.docker.com/engine/install/ubuntu/
