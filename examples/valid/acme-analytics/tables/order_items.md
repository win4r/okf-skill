---
type: BigQuery Table
title: Order Items
description: One row per line item within an order.
resource: bigquery://acme/sales/order_items
tags: [sales, orders, line-items]
timestamp: 2026-05-28T14:30:00Z
---
# Overview

One row per line item. Each item belongs to exactly one [Order](/tables/orders.md).

# Schema

| Column | Type | Description |
|--------|------|-------------|
| `order_item_id` | STRING | Unique line-item identifier. |
| `order_id` | STRING | FK to [Orders](/tables/orders.md). |
| `sku` | STRING | Product SKU. |
| `quantity` | INT64 | Units purchased. |
| `unit_price` | NUMERIC | Price per unit in USD. |
