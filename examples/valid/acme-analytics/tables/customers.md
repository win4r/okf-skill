---
type: BigQuery Table
title: Customers
description: One row per customer account.
resource: bigquery://acme/sales/customers
tags: [sales, customers]
timestamp: 2026-05-22T09:00:00Z
---
# Overview

One row per customer account. Referenced by [Orders](/tables/orders.md).

# Schema

| Column | Type | Description |
|--------|------|-------------|
| `customer_id` | STRING | Globally unique customer identifier. |
| `email` | STRING | Account email (PII). |
| `signed_up_at` | TIMESTAMP | Account creation time (UTC). |
