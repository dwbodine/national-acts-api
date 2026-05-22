# National Acts API

This is the API layer for nationalactsvip.com

Among the interesting points:
- uses Python 3.13.7 with a Flask API
- it is dockerized to run the database and PHPMyAdmin locally in containers
- an additional Docker file will containerize the API running gunicorn, but it is rarely used outside of production - instead I run the Flask API locally with the debugger attached
- there is an AWS folder that encapsulates some of the activity on AWS, including the docker-compose.yml that shows the full structure
- the site is hosted on a single EC2 instance on AWS for cost savings - full setup:
    - MariaDB database
    - custom database backup to S3 that runs nightly
    - phpmyadmin secured by simple auth + IP filter
    - a user portal secured by login using JWT authentication
    - main www website
    - test www website to show new features
    - traefik reverse proxy that serves all the subdomains
- Flask app uses a custom data layer with validation (hey that was written before I knew any better!)
- using a custom snake-case converter to accept camel-case input from the React apps
- also contains integrations with TicketSocket API, Stripe (not the payment service - for foreign exchange rates), Sender API and Twilio/SendGrid
- synchronization updates are controlled by crontab on the EC2 box
- all endpoints are secured by either role-based JWT or an API key  
- formatting using Black
- linting using PyLint
- 100% test coverage using PyTest
- all secrets removed from Github before it went public
