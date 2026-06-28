---
type: BigQuery Dataset
title: Sales Database
description: Core transactional dataset backing the Acme storefront.
resource: bigquery://acme/sales
tags: [sales, transactional, core]
timestamp: 2026-05-22T09:00:00Z
---
# Overview

The `sales` dataset holds the storefront's transactional tables. It is the source of truth
for orders, line items, and customer accounts.

## Tables
* [Orders](/tables/orders.md)
* [Order Items](/tables/order_items.md)
* [Customers](/tables/customers.md)

# Citations

[1] [Acme Data Warehouse Charter](https://acme.example/docs/warehouse-charter)
