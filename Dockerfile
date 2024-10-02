# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.9.18

EXPOSE 5000

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# app environment variables
ENV API_PK_1=81dcb218c7ac1788e040d0b7dc36d6af-966361
ENV API_PK_2=c83d4367212e4c0d2691068404cc984d-800285
ENV API_PK_3=2782a5e2399284cdc535cf55a79facb4-276094
ENV API_PK_4=26ca6741e67c857a49517edaede2269e-276360
ENV API_PK_SLUG_1=dashboard-key
ENV API_PK_SLUG_2=dashboard-key
ENV API_PK_SLUG_3=dashboard-key
ENV API_PK_SLUG_4=dashboard-key
ENV API_PWD_1=yugipa123!
ENV API_PWD_2=yugipa123!
ENV API_PWD_3=yugipa123!
ENV API_PWD_4=yugipa123!
ENV API_UID_1=apiguy
ENV API_UID_2=apiguy
ENV API_UID_3=apiguy
ENV API_UID_4=apiguy
ENV DB_DB=nationalacts20
ENV DB_HOST=nationalactsdb
ENV DB_PASSWORD=All41n14@ll
ENV DB_USER=root
ENV SECRET_KEY=B1gB1gT1ttiez!
ENV STRIPE_API_KEY=83ba669a-9895-48e3-a109-965788858ab1
ENV SENDGRID_API_KEY=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
ENV MAIL_API_KEY=nyGpM0.DG4ODMo33G6mRVnJFf6LWb5UQAWBt-c33ecTR6EeojA2v
ENV INTERNAL_API_KEY=jYF6PT.8XlRWG9ApI0g8T0JdPLJCxh8DRkc4-fAJF4giDUc65PiGGie
ENV USER_API_KEY=AhRTNs.Hi63UCJetidPliMbyNeBMRbtkK58k-0rqmcnk3RsUWnbZ
ENV PUBLIC_API_KEY=bMH5MsIXZbZuc2B6eBe3BDFyiXxxSjQ6mTRDVeyGGoMyELkFjs2fjoGb8iZ6nq1z9vtLAN4TICE
ENV CRON_API_KEY=U2FsdGVkX1/+bHhSNoUDW8YXj5eXjq9HtLw+sO/K3r7KQ1tYTV6SKX9PlSVmpEUp

# Install pip requirements
COPY requirements_docker.txt .
RUN python -m pip install -r requirements_docker.txt

WORKDIR /app
COPY . /app

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "passenger_wsgi:application", "--timeout=3000"]
