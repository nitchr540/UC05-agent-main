# UC AI Impact Analysis Assistant

## GitHub Native Demo Guide

### Demo 1 - Low
Change README.md and push feature branch. Expected LOW.

### Demo 2 - High
Remove customerType from shared-contracts/customer/CustomerContract.json. Expected HIGH.

### Demo 3 - Critical
Drop status column from database/tables/Customer_Contract.sql. Expected CRITICAL with impacted downstream services.

View results in GitHub Actions > UC Feature Branch Impact Analysis.
Updated workflow diagram.