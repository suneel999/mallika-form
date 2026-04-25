# Mallika Hospital Ubuntu EC2 Deployment

This guide is for deploying the project on an AWS EC2 Ubuntu server behind Nginx and Gunicorn.

## Architecture

- Ubuntu EC2 instance
- Nginx on ports `80/443`
- Gunicorn serving Flask on `127.0.0.1:8000`
- LibreOffice installed on Ubuntu for DOCX to PDF conversion
- Route 53 record for `camp.mallikahospitals.in`

## 1. Launch the EC2 instance

Use an Ubuntu LTS AMI and allow these inbound security group rules:

- `22` from your office or current IP
- `80` from `0.0.0.0/0`
- `443` from `0.0.0.0/0`

AWS references:
- EC2 getting started: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html
- EC2 security groups: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-security-groups.html

## 2. Point the domain

Create a Route 53 record for `camp.mallikahospitals.in` pointing to the EC2 public IP or Elastic IP.

AWS reference:
- Route 53 routing to an EC2 instance: https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-to-ec2-instance.html

## 3. Connect to the server

```bash
ssh -i your-key.pem ubuntu@YOUR_SERVER_IP
```

## 4. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx libreoffice libreoffice-writer fonts-dejavu fonts-liberation git
```

If your Word template uses custom fonts, copy them later into `/var/www/mallika-form/fonts/`.

## 5. Clone the GitHub repo

```bash
cd /var/www
sudo git clone https://github.com/suneel999/mallika-form.git
sudo chown -R ubuntu:ubuntu /var/www/mallika-form
cd /var/www/mallika-form
```

## 6. Create the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 7. Create the auth environment file

Create `/etc/mallika-form.env`:

```bash
sudo tee /etc/mallika-form.env > /dev/null <<'EOF'
APP_SECRET_KEY=replace-with-a-long-random-secret
REGISTRATION_SECRET=replace-with-hospital-registration-key
EOF
sudo chmod 600 /etc/mallika-form.env
```

## 8. Test the app directly

```bash
export PORT=8000
export FLASK_DEBUG=0
export APP_SECRET_KEY=replace-with-a-long-random-secret
export REGISTRATION_SECRET=replace-with-hospital-registration-key
python3 app.py
```

Open another SSH tab and test:

```bash
curl http://127.0.0.1:8000/health
```

Stop the app after the health check works.

## 9. Create a systemd service

Create `/etc/systemd/system/mallika-form.service`:

```ini
[Unit]
Description=Mallika Hospital Flask Report Service
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/var/www/mallika-form
EnvironmentFile=-/etc/mallika-form.env
Environment="PORT=8000"
Environment="FLASK_DEBUG=0"
ExecStart=/var/www/mallika-form/.venv/bin/gunicorn -c /var/www/mallika-form/gunicorn.conf.py wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable mallika-form
sudo systemctl start mallika-form
sudo systemctl status mallika-form
```

## 10. Configure Nginx

Create `/etc/nginx/sites-available/mallika-form`:

```nginx
server {
    listen 80;
    server_name camp.mallikahospitals.in;

    client_max_body_size 25M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
```

Enable it:

```bash
sudo ln -s /etc/nginx/sites-available/mallika-form /etc/nginx/sites-enabled/mallika-form
sudo nginx -t
sudo systemctl restart nginx
```

## 11. Add HTTPS with Certbot

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d camp.mallikahospitals.in
```

Check renewal:

```bash
sudo certbot renew --dry-run
```

## 12. Update the app later

```bash
cd /var/www/mallika-form
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart mallika-form
```

## 13. Important production notes

- Save and close `template.docx` before uploading or pushing changes.
- Make sure `{{add}}` is actually saved in the template before deploying.
- Ubuntu uses LibreOffice for PDF generation, not Microsoft Word.
- For the closest PDF match, upload any custom template fonts into the repo `fonts/` folder before deploying.
- Keep `/etc/mallika-form.env` private because it contains the app session secret and the registration key.
