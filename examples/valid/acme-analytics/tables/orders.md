---
type: BigQuery Table
title: Orders
description: One row per completed customer order.
resource: bigquery://acme/sales/orders
tags: [sales, revenue, orders]
timestamp: 2026-05-28T14:30:00Z
---
# Overview

One row per completed order. Cancelled and abandoned carts are excluded. Part of the
[Sales Database](/datasets/sales_db.md).

# Schema

| Column | Type | Description |
|--------|------|-------------|
| `order_id` | STRING | Globally unique order identifier. |
| `customer_id` | STRING | FK to [Customers](/tables/customers.md). |
| `order_total` | NUMERIC | Order total in USD, tax inclusive. |
| `status` | STRING | Always `completed` in this table. |
| `created_at` | TIMESTAMP | When the order was placed (UTC). |

# Joins

Joined to [Order Items](/tables/order_items.md) on `order_id`, and to
[Customers](/tables/customers.md) on `customer_id`.

# Examples

```sql
SELECT customer_id, SUM(order_total) AS lifetime_value
FROM `acme.sales.orders`
GROUP BY customer_id;
```

# Citations

[1] [Order lifecycle runbook](https://acme.example/docs/order-lifecycle)
