[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=softwareone-platform_mpt-finops-extension&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=softwareone-platform_mpt-finops-extension) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=softwareone-platform_mpt-finops-extension&metric=coverage)](https://sonarcloud.io/summary/new_code?id=softwareone-platform_mpt-finops-extension)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

# SoftwareONE FinOps for Cloud Marketplace Extension
Extension integrates FinOps for CLoud Marketplace Extension with the SoftwareONE Marketplace

# Run tests
```
$ docker-compose build app_test
$ docker-compose run --service-ports app_test
```

# Local run using SoftwareONE Marketplace API

## Create configuration files

1. Create environment file
```
$ cp .env.sample .env
```

1. Setup parameters for `.env` file
```
MPT_PRODUCTS_IDS=PRD-1111-1111
MPT_PORTAL_BASE_URL=http://devmock:8000
MPT_API_BASE_URL=http://devmock:8000
MPT_API_TOKEN=<vendor-api-token>
MPT_ORDERS_API_POLLING_INTERVAL_SECS=120
EXT_WEBHOOKS_SECRETS={"PRD-1111-1111": "<super-jwt-secret>"}
EXT_MSTEAMS_WEBHOOK_URL=https://whatever.webhook.office.com/webhookb2/<...>
EXT_AWS_SES_CREDENTIALS=<access-key>:<secret-key>
EXT_EMAIL_NOTIFICATIONS_SENDER=no-reply@domain.com
EXT_EMAIL_NOTIFICATIONS_ENABLED=1
```

`MPT_PRODUCTS_IDS` should be a comma-separated list of the SWO Marketplace Product identifiers
For each of the defined product id in the `MPT_PRODUCTS_IDS` list define `WEBHOOKS_SECRETS` json variables using product ID as key.

```
EXT_WEBHOOKS_SECRETS={"PRD-1111-1111": "<webhook-secret-for-product>"}
```

Example of `.env` file
```
MPT_PRODUCTS_IDS=PRD-1111-1111
MPT_PORTAL_BASE_URL=http://devmock:8000
MPT_API_BASE_URL=http://devmock:8000
MPT_API_TOKEN=<vendor-api-token>
MPT_ORDERS_API_POLLING_INTERVAL_SECS=120
EXT_WEBHOOKS_SECRETS={"PRD-1111-1111": "<super-jwt-secret>"}
EXT_MSTEAMS_WEBHOOK_URL=https://whatever.webhook.office.com/webhookb2/<...>
EXT_AWS_SES_CREDENTIALS=<access-key>:<secret-key>
EXT_EMAIL_NOTIFICATIONS_SENDER=no-reply@domain.com
EXT_EMAIL_NOTIFICATIONS_ENABLED=1
```


## Build and run extension

1. Build and run the extension
```
$ docker-compose build app
$ docker-compose run --service-ports app
```

# Configuration

## Application
| Environment Variable            | Default               | Example                               | Description                                                                               |
|---------------------------------|-----------------------|---------------------------------------|-------------------------------------------------------------------------------------------|
| `EXT_WEBHOOKS_SECRETS`          | -                     | {"PRD-1111-1111": "123qweasd3432234"} | Webhook secret of the Draft validation Webhook in SoftwareONE Marketplace for the product |
| `MPT_PRODUCTS_IDS`              | PRD-1111-1111         | PRD-1234-1234,PRD-4321-4321           | Comma-separated list of SoftwareONE Marketplace Product ID                                |
| `MPT_API_BASE_URL`              | http://localhost:8000 | https://portal.softwareone.com/mpt    | SoftwareONE Marketplace API URL                                                           |
| `MPT_API_TOKEN`                 | -                     | eyJhbGciOiJSUzI1N...                  | SoftwareONE Marketplace API Token                                                         |
    
    

## Azure AppInsights
| Environment Variable                    | Default                     | Example                                                                                                                                                                                             | Description                                                                                                   |
|-----------------------------------------|-----------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| `SERVICE_NAME`                          | Swo.Extensions.FFC          | Swo.Extensions.FFC                                                                                                                                                                                  | Service name that is visible in the AppInsights logs                                                          |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | -                           | InstrumentationKey=cf280af3-b686-40fd-8183-ec87468c12ba;IngestionEndpoint=https://westeurope-1.in.applicationinsights.azure.com/;LiveEndpoint=https://westeurope.livediagnostics.monitor.azure.com/ | Azure Application Insights connection string                                                                  |

## Other
| Environment Variable                   | Default | Example | Description                                                          |
|----------------------------------------|---------|---------|----------------------------------------------------------------------|
| `MPT_ORDERS_API_POLLING_INTERVAL_SECS` | 120     | 60      | Orders polling interval from the Software Marketplace API in seconds |
