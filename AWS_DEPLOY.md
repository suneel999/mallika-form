# Mallika Hospital AWS Deployment

This project is prepared for container-based deployment on AWS Elastic Beanstalk using Docker.

## Why this path

As of March 31, 2026, AWS App Runner is no longer open to new customers, so Elastic Beanstalk is the safer smooth path for a new deployment.

Official AWS references:
- App Runner availability change: https://docs.aws.amazon.com/apprunner/latest/api/API_AssociateCustomDomain.html
- Docker image deployment for Elastic Beanstalk: https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/single-container-docker-configuration.html
- HTTPS termination on Elastic Beanstalk load balancers: https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/configuring-https-elb.html
- Route 53 to Elastic Beanstalk: https://docs.aws.amazon.com/Route53/latest/DeveloperGuide/routing-to-beanstalk-environment.html

## Included production files

- `Dockerfile`
- `wsgi.py`
- `gunicorn.conf.py`

The container installs LibreOffice so Linux-based AWS deployments can convert DOCX to PDF without Microsoft Word.

## Pre-deploy checklist

1. Save and close `template.docx` after adding placeholders such as `{{add}}`.
2. If the Word template uses custom fonts, place the `.ttf` or `.otf` files into the `fonts/` folder before building the Docker image.
3. Keep `template.docx` in the project root.

## Local Docker test

```bash
docker build -t mallika-report-service .
docker run --rm -p 8000:8000 mallika-report-service
```

Open `http://127.0.0.1:8000`.

## Elastic Beanstalk deployment steps

1. Create an ACM certificate for `camp.mallikahospitals.in` in the same AWS region as Elastic Beanstalk.
2. Create a new Elastic Beanstalk application.
3. Choose the Docker platform.
4. Use a load-balanced environment, not single-instance.
5. Upload this project as a source bundle or deploy through the EB CLI.
6. Set environment variables:
   - `PORT=8000`
   - `FLASK_DEBUG=0`
   - `GUNICORN_TIMEOUT=180`
7. Set the health check path to `/health`.
8. In the load balancer configuration, add HTTPS on port `443` and attach the ACM certificate.
9. Optionally redirect HTTP to HTTPS at the load balancer level.

## Domain mapping for camp.mallikahospitals.in

If your DNS is in Route 53:

1. Open the hosted zone for `mallikahospitals.in`.
2. Create a record for `camp`.
3. Point it to the Elastic Beanstalk environment or its load balancer using the Route 53 alias flow.

If your DNS is outside Route 53:

1. Copy the Elastic Beanstalk environment CNAME.
2. Create a CNAME record for `camp.mallikahospitals.in`.
3. Point it to the Elastic Beanstalk environment hostname.

## Notes for PDF layout fidelity

- The AWS container uses LibreOffice, so exact PDF layout depends on the template fonts being available inside the container.
- For the best match, keep the template fonts in the `fonts/` folder before deployment.
- If the template is edited in Microsoft Word, save and close it fully before testing generation.
