---
okf_version: "0.1"
---
# Acme Analytics Knowledge

Curated knowledge for Acme's analytics warehouse: datasets, tables, metrics, and the
playbooks that tie them together. This bundle is a conformant OKF v0.1 reference.

## Datasets
* [Sales Database](datasets/sales_db.md) - Core transactional dataset for the storefront.

## Tables
* [Orders](tables/orders.md) - One row per completed customer order.
* [Order Items](tables/order_items.md) - One row per line item within an order.
* [Customers](tables/customers.md) - One row per customer account.

## Metrics
* [Gross Revenue](metrics/gross_revenue.md) - Sum of order totals over a period.
* [Weekly Active Users](metrics/weekly_active_users.md) - Distinct purchasing users per ISO week.

## Playbooks
* [Revenue Reconciliation](playbooks/revenue_reconciliation.md) - How to reconcile warehouse revenue with finance.

## Glossary
* [Average Order Value](glossary/average_order_value.md) - Mean revenue per order.
